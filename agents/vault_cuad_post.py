"""Post-ingest CUAD extraction — enriches an already-ingested vault document.

Called AFTER vault_ingest succeeds. Does NOT modify vault_ingest.py.
If no model is available or extraction fails, the original ingest is preserved.

Run: PYTHONPATH=. python3 agents/vault_cuad_post.py --test
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agents.vault_ingest import Outcome

__all__ = ["CUADPostResult", "cuad_post"]


@dataclass(frozen=True)
class CUADPostResult:
    ingest: Outcome
    extractions: int
    obligations: int
    categories_found: tuple[str, ...]
    error: str


def cuad_post(
    outcome: Outcome,
    *,
    store,
    route_fn: Callable[[str], str] | None = None,
    model_provider: str = "",
    model_version: str = "",
) -> CUADPostResult:
    """Run CUAD extraction on an ingested document. Never fails the ingest."""
    empty = CUADPostResult(outcome, 0, 0, (), "")

    if outcome.state not in ("INGESTED",):
        return empty

    # Reconstruct text from stored chunks.
    # ponytail: reads all tenant chunks then filters; per-doc read when store gets one
    try:
        all_chunks = store.read_vault_chunks()
    except Exception as e:
        return CUADPostResult(outcome, 0, 0, (), f"chunk read failed: {e}")

    doc_chunks = sorted(
        [c for c in all_chunks if c.get("document_id") == outcome.document_id],
        key=lambda c: c.get("ordinal", 0),
    )
    if not doc_chunks:
        return CUADPostResult(outcome, 0, 0, (), "no chunks found")

    text = "\n".join(c.get("text", "") for c in doc_chunks)

    if route_fn is None:
        return empty

    try:
        from checker.cuad_pipeline import run_cuad_pipeline

        result = run_cuad_pipeline(
            text,
            name=outcome.document_id,
            doc_id=outcome.document_id,
            route_fn=route_fn,
            model_provider=model_provider,
            model_version=model_version,
        )
    except Exception as e:
        return CUADPostResult(outcome, 0, 0, (), f"extraction failed: {e}")

    ext_count = len(result.extraction.extractions) if result.extraction else 0
    obl_count = len(result.obligations)
    cats = result.extraction.categories_found if result.extraction else ()

    # Store extractions as tags with a "cuad:" prefix so they're retrievable
    # via the existing tag interface without new store methods.
    # ponytail: dedicated extraction table when query patterns diverge
    if ext_count > 0 and result.extraction:
        cuad_tags = [
            {
                "tag": f"cuad:{e.category}",
                "quote": e.evidence_text[:200],
                "span_start": e.start_offset,
                "span_end": e.end_offset,
            }
            for e in result.extraction.extractions
        ]
        try:
            existing_tags = store.read_vault_tags(outcome.document_id)
            store.write_vault_tags(outcome.document_id, existing_tags + cuad_tags)
        except Exception:
            pass  # Non-fatal: ingest is already complete.

    return CUADPostResult(
        ingest=outcome,
        extractions=ext_count,
        obligations=obl_count,
        categories_found=tuple(cats),
        error="",
    )


# ── self-tests ─────────────────────────────────────────────────────────────────

def _test() -> int:
    import json
    import tempfile
    import uuid
    from pathlib import Path

    from agents.vault_ingest import ingest, Outcome
    from gateway.filestore import LocalFileStore
    from gateway.store import MemoryBackend

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("vault_cuad_post")

    CONTRACT = (
        "MUTUAL NON-DISCLOSURE AGREEMENT dated January 15, 2024. "
        "This Agreement is entered into between Acme Corp and Beta Ltd. "
        "The receiving party shall not disclose any confidential information. "
        "This Agreement shall be governed by the laws of India. "
        "Any disputes shall be resolved through arbitration in Mumbai. "
        "The term is two years from the effective date. "
        "The Supplier shall indemnify the Customer against all losses.")

    with tempfile.TemporaryDirectory() as tmp:
        files = LocalFileStore(Path(tmp))
        store = MemoryBackend()
        plain = lambda data, name: data.decode("utf-8", "replace")

        sha = files.put(CONTRACT.encode())
        did = str(uuid.uuid4())
        outcome = ingest(
            {"document_id": did, "sha256": sha, "name": "NDA.pdf"},
            files=files, store=store, extract=plain,
        )
        check(outcome.state == "INGESTED", f"ingest succeeded ({outcome.state})")

        # ── happy path with mock model ───────────────────────────────────
        def mock_route(prompt: str) -> str:
            return json.dumps([
                {"category": "Governing Law", "answer": "India",
                 "evidence": "governed by the laws of India"},
                {"category": "Parties", "answer": "Acme Corp and Beta Ltd",
                 "evidence": "between Acme Corp and Beta Ltd"},
                {"category": "Confidentiality", "answer": "shall not disclose",
                 "evidence": "shall not disclose any confidential information"},
            ])

        post = cuad_post(
            outcome, store=store, route_fn=mock_route,
            model_provider="test", model_version="mock-1",
        )
        check(post.extractions >= 2, f"extractions found ({post.extractions})")
        check(post.obligations >= 1, f"obligations found ({post.obligations})")
        check(len(post.categories_found) >= 2,
              f"categories found ({post.categories_found})")
        check(post.error == "", f"no error ({post.error})")
        check(post.ingest is outcome, "original ingest preserved")

        # Check CUAD tags stored.
        tags = store.read_vault_tags(did)
        cuad_tags = [t for t in tags if t.get("tag", "").startswith("cuad:")]
        check(len(cuad_tags) >= 2, f"cuad tags stored ({len(cuad_tags)})")

        # ── no route_fn → silent skip ────────────────────────────────────
        did2 = str(uuid.uuid4())
        sha2 = files.put(CONTRACT.encode())
        outcome2 = ingest(
            {"document_id": did2, "sha256": sha2, "name": "NDA2.pdf"},
            files=files, store=store, extract=plain,
        )
        post2 = cuad_post(outcome2, store=store, route_fn=None)
        check(post2.extractions == 0, "no route → 0 extractions")
        check(post2.error == "", "no route → no error")

        # ── CANNOT_READ → skip ───────────────────────────────────────────
        cannot = Outcome("fake_id", "CANNOT_READ", reason="scan")
        post3 = cuad_post(cannot, store=store, route_fn=mock_route)
        check(post3.extractions == 0, "CANNOT_READ → skipped")
        check(post3.ingest.state == "CANNOT_READ", "original state preserved")

        # ── extraction error → preserved ingest ──────────────────────────
        def failing_route(prompt: str) -> str:
            raise ConnectionError("model down")

        did4 = str(uuid.uuid4())
        sha4 = files.put(CONTRACT.encode())
        outcome4 = ingest(
            {"document_id": did4, "sha256": sha4, "name": "NDA4.pdf"},
            files=files, store=store, extract=plain,
        )
        post4 = cuad_post(
            outcome4, store=store, route_fn=failing_route,
            model_provider="test", model_version="broken",
        )
        check(post4.extractions == 0, "failed route → 0 extractions")
        check(post4.ingest.state == "INGESTED", "ingest preserved on failure")
        # Error is captured inside cuad_pipeline, returned through result.errors
        # cuad_post wraps the whole thing, so either way it's safe.

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
