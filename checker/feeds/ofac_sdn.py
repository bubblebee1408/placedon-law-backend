"""OFAC SDN — the first concrete feed. Ring 2. Observations only, never a decision.

## Why this source first

PLAN_14 §6 (T3) put OFAC before any Indian register deliberately: if the pipeline
cannot carry the easiest possible live source cleanly, it is not ready for the ones
with contracts attached. The SDN list is a single, published, machine-readable file
with no API key.

## What was measured before a line of this was written (2026-09-17)

Every one of these would have broken a naive adapter:

1. **The widely-cited URL is not the source.** `www.treasury.gov/ofac/downloads/sdn.xml`
   302-redirects, and `www.treasury.gov/robots.txt` itself 301-redirects to
   `home.treasury.gov/` -- an HTML **homepage**, not a robots file. `checker.robots`
   follows that redirect, parses the homepage as rules, finds no directives and
   reports "allowed". That verdict rests on a web page being misread as policy, so
   this adapter does not use that host.

2. **The entry used instead** is OFAC's own Sanctions List Service,
   `sanctionslistservice.ofac.treas.gov`, whose `robots.txt` answers a genuine
   **HTTP 404**. RFC 9309 defines an unavailable (4xx) robots file as full
   allowance, and `checker.robots` implements exactly that. A defined case, not a
   misread one.

3. **The payload host differs and the link expires.** The entry 302-redirects to a
   pre-signed AWS GovCloud S3 object carrying `X-Amz-Expires=3600`. So the stable
   entry URL is the identity; the signed URL is never stored, cached or reused.
   `checker.feeds.common.fetch` refuses any redirect whose target host is not named,
   so this adapter names exactly one: `PAYLOAD_HOST`.

4. **Size: 29,076,910 bytes.** Inside `fetch`'s 64 MB cap. Parsed with
   `iterparse` and cleared element by element, so memory does not scale with the
   list.

5. **The file states its own record count.** `<Record_Count>19385</Record_Count>`.
   That is an integrity check for free: a parse that yields a different number of
   entries is not a successful parse. `parse()` records the mismatch rather than
   trusting either figure.

## Licence -- UNVERIFIED, and deliberately so

OFAC's own FAQ does not state redistribution terms. US federal government works are
generally not subject to copyright (17 U.S.C. §105), but that is **reasoning about
who published the file, not the source's own words**, and `checker.feeds` defines
`PUBLIC_DOMAIN` as "the source states this itself; not inferred from who published
it". So `LICENCE = LICENCE_UNVERIFIED`, and an observation from this feed **refuses
commercial serving** until the terms are confirmed. That refusal is the layer
working. Changing it is a one-line edit that must cite the source's own statement.

## Blindness -- EITHER

The file is a snapshot at `Publish_Date`. A designation made after that date is
absent (the truth is *at least* this list -- a FLOOR); a delisting made after that
date is still present (the truth is *at most* this list -- a CEILING). Both are
open, so the honest state is `EITHER`. An empty screening result against this file
is therefore **"not on the list as published on <date>"**, never "not sanctioned".

## What this module is not

It is not a screening decision. `screen()` returns candidate matches for a human.
Exact normalised-name matching misses transliterations and aliases the list does not
spell out, and fuzzy matching invents hits; neither may enter a Ring 0 decider, which
`checker/rings.py` enforces by test.

Also noted and preserved, not corrected: OFAC's own element is spelled
`publshInformation`. That is the source's spelling.

## Vessel index -- schema measured, not assumed (2026-09-17)

Before `vessels()`/`lookup_vessel()` were written, the live file was read directly
(`curl -r 0-5000000`, `<sdnEntry sdnType="Vessel">` blocks, no state through
`checker.robots`) to see what OFAC actually publishes, because assuming a schema and
writing a parser against the assumption is exactly the mistake this module's own
docstring already warns against for `publshInformation`. What is really there, per
`<sdnEntry>`:

  `<idList><id><idType>Vessel Registration Identification</idType>
   <idNumber>IMO 7406784</idNumber></id></idList>` -- one `<id>` per identifier; the
  IMO number lives under EXACTLY this `idType` string (measured against 81 Vessel
  entries in the first 5,000,000 bytes of the live file, 81/81 matched). Two
  spellings of `idNumber` were both observed: `IMO 7406784` (prefixed) and
  `8606173` (bare, no prefix) -- both are 7 digits once the optional `IMO` prefix
  and surrounding whitespace are stripped, and both pass the IMO check digit for
  real entries. A vessel may carry NO `<idList>` at all (measured: uid 4238,
  `MAR AZUL`) -- not every Vessel entry has an IMO.

  `<vesselInfo><callSign>…</callSign><vesselType>…</vesselType>
   <vesselFlag>…</vesselFlag><vesselOwner>…</vesselOwner><tonnage>…</tonnage>
   <grossRegisteredTonnage>…</grossRegisteredTonnage></vesselInfo>` -- every field
  measured optional in practice (e.g. `callSign` and `vesselOwner` were present on
  41/82 and 4/82 of the sampled Vessel entries respectively); none is assumed
  present.

`vessels()` keys strictly on `idType == "Vessel Registration Identification"` and a
7-digit candidate (after stripping "IMO" and whitespace) -- not on any `idType`
that merely mentions "Registration" (the file also carries, on non-vessel entries,
`Public Registration Number` and `Romanian Tax Registration`, which are unrelated
fields that happen to share a word). A candidate whose 7th digit fails the IMO
check digit is INDEXED, not dropped or corrected: `imo_check_digit_valid=False` is
the report; CLAUDE.md forbids repairing a defective source, and a source that
misstates a check digit is not this module's mistake to fix silently.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from checker.feeds import (EITHER, LICENCE_UNVERIFIED, FetchResult, Observation)
from checker.feeds.common.fetch import fetch as _fetch
from checker.provenance import ACCESSIBLE

__all__ = ["OfacSdnFeed", "ENTRY_URL", "PAYLOAD_HOST", "entries", "screen", "normalise",
          "vessels", "lookup_vessel", "normalise_imo", "imo_check_digit_valid"]

SOURCE_ID = "ofac.sdn"
ENTRY_URL = "https://sanctionslistservice.ofac.treas.gov/api/download/SDN.XML"
PAYLOAD_HOST = "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com"
LICENCE = LICENCE_UNVERIFIED
BLINDNESS = EITHER

# Measured against the live file 2026-09-17 (see module docstring): this exact
# idType string is where a vessel's IMO number lives. Matching on "contains
# Registration" would also catch unrelated fields on non-vessel entries
# ("Public Registration Number", "Romanian Tax Registration") -- exact match only.
_IMO_ID_TYPE = "Vessel Registration Identification"
# RT-13: `\\d` matches every Unicode decimal, so an IMO written in Devanagari or
# fullwidth digits would key the index under a string no caller can type. ASCII only.
_IMO_SHAPE = re.compile(r"^[0-9]{7}$")
_IMO_PREFIX = re.compile(r"(?i)^imo\s*")

# The namespace OFAC publishes under, read from the live file on 2026-09-17. Parsing
# is namespace-agnostic (`_local`) so a namespace change degrades to a count
# mismatch that parse() reports, rather than a silent zero.
_NS_SEEN = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalise(name: str) -> str:
    """Case-fold, strip punctuation, collapse whitespace. Deliberately crude: it is
    a candidate generator for a human, not an identity function."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", name.casefold())).strip()


