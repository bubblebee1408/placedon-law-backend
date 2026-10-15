#!/usr/bin/env python3
"""Build the Voyage dense index that `checker/judgment_dense.py` searches at runtime.

Mirrors `scripts/build_voyage_index.py` (#99's Companies Act builder) for judgments. This is
the OFFLINE builder: for each row of the committed judgment metadata index
(`checker/sources/judgment_index.default_index()`, 8,977 Supreme Court judgments today), it
fetches the judgment PDF from the keyless AWS Open Data bucket
(`checker.sources.judgments_open.OpenJudgments`), extracts its text
(`checker.pdf_pages.extract_pages`), and embeds title + parties + a bounded slice of the
body with Voyage's `voyage-law-2` into a compact JSON file checked into
`corpus/judgments/`. The RUNTIME (`checker/judgment_dense.py`) never calls Voyage to embed a
judgment; only the live QUERY goes to Voyage, per request, with `input_type="query"` there
against `input_type="document"` here -- the same pinned-pair discipline
`build_voyage_index.py`'s own docstring explains.

## Why `row_to_record` and `_embedding_text` are tested without the real corpus or network

Mirrors `build_voyage_index.py`: the mapping from a judgment ref + its extracted body onto an
index record is the one piece that breaks if either side's shape drifts, so both are pure
functions with their own fixture tests. `build_live` itself IS exercised in the gate too, but
with the PDF fetch, text extraction and the Voyage call all injected -- `_fetch_body` replaces
the real fetch+extract pipeline, and `_embed_transport` replaces the real Voyage transport, so
the gate opens no socket and needs no PDF engine either.

## Conservative by default: `--live` caps how much it embeds and fetches

The committed judgment index holds 8,977 rows. Embedding and fetching all of them in one run
is real money (Voyage) and real bandwidth (one PDF GET per judgment) for a first activation
nobody has sized yet. `--live` defaults to `DEFAULT_LIMIT` judgments; pass `--limit 0` for an
explicit full run once the first sample has been reviewed.

Run:  PYTHONPATH=. python3 scripts/build_judgment_voyage_index.py --test   # mapping + batching, no network
      PYTHONPATH=. python3 scripts/build_judgment_voyage_index.py --live   # the real fetch + embed + write
                                                                            # (needs VOYAGE_API_KEY; reads
                                                                            # the keyless S3 bucket)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checker.sources import judgment_index as ji                 # noqa: E402
from checker.sources.base import FetchError                      # noqa: E402
from checker.sources.judgments_open import NotAPdf, OpenJudgments  # noqa: E402
from checker import voyage_model                                 # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "corpus" / "judgments" / "voyage_dense_index.json"
SC = "aws_sc_judgments"
BATCH_SIZE = 50           # well inside the 1,000-item and ~120K-token documented limits
BODY_CHARS = 4000         # judgments run long; a bounded slice still carries the topic signal
DEFAULT_LIMIT = 200       # conservative cap for a first --live run; pass --limit 0 for all rows


def row_to_record(s3_key: str, title: str, text: str) -> dict:
    """One judgment's identity + embedding text -> the index record for it, minus its vector.

    Pure, so the shape this builder produces -- and `judgment_dense._load_index` consumes --
    is tested without reading the corpus, fetching a PDF, or the network.
    """
    return {"s3_key": s3_key, "title": title, "text": text}


def _embedding_text(ref: ji.JudgmentRef, body: str) -> str:
    """Title + parties + the judgment's own words -- the embedding input.

    Metadata (title/parties) carries identity; `body` is where the legal TOPIC lives, which
    is exactly what `checker/sources/judgment_index.py` says metadata search cannot see.
    Mirrors `checker/dense_index._corpus`'s `Section {n}. {title}. {body[:1200]}` shape:
    identity first, then a bounded slice of the words that actually carry the subject.
    """
    bits = [ref.title, ", ".join(ref.parties), body]
    return ". ".join(b.strip() for b in bits if b and b.strip())


def _batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _fetch_pdf_bytes(oj: OpenJudgments, s3_key: str) -> bytes:
    """One anonymous GET for a key the committed judgment index already names in full.

    Validates the %PDF magic bytes and content-type the same way
    `OpenJudgments.fetch` does -- never the status code alone -- but returns the bytes,
    which `fetch()` does not keep, since text extraction needs them. Builds the URL from
    the key directly rather than reversing `path`/`lang`/suffix back out of it, which
    `fetch()` demands and which this key already carries whole.
    """
    resp = oj.transport(oj._url(s3_key))
    if resp.status != 200:
        raise FetchError(f"{oj.source_id}: {s3_key} returned HTTP {resp.status}")
    ct = (resp.content_type or "").lower()
    if "pdf" not in ct or resp.body[:4] != b"%PDF":
        raise NotAPdf(
            f"{oj.source_id}: {s3_key} is not a PDF (content-type {ct!r}, first bytes "
            f"{resp.body[:8]!r}). A 200 of XML where a PDF was expected is never read as "
            f"a judgment.")
    return resp.body


def _extract_body(pdf_bytes: bytes, *, max_chars: int = BODY_CHARS) -> str:
    """The judgment's own words, truncated. `checker.pdf_pages` reads a path, not bytes, so
    the fetched PDF is written to a temp file -- pdfplumber is already a dependency of that
    module (requirements-dev.txt), never of the served path, and this builder is offline
    tooling like it."""
    import tempfile

    from checker import pdf_pages
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        pages = pdf_pages.extract_pages(tmp.name)
    return " ".join(p for p in pages if p)[:max_chars]


def _default_fetch_body(oj: OpenJudgments, ref: ji.JudgmentRef) -> str:
    return _extract_body(_fetch_pdf_bytes(oj, ref.s3_key))


def build_live(*, source_id: str = SC, limit: int = DEFAULT_LIMIT, batch_size: int = BATCH_SIZE,
                _refs=None, _oj=None, _fetch_body=None, _embed_transport=None) -> list[dict]:
    """Fetch, extract and embed up to `limit` committed judgment-index rows for `source_id`.

    `_refs`, `_oj`, `_fetch_body` and `_embed_transport` are the gate's injection points --
    together they let `_test()` exercise this function's batching and mapping with zero
    sockets and no PDF engine, the same discipline `build_voyage_index.build_live` uses for
    the Companies Act corpus.
    """
    refs = _refs if _refs is not None else [r for r in ji.default_index() if r.source_id == source_id]
    if limit:
        refs = refs[:limit]
    if not refs:
        raise RuntimeError(f"no committed judgment-index rows for {source_id!r}; nothing to index")
    oj = _oj if _oj is not None else OpenJudgments(source_id)
    fetch_body = _fetch_body or _default_fetch_body

    rows = []
    for ref in refs:
        body = fetch_body(oj, ref)
        rows.append(row_to_record(ref.s3_key, ref.title, _embedding_text(ref, body)))

    out: list[dict] = []
    for batch in _batches(rows, batch_size):
        texts = [r["text"] for r in batch]
        vectors, call = voyage_model.embed(texts, input_type="document", model=voyage_model.LAW,
                                           _transport=_embed_transport)
        print(f"  embedded {len(texts)} judgments ({call.total_tokens} tokens, "
              f"Rs {call.cost_inr:.4f})")
        for row, vec in zip(batch, vectors):
            out.append({"s3_key": row["s3_key"], "title": row["title"], "vector": vec})
    return out


def dump_index(records: list[dict], path: Path = OUT, *, model: str = voyage_model.LAW) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "model": model,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "judgments": records,
    }, indent=1))


def _test() -> int:
    ok = fail = 0

    def check(c, label):
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if c else (ok, fail + 1)
        print(f"  [{'PASS' if c else 'FAIL'}] {label}")

    print("build_judgment_voyage_index")

    # row_to_record is a pure mapping -- no network, no corpus read, no PDF.
    row = row_to_record("data/pdf/year=2021/english/tata-mistry_EN.pdf",
                        "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd",
                        "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd. Tata Sons, Cyrus "
                        "Investments. the tribunal held the removal was oppressive")
    check(row == {"s3_key": "data/pdf/year=2021/english/tata-mistry_EN.pdf",
                  "title": "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd",
                  "text": "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd. Tata Sons, Cyrus "
                          "Investments. the tribunal held the removal was oppressive"},
          "row_to_record maps identity + title + text to an index record, minus its vector")

    check(_batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]],
          "batching splits into groups of the given size, remainder last")
    check(_batches([], 2) == [], "batching an empty list yields no batches")

    tata_ref = ji.JudgmentRef(SC, "data/pdf/year=2021/english/tata-mistry_EN.pdf",
                              "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd",
                              ("Tata Sons Private Limited", "Cyrus Investments Private Limited"),
                              2021, "2021-03-26", "")
    check(_embedding_text(tata_ref, "the tribunal held the removal was oppressive") ==
          "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd. Tata Sons Private Limited, Cyrus "
          "Investments Private Limited. the tribunal held the removal was oppressive",
          "the embedding text joins title, parties and body, in that order")
    no_parties_ref = ji.JudgmentRef(SC, "data/pdf/year=2020/english/x_EN.pdf", "X v. Y", (), 2020)
    check(_embedding_text(no_parties_ref, "") == "X v. Y",
          "empty parties and an empty body are dropped, never joined as blank segments")

    DIM = voyage_model.DOCUMENTED_DIM[voyage_model.LAW]

    def fixture_transport(endpoint, payload):
        n = len(payload["input"])
        return {"object": "list", "model": payload["model"], "usage": {"total_tokens": 10 * n},
                "data": [{"object": "embedding", "index": i,
                          "embedding": [0.1 * (i + 1)] + [0.0] * (DIM - 1)}
                         for i in range(n)]}

    refs = [
        tata_ref,
        ji.JudgmentRef(SC, "data/pdf/year=2019/english/oppression_EN.pdf",
                       "Some Company v. Registrar (oppression and mismanagement)",
                       ("Some Company Limited",), 2019, "2019-07-10", ""),
        ji.JudgmentRef(SC, "data/pdf/year=2026/english/data-priv_EN.pdf",
                       "ABC Ltd v. Union of India (data protection)",
                       ("ABC Limited", "Union of India"), 2026, "2026-02-01", ""),
    ]
    bodies = {
        refs[0].s3_key: "the tribunal held the removal of directors was oppressive conduct",
        refs[1].s3_key: "mismanagement of company affairs and oppression of minority shareholders",
        refs[2].s3_key: "personal data processed without consent breaches the statute",
    }
    fetch_calls: list[str] = []

    def fake_fetch_body(oj, ref):
        fetch_calls.append(ref.s3_key)
        return bodies[ref.s3_key]

    class _FakeOJ:
        """Enough shape to pass through build_live when _fetch_body is injected -- never
        actually touched by fake_fetch_body, which ignores it."""
        source_id = SC

    # The live flow end to end, on a small fixture, with the PDF fetch+extract AND the
    # Voyage transport both replaced -- proves build_live's batching and mapping without
    # ever opening a socket or needing a PDF engine.
    records = build_live(limit=0, batch_size=2, _refs=refs, _oj=_FakeOJ(),
                         _fetch_body=fake_fetch_body, _embed_transport=fixture_transport)
    check(len(records) == 3, f"build_live returns one record per ref (3 expected, got "
                             f"{len(records)})")
    check(fetch_calls == [r.s3_key for r in refs],
          "every ref's body was fetched exactly once, in order")
    check({r["s3_key"] for r in records} == {r.s3_key for r in refs},
          "every s3_key in the slice is represented, none invented")
    check(all(len(r["vector"]) == DIM for r in records),
          f"every vector is {DIM}-dimensional, the documented width for {voyage_model.LAW}")
    check(all(r["title"] for r in records), "every record carries its judgment's title")

    # `limit` truncates which rows are processed at all -- proven on the same fixture.
    limited = build_live(limit=1, batch_size=2, _refs=refs, _oj=_FakeOJ(),
                         _fetch_body=fake_fetch_body, _embed_transport=fixture_transport)
    check(len(limited) == 1 and limited[0]["s3_key"] == refs[0].s3_key,
          "limit caps how many committed rows one --live run processes")

    check(0 < DEFAULT_LIMIT <= 2000,
          f"the default --live run is capped well under a full corpus-sized index "
          f"({DEFAULT_LIMIT}) -- a bare --live cannot accidentally embed+fetch everything")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "voyage_dense_index.json"
        dump_index(records, out)
        check(out.is_file(), "dump_index writes the file")

        # Round-trip through the RUNTIME loader this index is built for -- the two modules
        # must agree on the shape, not merely on each one's own opinion of it.
        from checker import judgment_dense
        keys, titles, vectors, model = judgment_dense._load_index(out)
        check(set(keys) == {r["s3_key"] for r in records},
              "the runtime loader reads back every judgment this builder wrote")
        check(model == voyage_model.LAW, "the runtime loader confirms the model name round-trips")
        check(len(vectors[0]) == DIM, "the runtime loader confirms the vector width round-trips")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--source-id", default=SC)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="cap on judgments fetched+embedded; 0 = no cap (the full committed index)")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    if a.test:
        return _test()
    if a.live:
        records = build_live(source_id=a.source_id, limit=a.limit, batch_size=a.batch_size)
        dump_index(records, Path(a.out))
        print(f"wrote {len(records)} judgments -> {a.out}")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
