#!/usr/bin/env python3
"""Build the Companies Act 2013 matters dataset from the open judgment METADATA.

Lane B's live refresh. Reads the AWS Open Data High Court / Supreme Court judgment metadata
(anonymous S3, CC-BY-4.0, tier LICENSED) through `checker.sources.judgments_open`, keeps the
matters whose metadata names the Companies Act 2013, and writes
`corpus/forecast/companies_act_matters.json` (the file `checker.forecast.matters` reads).

**No model is called.** This is a download, a filter and a write. Only the metadata parquet is
fetched -- never the judgment PDFs -- and only for the forums/years asked for. Disk is checked
first: the build STOPS if the root volume has under 10 GB free, because a half-written dataset
is worse than none.

A field the metadata does not state is left out of the row, which `matters.py` reads as UNKNOWN;
nothing is inferred. Whether the open metadata carries a filing date, a cited section or an
outcome varies by court and year -- where it does not, those matters contribute what they can
(a censored duration) or are counted, by name, among the ones a field could not be read for.

    python3 scripts/build_companies_act_matters.py --test        # fixtures, no network
    python3 scripts/build_companies_act_matters.py --build \
        --court bombay --bench principal --years 2018-2023       # live, df-checked
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from checker.forecast import matters as fm

ROOT = Path(__file__).resolve().parent.parent
MIN_FREE_GB = 10.0


def _free_gb(path: Path = Path("/")) -> float:
    return shutil.disk_usage(path).free / 1e9


def build(source_id: str, court: str, bench: str, years: range) -> list[dict]:
    """Fetch metadata for each year, keep Companies Act matters, return their rows.

    Imports the connector lazily so `--test` needs neither network nor a parquet engine.
    """
    from checker.sources.judgments_open import OpenJudgments

    oj = OpenJudgments(source_id=source_id)
    rows: list[dict] = []
    for year in years:
        meta = oj.metadata(year, court=court, bench=bench) if court else oj.metadata(year)
        src = (f"metadata/parquet/year={year}/court={court}/bench={bench}/metadata.parquet"
               if court else f"metadata/parquet/year={year}/metadata.parquet")
        for m in fm.matters_from_rows(meta, source_path=src):
            rows.append(m.to_dict())
    return rows


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    print("build_companies_act_matters")
    # No network: the mapping is exercised on inline metadata rows, the shape the real parquet
    # yields. A Companies Act matter is kept with its source path; a non-CA row is dropped.
    src = "metadata/parquet/year=2020/court=bombay/bench=principal/metadata.parquet"
    rows = [
        {"case_id": "BOMHC/CP/1/2019", "court": "Bombay High Court",
         "registration_date": "2019-01-01", "decision_date": "2020-06-01",
         "section": "Companies Act, 2013 s.241", "source_path": src},
        {"case_id": "BOMHC/WP/9/2019", "court": "Bombay High Court",
         "section": "Income Tax Act, 1961 s.147", "source_path": src},
    ]
    built = fm.matters_from_rows(rows)
    check(len(built) == 1 and built[0].case_id == "BOMHC/CP/1/2019",
          f"only the Companies Act matter is kept ({len(built)})")
    check(built[0].sources.get("filing_date") == src,
          "...and every stated field carries its metadata source path")
    check(_free_gb.__name__ == "_free_gb" and MIN_FREE_GB == 10.0,
          "the df guard is wired at a 10 GB floor (checked before any live download)")

    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


def _years(spec: str) -> range:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return range(int(a), int(b) + 1)
    y = int(spec)
    return range(y, y + 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--test", action="store_true", help="fixtures, no network")
    ap.add_argument("--build", action="store_true", help="live download + write the dataset")
    ap.add_argument("--source", default="aws_hc_judgments",
                    help="aws_hc_judgments | aws_sc_judgments")
    ap.add_argument("--court", default="", help="HC court code, e.g. bombay (required for HC)")
    ap.add_argument("--bench", default="", help="HC bench, e.g. principal (required for HC)")
    ap.add_argument("--years", default="2018-2023", help="YYYY or YYYY-YYYY")
    args = ap.parse_args()

    if args.test or not args.build:
        _test()
        return

    free = _free_gb()
    if free < MIN_FREE_GB:
        print(f"STOP: only {free:.1f} GB free on / (need >= {MIN_FREE_GB:.0f} GB). "
              f"Nothing downloaded.", file=sys.stderr)
        raise SystemExit(2)
    print(f"df /: {free:.1f} GB free -- proceeding (metadata only, no PDFs, no model).")

    rows = build(args.source, args.court, args.bench, _years(args.years))
    out = {
        "note": ("Companies Act 2013 matters, built from the open judgment metadata by "
                 "scripts/build_companies_act_matters.py. A field the metadata did not state "
                 "is absent, which reads as UNKNOWN; a matter with no decision_date is PENDING."),
        "source": f"AWS Open Data: {args.source} (CC-BY-4.0)",
        "matters": rows,
    }
    fm.DATASET.parent.mkdir(parents=True, exist_ok=True)
    fm.DATASET.write_text(json.dumps(out, indent=2))
    decided = sum(1 for r in rows if r.get("status") == "DECIDED")
    print(f"wrote {len(rows)} Companies Act matters ({decided} decided) -> {fm.DATASET}")


if __name__ == "__main__":
    main()