def _text(el, child: str) -> str:
    for c in el:
        if _local(c.tag) == child:
            return (c.text or "").strip()
    return ""


def _entry(el) -> dict:
    """One <sdnEntry> as a plain dict. Names what screening needs, plus (added for
    the vessel index) the raw `<idList>` entries and `<vesselInfo>` block -- both
    empty/absent on the vast majority of entries (individuals, entities), so this
    costs nothing there and keeps `entries()` the single streaming source both
    `screen()` and `vessels()` read from."""
    first, last = _text(el, "firstName"), _text(el, "lastName")
    akas, programs, ids = [], [], []
    vessel_info: dict = {}
    for c in el:
        tag = _local(c.tag)
        if tag == "programList":
            programs = [(p.text or "").strip() for p in c if _local(p.tag) == "program"]
        elif tag == "akaList":
            for a in c:
                if _local(a.tag) != "aka":
                    continue
                n = " ".join(x for x in (_text(a, "firstName"), _text(a, "lastName")) if x)
                if n:
                    akas.append({"name": n, "category": _text(a, "category")})
        elif tag == "idList":
            for idnode in c:
                if _local(idnode.tag) != "id":
                    continue
                ids.append({"id_type": _text(idnode, "idType"),
                           "id_number": _text(idnode, "idNumber")})
        elif tag == "vesselInfo":
            vessel_info = {
                "call_sign": _text(c, "callSign"),
                "vessel_type": _text(c, "vesselType"),
                "vessel_flag": _text(c, "vesselFlag"),
                "vessel_owner": _text(c, "vesselOwner"),
                "tonnage": _text(c, "tonnage"),
                "gross_registered_tonnage": _text(c, "grossRegisteredTonnage"),
            }
    return {
        "uid": _text(el, "uid"),
        "name": " ".join(x for x in (first, last) if x),
        "sdn_type": _text(el, "sdnType"),
        "programs": programs,
        "akas": akas,
        "ids": ids,
        "vessel_info": vessel_info,
    }


