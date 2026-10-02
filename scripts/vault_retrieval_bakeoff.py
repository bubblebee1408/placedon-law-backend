#!/usr/bin/env python3
"""Does giving a chunk its context actually help? Measured, before and after.

V1 asks for contextual BM25 and for the retrieval failure to be measured before and after.
This is that measurement. It is a SCRIPT and not a docstring claim, because a retrieval
number written in prose is a number nobody re-runs.

## What is measured

**Failure rate**: the share of queries whose target document is NOT in the top k. Not
"accuracy" -- there is no human-labelled relevance here, only a synthetic corpus where the
right answer is known by construction, which is a weaker thing and is named as such.

Each rate carries a **Wilson 95% interval**, because 20 queries is a small sample and a
bare percentage from one invites a decision the sample cannot support.

## The corpus is synthetic and says so

Documents are generated from templates with known clauses, and every query targets a
document by a fact only that document holds. That makes the ceiling 100% by construction
and the comparison still meaningful: both indexes face the same queries, and the only
difference is whether the chunk was told where it came from.

It does NOT tell you how retrieval behaves on a real vault. Nothing here claims it does.

Run: PYTHONPATH=. python3 scripts/vault_retrieval_bakeoff.py
"""
from __future__ import annotations

import sys

TOP_K = 5

# (name, class, clause heading, the distinguishing sentence)
_TEMPLATES = (
    ("{co} NDA", "nda", "2. Term",
     "The confidentiality obligations continue for {n} years from the Effective Date."),
    ("{co} Services Agreement", "services_agreement", "7. Indemnity",
     "The supplier shall indemnify the customer up to INR {n},00,000."),
    ("{co} Office Lease", "lease", "4. Rent",
     "Rent of INR {n},000 is payable monthly in advance."),
    ("{co} Loan Agreement", "loan_agreement", "3. Interest",
     "Interest accrues at {n} per cent per annum."),
    ("{co} Employment Agreement", "employment_agreement", "5. Notice",
     "Either party may terminate on {n} days written notice."),
)

_COMPANIES = ("Petrichor", "Lodestar", "Meridian", "Alcove", "Kestrel", "Ravine",
              "Juniper", "Thorn", "Vellum", "Quarry")


def corpus() -> tuple[list, list]:
    """(chunk rows, queries). Synthetic, and the right answer is known by construction."""
    rows, queries = [], []
    doc_n = 0
    for co in _COMPANIES:
        for name_t, cls, heading, body_t in _TEMPLATES:
            doc_n += 1
            did = f"d{doc_n:03d}"
            name = name_t.format(co=co)
            body = body_t.format(n=doc_n)
            text = (f"{heading}\n\n{body}\n\n"
                    f"This agreement is governed by the laws of India.")
            rows.append({"document_id": did, "ordinal": 0, "tenant_id": "t1",
                         "name": name, "doc_class": cls, "text": text})
            # The query a lawyer would type: the counterparty and the subject, which is
            # exactly what a plain chunk does not contain.
            queries.append((f"{co} {heading.split('. ', 1)[-1].lower()}", did))
    return rows, queries


def failure_rate(rows, queries, *, contextual: bool, k: int = TOP_K) -> tuple[int, int]:
    """(misses, total). A miss is a query whose target is not in the top k."""
    from checker.vault_search import Index
    index = Index.build(rows, tenant_id="t1", contextual=contextual)
    misses = 0
    for query, target in queries:
        hits = index.search(query, limit=k).hits
        if target not in {h.document_id for h in hits}:
            misses += 1
    return misses, len(queries)


def report() -> str:
    from checker.review_grid import wilson
    rows, queries = corpus()
    out = ["vault retrieval: plain chunks vs chunks told where they came from", "",
           f"  corpus   {len({r['document_id'] for r in rows})} synthetic documents",
           f"  queries  {len(queries)}, each naming a counterparty and a subject",
           f"  top-k    {TOP_K}", ""]
    results = {}
    for label, contextual in (("plain", False), ("contextual", True)):
        misses, total = failure_rate(rows, queries, contextual=contextual)
        lo, hi = wilson(misses, total)
        results[label] = (misses, total, lo, hi)
        out.append(f"  {label:<12} failure {misses}/{total} = {misses / total:.0%}  "
                   f"(95% CI {lo:.0%}-{hi:.0%})")
    pm, pt, _plo, _phi = results["plain"]
    cm, ct, _clo, _chi = results["contextual"]
    out += ["", f"  contextual chunks change the failure rate by "
                f"{(cm / ct) - (pm / pt):+.0%} on this corpus."]
    if results["plain"][2] <= results["contextual"][3] and \
            results["contextual"][2] <= results["plain"][3]:
        out.append("  The two intervals OVERLAP: this corpus does not separate them. "
                   "That is a\n  result, not a disappointment -- and not a reason to "
                   "report the point estimate\n  as though it did.")
    else:
        out.append("  The intervals do not overlap.")
    out += ["", "  This is a SYNTHETIC corpus: the right answer is known by construction, "
                "so the\n  ceiling is 100% and nothing here says how retrieval behaves on "
                "a real vault."]
    return "\n".join(out)


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

    print("vault_retrieval_bakeoff")
    rows, queries = corpus()
    check(len({r["document_id"] for r in rows}) == 50,
          f"the corpus is 50 synthetic documents ({len({r['document_id'] for r in rows})})")
    check(len(queries) == 50 and len({q for q, _ in queries}) == 50,
          f"...and 50 distinct queries ({len({q for q, _ in queries})})")
    check(all(t in {r['document_id'] for r in rows} for _q, t in queries),
          "every query targets a document that exists")

    pm, pt = failure_rate(rows, queries, contextual=False)
    cm, ct = failure_rate(rows, queries, contextual=True)
    check(pt == ct == len(queries), "both indexes face the SAME queries")
    check(cm <= pm,
          f"contextual chunks do not retrieve WORSE on this corpus "
          f"(plain {pm}/{pt}, contextual {cm}/{ct})")
    check(pm > 0,
          f"...and the plain index really does miss some, so the comparison is measuring "
          f"something ({pm} misses)")

    text = report()
    check("SYNTHETIC" in text and "known by construction" in text,
          "the report says the corpus is synthetic and why that caps what it shows")
    check("accuracy" not in text.lower(),
          "...and never says 'accuracy': there are no human relevance labels here")
    check("95% CI" in text, "every rate carries a Wilson interval")
    check(("OVERLAP" in text) or ("do not overlap" in text),
          "...and the report states whether the intervals separate the two, rather than "
          "leaving a reader to compare point estimates")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(report())
