"""Optional LangChain-compatible wrappers for Placedon services.

Wraps existing functions as LangChain Runnables and StructuredTools.
langchain-core is an OPTIONAL dependency — this module degrades gracefully.

Usage (if langchain-core installed):
    from checker.langchain_wrappers import extraction_runnable, extraction_tool
    result = extraction_runnable.invoke({"text": "...", "name": "Contract.pdf"})

Run: PYTHONPATH=. python3 checker/langchain_wrappers.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from checker.cuad_pipeline import CUADResult, run_cuad_pipeline

__all__ = [
    "ExtractionInput", "ExtractionOutput",
    "make_extraction_runnable", "make_extraction_tool",
    "make_pipeline_chain",
]

# ── schemas ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExtractionInput:
    text: str
    name: str = ""
    doc_id: str = ""
    model_provider: str = ""
    model_version: str = ""


@dataclass(frozen=True)
class ExtractionOutput:
    document_id: str
    name: str
    doc_class: str
    tags: tuple
    extraction_count: int
    obligation_count: int
    injection_markers: int
    sensitive_hits: int
    errors: tuple[str, ...]


def _run_extraction(input_data: dict[str, Any]) -> dict[str, Any]:
    """Bridge function: dict in, dict out. No auth bypass — caller must
    have already verified tenant/matter access."""
    inp = ExtractionInput(**{k: v for k, v in input_data.items()
                            if k in ExtractionInput.__dataclass_fields__})
    result = run_cuad_pipeline(
        inp.text, name=inp.name, doc_id=inp.doc_id,
        model_provider=inp.model_provider, model_version=inp.model_version,
    )
    out = ExtractionOutput(
        document_id=result.document_id,
        name=result.name,
        doc_class=result.doc_class,
        tags=result.tags,
        extraction_count=len(result.extraction.extractions) if result.extraction else 0,
        obligation_count=len(result.obligations),
        injection_markers=len(result.injection_markers),
        sensitive_hits=result.sensitive_hits,
        errors=result.errors,
    )
    return asdict(out)


def _run_extraction_full(input_data: dict[str, Any]) -> dict[str, Any]:
    """Returns the full CUADResult as dict (for pipeline composition)."""
    inp = ExtractionInput(**{k: v for k, v in input_data.items()
                            if k in ExtractionInput.__dataclass_fields__})
    result = run_cuad_pipeline(
        inp.text, name=inp.name, doc_id=inp.doc_id,
        model_provider=inp.model_provider, model_version=inp.model_version,
    )
    return asdict(result)


# ── LangChain wrappers (optional import) ─────────────────────────────────────

_HAS_LANGCHAIN = False
try:
    from langchain_core.runnables import RunnableLambda
    from langchain_core.tools import StructuredTool
    _HAS_LANGCHAIN = True
except ImportError:
    pass


def make_extraction_runnable():
    """Create a RunnableLambda wrapping the extraction pipeline.
    Returns None if langchain-core is not installed."""
    if not _HAS_LANGCHAIN:
        return None
    return RunnableLambda(_run_extraction, name="placedon_extraction")


def make_extraction_tool():
    """Create a StructuredTool wrapping the extraction pipeline.
    Returns None if langchain-core is not installed."""
    if not _HAS_LANGCHAIN:
        return None
    return StructuredTool.from_function(
        func=_run_extraction,
        name="placedon_extract",
        description=(
            "Extract verified contractual information from an authorized "
            "Placedon matter. Input: {text, name, doc_id, model_provider, "
            "model_version}. Returns extraction summary."
        ),
    )


def make_pipeline_chain():
    """Create a composed runnable: extraction → summary.
    Returns None if langchain-core is not installed."""
    if not _HAS_LANGCHAIN:
        return None

    def _summarize(result: dict) -> dict:
        return {
            "document_id": result.get("document_id", ""),
            "doc_class": result.get("doc_class", ""),
            "extraction_count": result.get("extraction_count", 0),
            "obligation_count": result.get("obligation_count", 0),
            "has_issues": len(result.get("errors", ())) > 0,
        }

    return (
        RunnableLambda(_run_extraction, name="extract")
        | RunnableLambda(_summarize, name="summarize")
    )


# ── self-tests ────────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("langchain_wrappers")

    # ── bridge function works without langchain ─────────────────────────
    nda_text = (
        "MUTUAL NON-DISCLOSURE AGREEMENT dated January 15, 2024. "
        "This Agreement is entered into between Acme Corp and Beta Ltd. "
        "The receiving party shall not disclose any confidential information."
    )
    result = _run_extraction({"text": nda_text, "name": "NDA.pdf"})
    check(isinstance(result, dict), "bridge returns dict")
    check(result["doc_class"] == "nda", f"doc_class={result['doc_class']}")
    check(result["extraction_count"] == 0, "no extraction without route_fn")
    check(isinstance(result["tags"], (list, tuple)), "tags present")
    check(isinstance(result["errors"], (list, tuple)), "errors present")

    # ── full bridge ─────────────────────────────────────────────────────
    full = _run_extraction_full({"text": "Service Agreement between X and Y. X shall pay Y.", "name": "SA.pdf"})
    check("document_id" in full, "full result has document_id")
    check("extraction" in full, "full result has extraction key")

    # ── input schema validation ─────────────────────────────────────────
    inp = ExtractionInput(text="test", name="t.pdf")
    check(inp.text == "test", "input schema")
    check(inp.model_provider == "", "default provider empty")

    # ── output schema ───────────────────────────────────────────────────
    out = ExtractionOutput("id1", "t.pdf", "nda", ("confidentiality",), 0, 0, 0, 0, ())
    check(out.document_id == "id1", "output schema")

    # ── extra keys ignored ──────────────────────────────────────────────
    result2 = _run_extraction({"text": "test", "name": "t.pdf", "tenant_id": "IGNORE"})
    check(isinstance(result2, dict), "extra keys ignored safely")

    # ── langchain optional ──────────────────────────────────────────────
    r = make_extraction_runnable()
    if _HAS_LANGCHAIN:
        check(r is not None, "runnable created (langchain installed)")
        invoke_result = r.invoke({"text": "NDA between A and B", "name": "NDA.pdf"})
        check(isinstance(invoke_result, dict), "runnable invoke works")
        check("doc_class" in invoke_result, "runnable returns structured output")

        t = make_extraction_tool()
        check(t is not None, "tool created")
        check(t.name == "placedon_extract", f"tool name={t.name}")

        chain = make_pipeline_chain()
        check(chain is not None, "chain created")
        chain_result = chain.invoke({"text": "NDA between A and B", "name": "NDA.pdf"})
        check("has_issues" in chain_result, "chain composition works")
    else:
        check(r is None, "runnable=None (langchain not installed)")
        check(make_extraction_tool() is None, "tool=None")
        check(make_pipeline_chain() is None, "chain=None")

    # ── security: tenant_id not trusted ─────────────────────────────────
    # The wrapper doesn't accept or pass through auth fields
    check("tenant_id" not in ExtractionInput.__dataclass_fields__,
          "no tenant_id in input schema")
    check("matter_id" not in ExtractionInput.__dataclass_fields__,
          "no matter_id in input schema")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
