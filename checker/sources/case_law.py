#!/usr/bin/env python3
"""Case-law search over the open eCourts judgment metadata. LICENSED, and kept apart.

STEP 3a, part 3. `sources.search(query, case_law=...)` returns judgments from the AWS Open
Data buckets (via `judgments_open`) as its `case_law` source. Every result carries tier
LICENSED and the CC-BY attribution, and a quote is admitted only when it byte-matches the
stored PDF text.

## Why a SEPARATE index, not the statutory ranker

`checker/text_search.py` indexes the HELD Companies Act corpus. Case law is tier LICENSED,
not HELD, and the whole rings/tiers architecture exists to stop the two being confused:
`checker/sources/__init__.py` says "only HELD can make an answer VERIFIED". Folding judgment
metadata into the statutory index would let a judgment surface where a reader expects the
statute, and a mixed result set could be summarised as though a case were law we verified.
So case law is its own index, its results are tagged LICENSED at the source, and the two are
only ever combined by a caller that keeps the tier on every row.

The tokeniser is reused from `text_search` so the two rank words the same way; the ranking
here is a small, honest idf-weighted term overlap over the indexed rows, not a claim of parity
with the statutory ranker.

## What is indexed, and the honest limit on it

The rows come from `judgments_open` metadata. This environment has no parquet engine, so the
REAL parquet schema could not be read, and indexing columns I have not seen would be the guess
this repository refuses. The index therefore tokenises whatever searchable fields a row
actually carries (`SEARCHABLE`), defaulting to the ones VERIFIED from the JSON metadata — the
neutral citation and the year — and will pick up richer columns (case title, parties, headnote)
as soon as a real parquet read supplies them. The rows are INJECTED, so the gate indexes
fixtures and opens no socket.

Run: PYTHONPATH=. python3 checker/sources/case_law.py --test
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from checker import text_search as ts
from checker.sources import terms
from checker.sources.evidence import Evidence
from checker.sources.tiers import LICENSED

# The row fields worth indexing, most-specific first. Only `nc_display` and `citation_year`
# were verified present (from the JSON metadata); the rest are indexed when a richer reader
# (a real parquet read) supplies them, and ignored when absent -- never invented.
SEARCHABLE = ("case_name", "title", "headnote", "catchwords", "text", "nc_display")


@dataclass(frozen=True)
class CaseLawHit:
    """One ranked judgment, before any quote is made. Carries its tier and how to fetch it."""
    source_id: str
    path: str
    year: int
    citation: str
    score: float
    fields: dict
    tier: str = LICENSED

    @property
    def attribution(self) -> str:
        return terms.attribution_for(self.source_id)

    def to_dict(self) -> dict:
        return {"source_id": self.source_id, "path": self.path, "year": self.year,
                "citation": self.citation, "score": round(self.score, 4),
                "tier": self.tier, "attribution": self.attribution}


def _row_text(row: dict) -> str:
    """The searchable text of one metadata row, from the fields it actually has."""
    parts = [str(row.get(f)) for f in SEARCHABLE if row.get(f)]
    return " ".join(parts)


def _row_year(row: dict) -> int:
    for key in ("citation_year", "year", "decision_year"):
        v = row.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return 0


def _row_citation(row: dict) -> str:
    for key in ("nc_display", "neutral_citation", "citation"):
        if row.get(key):
            return str(row[key])
    return str(row.get("path") or "")


class CaseLawIndex:
    """An in-memory index of judgment metadata rows, searchable by content terms.

    Rows are injected -- from `judgments_open.metadata()` at deploy time (which needs a parquet
    engine) or from fixtures in a test. Building the index tokenises each row once; idf is
    computed over the indexed rows so a term common to every judgment counts for little.
    """

    def __init__(self, source_id: str, rows: list[dict]) -> None:
        if source_id not in ("aws_sc_judgments", "aws_hc_judgments"):
            raise ValueError(f"{source_id!r} is not an open-judgments source")
        self.source_id = source_id
        self._docs: list[dict] = []
        df: dict[str, int] = {}
        for row in rows:
            if not row.get("path"):
                continue  # a row we cannot fetch later is not worth returning
            terms_in = ts._content(ts._tokens(ts._norm(_row_text(row))))
            tf: dict[str, int] = {}
            for t in terms_in:
                tf[t] = tf.get(t, 0) + 1
            for t in set(terms_in):
                df[t] = df.get(t, 0) + 1
            self._docs.append({"row": row, "tf": tf,
                               "path": str(row["path"]),
                               "year": _row_year(row),
                               "citation": _row_citation(row)})
        n = max(1, len(self._docs))
        # Smoothed idf, so a term in every judgment (e.g. "court") scores ~0 rather than
        # dominating, and an unseen term is simply absent.
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}

    def __len__(self) -> int:
        return len(self._docs)

    def search(self, query: str, *, limit: int = 5) -> list[CaseLawHit]:
        """The judgments whose metadata best matches the query, ranked. Never raises.

        An empty query, or one with no content terms, returns [] -- which here honestly means
        "nothing matched", not "there is no case law": the caller asked and the index answered.
        """
        q_terms = ts._content(ts._tokens(ts._norm(query or "")))
        if not q_terms:
            return []
        hits: list[CaseLawHit] = []
        for d in self._docs:
            score = 0.0
            for t in set(q_terms):
                if t in d["tf"]:
                    # tf capped by a log so one field repeating a word cannot swamp relevance.
                    score += self._idf.get(t, 0.0) * (1.0 + math.log(d["tf"][t]))
            if score > 0.0:
                hits.append(CaseLawHit(
                    source_id=self.source_id, path=d["path"], year=d["year"],
                    citation=d["citation"], score=score, fields=d["row"]))
        hits.sort(key=lambda h: (-h.score, h.year, h.path))
        return hits[:limit]


def quote_from_hit(connector, hit: CaseLawHit, span: str, *, document_text: str) -> Evidence:
    """Turn a hit into a citable Evidence -- only if `span` byte-matches the stored PDF text.

    The two steps the tier demands, in order: fetch the actual PDF (asserting its %PDF bytes,
    storing its sha256), then admit the quote only if it is present verbatim in the text
    extracted from THAT document. `judgments_open.quote` does the byte-match and refuses
    otherwise; this is the search-to-citation path.
    """
    stored = connector.fetch(hit.path, year=hit.year)
    return connector.quote(stored, span, document_text=document_text)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("case_law")

    from checker.sources import search as sources_search
    from checker.sources.judgments_open import OpenJudgments, Response
    from checker.sources.tiers import can_verify

    ROWS = [
        {"path": "1950_1_15_25", "citation_year": 1950, "nc_display": "1950INSC1",
         "case_name": "A company must hold an annual general meeting every year"},
        {"path": "1950_1_25_29", "citation_year": 1950, "nc_display": "1950INSC2",
         "case_name": "On the winding up of a company and the powers of the liquidator"},
        {"path": "1951_2_3_9", "citation_year": 1951, "nc_display": "1951INSC7",
         "case_name": "The annual return and its filing under the Companies Act"},
        {"path": "", "citation_year": 1952, "nc_display": "1952INSC9",
         "case_name": "an unfetchable row with no path"},
    ]
    idx = CaseLawIndex("aws_sc_judgments", ROWS)

    # ── indexed, and the unfetchable row is dropped ─────────────────────────
    check(len(idx) == 3, f"rows with a path are indexed; the one without is dropped "
                         f"({len(idx)})")

    # ── search ranks by content, and carries tier + attribution ─────────────
    hits = idx.search("annual general meeting")
    check(hits and hits[0].path == "1950_1_15_25",
          f"the most on-topic judgment ranks first ({hits[0].path if hits else None})")
    check(all(h.tier == LICENSED for h in hits),
          "every hit is tier LICENSED")
    check(not can_verify(LICENSED),
          "...which can never make an answer VERIFIED")
    check(hits[0].attribution == terms.attribution_for("aws_sc_judgments")
          and hits[0].attribution,
          "...and carries the CC-BY attribution, the terms' own words")
    check(hits[0].citation == "1950INSC1",
          f"...and the neutral citation ({hits[0].citation})")

    # a term common to several judgments ("company") does not dominate a specific one
    annual = idx.search("annual return filing")
    check(annual and annual[0].path == "1951_2_3_9",
          f"a specific query finds the specific judgment ({annual[0].path if annual else None})")

    # ── honest empties: 'nothing matched', never 'no case law exists' ───────
    check(idx.search("maritime salvage admiralty jurisdiction") == [],
          "a query matching nothing returns [], which means 'nothing matched' here")
    check(idx.search("") == [] and idx.search("the of and") == [],
          "an empty or all-stopword query returns [] rather than everything")

    # ── sources.search dispatches to the case_law index ─────────────────────
    via = sources_search("annual general meeting", case_law=idx)
    check(via and via[0].path == hits[0].path,
          "sources.search(case_law=...) returns the same ranked case law")
    check(sources_search("anything", case_law=None) == [],
          "sources.search with no case_law index returns [] -- no source, no result")

    # ── the quote path: byte-match against the fetched PDF, or refuse ────────
    PDF = b"%PDF-1.7\nHELD: a company must hold an annual general meeting every year.\n%%EOF"
    TEXT = "HELD: a company must hold an annual general meeting every year."

    def transport(url: str) -> Response:
        if url.endswith("1950_1_15_25_EN.pdf"):
            return Response(200, "application/pdf", PDF)
        return Response(404, "application/xml", b"<Error><Code>NoSuchKey</Code></Error>")

    conn = OpenJudgments("aws_sc_judgments", transport=transport,
                         metadata_reader=lambda b: ROWS)
    ev = quote_from_hit(conn, hits[0], "annual general meeting", document_text=TEXT)
    check(ev.tier == LICENSED and ev.quoted_span == "annual general meeting",
          "a byte-matched span becomes a LICENSED Evidence")
    check(ev.attribution == terms.attribution_for("aws_sc_judgments"),
          "...carrying the required attribution")
    try:
        quote_from_hit(conn, hits[0], "a sentence not in the judgment", document_text=TEXT)
        check(False, "a span absent from the stored text must be refused")
    except Exception as e:  # noqa: BLE001
        check("not present byte-for-byte" in str(e),
              "a quote that is not in the stored PDF text is refused, not approximated")

    # ── the index reuses the statutory tokeniser, and stays SEPARATE from it ─
    import inspect
    src = inspect.getsource(CaseLawIndex)
    check("ts._tokens" in src and "ts._content" in src,
          "the case-law index reuses text_search's tokeniser, so both rank words alike")
    check("_records" not in src,
          "...but never reads the statutory corpus: case law is not folded into the HELD "
          "index, which is what keeps the tiers from being confused")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
