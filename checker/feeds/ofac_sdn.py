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
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from checker.feeds import (EITHER, LICENCE_UNVERIFIED, FetchResult, Observation)
from checker.feeds.common.fetch import fetch as _fetch
from checker.provenance import ACCESSIBLE

__all__ = ["OfacSdnFeed", "ENTRY_URL", "PAYLOAD_HOST", "entries", "screen", "normalise"]

SOURCE_ID = "ofac.sdn"
ENTRY_URL = "https://sanctionslistservice.ofac.treas.gov/api/download/SDN.XML"
PAYLOAD_HOST = "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com"
LICENCE = LICENCE_UNVERIFIED
BLINDNESS = EITHER

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
    """One <sdnEntry> as a plain dict. Names only what screening needs."""
    first, last = _text(el, "firstName"), _text(el, "lastName")
    akas, programs = [], []
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
    return {
        "uid": _text(el, "uid"),
        "name": " ".join(x for x in (first, last) if x),
        "sdn_type": _text(el, "sdnType"),
        "programs": programs,
        "akas": akas,
    }


def entries(content: bytes):
    """Yield every <sdnEntry> as a dict, streaming. Memory stays flat on 29 MB."""
    for _event, el in ET.iterparse(io.BytesIO(content), events=("end",)):
        if _local(el.tag) == "sdnEntry":
            yield _entry(el)
            el.clear()


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
    else:
        print("  [SKIP] live fetch (set THEMIS_LIVE=1 to hit the real Sanctions List Service)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
