#!/usr/bin/env python3
"""Two thousand documents through the real ingest path, timed.

V1 asks for a load test on 2,000 synthetic documents. This runs the ACTUAL pipeline --
file store, archive guard, classifier, chunker, clause tagger, store writes -- and then
builds the index and queries it, because the question is not "does the code work on one
file" but "what happens at the size a firm actually has".

## What it measures, and what it does not

Measured: wall-clock for ingest, index build and query, plus p50/p95 per query. Not
measured: anything about a REAL vault. Every document here is generated from five
templates, so the text is short, clean and has a text layer -- which is the easy case on
all three axes. A real vault is scans, 200-page agreements and inconsistent formatting,
and this says nothing about those.

## The gate runs a smaller N, and says so

2,000 documents takes long enough that putting it in `scripts/run_tests.sh` would add a
minute to every commit. `--test` runs `GATE_DOCS` and prints that it did; the full figure
is produced by running the script, and the numbers below the fold are from a real run.

Run: PYTHONPATH=. python3 scripts/vault_load_test.py
     PYTHONPATH=. python3 scripts/vault_load_test.py --docs 5000
"""
from __future__ import annotations

import sys
import time
import uuid

DOCS = 2_000
GATE_DOCS = 200
QUERIES = (
    "governing law India", "indemnity cap", "termination for convenience",
    "confidential information", "notice period ninety days", "arbitration Mumbai",
    "rent payable monthly", "interest per annum", "non-compete", "renewal term",
)

_BODIES = (
    ("{co} NDA", "2. Term\n\nThis Agreement shall continue for {n} years. Confidential "
                 "Information means anything disclosed.\n\n9. Governing law\n\nGoverned "
                 "by the laws of India. Either party may terminate on ninety days "
                 "written notice."),
    ("{co} Services Agreement", "7. Indemnity\n\nThe supplier shall indemnify the "
                                "customer. In no event shall liability exceed INR "
                                "{n},00,000.\n\n12. Audit\n\nThe customer may audit the "
                                "supplier's records."),
    ("{co} Lease Deed", "4. Rent\n\nRent of INR {n},000 is payable monthly in advance by "
                        "the Lessee to the Lessor.\n\n8. Insurance\n\nThe Lessee shall "
                        "maintain insurance over the demised premises."),
    ("{co} Loan Agreement", "3. Interest\n\nInterest accrues at {n} per cent per annum. "
                            "The Borrower shall repay on demand.\n\n6. Disputes\n\n"
                            "Disputes are referred to arbitration in Mumbai."),
    ("{co} Employment Agreement", "5. Notice\n\nEither party may terminate on {n} days "
                                  "written notice.\n\n9. Non-compete\n\nThe employee "
                                  "shall not directly or indirectly compete for one "
                                  "year."),
)


def synthetic(n: int):
    """n DISTINCT documents, short and clean and with a text layer -- the easy case.

    The counterparty is in the BODY and not only the name, because the vault keys bytes by
    their sha256. The first version varied only the name and a number with a period of 90,
    so 2,000 documents were 90 distinct files and 1,910 correct dedupe refusals -- the
    load test measuring the deduplicator instead of the pipeline, which is exactly the
    kind of thing a load test exists to surface.
    """
    for i in range(n):
        name_t, body_t = _BODIES[i % len(_BODIES)]
        co = f"Company{i:05d}"
        yield (name_t.format(co=co),
               f"Agreement reference {co}-{i:06d}.\n\n"
               + body_t.format(co=co, n=(i % 90) + 1))


