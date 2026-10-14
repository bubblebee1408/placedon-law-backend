#!/usr/bin/env python3
"""Build the slim judgment index that `checker/sources/judgment_index.py` searches at runtime.

GENERAL-RESEARCH step 1b (`.claude/loops/DECISION_GENERAL_RESEARCH.md`). This is the OFFLINE
builder: it reads the AWS Open Data judgment metadata (parquet) with `pyarrow` and distils it
into a compact `JudgmentRef` list checked into `corpus/judgments/`. The RUNTIME never runs this
and never imports pyarrow -- it reads the dumped JSON with the standard library.

## The real schema (confirmed 2026-10-14 against `indian-supreme-court-judgments`)

The Supreme Court metadata (`metadata/parquet/year=YYYY/metadata.parquet`, flat) carries:
`title, petitioner, respondent, description, judge, author_judge, citation, case_id, cnr,
decision_date (DD-MM-YYYY), disposal_nature, court, available_languages, raw_html, path,
nc_display, scraped_at, year`. We keep only what discovery needs — title, parties, year,
date, court — plus the PDF key derived from `path`:

    data/pdf/year=YYYY/english/<path>_EN.pdf      (judgments_open.OpenJudgments.fetch layout)

High Court metadata is partitioned by court and bench; it is a follow-up (needs the court/bench
catalogue), so this builder does the flat Supreme Court set first.

## Why `row_to_ref` is the only thing tested here

The mapping from real columns onto `JudgmentRef` is the one piece that breaks if the dataset
schema shifts, so it is a pure function with a fixture test. The network fetch + the dump are
the `--live` path and are not in the gate (no socket in a test).

Run:  PYTHONPATH=. python3 scripts/build_judgment_index.py --test                  # mapping, no network
      PYTHONPATH=. python3 scripts/build_judgment_index.py --live --years 2015-2026 # fetch + write the index
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checker.sources.judgment_index import JudgmentRef, dump_index, IndexError_  # noqa: E402

SC = "aws_sc_judgments"
BUCKET = {"aws_sc_judgments": "indian-supreme-court-judgments"}
REGION = "ap-south-1"
OUT = Path(__file__).resolve().parents[1] / "corpus" / "judgments" / "sc_index.json"


def _iso(decision_date: str) -> str:
    """`DD-MM-YYYY` -> `YYYY-MM-DD`, or "" when the dataset omits/garbles it. Never guessed."""
    parts = (decision_date or "").strip().split("-")
    if len(parts) == 3 and parts[2].isdigit() and len(parts[2]) == 4:
        d, m, y = parts
        if d.isdigit() and m.isdigit():
            return f"{y}-{int(m):02d}-{int(d):02d}"
    return ""


def row_to_ref(row: dict, source_id: str = SC) -> JudgmentRef | None:
    """One parquet row -> a JudgmentRef, or None when it cannot be made fetchable/searchable.

    A row with no `path` has no PDF to open, and a row with no title AND no parties carries no
    discovery signal; both are dropped rather than indexed as a result nobody could use."""
    path = str(row.get("path") or "").strip()
    year_raw = str(row.get("year") or "").strip()
    if not path or not year_raw.isdigit():
        return None
    title = str(row.get("title") or "").strip()
    parties = tuple(p for p in (str(row.get("petitioner") or "").strip(),
                                str(row.get("respondent") or "").strip()) if p)
    if not title and not parties:
        return None
    try:
        return JudgmentRef(
            source_id=source_id,
            s3_key=f"data/pdf/year={int(year_raw)}/english/{path}_EN.pdf",
            title=title,
            parties=parties,
            year=int(year_raw),
            date=_iso(str(row.get("decision_date") or "")),
            court=str(row.get("court") or "").strip(),
        )
    except IndexError_:
        return None


def _years(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def _fetch_parquet(source_id: str, year: int) -> bytes:
    """Anonymous HTTPS GET of one year's metadata parquet. `--live` only."""
    import ssl
    import urllib.request
    url = (f"https://{BUCKET[source_id]}.s3.{REGION}.amazonaws.com/"
           f"metadata/parquet/year={year}/metadata.parquet")
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, timeout=90, context=ctx) as resp:
        if resp.status != 200:
            raise RuntimeError(f"{url} -> HTTP {resp.status}")
        return resp.read()


def build_live(years: list[int]) -> list[JudgmentRef]:
    import io
    import pyarrow.parquet as pq
    refs: list[JudgmentRef] = []
    for y in years:
        try:
            data = _fetch_parquet(SC, y)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  year {y}: SKIP ({type(exc).__name__}: {str(exc)[:80]})")
            continue
        rows = pq.read_table(io.BytesIO(data)).to_pylist()
        kept = [r for r in (row_to_ref(x) for x in rows) if r is not None]
        refs.extend(kept)
        print(f"  year {y}: {len(kept)}/{len(rows)} rows indexed")
    return refs


def _test() -> int:
    ok = fail = 0

    def check(c, label):
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if c else (ok, fail + 1)
        print(f"  [{'PASS' if c else 'FAIL'}] {label}")

    print("build_judgment_index")
    # A fixture row in the CONFIRMED real schema (the Tata/Cyrus SC judgment).
    row = {"title": "TATA CONSULTANCY SERVICES LIMITED versus CYRUS INVESTMENTS PVT. LTD. AND ORS.",
           "petitioner": "TATA CONSULTANCY SERVICES LIMITED",
           "respondent": "CYRUS INVESTMENTS PVT. LTD. AND ORS.",
           "decision_date": "26-03-2021", "court": "Supreme Court of India",
           "path": "2021_12_903_1070", "year": "2021", "raw_html": "<select...", "cnr": "x"}
    ref = row_to_ref(row)
    check(ref is not None, "a real-schema row maps to a JudgmentRef")
    check(ref.s3_key == "data/pdf/year=2021/english/2021_12_903_1070_EN.pdf",
          "the PDF s3_key is derived from path+year in judgments_open's layout")
    check("TATA CONSULTANCY SERVICES LIMITED" in ref.parties and ref.year == 2021,
          "petitioner/respondent become parties and year is an int")
    check(ref.date == "2021-03-26", "decision_date DD-MM-YYYY becomes ISO YYYY-MM-DD")

    check(_iso("26-03-2021") == "2021-03-26" and _iso("") == "" and _iso("garbage") == "",
          "date parse is exact and never guesses")

    check(row_to_ref({"year": "2021", "title": "X", "petitioner": "P"}) is None,
          "a row with no path is dropped (no PDF to open)")
    check(row_to_ref({"path": "p", "year": "2021"}) is None,
          "a row with no title and no parties is dropped (no discovery signal)")
    check(row_to_ref({"path": "p", "year": "notayear", "title": "X"}) is None,
          "a row with a non-numeric year is dropped")

    # The mapping feeds search end to end.
    from checker.sources.judgment_index import search_index
    hits = search_index("Tata Cyrus", [row_to_ref(row)])
    check(bool(hits) and hits[0].year == 2021, "the mapped ref is findable by a generic query")

    check(_years("2019-2021") == [2019, 2020, 2021] and _years("2021") == [2021],
          "the --years spec parses a range and a single year")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--years", default="2015-2026")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.test:
        return _test()
    if a.live:
        refs = build_live(_years(a.years))
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        dump_index(refs, a.out)
        print(f"wrote {len(refs)} judgments -> {a.out}")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
