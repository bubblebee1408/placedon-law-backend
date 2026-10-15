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


# ── the committed default index, for discovery at request time ──────────────────────────
# repo root is parents[2]: checker/sources/judgment_index.py -> sources -> checker -> root.
DEFAULT_INDEX_PATH = Path(__file__).resolve().parents[2] / "corpus" / "judgments" / "sc_index.json"
_DEFAULT: list | None = None


def default_index() -> list:
    """The committed index, loaded once. Empty when none is built yet, so discovery degrades
    to 'no judgments' rather than raising on a deployment that has not shipped the index."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_index(DEFAULT_INDEX_PATH) if DEFAULT_INDEX_PATH.exists() else []
    return _DEFAULT


def indexed_source_ids(index=None) -> frozenset:
    """Which judgment sources actually have rows (the rest are 'permitted but not built yet')."""
    return frozenset(r.source_id for r in (default_index() if index is None else index))


# ── topic (dense) fusion ──────────────────────────────────────────────────────────────────
# `search_index` above matches a query's WORDS against PARTY/TITLE/COURT metadata only -- the
# dataset carries no topic field, so "oppression and mismanagement cases" or "cases on
# related-party transactions" return an honest [] even when judgments on exactly that topic
# sit in the index. `checker/judgment_dense.py` mirrors #99's `checker/voyage_dense.py` for
# judgments: a precomputed Voyage index over judgment BODIES, ranked by meaning. The two
# lists are fused by Reciprocal Rank Fusion, mirroring `checker/retrieve.py:hybrid_search`
# exactly (same k=60 constant): a metadata rank and a cosine are not on the same scale, and
# fusing RANKS rather than scores never invents a comparability that is not there.
#
# Fail-safe by construction, the same shape as hybrid_search: when the judgment dense index
# or a Voyage key is unavailable -- every environment until a --live build supplies both --
# `discover()` degrades EXACTLY to `search_index` alone, so nothing already shipped regresses.
# And a dense hit is never served unless its s3_key is ALSO a real row of THIS index -- a
# dense hit naming a judgment the index does not hold is dropped, mirroring
# `checker/retrieve.py`'s `_row_for_number` guard against fabricating a provision.
_RRF_K = 60
_DENSE_POOL = 20


def _rank_map(keys: list[str]) -> dict[str, int]:
    """Best-first s3_keys -> {s3_key: 1-based rank}, first occurrence wins."""
    ranks: dict[str, int] = {}
    for i, k in enumerate(keys):
        ranks.setdefault(k, i + 1)
    return ranks


def _dense_topic_hits(query: str, *, top_k: int) -> list[tuple[str, str, float]]:
    """(s3_key, title, cosine) the dense judgment index ranks for this query, or [] when it
    cannot run. Never raises: a caller already has the metadata list and must fall back to
    it exactly -- the same discipline as `checker/retrieve.py`'s `hybrid_search`."""
    from checker import judgment_dense
    ok, _why = judgment_dense.available()
    if not ok:
        return []
    try:
        return judgment_dense.search(query, top_k=top_k)
    except judgment_dense.JudgmentDenseUnavailable:
        return []


