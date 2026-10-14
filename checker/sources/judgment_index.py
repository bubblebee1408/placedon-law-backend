#!/usr/bin/env python3
"""A slim, in-repo index of eCourts judgments, for DISCOVERY by a generic query.

GENERAL-RESEARCH step 1 (`.claude/loops/DECISION_GENERAL_RESEARCH.md`). The point of this
file is to let a person write generically -- "the Tata Sons vs Cyrus Mistry battle", "a 2026
data-protection case" -- and get back the right judgment to open, WITHOUT carrying a heavy
parquet dependency into the request path.

## Why an index, not a live parquet read per request

The AWS Open Data metadata ships as per-year parquet (High Court: per-court, per-bench),
read only with pandas + pyarrow. Loading that on every "find a case" is the wrong trade.
Instead a one-off OFFLINE builder (lives in `scripts/`, `--live`, pandas) distils the
metadata into a compact list of `JudgmentRef` rows checked into the repo, and the request
path reads THAT with the standard library and spends no dependency. The judgment TEXT is
still fetched and byte-quoted on demand by `checker/sources/judgments_open.OpenJudgments`
(tier LICENSED: a judgment may SUPPORT an answer and can never make one VERIFIED).

## What this file is, and is not

It is the **schema** (`JudgmentRef`) and the **search** (`search_index`). It is deliberately
NOT the builder: mapping the real parquet columns onto `JudgmentRef` is the one thing that
changes if the datasets' schema differs, so it is isolated in the builder and confirmed by a
`--live` probe before anything is committed as real data. This file, and the search it
exposes, is validated here against a fixture and needs no network and no parquet engine.

Discovery is METADATA-only in v1 (parties, title, court, year) -- there is no full-text
index over judgment bodies, and the screen must say so. A metadata miss is an honest empty,
never a guess.

Run: PYTHONPATH=. python3 checker/sources/judgment_index.py --test
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

# The terms-governed open-judgment sources this index may reference. Kept in step with
# `checker/source_picker._LICENSED_IDS` (the judgment subset) and `judgments_open.BUCKETS`.
JUDGMENT_SOURCE_IDS = ("aws_sc_judgments", "aws_hc_judgments")

# Short tokens carry no discriminating signal and would match everything ("re", "vs", "of").
_MIN_TOKEN = 3
_YEAR = re.compile(r"^(1[89]|20)\d{2}$")

# Discovery matches on PARTY NAMES and the case title, not on legal subject: the dataset
# metadata has no topic field, so "insolvency case" cannot match unless a party is named
# "insolvency". These filler and legal-generic words are therefore dropped from a query, so
# "a 2026 case" becomes the year 2026 and "the legal battle between Tata Sons and Cyrus
# Mistry" becomes {tata, sons, cyrus, mistry} -- the distinctive tokens that actually match.
_STOPWORDS = frozenset((
    "a an the of on in for to and or vs versus case cases judgment judgement court order "
    "find show me need want documents document legal battle between about regarding matter "
    "dispute please get give latest recent any some this that with from new old year"
).split())


class IndexError_(ValueError):
    """A row that cannot be an index entry. Never silently dropped."""


@dataclass(frozen=True)
class JudgmentRef:
    """One discoverable judgment. Everything `OpenJudgments.fetch` needs, and nothing a
    quote would need -- the quote is read from the bytes on demand, never from here."""
    source_id: str               # aws_sc_judgments | aws_hc_judgments (terms-governed)
    s3_key: str                  # the PDF key OpenJudgments.fetch uses, verbatim
    title: str                   # case title as the dataset records it
    parties: tuple[str, ...]     # party names, for matching; may be empty
    year: int
    date: str = ""               # ISO date, or "" when the dataset omits it
    court: str = ""              # court code/name; "" for the flat Supreme Court set

    def __post_init__(self) -> None:
        if self.source_id not in JUDGMENT_SOURCE_IDS:
            raise IndexError_(
                f"source_id must be one of {JUDGMENT_SOURCE_IDS} (terms-governed), got "
                f"{self.source_id!r}. An index row for a source with no terms record would "
                f"point at bytes nobody is allowed to fetch.")
        if not self.s3_key:
            raise IndexError_("s3_key is required: an index row that cannot be fetched is "
                              "a result that cannot be opened.")
        if not isinstance(self.year, int) or not (1800 < self.year < 2200):
            raise IndexError_(f"year must be a plausible integer, got {self.year!r}")


def _tokens(text: str) -> list[str]:
    """Lower-cased alphanumeric tokens. Not a stemmer: matching is substring-free and exact
    per token, so 'mistry' matches 'Mistry' but never 'ministry'."""
    return [t for t in re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split() if t]


def search_index(query: str, index, *, limit: int = 20) -> list[JudgmentRef]:
    """Rank index rows against a generic query. Metadata only (parties, title, court, year).

    Rules, each chosen so a miss is honest rather than a guess:
      - A four-digit year in the query is a HARD filter: "a 2026 case" never returns 2019.
      - Every other token of length >= 3 is a soft signal; a row with zero token hits and no
        year-only query is dropped, so an unrelated judgment never surfaces.
      - A query that is only a year returns that year's rows (the year IS the signal).
      - Ties break by more token hits, then by most recent, so the closest match leads.
    """
    toks = _tokens(query)
    year = next((int(t) for t in toks if _YEAR.match(t)), None)
    terms = [t for t in toks
             if not _YEAR.match(t) and len(t) >= _MIN_TOKEN and t not in _STOPWORDS]

    ranked: list[tuple[int, int, JudgmentRef]] = []
    for ref in index:
        if year is not None and ref.year != year:
            continue
        hay = " ".join(_tokens(" ".join((ref.title, *ref.parties, ref.court))))
        hits = sum(1 for t in set(terms) if t in hay.split())
        if terms and hits == 0:
            continue                 # named something; this row matches none of it
        if not terms and year is None:
            continue                 # an empty query matches nothing, never everything
        ranked.append((hits, ref.year, ref))
    ranked.sort(key=lambda r: (-r[0], -r[1]))
    return [r for _, _, r in ranked[:limit]]


def dump_index(refs, path) -> None:
    """Write the index as JSON. Stable key order so a rebuild diffs cleanly."""
    rows = [asdict(r) for r in refs]
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                          encoding="utf-8")


def load_index(path) -> list[JudgmentRef]:
    """Read a dumped index. Each row is validated through `JudgmentRef`, so a corrupt row
    raises at load rather than surfacing as a result that cannot be opened."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for row in rows:
        out.append(JudgmentRef(
            source_id=row["source_id"], s3_key=row["s3_key"], title=row.get("title", ""),
            parties=tuple(row.get("parties", []) or ()), year=int(row["year"]),
            date=row.get("date", ""), court=row.get("court", "")))
    return out


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("judgment_index")
    # A fixture index. NOT a claim these judgments are in the real datasets -- it proves the
    # SEARCH, which is schema-independent. The real rows come from the offline builder later.
    idx = [
        JudgmentRef("aws_sc_judgments", "data/pdf/year=2021/english/tata-mistry_EN.pdf",
                    "Tata Consultancy ... Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd",
                    ("Tata Sons Private Limited", "Cyrus Investments Private Limited"),
                    2021, "2021-03-26", ""),
        JudgmentRef("aws_hc_judgments", "data/pdf/year=2019/english/oppression_EN.pdf",
                    "Some Company v. Registrar (oppression and mismanagement)",
                    ("Some Company Limited", "Registrar of Companies"), 2019, "2019-07-10",
                    "DELHC"),
        JudgmentRef("aws_sc_judgments", "data/pdf/year=2026/english/data-priv_EN.pdf",
                    "ABC Ltd v. Union of India (data protection)",
                    ("ABC Limited", "Union of India"), 2026, "2026-02-01", ""),
    ]

    r = search_index("Tata Sons vs Cyrus Mistry", idx)
    check(bool(r) and r[0].parties[0].startswith("Tata"),
          "a generic party query finds the Tata/Cyrus judgment")
    check("Cyrus" in " ".join(r[0].parties) or "Cyrus" in r[0].title,
          "...the match is on the parties/title, not luck")

    y = search_index("a 2026 data protection case", idx)
    check(len(y) == 1 and y[0].year == 2026,
          "a year in the query is a HARD filter: 2026 returns only 2026")
    check("data" in y[0].title.lower(), "...and the token still has to match")

    check(search_index("insolvency waterfall priority", idx) == [],
          "a query matching nothing returns an honest empty, never the whole index")
    check(search_index("", idx) == [],
          "an empty query matches nothing, not everything")
    check(search_index("2019", idx) and all(j.year == 2019 for j in search_index("2019", idx)),
          "a year-only query returns that year (the year is the signal)")

    # Filler words must not break a natural query.
    ac = search_index("a 2026 case", idx)
    check(len(ac) == 1 and ac[0].year == 2026,
          "'a 2026 case' drops the filler 'case' -> year-only -> returns 2026, not nothing")
    nat = search_index("the legal battle between Tata Sons and Cyrus Mistry", idx)
    check(bool(nat) and "Cyrus" in (nat[0].title + " ".join(nat[0].parties)),
          "a natural sentence still finds the case on its distinctive party tokens")

    # Every result can actually be opened and is terms-governed.
    for j in search_index("Tata", idx):
        check(j.source_id in JUDGMENT_SOURCE_IDS and j.s3_key,
              "every result names a terms-governed source and a fetchable key")

    # Schema refuses a row that could not be fetched or is not terms-governed.
    for bad, why in (
        (dict(source_id="held", s3_key="k", title="t", parties=(), year=2020),
         "a non-judgment source is refused (no terms record to fetch under)"),
        (dict(source_id="aws_sc_judgments", s3_key="", title="t", parties=(), year=2020),
         "a row with no s3_key is refused (a result nobody can open)"),
        (dict(source_id="aws_sc_judgments", s3_key="k", title="t", parties=(), year=12),
         "an implausible year is refused"),
    ):
        try:
            JudgmentRef(**bad); check(False, why)
        except IndexError_:
            check(True, why)

    # Dump/load round-trips through validation.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "idx.json"
        dump_index(idx, p)
        back = load_index(p)
        check(len(back) == len(idx) and back[0].parties == idx[0].parties,
              "the index round-trips through dump_index/load_index")
        check(search_index("Tata Cyrus", back), "...and search works on the loaded index")

    # Stays in step with the connector's source set.
    from checker.sources.judgments_open import BUCKETS
    check(set(JUDGMENT_SOURCE_IDS) == set(BUCKETS),
          "the index's judgment sources match judgments_open.BUCKETS exactly")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
