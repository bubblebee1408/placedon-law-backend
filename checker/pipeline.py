"""Document processing pipeline — the orchestration layer.

Ties together: classification → clause extraction → summarization → dedup.
LangChain is the orchestration framework; model inference goes through the
router (PLAN_22 D3); deterministic code validates every model output before
anything downstream sees it (PLAN_23).

The pipeline is a sequence of STAGES. Each stage is a pure function that
takes a document state and returns a new document state (immutability).
Code owns the plans and hand-offs — no model decides what runs next.

Stages:
  1. classify     — doc_classifier.classify (rule-based, no model)
  2. tag_clauses  — clause_tags.tag (rule-based, no model)
  3. extract      — CUAD-style extractive QA via router (model, HIGH consequence)
  4. summarize    — textrank.summarize (no model, TextRank from Mihalcea & Tarau 2004)
  5. dedup_check  — dedup.minhash + jaccard_estimate (no model, MinHash from Broder 1997)

Stages 1, 2, 4, 5 are deterministic — no model call. Stage 3 is the only
model-dependent stage and goes through router.route().

Run: PYTHONPATH=. python3 checker/pipeline.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from checker.clause_tags import Tag, tag
from checker.dedup import MinHashSignature, minhash
from checker.doc_classifier import classify
from checker.textrank import summarize

__all__ = ["DocumentState", "process", "process_batch"]


@dataclass(frozen=True)
class DocumentState:
    """Immutable state of a document through the pipeline."""
    doc_id: str
    text: str
    name: str = ""

    # Stage 1: classification
    doc_class: str = ""
    class_reason: str = ""

    # Stage 2: clause tags
    tags: tuple[Tag, ...] = ()

    # Stage 3: model extraction (populated only when a model is called)
    extractions: tuple[dict[str, Any], ...] = ()
    extraction_route: str = ""

    # Stage 4: summary
    summary_sentences: tuple[str, ...] = ()

    # Stage 5: dedup signature
    signature: MinHashSignature = ()

    # Pipeline metadata
    stages_completed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def _with(state: DocumentState, **kwargs: Any) -> DocumentState:
    """Return a new DocumentState with updated fields. Immutability."""
    d = {f.name: getattr(state, f.name) for f in state.__dataclass_fields__.values()}
    d.update(kwargs)
    return DocumentState(**d)


def _stage_classify(state: DocumentState) -> DocumentState:
    doc_class, reason = classify(state.text, name=state.name)
    return _with(state,
                 doc_class=doc_class,
                 class_reason=reason,
                 stages_completed=state.stages_completed + ("classify",))


def _stage_tag(state: DocumentState) -> DocumentState:
    tags_found = tag(state.text)
    return _with(state,
                 tags=tuple(tags_found),
                 stages_completed=state.stages_completed + ("tag_clauses",))


def _stage_summarize(state: DocumentState) -> DocumentState:
    sentences = summarize(state.text, ratio=0.2, max_sentences=8)
    return _with(state,
                 summary_sentences=tuple(sentences),
                 stages_completed=state.stages_completed + ("summarize",))


def _stage_dedup(state: DocumentState) -> DocumentState:
    sig = minhash(state.text)
    return _with(state,
                 signature=sig,
                 stages_completed=state.stages_completed + ("dedup_check",))


# The deterministic stages. Model extraction is omitted — it requires a route
# and is called explicitly when a model is available.
_DETERMINISTIC_STAGES = (
    _stage_classify,
    _stage_tag,
    _stage_summarize,
    _stage_dedup,
)


def process(text: str, *, doc_id: str = "", name: str = "") -> DocumentState:
    """Run all deterministic stages on a single document.

    Model-dependent extraction is NOT included here — call it separately
    when a route is available. Code owns the pipeline; the caller decides
    whether to call a model.
    """
    state = DocumentState(doc_id=doc_id or "doc", text=text, name=name)
    for stage_fn in _DETERMINISTIC_STAGES:
        try:
            state = stage_fn(state)
        except Exception as e:
            state = _with(state, errors=state.errors + (f"{stage_fn.__name__}: {e}",))
    return state


def process_batch(documents: dict[str, str],
                  *, names: dict[str, str] | None = None) -> dict[str, DocumentState]:
    """Process multiple documents and return states keyed by doc_id."""
    names = names or {}
    return {
        doc_id: process(text, doc_id=doc_id, name=names.get(doc_id, ""))
        for doc_id, text in documents.items()
    }


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("pipeline")

    # ── single document ───────────────────────────────────────────────────
    nda = ("MUTUAL NON-DISCLOSURE AGREEMENT. This Non-Disclosure Agreement is "
           "entered into between Acme Corp and Beta Ltd. The parties agree to "
           "keep all confidential information strictly private. Confidential "
           "information includes trade secrets, business plans, and financial "
           "data. The receiving party shall not disclose any confidential "
           "information to third parties without prior written consent. This "
           "agreement shall remain in force for a period of two years from the "
           "date of execution. The agreement shall be governed by the laws of "
           "India. Any disputes shall be resolved through arbitration in Mumbai.")

    state = process(nda, doc_id="nda_001", name="NDA - Acme Beta.pdf")

    check(state.doc_id == "nda_001", f"doc_id preserved ({state.doc_id})")
    check(state.doc_class == "nda", f"classified as NDA ({state.doc_class})")
    check(len(state.tags) > 0, f"found clause tags ({len(state.tags)})")
    check(any(t.tag == "Confidentiality" for t in state.tags),
          "found Confidentiality tag")
    check(any(t.tag == "Governing Law" for t in state.tags),
          "found Governing Law tag")
    check(len(state.summary_sentences) >= 1,
          f"produced summary ({len(state.summary_sentences)} sentences)")
    check(len(state.signature) > 0, "computed dedup signature")
    check(state.stages_completed == ("classify", "tag_clauses", "summarize", "dedup_check"),
          f"all stages completed ({state.stages_completed})")
    check(state.errors == (), f"no errors ({state.errors})")

    # ── immutability ──────────────────────────────────────────────────────
    state2 = process(nda, doc_id="nda_002")
    check(state.doc_id == "nda_001" and state2.doc_id == "nda_002",
          "processing a second doc does not mutate the first")

    # ── batch ─────────────────────────────────────────────────────────────
    minutes = ("MINUTES OF THE MEETING OF THE BOARD. The chairman took the "
               "chair. Leave of absence was granted. The meeting commenced at "
               "10:00 AM. The board discussed the annual results.")
    batch = process_batch({"nda": nda, "minutes": minutes},
                          names={"nda": "NDA.pdf", "minutes": "Board Minutes.pdf"})
    check(len(batch) == 2, f"batch processed 2 documents ({len(batch)})")
    check(batch["nda"].doc_class == "nda", "batch: NDA classified correctly")
    check(batch["minutes"].doc_class == "board_minutes",
          f"batch: minutes classified correctly ({batch['minutes'].doc_class})")

    # ── empty / unknown ───────────────────────────────────────────────────
    empty = process("", doc_id="empty")
    check(empty.doc_class == "unknown", f"empty text is unknown ({empty.doc_class})")
    check(empty.errors == (), "empty text produces no errors")

    # ── dedup signatures differ for different docs ────────────────────────
    from checker.dedup import jaccard_estimate
    sim = jaccard_estimate(batch["nda"].signature, batch["minutes"].signature)
    check(sim < 0.3, f"NDA and minutes are not near-duplicates ({sim:.3f})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
