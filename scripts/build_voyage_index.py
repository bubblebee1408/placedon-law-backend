#!/usr/bin/env python3
"""Build the Voyage dense index that `checker/voyage_dense.py` searches at runtime.

Semantic retrieval activation, step 2. This is the OFFLINE builder: it reads every
held Companies Act section -- via `checker.dense_index._corpus()`, the same
embedding-text construction already measured and gated there (`Section {n}. {title}.
{body[:1200]}`) -- and embeds it with Voyage's `voyage-law-2`
(`checker/voyage_model.py`) into a compact JSON file checked into
`corpus/companies_act/`. The RUNTIME (`checker/voyage_dense.py`) never calls Voyage
to embed the corpus; only the live query goes to Voyage, per request, with
`input_type="query"` there against `input_type="document"` here. The FAQ voyage_model
already cites says never to omit `input_type` for retrieval -- a query embedded as a
document is a quiet, measurable degradation -- so the two input_types are pinned at
their two call sites rather than left to a caller to remember.

## Why `row_to_record` is the only thing tested without the real corpus

Mirrors `scripts/build_judgment_index.py`: the mapping from a corpus tuple to an
index record is the one piece that breaks if the shape of either side drifts, so it
is a pure function with its own fixture test. The network embed call is `--live`
only and is not in the gate -- `--test` proves the SAME batching and mapping code
runs correctly by injecting a fixture transport, never a real socket.

## Batched, because the documented limits are per request, not per corpus

`voyage_model.MAX_ITEMS` caps one call at 1,000 texts, and the docs separately cap
request size at ~120K tokens. This repo holds on the order of 500 sections, so the
corpus fits in one call by count, but each embedding text can run close to 1,200
characters -- batching keeps any one request well inside the token budget rather
than betting the whole corpus on a single call succeeding.

Run:  PYTHONPATH=. python3 scripts/build_voyage_index.py --test   # mapping + batching, no network
      PYTHONPATH=. python3 scripts/build_voyage_index.py --live   # the real embed + write (needs
                                                                    # VOYAGE_API_KEY)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checker import dense_index                                  # noqa: E402
from checker import voyage_model                                 # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "corpus" / "companies_act" / "voyage_dense_index.json"
BATCH_SIZE = 100          # well inside the 1,000-item and ~120K-token documented limits


def row_to_record(number: str, title: str, text: str) -> dict:
    """One `dense_index._corpus()` tuple -> the index record for it, minus its vector.

    Pure, so the shape this builder produces -- and `voyage_dense._load_index`
    consumes -- is tested without reading the corpus or the network.
    """
    return {"number": str(number), "title": title, "text": text}


def _batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_live(*, batch_size: int = BATCH_SIZE, _transport=None) -> list[dict]:
    """Embed every held section and return index records (number/title/vector).

    `_transport` is forwarded to `voyage_model.embed` -- the gate's injection point.
    `_test()` uses it to prove this function's batching and mapping with zero sockets.
    """
    corpus = dense_index._corpus()
    if not corpus:
        raise RuntimeError("the Companies Act corpus is empty; nothing to index")
    rows = [row_to_record(n, t, text) for n, t, text in corpus]
    out: list[dict] = []
    for batch in _batches(rows, batch_size):
        texts = [r["text"] for r in batch]
        vectors, call = voyage_model.embed(texts, input_type="document",
                                           model=voyage_model.LAW, _transport=_transport)
        print(f"  embedded {len(texts)} sections ({call.total_tokens} tokens, "
              f"Rs {call.cost_inr:.4f})")
        for row, vec in zip(batch, vectors):
            out.append({"number": row["number"], "title": row["title"], "vector": vec})
    return out


def dump_index(records: list[dict], path: Path = OUT, *, model: str = voyage_model.LAW) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "model": model,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sections": records,
    }, indent=1))


def _test() -> int:
    ok = fail = 0

    def check(c, label):
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if c else (ok, fail + 1)
        print(f"  [{'PASS' if c else 'FAIL'}] {label}")

    print("build_voyage_index")

    # row_to_record is a pure mapping -- no network, no corpus read.
    row = row_to_record("173", "Meetings of Board", "Section 173. Meetings of Board. ...")
    check(row == {"number": "173", "title": "Meetings of Board",
                  "text": "Section 173. Meetings of Board. ..."},
          "row_to_record maps a corpus tuple to an index record, minus its vector")

    check(_batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]],
          "batching splits into groups of the given size, remainder last")
    check(_batches([], 2) == [], "batching an empty list yields no batches")

    # The real corpus, read from disk only -- the same call checker/dense_index.py's
    # own gate already makes; no network here either.
    corpus = dense_index._corpus()
    check(len(corpus) > 400, f"the held Companies Act corpus has sections to index ({len(corpus)})")
    check(all(isinstance(n, str) and isinstance(t, str) and isinstance(txt, str)
              for n, t, txt in corpus[:5]),
          "each corpus entry is (section_number, title, embedding_text), all strings")

    DIM = voyage_model.DOCUMENTED_DIM[voyage_model.LAW]

    def fixture_transport(endpoint, payload):
        n = len(payload["input"])
        return {"object": "list", "model": payload["model"], "usage": {"total_tokens": 10 * n},
                "data": [{"object": "embedding", "index": i,
                          "embedding": [0.1 * (i + 1)] + [0.0] * (DIM - 1)}
                         for i in range(n)]}

    # The live flow end to end, on a small slice of the real corpus, with the network
    # replaced by a fixture transport -- proves build_live's batching and mapping
    # without ever opening a socket. dense_index._corpus is reassigned on the MODULE
    # (not the name imported here) so build_live's own `dense_index._corpus()` call
    # picks up the patch.
    small = corpus[:7]
    held_corpus_fn = dense_index._corpus
    dense_index._corpus = lambda: small
    try:
        records = build_live(batch_size=3, _transport=fixture_transport)
    finally:
        dense_index._corpus = held_corpus_fn
    check(len(records) == 7, f"build_live returns one record per corpus section (7 expected, got "
                             f"{len(records)})")
    check({r["number"] for r in records} == {n for n, _t, _x in small},
          "every section number in the slice is represented, none invented")
    check(all(len(r["vector"]) == DIM for r in records),
          f"every vector is {DIM}-dimensional, the documented width for {voyage_model.LAW}")
    check(all(r["title"] for r in records), "every record carries its section's title")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "voyage_dense_index.json"
        dump_index(records, out)
        check(out.is_file(), "dump_index writes the file")

        # Round-trip through the RUNTIME loader this index is built for -- the two
        # modules must agree on the shape, not merely on each one's own opinion of it.
        from checker import voyage_dense
        numbers, titles, vectors, model = voyage_dense._load_index(out)
        check(set(numbers) == {r["number"] for r in records},
              "the runtime loader reads back every section this builder wrote")
        check(model == voyage_model.LAW, "the runtime loader confirms the model name round-trips")
        check(len(vectors[0]) == DIM, "the runtime loader confirms the vector width round-trips")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.test:
        return _test()
    if a.live:
        records = build_live(batch_size=a.batch_size)
        dump_index(records, Path(a.out))
        print(f"wrote {len(records)} sections -> {a.out}")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