def discover(query: str, *, limit: int = 10, index=None) -> list:
    """Discovery hits for a generic query: metadata (party/title) UNION topic (dense), fused.

    Reads the LOCAL metadata index for the party/title half (no network) and a LOCAL
    precomputed Voyage index for the topic half (no network -- only the query, if any, is
    embedded live). The verbatim quote is still fetched on OPEN by
    `judgments_open.OpenJudgments`. Support, not VERIFIED.

    Fail-safe: when the dense index or a Voyage key is unavailable -- true until a --live
    build supplies both -- this is IDENTICAL to metadata-only discovery, never worse.
    """
    idx = default_index() if index is None else index
    pool = max(limit, _DENSE_POOL)
    metadata_hits = search_index(query, idx, limit=pool)
    dense_hits = _dense_topic_hits(query, top_k=_DENSE_POOL)
    if not dense_hits:
        return metadata_hits[:limit]

    by_key = {r.s3_key: r for r in idx}
    meta_by_key = {r.s3_key: r for r in metadata_hits}
    rank_maps = (_rank_map([r.s3_key for r in metadata_hits]),
                 _rank_map([key for key, _title, _cosine in dense_hits]))
    fused: dict[str, float] = {}
    for ranks in rank_maps:
        for key, rank in ranks.items():
            fused[key] = fused.get(key, 0.0) + 1.0 / (_RRF_K + rank)
    order = sorted(fused, key=lambda k: -fused[k])

    out: list[JudgmentRef] = []
    for key in order:
        ref = meta_by_key.get(key) or by_key.get(key)
        if ref is not None:            # a dense hit naming a row not in THIS index is dropped
            out.append(ref)
        if len(out) >= limit:
            break
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

    d = discover("Tata Cyrus", index=idx)
    check(bool(d) and "Cyrus" in (d[0].title + " ".join(d[0].parties)),
          "discover() runs the search over an injected index")
    check(indexed_source_ids(idx) == {"aws_sc_judgments", "aws_hc_judgments"},
          "indexed_source_ids reports exactly the sources present in an index")

    # ── topic (dense) fusion: fail-safe identity first ──────────────────────────────
    # No VOYAGE_API_KEY and no built judgment dense index exist in this gate (run_tests.sh
    # unsets every provider key), so judgment_dense.available() is False here by
    # construction -- discover() must degrade to EXACTLY metadata-only search_index.
    from checker import judgment_dense
    for q in ("Tata Sons vs Cyrus Mistry", "a 2026 data protection case",
              "insolvency waterfall priority", "2019", ""):
        check(discover(q, index=idx) == search_index(q, idx, limit=10),
              f"with dense unavailable, discover({q!r}) is IDENTICAL to metadata search alone")

    # ── topic (dense) fusion: a topic query metadata cannot reach ───────────────────
    # "cases on related-party transactions" names no party and matches no fixture
    # title/court -- metadata search is an honest []. A dense index built from judgment
    # BODIES can carry that topic even though no word of it is in the title.
    TOPIC_Q = "cases on related-party transactions"
    check(search_index(TOPIC_Q, idx) == [],
          "the topic query matches nothing in metadata -- an honest empty, as today")

    from unittest import mock

    def fake_available(path=judgment_dense.INDEX_PATH):
        return True, "fixture"

    def fake_dense_hit(q, top_k=5, **kw):
        # Stubbed as though the Tata/Cyrus judgment's BODY discusses related-party
        # governance -- the index's own vectors are never read by this fixture.
        return [(idx[0].s3_key, idx[0].title, 0.91)]

    with mock.patch.object(judgment_dense, "available", side_effect=fake_available), \
         mock.patch.object(judgment_dense, "search", side_effect=fake_dense_hit):
        hits = discover(TOPIC_Q, index=idx)
        check(hits == [idx[0]],
              f"discover() reaches the Tata/Cyrus judgment by TOPIC where metadata alone "
              f"reaches nothing ({hits})")
        check(hits[0].s3_key in {r.s3_key for r in idx},
              "...and the row served is the real, committed JudgmentRef -- not fabricated")

    # ── invariant: a dense hit naming a judgment THIS index does not hold is dropped ─
    def fake_dense_bogus(q, top_k=5, **kw):
        return [("data/pdf/year=1999/english/not-a-real-judgment_EN.pdf", "Invented", 0.99)]

    with mock.patch.object(judgment_dense, "available", side_effect=fake_available), \
         mock.patch.object(judgment_dense, "search", side_effect=fake_dense_bogus):
        hits = discover(TOPIC_Q, index=idx)
        check(hits == [],
              f"a dense hit naming a judgment not in the real index is silently dropped, "
              f"never served as though it existed ({hits})")

    # ── additive: a metadata hit already found survives fusion, dense disagreement aside ─
    def fake_dense_disjoint(q, top_k=5, **kw):
        return [(idx[1].s3_key, idx[1].title, 0.4)]   # unrelated to this query's metadata hit

    with mock.patch.object(judgment_dense, "available", side_effect=fake_available), \
         mock.patch.object(judgment_dense, "search", side_effect=fake_dense_disjoint):
        hits = discover("Tata Sons vs Cyrus Mistry", index=idx)
        keys = [h.s3_key for h in hits]
        check(idx[0].s3_key in keys,
              f"the metadata hit for 'Tata Sons vs Cyrus Mistry' survives fusion even though "
              f"dense (stubbed) ranks something unrelated ({keys})")

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