def entries(content: bytes):
    """Yield every <sdnEntry> as a dict, streaming. Memory stays flat on 29 MB."""
    for _event, el in ET.iterparse(io.BytesIO(content), events=("end",)):
        if _local(el.tag) == "sdnEntry":
            yield _entry(el)
            el.clear()


def normalise_imo(raw: str) -> str:
    """Strip a leading "IMO" (any case) and surrounding whitespace. Does NOT
    validate shape or check digit -- see `imo_check_digit_valid`. Both spellings
    measured on the live file (`IMO 7406784` and bare `8606173`) normalise to the
    same form; stripping a prefix that is not there is a no-op."""
    return _IMO_PREFIX.sub("", raw.strip()).strip()


def imo_check_digit_valid(imo: str) -> bool:
    """True iff `imo` is exactly 7 digits and its 7th digit is the IMO check
    digit: the sum of the first six digits, each multiplied by 7,6,5,4,3,2 in
    order, ends in the 7th digit. False for anything not 7 digits -- an
    unexpected shape is not this function's business to coerce, only to report
    (via the caller) as not IMO-shaped.
    """
    if not _IMO_SHAPE.match(imo):
        return False
    digits = [int(c) for c in imo]
    total = sum(d * w for d, w in zip(digits[:6], (7, 6, 5, 4, 3, 2)))
    return total % 10 == digits[6]


def vessels(content: bytes) -> dict[str, dict]:
    """Every Vessel-type <sdnEntry> that carries an IMO-shaped identifier,
    keyed by that IMO number (post-`normalise_imo`, still exactly as published --
    never re-derived or corrected).

    Only `idType == "Vessel Registration Identification"` (the exact string
    measured on the live file -- see module docstring) is read as a candidate
    IMO. A candidate that is not 7 digits after normalising is not indexed at
    all (it is not IMO-shaped, so there is nothing to validate); a candidate
    that IS 7 digits but fails the check digit IS indexed, with
    `imo_check_digit_valid=False` -- CLAUDE.md: never repair a defective
    source, flag it and preserve it verbatim. A Vessel entry with no IMO-shaped
    id at all (measured: `MAR AZUL`, uid 4238) is simply absent from this index;
    it is still reachable via `entries()`.

    Re-parses `content` on every call (streaming, flat memory, no persistent
    index) -- call once per fetch and reuse the returned dict rather than
    calling this in a loop over many lookups.
    """
    out: dict[str, dict] = {}
    for e in entries(content):
        if e["sdn_type"] != "Vessel":
            continue
        for idrec in e["ids"]:
            if idrec["id_type"] != _IMO_ID_TYPE:
                continue
            imo = normalise_imo(idrec["id_number"])
            if not _IMO_SHAPE.match(imo):
                continue  # not 7 digits once normalised -- not IMO-shaped, nothing to index
            out[imo] = {
                "imo": imo,
                "imo_check_digit_valid": imo_check_digit_valid(imo),
                "uid": e["uid"],
                "name": e["name"],
                "programs": e["programs"],
                **e["vessel_info"],
            }
    return out


