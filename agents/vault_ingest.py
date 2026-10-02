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

    def to_dict(self) -> dict:
        return {"document_id": self.document_id, "state": self.state,
                "doc_class": self.doc_class, "chunks": self.chunks, "tags": self.tags,
                "text_chars": self.text_chars, "ocr_state": self.ocr_state,
                "reason": self.reason}


def ingest(args: dict, *, files, store, extract) -> Outcome:
    """One file. `extract(data, name) -> str` is injected and may return "" for a scan."""
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
    store.write_vault_document({
        "document_id": did, "matter_id": args.get("matter_id"), "sha256": sha,
        "name": name, "byte_count": len(data), "state": "INGESTED",
        "doc_class": doc_class, "class_reason": why, "text_chars": len(text),
        "ocr_state": "NOT_NEEDED"})
    store.write_vault_chunks(did, chunks)
    store.write_vault_tags(did, tags)
    return Outcome(did, "INGESTED", doc_class, len(chunks), len(tags), len(text),
                   reason=why)


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

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