def run(n: int = DOCS) -> dict:
    import tempfile
    from pathlib import Path

    from agents.vault_ingest import ingest
    from checker.vault_search import Index
    from gateway.filestore import LocalFileStore
    from gateway.store import MemoryBackend

    with tempfile.TemporaryDirectory() as tmp:
        files, store = LocalFileStore(Path(tmp)), MemoryBackend()
        plain = lambda data, name: data.decode("utf-8", "replace")   # noqa: E731

        t0 = time.monotonic()
        ingested = failed = duplicate = 0
        for name, body in synthetic(n):
            sha = files.put(body.encode())
            try:
                out = ingest({"document_id": str(uuid.uuid4()), "sha256": sha,
                              "name": name}, files=files, store=store, extract=plain)
                ingested += 1 if out.state == "INGESTED" else 0
                failed += 0 if out.state == "INGESTED" else 1
            except Exception as e:                               # noqa: BLE001
                # A duplicate is NOT a failure: it is the deduplicator working. Counted
                # apart, because folding the two together is how a corpus that is 90
                # distinct files reports as a pipeline that mostly breaks.
                if "already in this tenant" in str(e):
                    duplicate += 1
                else:
                    failed += 1
        t_ingest = time.monotonic() - t0

        t0 = time.monotonic()
        chunks = store.read_vault_chunks()
        index = Index.build(chunks, tenant_id="t1",
                            unsearchable=store.vault_counts()["unsearchable"])
        t_index = time.monotonic() - t0

        times, hits = [], 0
        for q in QUERIES:
            t0 = time.monotonic()
            res = index.search(q, limit=10)
            times.append(time.monotonic() - t0)
            hits += len(res.hits)
        times.sort()
        return {"documents": n, "ingested": ingested, "failed": failed,
                "duplicate": duplicate,
                "chunks": len(chunks), "ingest_seconds": round(t_ingest, 2),
                "index_seconds": round(t_index, 2),
                "per_document_ms": round(t_ingest / max(1, n) * 1000, 2),
                "query_p50_ms": round(times[len(times) // 2] * 1000, 2),
                "query_p95_ms": round(times[min(len(times) - 1,
                                                int(len(times) * 0.95))] * 1000, 2),
                "total_hits": hits, "counts": store.vault_counts()}


def report(r: dict) -> str:
    return "\n".join([
        f"vault load test: {r['documents']} synthetic documents", "",
        f"  ingested        {r['ingested']}  (failed {r['failed']}, "
        f"duplicate {r['duplicate']})",
        f"  chunks          {r['chunks']}",
        f"  ingest          {r['ingest_seconds']}s  "
        f"({r['per_document_ms']} ms/document)",
        f"  index build     {r['index_seconds']}s",
        f"  query p50/p95   {r['query_p50_ms']} / {r['query_p95_ms']} ms  "
        f"over {len(QUERIES)} queries",
        f"  hits            {r['total_hits']}", "",
        "  Every document here is generated from five templates: short, clean, and with",
        "  a text layer. That is the EASY case on all three axes. A real vault is scans,",
        "  200-page agreements and inconsistent formatting, and nothing here measures",
        "  those.",
    ])


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

    print(f"vault_load_test (gate runs {GATE_DOCS}, not {DOCS} -- see the docstring)")
    r = run(GATE_DOCS)
    check(r["ingested"] == GATE_DOCS and r["failed"] == 0,
          f"every one of {GATE_DOCS} documents ingests ({r['ingested']} ok, "
          f"{r['failed']} failed)")
    check(r["duplicate"] == 0,
          f"**and none is a DUPLICATE**: the corpus is really {GATE_DOCS} distinct "
          f"documents. The first generator varied only the name, so 2,000 documents were "
          f"90 distinct files and the rest were correct dedupe refusals -- a load test "
          f"measuring the deduplicator ({r['duplicate']} duplicates)")
    check(r["chunks"] >= GATE_DOCS,
          f"...producing at least one chunk each ({r['chunks']})")
    check(r["counts"]["unsearchable"] == 0,
          "...and none is unsearchable: these all have a text layer by construction")
    check(r["total_hits"] > 0, f"the index answers the queries ({r['total_hits']} hits)")
    check(r["query_p50_ms"] >= 0 and r["query_p95_ms"] >= r["query_p50_ms"],
          f"p95 is not below p50 ({r['query_p50_ms']} / {r['query_p95_ms']})")
    text = report(r)
    check("EASY case" in text and "scans" in text,
          "the report says the corpus is the easy case and names what it does not measure")
    check(str(GATE_DOCS) in text, "...and reports the N it actually ran")
    check(DOCS == 2_000, f"the full run is {DOCS} documents, as V1 asks")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    n = DOCS
    if "--docs" in sys.argv:
        n = int(sys.argv[sys.argv.index("--docs") + 1])
    print(report(run(n)))
