"""
Ingest the Companies Act 2013 from India Code.

Enumerates section IDs off the act page (never by iterating integers — inserted sections carry
high IDs, e.g. s.3A -> 48973), then fetches each section's {content, footnote} from the
undocumented SectionPageContent JSON endpoint.

Born-digital: no OCR anywhere. robots.txt disallows only /discover and /simple-search.

Resumable: a section already on disk with a matching hash is skipped.

Run: python3 scripts/ingest_companies_act.py [--limit N]
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import pathlib
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ACT_ID = "AC_CEN_22_29_00008_201318_1517807327856"
ACT_PAGE = "https://www.indiacode.nic.in/handle/123456789/2114"
CONTENT_EP = "https://www.indiacode.nic.in/SectionPageContent?actid={act}&sectionID={sid}"
OUT = Path(__file__).resolve().parent.parent / "corpus/companies_act"
# TLS verification and the user agent were both disabled/faked here until
# 2026-09-18 (red team RT-14, docs/research/RED_TEAM_RING2_2026_09_18.md):
#
#     CTX.check_hostname = False
#     CTX.verify_mode = ssl.CERT_NONE
#     UA = {"User-Agent": "Mozilla/5.0 ... Chrome/126 Safari/537.36"}
#
# on the script that ingests the Companies Act corpus itself -- the one fetch in
# this repository where a man-in-the-middle would rewrite the statute. It was not
# exploitable on the day it was found (CLAUDE.md records indiacode.nic.in as a dead
# domain; the live host is indiacode.gov.in), but it was live, unconditional, and
# one hostname away from being reachable.
#
# Both now come from checker.robots, which fails closed: no CA bundle means no
# fetch, and the user agent identifies us honestly, as the source policy requires.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checker.robots import USER_AGENT, ssl_context      # noqa: E402

UA = {"User-Agent": USER_AGENT}
CTX = ssl_context()
if CTX is None:
    raise SystemExit("ingest_companies_act: no CA bundle available; refusing to fetch "
                     "the statute over an unverified connection")
PAUSE = 0.4  # be a polite client


def _get(url: str, tries: int = 3) -> str:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=60, context=CTX).read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def enumerate_sections() -> list[str]:
    """Parse section IDs off the act page. One fetch returns all of them."""
    html = _get(ACT_PAGE)
    ids: list[str] = []
    seen = set()
    for sid in re.findall(r"sectionI[dD]=(\d+)", html):
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)  # document order preserved
    return ids


def fetch_section(sid: str) -> dict:
    raw = _get(CONTENT_EP.format(act=ACT_ID, sid=sid))
    data = json.loads(raw)
    content = data.get("content") or ""
    footnote = data.get("footnote") or ""
    return {
        "section_id": sid,
        "act_id": ACT_ID,
        "content": content,
        "footnote": footnote,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_url": CONTENT_EP.format(act=ACT_ID, sid=sid),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    OUT.mkdir(parents=True, exist_ok=True)
    ids = enumerate_sections()
    print(f"enumerated {len(ids)} section ids", flush=True)

    # **An empty enumeration is a failed enumeration, never a corpus of nothing.**
    # The manifest write used to sit here unconditionally, so a page that parsed to zero
    # section ids replaced the record of what this corpus should contain with
    # `count: 0, section_ids: []` and a FRESH `enumerated_at` -- and returned exit 0.
    # The section JSONs survived (the loop below iterates an empty list), so the damage
    # was invisible: 529 files on disk and a manifest saying the Act has no sections.
    #
    # It is reachable. Measured 2026-09-26: `indiacode.gov.in/handle/123456789/2114`
    # answers **200 `text/html`, 6,762 bytes** -- the DSpace Angular shell -- with zero
    # `sectionId=` matches. The payload guard in `checker/robots.py` cannot catch this one,
    # because HTML is exactly what this page is supposed to be; the shape of the result is
    # the only evidence, which is why the check belongs here.
    if not ids:
        print(f"REFUSED: {ACT_PAGE} parsed to 0 section ids. A page that yields no "
              f"sections is a source we could not read, not an Act with no sections -- "
              f"the manifest is left as it was.", flush=True)
        return 1

    (OUT / "_manifest.json").write_text(json.dumps(
        {"act_id": ACT_ID, "section_ids": ids, "count": len(ids),
         "enumerated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2))

    if limit:
        ids = ids[:limit]

    fetched = skipped = failed = 0
    for n, sid in enumerate(ids, 1):
        path = OUT / f"{sid}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            rec = fetch_section(sid)
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
            fetched += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL {sid}: {type(e).__name__}", flush=True)
        if n % 25 == 0:
            print(f"  {n}/{len(ids)} fetched={fetched} skipped={skipped} failed={failed}", flush=True)
        time.sleep(PAUSE)

    print(f"done. fetched={fetched} skipped={skipped} failed={failed}", flush=True)
    # A per-section failure is not a failed run: the loop reports it and the manifest is
    # already correct. Only an unreadable enumeration (above) refuses.
    return 0



def _test() -> int:
    """Stub-only. No network: `enumerate_sections` is replaced, never called for real."""
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("ingest_companies_act")
    import tempfile
    global OUT, enumerate_sections
    real_out, real_enum = OUT, enumerate_sections

    # The defect: a soft-404 parses to zero ids. The manifest must survive it.
    with tempfile.TemporaryDirectory() as d:
        OUT = pathlib.Path(d)
        good = {"act_id": ACT_ID, "section_ids": ["1", "2"], "count": 527,
                "enumerated_at": "2026-08-18T22:15:46+00:00"}
        (OUT / "_manifest.json").write_text(json.dumps(good, indent=2))
        enumerate_sections = lambda: []                                  # noqa: E731
        rc = main()
        after = json.loads((OUT / "_manifest.json").read_text())
        check(rc != 0, f"an empty enumeration exits non-zero (got {rc})")
        check(after == good,
              "the manifest is byte-identical after a zero-section enumeration")
        check(after["count"] == 527 and after["enumerated_at"] == good["enumerated_at"],
              "neither the count nor enumerated_at is touched -- no fresh timestamp on a failure")

    # And the happy path still writes.
    with tempfile.TemporaryDirectory() as d:
        OUT = pathlib.Path(d)
        enumerate_sections = lambda: ["11", "12", "13"]                  # noqa: E731
        global fetch_section
        real_fetch = fetch_section
        fetch_section = lambda sid: {"id": sid, "content": "x"}          # noqa: E731
        try:
            rc = main()
            m = json.loads((OUT / "_manifest.json").read_text())
            check(rc == 0, "a real enumeration exits 0")
            check(m["count"] == 3 and m["section_ids"] == ["11", "12", "13"],
                  "a real enumeration is written to the manifest")
        finally:
            fetch_section = real_fetch

    OUT, enumerate_sections = real_out, real_enum
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0

if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main())