def lookup_vessel(imo: str, content: bytes) -> dict | None:
    """One vessel record by IMO number (any spelling `normalise_imo` accepts),
    or None if no Vessel entry in `content` carries it. Thin wrapper over
    `vessels()` -- see its docstring for the indexing rules."""
    return vessels(content).get(normalise_imo(imo))


def _publish_info(content: bytes) -> tuple[str, int | None]:
    """(Publish_Date as written, stated Record_Count). Read from the head only."""
    for _event, el in ET.iterparse(io.BytesIO(content), events=("end",)):
        if _local(el.tag) == "publshInformation":          # OFAC's spelling, preserved
            date = _text(el, "Publish_Date")
            count = _text(el, "Record_Count")
            return date, (int(count) if count.isdigit() else None)
        if _local(el.tag) == "sdnEntry":
            break                                         # header absent; do not scan 29 MB for it
    return "", None


def screen(name: str, content: bytes) -> list[dict]:
    """Candidate matches for `name`: exact on the normalised primary name or any
    alias. A candidate list for a reviewer. An empty list means "not on the list as
    published", which is not "not sanctioned" -- see BLINDNESS."""
    want = normalise(name)
    if not want:
        return []
    hits = []
    for e in entries(content):
        on = [e["name"]] + [a["name"] for a in e["akas"]]
        matched = [n for n in on if normalise(n) == want]
        if matched:
            hits.append({**e, "matched_on": matched[0]})
    return hits


