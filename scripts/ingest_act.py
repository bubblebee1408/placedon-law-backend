#!/usr/bin/env python3
"""
Ingest one Central Act from India Code, for any Act in the register below.

Generalised from `scripts/ingest_companies_act.py` on 2026-09-27 (Harvey-for-India plan, Day 1),
which this file replaces. Every property that file had been taught the hard way is carried, and
each is named where it lives, because the reason is what stops it being undone:

  * **TLS is verified and the user agent is honest (RT-14).** Both were disabled here until
    2026-09-18 -- `CERT_NONE`, `check_hostname = False`, and a spoofed Chrome UA -- on the one
    fetch in this repository where a man-in-the-middle rewrites the statute. Not exploitable that
    day only because the hostname was dead. Now from `checker.robots`, which fails closed: no CA
    bundle means no fetch.
  * **An empty enumeration is a failed enumeration, never a corpus of nothing.** The manifest
    write used to happen before the fetch loop, unconditionally, so a page parsing to zero
    section ids replaced the record of what the corpus should contain with `count: 0` and a FRESH
    timestamp, and exited 0. The section files survived, so the damage was invisible. It is
    reachable: measured 2026-09-26, `indiacode.gov.in/handle/123456789/2114` answers 200
    `text/html`, 6,762 bytes -- the DSpace Angular shell -- with zero `sectionId=` matches. The
    payload guard in `checker/robots.py` cannot catch it, because HTML is what that page IS. The
    shape of the result is the only evidence, so the check belongs here.
  * **Section ids are enumerated off the act page, never by counting integers.** Inserted
    sections carry high ids -- s.3A is 48973 -- so iterating 1..N silently fetches the wrong law.

## Why most Acts in the register refuse to run

**An India Code `actid` is not guessable and must never be guessed.** A wrong id fetches a
different statute, and the result would look exactly like a successful ingest: well-formed JSON,
real section text, a clean hash. Nothing downstream could tell. So an Act whose `act_id` has not
been confirmed against India Code by a person is `PENDING_ID` and this script refuses it, naming
what to do. Filling one in is a deliberate act with a URL recorded beside it.

Run:  python3 scripts/ingest_act.py --list
      python3 scripts/ingest_act.py companies_act [--limit N]
      python3 scripts/ingest_act.py --test
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from checker.robots import USER_AGENT, allowed, fetch_rules, ssl_context   # noqa: E402

UA = {"User-Agent": USER_AGENT}
PAUSE = 0.4                      # be a polite client

# ── One host, and it is indiacode.gov.in (founder instruction, 2026-09-27) ────
# Measured the same day, from this machine, so the rule is recorded with its evidence
# rather than as a preference:
#
#   www.indiacode.nic.in/handle/123456789/2114   HTTP 000 -- no answer. DNS resolves
#                                               (184.84.232.9), so this is a connection
#                                               or TLS failure: UNREACHABLE in
#                                               docs/ACQUISITION_POLICY.md's taxonomy,
#                                               which is the one retryable class.
#   indiacode.gov.in/handle/123456789/2114       HTTP 200, text/html, 6,762 bytes, and
#                                               ZERO sectionId= matches -- the DSpace
#                                               Angular shell. A soft-404 in the shape
#                                               this repository exists to refuse.
#
# So the HTML handle page enumerates on NEITHER host today, and `enumerate_sections`
# below would return [] for both -- which the empty-enumeration guard correctly refuses
# rather than writing an empty manifest.
#
# What DOES work on indiacode.gov.in is the DSpace 7 REST API: `/server/api` answers 200
# application/hal+json with 80 link relations, and
# /server/api/discover/search/objects?query=dc.identifier.section_number:*&dsoType=item
# reports **74,821** items carrying `dc.identifier.section_number`, each with
# `dc.identifier.section_id`, `section_number`, `section_footnote` and `dc.title`. That is
# a better enumeration surface than the HTML ever was, and it is on the permitted host.
# Scoping it to ONE Act is not yet established -- see enumerate_sections' docstring.
PERMITTED_HOST = "indiacode.gov.in"
CONTENT_EP = ("https://indiacode.gov.in/SectionPageContent"
              "?actid={act}&sectionID={sid}")


class HostRefused(ValueError):
    """A URL outside the permitted host. Raised before any request is made."""


class RobotsRefused(ValueError):
    """robots.txt does not permit this fetch. Raised before any request is made.

    Found 2026-09-28 by a corpus agent, in code I had written the day before: `_get` called
    `check_host()` and then `urlopen`, and imported only `USER_AGENT` and `ssl_context` from
    `checker.robots` -- the two helpers, and not the part that says no. **The one script in
    this repository that fetches statutes was the one script robots.txt could not stop**,
    and the Companies Act's 527 sections came through it.

    It is not hypothetical. Measured the same day: `indiacode.gov.in/robots.txt` answers
    **HTTP 500**, and `checker.robots.fetch_rules` fails closed on 5xx per RFC 9309
    (a 4xx means "no rules published", so fetching is allowed; a 5xx means "rules exist but
    are undetermined", so it is not). The repo's own gate already said
    `allowed('https://indiacode.gov.in/server/api/core/items', rules) == False`. Nothing was
    asking it.

    That is also why "the REST API is live" and "the REST API is permitted" are different
    statements, and why I had conflated them: I measured the first with curl, which goes
    around the gate.
    """


def check_host(url: str) -> str:
    """`url` unchanged, or raise. The netloc must BE the permitted host or a subdomain.

    A substring test would accept `indiacode.gov.in.evil.example`, so the comparison is
    on the parsed netloc with an explicit dot-suffix rule.
    """
    from urllib.parse import urlsplit
    netloc = urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    if netloc != PERMITTED_HOST and not netloc.endswith("." + PERMITTED_HOST):
        raise HostRefused(
            f"{netloc or url!r} is not {PERMITTED_HOST}. Only that host is permitted for "
            f"statute acquisition (founder instruction 2026-09-27). www.indiacode.nic.in "
            f"answered HTTP 000 when measured that day; whatever it serves, it is not "
            f"reachable from here and it is not the declared source.")
    return url

# A corpus directory name, and nothing that could escape `corpus/`.
_KEY_OK = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


@dataclass(frozen=True)
class Act:
    """One Central Act. `act_id` is None until a person has confirmed it on India Code."""

    key: str                     # corpus/<key>/ -- validated against _KEY_OK
    title: str
    act_id: str | None
    handle: str | None           # the act page whose HTML carries every sectionId=
    note: str = ""

    @property
    def pending(self) -> bool:
        return not (self.act_id and self.handle)


# ── The register. Order is PLAN order: the Harvey-for-India plan's §3 list. ───────────────────
ACTS: dict[str, Act] = {a.key: a for a in (
    Act("companies_act", "Companies Act, 2013",
        "AC_CEN_22_29_00008_201318_1517807327856",
        "https://indiacode.gov.in/handle/123456789/2114",
        "Held: 527 sections, hash-stamped. The handle moved from www.indiacode.nic.in to "
        "indiacode.gov.in on 2026-09-27 to satisfy the one-host rule. The 527 records "
        "already on disk carry .nic.in source_urls, which is what they were fetched from "
        "and must not be rewritten -- provenance records where a thing CAME from."),

    # Everything below is DECLARED in the plan and PENDING_ID here. Confirm the actid and the
    # handle URL on India Code, paste both, and record where you found them. Do not guess:
    # a wrong actid returns a different Act's sections and every downstream check passes.
    Act("llp2008", "Limited Liability Partnership Act, 2008", None, None,
        "PLAN body 4. Needs actid + handle from India Code."),
    Act("fema1999", "Foreign Exchange Management Act, 1999", None, None,
        "PLAN body 5. FDI rules move by press note and are NOT part of the Act ingest."),
    Act("ibc2016", "Insolvency and Bankruptcy Code, 2016", None, None,
        "PLAN body 6. Needs actid + handle."),
    Act("comp2002", "Competition Act, 2002", None, None,
        "PLAN body 7. Needs actid + handle."),
    Act("dpdp2023", "Digital Personal Data Protection Act, 2023", None, None,
        "PLAN body 8. Declared in scope by the plan; note DPDP was previously ruled OUT "
        "(BUSINESS_PLAN 2026-08-16). The plan supersedes that -- confirm with the founder "
        "before acquiring, because it reverses a recorded decision."),
)}


def known_keys() -> list[str]:
    return sorted(ACTS)


def corpus_dir(act: Act, root: Path = ROOT) -> Path:
    """`corpus/<key>/`, with the key validated so it cannot climb out of corpus/."""
    if not _KEY_OK.match(act.key):
        raise ValueError(f"unusable corpus key {act.key!r}: must match {_KEY_OK.pattern}")
    return root / "corpus" / act.key


# One robots ruleset per origin, fetched once. Without the cache this would re-request
# robots.txt before every section -- hundreds of times per Act, which is impolite to the
# host and slow, and would make a mid-run robots change apply to half a corpus.
_RULES: dict[str, object] = {}


def rules_for(url: str, *, fetch=None) -> object:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _RULES:
        _RULES[origin] = (fetch or fetch_rules)(origin)
    return _RULES[origin]


def _get(url: str, tries: int = 3, *, rules_fetch=None) -> str:
    check_host(url)                  # before the socket, not after
    rules = rules_for(url, fetch=rules_fetch)
    if not allowed(url, rules):
        raise RobotsRefused(
            f"robots.txt does not permit {url} (ruleset: "
            f"{getattr(rules, 'source', '?')}, loaded={getattr(rules, 'loaded', '?')}). "
            f"checker.robots fails CLOSED: an unloaded ruleset grants nothing, and a 5xx on "
            f"robots.txt means the rules are undetermined rather than absent. This is a fact "
            f"about the host, not about the law -- escalate to a human read.")
    ctx = ssl_context()
    if ctx is None:
        raise RuntimeError("no CA bundle available; refusing to fetch a statute over an "
                           "unverified connection (RT-14)")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def enumerate_sections(act: Act, get=_get) -> list[str]:
    """Section ids in document order, parsed off the act page. One fetch returns all of them.

    **This mechanism does not currently work on any permitted host, and that is measured,
    not assumed.** `indiacode.gov.in`'s handle page is the DSpace Angular shell: 200,
    text/html, 6,762 bytes, zero `sectionId=` matches. It returns `[]`, and `ingest()`
    refuses an empty enumeration rather than writing a manifest of nothing -- so the
    failure is loud and nothing is corrupted.

    The replacement is the DSpace REST API on the same host, which is live and open (see
    PERMITTED_HOST above for the measured totals). It is NOT built here, because scoping
    its 74,821 section-bearing items to one Act is unestablished: the handle did not
    resolve through `/server/api/pid/find?id=hdl:123456789/2114` (404), so the
    handle -> collection mapping has to be found before an Act can be enumerated. Writing
    a plausible query that silently returns another Act's sections is the failure this
    repository refuses most consistently.
    """
    html = get(act.handle)
    ids: list[str] = []
    seen: set[str] = set()
    for sid in re.findall(r"sectionI[dD]=(\d+)", html):
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def fetch_section(act: Act, sid: str, get=_get) -> dict:
    url = CONTENT_EP.format(act=act.act_id, sid=sid)
    data = json.loads(get(url))
    content = data.get("content") or ""
    return {
        "section_id": sid,
        "act_key": act.key,
        "act_id": act.act_id,
        "act_title": act.title,
        "content": content,
        "footnote": data.get("footnote") or "",
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def ingest(act: Act, *, limit: int | None = None, root: Path = ROOT,
           enumerate_fn=enumerate_sections, fetch_fn=fetch_section) -> int:
    """Ingest one Act. Returns a process exit code: 0 ok, 1 refused.

    The two callables are injected rather than patched, so a test can drive the whole path
    without a network and without reassigning module globals -- which the previous version's
    tests had to do, and which meant a test could pass while the real call site was wrong.
    """
    if act.pending:
        print(f"REFUSED: {act.key} ({act.title}) has no confirmed India Code actid.\n"
              f"  {act.note}\n"
              f"  An actid is not guessable. A wrong one returns a DIFFERENT Act's sections and "
              f"every check downstream would pass, because the result is well-formed. Confirm it "
              f"on India Code, then record the actid and the handle URL in ACTS.", flush=True)
        return 1

    out = corpus_dir(act, root)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "_manifest.json"

    ids = enumerate_fn(act)
    print(f"{act.key}: enumerated {len(ids)} section ids", flush=True)

    # An empty enumeration is a failed enumeration. See the module docstring: this is the check
    # that stops a soft-404 overwriting the record of what the corpus should contain.
    if not ids:
        print(f"REFUSED: {act.handle} parsed to 0 section ids. A page that yields no sections is "
              f"a source we could not read, not an Act with no sections -- the manifest is left "
              f"as it was.", flush=True)
        return 1

    # `act_key` and `act_id` are both written, so a manifest can never be read as another Act's.
    # The old single-Act manifest carried act_id alone, which was unambiguous only while there
    # was exactly one corpus.
    #
    # **Rewritten only when the enumeration actually changed.** A re-run is supposed to be a
    # no-op, and it was not: the manifest was rewritten unconditionally with a fresh
    # `enumerated_at`, so every re-run dirtied a TRACKED file for no new information. Found
    # by asserting byte-identity across two runs rather than only "nothing was refetched" --
    # the section files were identical and the manifest was not. An unchanged id list means
    # the enumeration did not change, and a timestamp saying otherwise is churn, not news.
    record = {"act_key": act.key, "act_id": act.act_id, "act_title": act.title,
              "section_ids": ids, "count": len(ids)}
    previous = None
    if manifest.exists():
        try:
            previous = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            previous = None          # unreadable or corrupt: rewrite it
    if not (previous and {k: previous.get(k) for k in record} == record):
        manifest.write_text(json.dumps(
            {**record,
             "enumerated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            indent=2))
    else:
        print(f"{act.key}: enumeration unchanged; manifest left as it was", flush=True)

    if limit:
        ids = ids[:limit]

    fetched = skipped = failed = 0
    for n, sid in enumerate(ids, 1):
        path = out / f"{sid}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            path.write_text(json.dumps(fetch_fn(act, sid), ensure_ascii=False, indent=2))
            fetched += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL {sid}: {type(e).__name__}", flush=True)
        if n % 25 == 0:
            print(f"  {n}/{len(ids)} fetched={fetched} skipped={skipped} failed={failed}",
                  flush=True)
        time.sleep(PAUSE)

    print(f"{act.key}: done. fetched={fetched} skipped={skipped} failed={failed}", flush=True)
    # A per-section failure is not a failed run: it is reported and the manifest is already
    # correct. Only an unreadable enumeration, or an unconfirmed actid, refuses.
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if "--list" in argv or not args:
        print("Acts in the register:\n")
        for k in known_keys():
            a = ACTS[k]
            print(f"  {k:16s} {'READY     ' if not a.pending else 'PENDING_ID'} {a.title}")
            if a.note:
                print(f"                   {a.note}")
        print(f"\nRun: python3 scripts/ingest_act.py <key> [--limit N]")
        return 0 if "--list" in argv else 1

    # An Act not in the register can be named directly: --act-key plus --handle and
    # --act-id. All three are required together, because two of them are not enough to
    # fetch anything and a partial set would otherwise fall back to a register entry --
    # i.e. silently ingest a different Act than the one named.
    if "--handle" in argv or "--act-id" in argv or "--act-key" in argv:
        def opt(name):
            return argv[argv.index(name) + 1] if name in argv else None
        key, handle, act_id = opt("--act-key"), opt("--handle"), opt("--act-id")
        missing = [n for n, v in (("--act-key", key), ("--handle", handle),
                                  ("--act-id", act_id)) if not v]
        if missing:
            print(f"REFUSED: {', '.join(missing)} missing. An ad-hoc Act needs all three: "
                  f"--act-key (the corpus directory), --handle (the act page) and --act-id "
                  f"(the India Code actid). Two of the three cannot fetch anything, and "
                  f"falling back to the register would ingest a DIFFERENT Act than the one "
                  f"named.", flush=True)
            return 1
        if key in ACTS:
            print(f"REFUSED: {key!r} is already in the register. Edit ACTS rather than "
                  f"passing it on the command line, so the actid is recorded with the URL "
                  f"it was confirmed at.", flush=True)
            return 1
        try:
            ad_hoc = Act(key, f"(ad hoc) {key}", act_id, check_host(handle),
                         "Named on the command line, not in the register.")
            corpus_dir(ad_hoc)                       # validates the key before any fetch
        except (HostRefused, ValueError) as e:
            print(f"REFUSED: {e}", flush=True)
            return 1
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
        return ingest(ad_hoc, limit=limit)

    key = args[0]
    if key not in ACTS:
        print(f"REFUSED: {key!r} is not in the register. Known: {', '.join(known_keys())}.\n"
              f"  Add it to ACTS with a CONFIRMED India Code actid and handle URL. An Act this "
              f"script has never been told about is not an Act with no sections.", flush=True)
        return 1

    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    return ingest(ACTS[key], limit=limit)


def _test() -> int:
    """No network. Both fetchers are injected, so nothing here can reach India Code."""
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def attempt(fn):
        """The exception fn() raised, or None. Its TYPE is what the caller asserts on."""
        try:
            fn()
        except Exception as e:                      # noqa: BLE001 - inspected by the test
            return e
        return None

    print("ingest_act")
    CA = ACTS["companies_act"]

    # ── the register ─────────────────────────────────────────────────────────
    check(not CA.pending, "the Companies Act is READY -- it has a confirmed actid and handle")
    pend = [k for k in known_keys() if ACTS[k].pending]
    check(len(pend) == 5 and "companies_act" not in pend,
          f"every other body is PENDING_ID until a person confirms its actid ({pend})")
    check(all(ACTS[k].act_id is None for k in pend),
          "no PENDING body carries a guessed actid -- a wrong one is undetectable downstream")
    check(all(k == ACTS[k].key for k in ACTS),
          "the register is keyed by each Act's own key, so a lookup cannot return another Act")

    # ── the corpus path cannot escape corpus/ ────────────────────────────────
    check(corpus_dir(CA, Path("/tmp/x")) == Path("/tmp/x/corpus/companies_act"),
          "the corpus directory is derived from the key")
    for bad in ("../etc", "/abs", "Dot.Dot", "AB", "x"):
        try:
            corpus_dir(Act(bad, "t", "a", "h"))
            check(False, f"a key of {bad!r} must be refused")
        except ValueError:
            check(True, f"a key of {bad!r} is refused before it becomes a path")

    # ── an unconfirmed actid refuses, and never fetches ──────────────────────
    calls: list = []
    with tempfile.TemporaryDirectory() as d:
        rc = ingest(ACTS["ibc2016"], root=Path(d),
                    enumerate_fn=lambda a: calls.append(a) or ["1"],
                    fetch_fn=lambda a, s: calls.append(s) or {})
        check(rc == 1, "a PENDING_ID Act refuses")
        check(calls == [], "...and nothing was fetched -- the refusal is before the first call")
        check(not (Path(d) / "corpus").exists(),
              "...and no corpus directory was created for it")

    # ── an empty enumeration leaves the manifest exactly as it was ───────────
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "corpus/companies_act"
        out.mkdir(parents=True)
        good = {"act_key": "companies_act", "act_id": CA.act_id, "act_title": CA.title,
                "section_ids": ["1", "2"], "count": 527,
                "enumerated_at": "2026-08-18T22:15:46+00:00"}
        (out / "_manifest.json").write_text(json.dumps(good, indent=2))
        rc = ingest(CA, root=Path(d), enumerate_fn=lambda a: [],
                    fetch_fn=lambda a, s: {"unreachable": True})
        after = json.loads((out / "_manifest.json").read_text())
        check(rc == 1, "an empty enumeration exits non-zero")
        check(after == good, "the manifest is byte-identical after a zero-section enumeration")
        check(after["enumerated_at"] == good["enumerated_at"],
              "...including enumerated_at -- no fresh timestamp on a failure")

    # ── the happy path, and what it records ─────────────────────────────────
    with tempfile.TemporaryDirectory() as d:
        seen: list[str] = []

        def fake_fetch(a: Act, sid: str) -> dict:
            seen.append(sid)
            return {"section_id": sid, "act_key": a.key, "content": "x"}

        rc = ingest(CA, root=Path(d), enumerate_fn=lambda a: ["11", "12", "13"],
                    fetch_fn=fake_fetch)
        m = json.loads((Path(d) / "corpus/companies_act/_manifest.json").read_text())
        check(rc == 0, "a real enumeration exits 0")
        check(m["count"] == 3 and m["section_ids"] == ["11", "12", "13"],
              "the ids are written in document order")
        check(m["act_key"] == "companies_act" and m["act_id"] == CA.act_id,
              "the manifest names WHICH Act it is -- it cannot be read as another's")
        check(seen == ["11", "12", "13"], "every enumerated section was fetched")
        check((Path(d) / "corpus/companies_act/12.json").exists(),
              "...and written to <section_id>.json")

    # ── resumability: a section already on disk is skipped, not refetched ────
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "corpus/companies_act"
        out.mkdir(parents=True)
        (out / "11.json").write_text('{"already": true}')
        seen = []
        ingest(CA, root=Path(d), enumerate_fn=lambda a: ["11", "12"],
               fetch_fn=lambda a, s: seen.append(s) or {"section_id": s})
        check(seen == ["12"], "a section already on disk is skipped, not refetched")
        check(json.loads((out / "11.json").read_text()) == {"already": True},
              "...and the file on disk is left untouched")

    # ── --limit truncates the FETCH, never the manifest ──────────────────────
    with tempfile.TemporaryDirectory() as d:
        seen = []
        ingest(CA, limit=1, root=Path(d), enumerate_fn=lambda a: ["11", "12", "13"],
               fetch_fn=lambda a, s: seen.append(s) or {"section_id": s})
        m = json.loads((Path(d) / "corpus/companies_act/_manifest.json").read_text())
        check(seen == ["11"], "--limit truncates what is fetched")
        check(m["count"] == 3,
              "...but the manifest still records all 3 -- a partial fetch is not a smaller Act")

    # ── the one-host rule ────────────────────────────────────────────────────
    for good in ("https://indiacode.gov.in/handle/1", "https://www.indiacode.gov.in/x",
                 "https://indiacode.gov.in:443/y"):
        check(check_host(good) == good, f"permitted: {good}")
    for bad in ("https://www.indiacode.nic.in/handle/1",      # the old host
                "https://indiacode.gov.in.evil.example/x",    # suffix attack
                "https://evil.example/?u=indiacode.gov.in",   # substring attack
                "http://localhost/x", "https://indiacode.gov.in@evil.example/x"):
        check(isinstance(attempt(lambda u=bad: check_host(u)), HostRefused),
              f"refused: {bad}")
    check("indiacode.gov.in" in CONTENT_EP and "nic.in" not in CONTENT_EP,
          "the section-content endpoint is on the permitted host")
    check(all("nic.in" not in (a.handle or "") for a in ACTS.values()),
          "no Act in the register points at nic.in")

    # ── robots.txt is consulted, and it fails CLOSED ─────────────────────────
    # The defect this replaces: `_get` called check_host() and urlopen, and imported only
    # USER_AGENT and ssl_context from checker.robots -- the helpers, not the part that says
    # no. Found by a corpus agent on 2026-09-28, in code written the day before.
    from checker.robots import Rules, parse as _parse_robots

    _RULES.clear()
    unloaded = Rules()                       # what a 5xx robots.txt produces
    check(not unloaded.loaded, "an unloaded ruleset is what a 5xx robots.txt yields")
    e = attempt(lambda: _get("https://indiacode.gov.in/handle/1",
                             rules_fetch=lambda origin: unloaded))
    check(isinstance(e, RobotsRefused),
          f"_get REFUSES when robots.txt did not load -- no socket is opened ({type(e).__name__})")
    check("fails CLOSED" in str(e) and "not about the law" in str(e),
          "...and the refusal says it is a fact about the host, not about the law")

    _RULES.clear()
    disallowing = _parse_robots("User-agent: *\nDisallow: /server/\n")
    check(disallowing.loaded, "a well-formed ruleset loads")
    check(isinstance(attempt(lambda: _get("https://indiacode.gov.in/server/api/core/items",
                                          rules_fetch=lambda o: disallowing)), RobotsRefused),
          "_get refuses a path the ruleset disallows, even on the permitted host")

    # The host guard must still come FIRST: a forbidden host is refused before robots is
    # even fetched, so a bad host cannot be laundered through a permissive ruleset.
    _RULES.clear()
    permissive = _parse_robots("User-agent: *\nDisallow:\n")
    check(isinstance(attempt(lambda: _get("https://evil.example/x",
                                          rules_fetch=lambda o: permissive)), HostRefused),
          "a forbidden host is refused BEFORE robots, so a permissive ruleset cannot launder it")

    # One robots fetch per origin, not one per section.
    _RULES.clear()
    fetched: list[str] = []

    def counting_rules(origin):
        fetched.append(origin)
        return permissive

    for sid in ("1", "2", "3"):
        attempt(lambda s=sid: _get(f"https://indiacode.gov.in/x/{s}",
                                   rules_fetch=counting_rules))
    check(fetched == ["https://indiacode.gov.in"],
          f"robots.txt is fetched ONCE per origin, not once per section ({fetched})")
    _RULES.clear()

    # ── an offline fixture, per record shape ─────────────────────────────────
    # A captured SectionPageContent response. Offline on purpose: the shape is what this
    # test is about, and a live fetch would make it a network test that passes or fails
    # for reasons unrelated to the record.
    FIXTURE = json.dumps({
        "content": "<p>2. Definitions.\u2014In this Act, unless the context otherwise "
                   "requires,\u2014</p>",
        "footnote": "1. Subs. by Act 1 of 2018, s. 2 (w.e.f. 9-2-2018).",
        "extra_field_we_do_not_read": "ignored",
    })
    rec = fetch_section(CA, "100467", get=lambda u: FIXTURE)
    want_keys = {"section_id", "act_key", "act_id", "act_title", "content", "footnote",
                 "sha256", "source_url", "fetched_at"}
    check(set(rec) == want_keys, f"the record has exactly the declared keys ({set(rec) ^ want_keys or 'exact'})")
    check(rec["section_id"] == "100467" and rec["act_key"] == "companies_act"
          and rec["act_id"] == CA.act_id,
          "...identifying both the section and WHICH Act it belongs to")
    check(rec["sha256"] == hashlib.sha256(rec["content"].encode("utf-8")).hexdigest(),
          "...hash-stamped over the content, and the stamp verifies")
    check(rec["footnote"].startswith("1. Subs. by Act 1 of 2018"),
          "...carrying the footnote verbatim, which is where amendment history lives")
    check("indiacode.gov.in" in rec["source_url"] and "100467" in rec["source_url"],
          f"...and recording the URL it came from ({rec['source_url']})")
    check(rec["content"].startswith("<p>2. Definitions."),
          "...with the content unaltered -- never repair a government source")
    empty = fetch_section(CA, "1", get=lambda u: json.dumps({}))
    check(empty["content"] == "" and empty["footnote"] == ""
          and empty["sha256"] == hashlib.sha256(b"").hexdigest(),
          "a response with neither field yields empty strings and the empty-string hash, "
          "not a KeyError")

    # ── a re-run is a no-op ──────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        calls: list[str] = []

        def counting(a: Act, sid: str) -> dict:
            calls.append(sid)
            return {"section_id": sid, "act_key": a.key, "content": f"s{sid}"}

        ids = ["11", "12", "13"]
        rc1 = ingest(CA, root=root, enumerate_fn=lambda a: ids, fetch_fn=counting)
        first = sorted(p.name for p in (root / "corpus/companies_act").iterdir())
        bytes1 = {p.name: p.read_bytes() for p in (root / "corpus/companies_act").iterdir()}
        n_after_first = len(calls)

        rc2 = ingest(CA, root=root, enumerate_fn=lambda a: ids, fetch_fn=counting)
        second = sorted(p.name for p in (root / "corpus/companies_act").iterdir())
        bytes2 = {p.name: p.read_bytes() for p in (root / "corpus/companies_act").iterdir()}

        check(rc1 == 0 and rc2 == 0, "both runs exit 0")
        check(n_after_first == 3 and len(calls) == 3,
              f"the second run fetched NOTHING ({len(calls) - n_after_first} new calls)")
        check(first == second, "the same files are present after the re-run")
        check(bytes1 == bytes2,
              "...and every file is byte-identical, MANIFEST INCLUDED -- a re-run rewrites "
              "nothing at all")
        check("enumerated_at" in json.loads(bytes2["_manifest.json"]),
              "...while the manifest still carries enumerated_at from the run that wrote it")

        # But a CHANGED enumeration must be written: the no-op must not become a refusal
        # to record news.
        rc3 = ingest(CA, root=root, enumerate_fn=lambda a: ids + ["14"], fetch_fn=counting)
        m3 = json.loads((root / "corpus/companies_act/_manifest.json").read_text())
        check(rc3 == 0 and m3["count"] == 4 and m3["section_ids"][-1] == "14",
              "a changed enumeration IS written -- unchanged means quiet, not deaf")

    # ── an unknown key refuses and names what is known ──────────────────────
    check(main(["no_such_act"]) == 1, "an unknown key refuses")
    check(main(["--list"]) == 0, "--list exits 0")
    check(main([]) == 1, "no argument is a usage error, not a default Act")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main(sys.argv[1:]))
