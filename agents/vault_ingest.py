#!/usr/bin/env python3
"""One ingest job per file: read it, classify it, chunk it, tag it -- or say why not.

V1. Twenty thousand files means twenty thousand independent failures, so this is one job
per document and never a batch: a batch that dies at file 9,000 has done nine thousand
units of work nobody can resume from, and `gateway/jobs.py` already gives exactly-once
per run.

## A scan is not an empty document

If the bytes carry no text layer the document becomes `CANNOT_READ` with
`ocr_state='BLOCKED'`, because Textract is blocked until AWS. The alternative is
`INGESTED` with zero characters, which is indistinguishable from a genuinely blank page --
and a vault that cannot tell those apart answers every search from the documents it
happened to be able to read, while looking complete. `vault_counts().unsearchable` is what
makes that visible.

## Archives are guarded, and not expanded

`checker/archive_guard` runs on every upload, because an archive is the one file that is
small on the wire and ruinous in memory. An archive that FAILS the guard is refused with
the limit it crossed. An archive that PASSES is also refused, with a different reason:
expanding one into N documents is a real feature and it is not built, and a silent
"ingested, 0 chunks" would be the worst of both.

## Nothing here calls a model

Classification is rules (`checker/doc_classifier`), tagging is rules
(`checker/clause_tags`), chunking is arithmetic. `extract` is injected, so the gate runs
the whole pipeline without a PDF parser and a deployment swaps one in.

Run: PYTHONPATH=. python3 agents/vault_ingest.py --test
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["INTENT", "TEXTRACT_BLOCKED", "Outcome", "ingest", "IngestError"]

INTENT = "vault_ingest"

TEXTRACT_BLOCKED = (
    "OCR is BLOCKED: Amazon Textract is the chosen engine and AWS is not configured (B1 "
    "is held). The document is recorded as CANNOT_READ and counted in "
    "vault_counts().unsearchable, so a search says it could not look at this file -- "
    "rather than being INGESTED with no text, which is indistinguishable from a blank "
    "page.")


class IngestError(RuntimeError):
    """A job that cannot run at all. Distinct from a document that cannot be read."""


@dataclass(frozen=True)
class Outcome:
    document_id: str
    state: str
    doc_class: str = ""
    chunks: int = 0
    tags: int = 0
    text_chars: int | None = None
    ocr_state: str = "NOT_NEEDED"
    reason: str = ""
    # A1 item 6. Page numbers that could not be read. A document with any of these is
    # PARTIAL, never INGESTED -- it is stored and searchable, and the reader is told which
    # pages are missing rather than being handed a blank where page 7 should be.
    failed_pages: tuple = ()

    def to_dict(self) -> dict:
        return {"document_id": self.document_id, "state": self.state,
                "doc_class": self.doc_class, "chunks": self.chunks, "tags": self.tags,
                "text_chars": self.text_chars, "ocr_state": self.ocr_state,
                "reason": self.reason, "failed_pages": list(self.failed_pages)}


def ingest(args: dict, *, files, store, extract, pages=None) -> Outcome:
    """One file. `extract(data, name) -> str` is injected and may return "" for a scan.

    A1 item 6. `pages(data, name) -> Extraction` is the optional page-by-page path. When
    supplied it replaces `extract` for paged documents: the caps in `checker/page_stream` are
    checked BEFORE anything is read, pages are streamed one at a time so peak memory is one
    page, and a page that fails makes the document PARTIAL with that page NAMED.

    Without it the behaviour is unchanged -- `extract` returns one string and a document is
    INGESTED or CANNOT_READ, which is what every current caller does.
    """
    from checker import archive_guard as ag
    from checker import clause_tags, doc_classifier
    from checker.vault_search import chunk

    for field in ("document_id", "sha256", "name"):
        if not str(args.get(field) or "").strip():
            raise IngestError(f"an ingest job needs {field}")
    did, sha, name = args["document_id"], args["sha256"], args["name"]

    data = files.get(sha)
    if data is None:
        raise IngestError(
            f"no bytes are stored for {sha[:12]}..., so there is nothing to ingest. This "
            f"is a job fault, not a document that cannot be read")

    # The archive guard, on every upload.
    verdict = ag.inspect(data)
    if verdict.state != ag.NOT_ARCHIVE:
        reason = (f"archive refused: {verdict.reason}" if not verdict.ok else
                  "this is an archive. Expanding one into separate documents is not built "
                  "yet, and ingesting it as a single opaque file would store something no "
                  "search can reach")
        store.write_vault_document({
            "document_id": did, "matter_id": args.get("matter_id"), "sha256": sha,
            "name": name, "byte_count": len(data), "state": "CANNOT_READ",
            "ocr_state": "NOT_NEEDED"})
        return Outcome(did, "CANNOT_READ", reason=reason)

    failed_pages: tuple = ()
    if pages is not None:
        from checker.page_stream import PARTIAL as _PARTIAL
        from checker.page_stream import Refusal as _Refusal
        paged = pages(data, name)
        if isinstance(paged, _Refusal):
            # The cap, refused up front with its limit named. Nothing was read.
            store.write_vault_document({
                "document_id": did, "matter_id": args.get("matter_id"), "sha256": sha,
                "name": name, "byte_count": len(data), "state": "CANNOT_READ",
                "ocr_state": "NOT_NEEDED"})
            return Outcome(did, "CANNOT_READ", reason=paged.detail)
        failed_pages = tuple(paged.failed_pages)
        text = "\n".join(paged.pages[k] for k in sorted(paged.pages))
    else:
        text = str(extract(data, name) or "")
    if not text.strip():
        store.write_vault_document({
            "document_id": did, "matter_id": args.get("matter_id"), "sha256": sha,
            "name": name, "byte_count": len(data), "state": "CANNOT_READ",
            "ocr_state": "BLOCKED"})
        return Outcome(did, "CANNOT_READ", ocr_state="BLOCKED",
                       reason=TEXTRACT_BLOCKED)

    doc_class, why = doc_classifier.classify(text, name=name)
    chunks = chunk(text)
    tags = [t.to_dict() for t in clause_tags.tag(text)]
    # PARTIAL, not INGESTED, when any page failed. The chunks and tags from the pages that
    # DID read are still written -- they are correct and useful -- but the document must not
    # report itself complete, because a search that misses a clause on page 7 and a search
    # that found nothing look identical to the person reading it.
    state = "PARTIAL" if failed_pages else "INGESTED"
    note = why if not failed_pages else (
        f"{why}. PARTIAL: page(s) {', '.join(str(n) for n in failed_pages)} could not be "
        f"read and are NOT in this document's text or index")
    store.write_vault_document({
        "document_id": did, "matter_id": args.get("matter_id"), "sha256": sha,
        "name": name, "byte_count": len(data), "state": state,
        "doc_class": doc_class, "class_reason": note, "text_chars": len(text),
        "ocr_state": "NOT_NEEDED"})
    store.write_vault_chunks(did, chunks)
    store.write_vault_tags(did, tags)
    return Outcome(did, state, doc_class, len(chunks), len(tags), len(text),
                   reason=note, failed_pages=failed_pages)


def handler(*, files, store, extract):
    """`handler(args) -> (steps, result)` for gateway/worker.py."""
    def run(args: dict):
        try:
            out = ingest(args, files=files, store=store, extract=extract)
        except IngestError as e:
            return ([{"capability": "vault.ingest", "status": "FAILED",
                      "cost_note": "no model is called by this intent; the checks are "
                                   "code"}],
                    {"status": "FAILED", "error": str(e)})
        return ([{"capability": "vault.ingest", "status": "ANSWERED",
                  "cost_note": "no model is called by this intent; classification and "
                               "tagging are rules"}],
                {"status": "ANSWERED", **out.to_dict()})
    return run


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

    print("vault_ingest")
    import io
    import tempfile
    import uuid
    import zipfile
    from pathlib import Path

    from gateway.filestore import LocalFileStore
    from gateway.store import MemoryBackend

    CONTRACT = ("2. Term\n\nThis Agreement shall continue for five years. Either party "
                "may terminate on ninety days written notice.\n\n9. Governing law\n\n"
                "This Agreement is governed by the laws of India. Confidential "
                "Information means anything disclosed.")

    with tempfile.TemporaryDirectory() as tmp:
        files, store = LocalFileStore(Path(tmp)), MemoryBackend()
        plain = lambda data, name: data.decode("utf-8", "replace")   # noqa: E731

        # ── the happy path ─────────────────────────────────────────────────
        sha = files.put(CONTRACT.encode())
        did = str(uuid.uuid4())
        out = ingest({"document_id": did, "sha256": sha, "name": "Petrichor NDA.pdf"},
                     files=files, store=store, extract=plain)
        check(out.state == "INGESTED" and out.doc_class == "nda",
              f"a readable contract is INGESTED and classified ({out.state}, "
              f"{out.doc_class})")
        check(out.chunks >= 1 and out.tags >= 4,
              f"...chunked and tagged ({out.chunks} chunks, {out.tags} tags)")
        check(out.text_chars == len(CONTRACT),
              f"...and the text length is recorded ({out.text_chars})")
        row = store.read_vault_document(did) or {}
        check(row.get("state") == "INGESTED" and row.get("class_reason"),
              "...and the row carries the class AND the reason for it")
        check(len(store.read_vault_tags(did)) == out.tags,
              "...and the tags really landed in the store")

        # ── a scan is CANNOT_READ, not an empty document ───────────────────
        scan = files.put(b"%PDF-1.7 a scanned page with no text layer at all")
        sid = str(uuid.uuid4())
        s_out = ingest({"document_id": sid, "sha256": scan, "name": "scan.pdf"},
                       files=files, store=store, extract=lambda d, n: "")
        check(s_out.state == "CANNOT_READ" and s_out.ocr_state == "BLOCKED",
              f"**a file with no text layer is CANNOT_READ with OCR BLOCKED**, never "
              f"INGESTED with zero characters ({s_out.state}/{s_out.ocr_state})")
        check("Textract" in s_out.reason and "blank page" in s_out.reason,
              "...and the reason names the blocked engine and why the distinction matters")
        check(store.vault_counts()["unsearchable"] == 1,
              f"...and it is COUNTED as unsearchable, which is what lets a search say it "
              f"could not look at this file ({store.vault_counts()})")
        check(not store.read_vault_chunks() or all(
            c["document_id"] != sid for c in store.read_vault_chunks()),
            "...and it produced no chunks, so nothing pretends to be searchable")

        # ── archives: the guard runs on every upload ───────────────────────
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", "0" * 5_000_000)
        bomb = files.put(buf.getvalue())
        b_out = ingest({"document_id": str(uuid.uuid4()), "sha256": bomb,
                        "name": "archive.zip"}, files=files, store=store, extract=plain)
        check(b_out.state == "CANNOT_READ" and "archive refused" in b_out.reason,
              f"a zip bomb is REFUSED by the guard before anything is extracted "
              f"({b_out.reason[:40]})")
        check("200x limit" in b_out.reason or "ratio" in b_out.reason.lower(),
              f"...naming the limit it crossed ({b_out.reason[:60]})")

        ok_buf = io.BytesIO()
        with zipfile.ZipFile(ok_buf, "w") as zf:
            zf.writestr("a.txt", "a real document inside an archive")
        good_zip = files.put(ok_buf.getvalue())
        g_out = ingest({"document_id": str(uuid.uuid4()), "sha256": good_zip,
                        "name": "docs.zip"}, files=files, store=store, extract=plain)
        check(g_out.state == "CANNOT_READ" and "not built yet" in g_out.reason,
              f"a SAFE archive is also refused, with a different reason: expanding one "
              f"into separate documents is not built, and ingesting it opaquely would "
              f"store something no search can reach ({g_out.reason[:44]})")
        check(b_out.reason != g_out.reason,
              "...so 'this is dangerous' and 'this is not supported' are distinguishable")

        # ── a job fault is not a document that cannot be read ──────────────
        try:
            ingest({"document_id": str(uuid.uuid4()), "sha256": "f" * 64,
                    "name": "ghost.pdf"}, files=files, store=store, extract=plain)
            check(False, "missing bytes raise")
        except IngestError as e:
            check("job fault" in str(e),
                  "bytes that are not in the file store RAISE: that is a job fault, not a "
                  "document that cannot be read, and recording it as CANNOT_READ would "
                  "blame the client's file for our bug")
        for missing in ("document_id", "sha256", "name"):
            args = {"document_id": "d", "sha256": "a" * 64, "name": "n"}
            args[missing] = ""
            try:
                ingest(args, files=files, store=store, extract=plain)
                check(False, f"a job with no {missing} raises")
            except IngestError:
                check(True, f"a job with no {missing} is refused")

        # ── the handler shape the worker wants ─────────────────────────────
        run = handler(files=files, store=store, extract=plain)
        steps, result = run({"document_id": str(uuid.uuid4()),
                             "sha256": files.put(b"ANOTHER agreement governed by the "
                                                 b"laws of India."),
                             "name": "second.pdf"})
        check(result["status"] == "ANSWERED" and steps[0]["capability"] == "vault.ingest",
              "the handler returns (steps, result) for gateway/worker.py")
        check("no model is called" in steps[0]["cost_note"],
              "...and the step says no model was called, so UNPRICED is explained rather "
              "than blank")
        bad_steps, bad_result = run({"document_id": "x", "sha256": "e" * 64, "name": "n"})
        check(bad_result["status"] == "FAILED" and bad_steps[0]["status"] == "FAILED",
              "...and a job fault comes back FAILED rather than raising into the worker")

    # ── A1 item 6: the paged path reaches the DOCUMENT ──────────────────────
    from checker import page_stream as ps

    class _PagedStore:
        def __init__(self):
            self.docs = {}
            self.chunks = {}
            self.tags = {}

        def write_vault_document(self, row):
            self.docs[row["document_id"]] = dict(row)

        def write_vault_chunks(self, did, chunks):
            self.chunks[did] = list(chunks)

        def write_vault_tags(self, did, tags):
            self.tags[did] = list(tags)

    class _Doc:
        """Five pages of real contract text; page `boom` raises."""
        n = 5

        def __init__(self, boom=None):
            self.boom = boom

        def page_text(self, i):
            if i == self.boom:
                raise OSError("no readable content stream")
            return (f"Clause {i}. This Agreement shall be governed by the laws of India "
                    f"and the term of confidentiality shall expire on 2029-03-31.")

    _sha = "d" * 64
    _files = {_sha: b"%PDF-1.4 fake"}

    def _pages_for(doc):
        def pages(data, name):
            ref = ps.check_file(name, page_count=doc.n, size_bytes=len(data))
            return ref if ref is not None else ps.extract_streaming(
                name, reader=lambda _p: doc)
        return pages

    # A page that fails -> PARTIAL, naming the page, with every other page present.
    st = _PagedStore()
    out = ingest({"document_id": "docP", "sha256": _sha, "name": "five.pdf"},
                 files=_files, store=st, extract=lambda d, n: "unused",
                 pages=_pages_for(_Doc(boom=3)))
    check(out.state == "PARTIAL",
          f"a document whose page 3 failed is PARTIAL, never INGESTED ({out.state})")
    check(list(out.failed_pages) == [3],
          f"...and NAMES the page ({out.failed_pages})")
    check("page(s) 3" in out.reason and "NOT in this document" in out.reason,
          f"...and says the page is absent from the text AND the index, which is what a "
          f"reader needs to know ({out.reason[-60:]})")
    check(st.docs["docP"]["state"] == "PARTIAL",
          f"...and the stored document says PARTIAL too, not just the return value "
          f"({st.docs['docP']['state']})")
    for n in (1, 2, 4, 5):
        check(f"Clause {n}." in "\n".join(c if isinstance(c, str) else c.get("text", "")
                                          for c in st.chunks["docP"]),
              f"...while page {n}'s text IS indexed")
    check("Clause 3." not in "\n".join(c if isinstance(c, str) else c.get("text", "")
                                        for c in st.chunks["docP"]),
          "...and the failed page's text is absent rather than blank-but-present")

    # No page fails -> INGESTED.
    st2 = _PagedStore()
    good = ingest({"document_id": "docG", "sha256": _sha, "name": "five.pdf"},
                  files=_files, store=st2, extract=lambda d, n: "unused",
                  pages=_pages_for(_Doc()))
    check(good.state == "INGESTED" and not good.failed_pages,
          f"a document with no failed page is INGESTED ({good.state})")
    check(good.state != out.state,
          "INGESTED and PARTIAL are both reachable, so neither check passes by default")

    # Over the cap -> refused up front, with the cap named, nothing read.
    class _Huge:
        n = ps.MAX_PAGES + 1

        def page_text(self, i):
            raise AssertionError("a file over the cap must not be read at all")

    st3 = _PagedStore()
    big = ingest({"document_id": "docH", "sha256": _sha, "name": "huge.pdf"},
                 files=_files, store=st3, extract=lambda d, n: "unused",
                 pages=_pages_for(_Huge()))
    check(big.state == "CANNOT_READ",
          f"a file over the page cap is CANNOT_READ ({big.state})")
    check(str(ps.MAX_PAGES) in big.reason and "Nothing was read" in big.reason,
          f"...naming the cap, and saying nothing was read -- the fixture's page_text "
          f"raises AssertionError if it is touched ({big.reason[:70]})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
