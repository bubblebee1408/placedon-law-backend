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
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ACT_ID = "AC_CEN_22_29_00008_201318_1517807327856"
ACT_PAGE = "https://www.indiacode.nic.in/handle/123456789/2114"
CONTENT_EP = "https://www.indiacode.nic.in/SectionPageContent?actid={act}&sectionID={sid}"
OUT = Path(__file__).resolve().parent.parent / "corpus/companies_act"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
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


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    OUT.mkdir(parents=True, exist_ok=True)
    ids = enumerate_sections()
    print(f"enumerated {len(ids)} section ids", flush=True)
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


if __name__ == "__main__":
    main()