class OfacSdnFeed:
    """Implements `checker.feeds.Feed`."""

    source_id = SOURCE_ID
    licence = LICENCE

    def __init__(self, *, rules=None, opener=None):
        self._rules = rules
        self._opener = opener

    def fetch(self, entry_url: str = ENTRY_URL) -> FetchResult:
        kw = {"rules": self._rules, "allow_redirect_hosts": (PAYLOAD_HOST,)}
        if self._opener is not None:
            kw["opener"] = self._opener
        return _fetch(self.source_id, entry_url, **kw)

    def parse(self, result: FetchResult, *, observed_at: str,
              blindness: str = BLINDNESS) -> Observation:
        if result.source_behaviour != ACCESSIBLE:
            # A refusal or an outage is evidence of nothing: no payload, by invariant.
            return Observation(source_id=self.source_id, content_sha256=result.sha256,
                               observed_at=observed_at, licence=self.licence,
                               source_behaviour=result.source_behaviour, blindness=blindness)

        published, stated = _publish_info(result.content)
        parsed = 0
        by_type: dict[str, int] = {}
        for e in entries(result.content):
            parsed += 1
            by_type[e["sdn_type"] or "(none)"] = by_type.get(e["sdn_type"] or "(none)", 0) + 1

        payload = {
            "publish_date": published,
            "record_count_stated": stated,
            "record_count_parsed": parsed,
            # The integrity check the file offers for free. Not resolved in either
            # direction: a mismatch is reported, and neither number is preferred.
            "count_agrees": stated is not None and stated == parsed,
            "by_sdn_type": dict(sorted(by_type.items())),
            "served_via": result.resolved_host or "(direct)",
            "fetch_note": result.note,
            "empty_result_means": f"not on the SDN list as published {published or '(date unknown)'}; "
                                  "NOT 'not sanctioned' -- blindness EITHER",
        }
        return Observation(source_id=self.source_id, content_sha256=result.sha256,
                           observed_at=observed_at, licence=self.licence,
                           source_behaviour=ACCESSIBLE, blindness=blindness,
                           payload=payload)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _test() -> None:
    import os
    import urllib.error
    from email.message import Message

    from checker.feeds import Feed, may_serve_commercially
    from checker.feeds.common.fetch import _FakeResponse
    from checker.robots import parse as parse_robots

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    # A two-entry file in OFAC's real shape and namespace, with its own stated count.
    def sample(stated: int) -> bytes:
        return f"""<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="{_NS_SEEN}">
  <publshInformation><Publish_Date>09/16/2026</Publish_Date><Record_Count>{stated}</Record_Count></publshInformation>
  <sdnEntry><uid>306</uid><lastName>BANCO NACIONAL DE CUBA</lastName><sdnType>Entity</sdnType>
    <programList><program>CUBA</program></programList>
    <akaList><aka><uid>220</uid><type>a.k.a.</type><category>strong</category><lastName>NATIONAL BANK OF CUBA</lastName></aka></akaList>
  </sdnEntry>
  <sdnEntry><uid>9</uid><firstName>Jane</firstName><lastName>Doe-Example</lastName><sdnType>Individual</sdnType>
    <programList><program>SDGT</program></programList>
  </sdnEntry>
</sdnList>""".encode()

    good = sample(2)
    allow_all = parse_robots("")            # an empty robots file: everything allowed
    deny_all = parse_robots("User-agent: *\nDisallow: /\n")

    def redirecting_opener(body: bytes):
        """The measured behaviour: entry 302s to the S3 host, which serves the bytes."""
        def opener(url, *, timeout):
            if "sanctionslistservice" in url:
                h = Message()
                h["Location"] = f"https://{PAYLOAD_HOST}/Published/x/SDN.XML?X-Amz-Expires=3600"
                raise urllib.error.HTTPError(url, 302, "Found", h, None)
            return _FakeResponse(200, body)
        return opener

    feed = OfacSdnFeed(rules=allow_all, opener=redirecting_opener(good))

    # ---- the protocol --------------------------------------------------------
    check(isinstance(feed, Feed), "OfacSdnFeed satisfies the Feed protocol")
    check(feed.licence == LICENCE_UNVERIFIED, "licence is UNVERIFIED, not inferred from the publisher")
    check(not may_serve_commercially(feed.licence)[0], "...so it refuses commercial serving")

    # ---- the measured redirect shape -----------------------------------------
    r = feed.fetch()
    check(r.source_behaviour == ACCESSIBLE, "the trusted S3 redirect is followed")
    check(r.url == ENTRY_URL, "the result's identity is the stable entry URL, never the signed one")
    check("X-Amz" not in r.url, "the expiring signed URL is not stored anywhere on the result")
    check(r.resolved_host == PAYLOAD_HOST, "the payload host is recorded as metadata")

    # ---- parsing and the free integrity check --------------------------------
    obs = feed.parse(r, observed_at=_now())
    check(obs.payload["record_count_parsed"] == 2, "both entries parsed")
    check(obs.payload["count_agrees"] is True, "parsed count agrees with the file's own Record_Count")
    check(obs.payload["publish_date"] == "09/16/2026", "publish date read as written, not reformatted")
    check(obs.payload["by_sdn_type"] == {"Entity": 1, "Individual": 1}, "counted by type")
    check(obs.blindness == EITHER, "blindness is EITHER: additions and delistings both unseen")
    check("NOT 'not sanctioned'" in obs.payload["empty_result_means"],
          "the observation says what an empty result does NOT mean")

    lying = OfacSdnFeed(rules=allow_all, opener=redirecting_opener(sample(19385)))
    o2 = lying.parse(lying.fetch(), observed_at=_now())
    check(o2.payload["count_agrees"] is False,
          "a stated/parsed count mismatch is REPORTED, not smoothed over")

    # ---- screening -----------------------------------------------------------
    check(len(screen("Banco Nacional de Cuba", good)) == 1, "primary name matches")
    check(screen("national bank of cuba", good)[0]["matched_on"] == "NATIONAL BANK OF CUBA",
          "an alias matches, and says which name matched")
    check(screen("jane doe example", good)[0]["uid"] == "9", "punctuation is normalised away")
    check(screen("Acme Holdings Private Limited", good) == [], "an absent name yields no candidates")
    check(screen("   ", good) == [], "an empty query matches nothing rather than everything")

    # ---- failing closed ------------------------------------------------------
    blocked = OfacSdnFeed(rules=deny_all, opener=redirecting_opener(good))
    rb = blocked.fetch()
    check(rb.source_behaviour != ACCESSIBLE and rb.content == b"",
          "a robots disallow refuses, carrying no bytes")
    ob = blocked.parse(rb, observed_at=_now())
    check(ob.payload == {}, "a refused fetch yields an observation with NO payload")

    def rogue_opener(url, *, timeout):
        h = Message(); h["Location"] = "https://evil.example.com/SDN.XML"
        raise urllib.error.HTTPError(url, 302, "Found", h, None)
    rr = OfacSdnFeed(rules=allow_all, opener=rogue_opener).fetch()
    check(rr.source_behaviour != ACCESSIBLE, "a redirect to any host but PAYLOAD_HOST is refused")
    check("evil.example.com" in rr.note, "...and the refusal names the host it would not follow")

    # ---- the ring boundary ---------------------------------------------------
    from checker import rings
    check(rings.ring_of("checker.feeds.ofac_sdn") == rings.RING_2, "this module is registered Ring 2")

    # ---- vessel index: synthetic entries in the schema measured 2026-09-17 ---
    # uid 4243 EBANO / IMO 7406784 and the "IMO 7206512" example are real entries
    # copied verbatim from the live file (see module docstring); "IMO 7406783" is
    # the same digits as the real 7406784 with the check digit deliberately wrong.
    def vessel_sample() -> bytes:
        return f"""<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="{_NS_SEEN}">
  <publshInformation><Publish_Date>09/16/2026</Publish_Date><Record_Count>3</Record_Count></publshInformation>
  <sdnEntry><uid>4243</uid><lastName>EBANO</lastName><sdnType>Vessel</sdnType>
    <programList><program>CUBA</program></programList>
    <idList><id><uid>22133</uid><idType>Vessel Registration Identification</idType><idNumber>IMO 7406784</idNumber></id></idList>
    <vesselInfo><vesselType>General Cargo</vesselType><vesselFlag>Panama</vesselFlag><tonnage>2595</tonnage><grossRegisteredTonnage>1865</grossRegisteredTonnage></vesselInfo>
  </sdnEntry>
  <sdnEntry><uid>9001</uid><lastName>BAD CHECK DIGIT</lastName><sdnType>Vessel</sdnType>
    <programList><program>CUBA</program></programList>
    <idList><id><uid>2</uid><idType>Vessel Registration Identification</idType><idNumber>IMO 7406783</idNumber></id></idList>
    <vesselInfo><vesselType>Tanker</vesselType><vesselFlag>Panama</vesselFlag></vesselInfo>
  </sdnEntry>
  <sdnEntry><uid>4238</uid><lastName>MAR AZUL</lastName><sdnType>Vessel</sdnType>
    <programList><program>CUBA</program></programList>
    <vesselInfo><callSign>CL2192</callSign><vesselType>Tug</vesselType><vesselFlag>Cuba</vesselFlag><vesselOwner>Samir de Navegacion S.A.</vesselOwner><grossRegisteredTonnage>212</grossRegisteredTonnage></vesselInfo>
  </sdnEntry>
</sdnList>""".encode()

    vsample = vessel_sample()

    check(imo_check_digit_valid("7406784"), "the real EBANO IMO passes its own check digit")
    check(imo_check_digit_valid("7206512"), "a second real IMO (measured live) passes too")
    check(not imo_check_digit_valid("7406783"),
          "the same six leading digits with a wrong 7th digit fails")
    check(not imo_check_digit_valid("123456"), "a 6-digit string is not IMO-shaped at all")
    check(not imo_check_digit_valid("IMO 7406784"), "an unnormalised string is not IMO-shaped")
    check(normalise_imo("IMO 7406784") == "7406784", "a prefixed IMO strips to bare digits")
    check(normalise_imo("  imo  7406784 ") == "7406784", "stripping tolerates case and extra whitespace")
    check(normalise_imo("8606173") == "8606173", "stripping a prefix that is not there is a no-op")

    vidx = vessels(vsample)
    check(set(vidx) == {"7406784", "7406783"},
          "only the two entries with an IMO-shaped id are indexed -- MAR AZUL (no idList) is absent")
    check(vidx["7406784"]["imo_check_digit_valid"] is True, "the valid IMO is reported valid")
    check(vidx["7406784"]["name"] == "EBANO" and vidx["7406784"]["vessel_type"] == "General Cargo",
          "the valid entry carries its name and vesselInfo fields")
    check(vidx["7406784"]["gross_registered_tonnage"] == "1865", "tonnage fields pass through as published")
    check(vidx["7406783"]["imo_check_digit_valid"] is False,
          "a failing check digit is INDEXED, not dropped or repaired")
    check(vidx["7406783"]["name"] == "BAD CHECK DIGIT",
          "...so the bad record is still reachable by the IMO the source actually published")

    check(lookup_vessel("IMO 7406784", vsample)["uid"] == "4243",
          "lookup_vessel accepts a prefixed IMO")
    check(lookup_vessel("7406784", vsample)["uid"] == "4243",
          "...and a bare one, resolving to the same record")
    check(lookup_vessel("9999999", vsample) is None, "an IMO not on the list returns None, not a KeyError")
    check(lookup_vessel("7406784", good) is None,
          "a file with no Vessel entries at all (the Entity/Individual fixture) indexes nothing")

    no_imo_vessels = [e for e in entries(vsample) if e["sdn_type"] == "Vessel" and not e["ids"]]
    check(len(no_imo_vessels) == 1 and no_imo_vessels[0]["name"] == "MAR AZUL",
          "a Vessel entry with no idList at all is still readable via entries(), just not vessels()")

    # ---- optional: the real file. Off by default so the gate stays hermetic. --
    if os.environ.get("THEMIS_LIVE") == "1":
        live = OfacSdnFeed()
        lr = live.fetch()
        check(lr.source_behaviour == ACCESSIBLE, f"LIVE: fetched ({lr.note or lr.http_status})")
        if lr.source_behaviour == ACCESSIBLE:
            lo = live.parse(lr, observed_at=_now())
            p = lo.payload
            print(f"         LIVE published={p['publish_date']} stated={p['record_count_stated']} "
                  f"parsed={p['record_count_parsed']} bytes={len(lr.content):,} sha256={lr.sha256[:16]}…")
            check(p["count_agrees"], "LIVE: parsed count equals OFAC's own stated Record_Count")

            live_vessel_count = p["by_sdn_type"].get("Vessel", 0)
            lvidx = vessels(lr.content)
            valid_imo_count = sum(1 for v in lvidx.values() if v["imo_check_digit_valid"])
            print(f"         LIVE vessels={live_vessel_count} indexed_by_imo={len(lvidx)} "
                  f"valid_imo={valid_imo_count}")
            check(live_vessel_count > 0, "LIVE: at least one Vessel-type sdnEntry present")
            check(len(lvidx) <= live_vessel_count,
                  "LIVE: the IMO index can only be as large as the number of Vessel entries")
    else:
        print("  [SKIP] live fetch (set THEMIS_LIVE=1 to hit the real Sanctions List Service)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
