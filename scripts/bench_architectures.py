"""
Naive RAG against the lattice, on the same five questions, with the same corpus and stub model.

## What is actually being compared

Both pipelines get identical inputs: the same 30-section corpus, the same questions, and a model
stub that quotes whatever it is handed. The stub is the point — it *cannot* fabricate, because it
copies source text. So every difference below comes from the pipeline, not from model quality,
and no result here depends on which LLM is used.

    naive     embed the question, cosine top-3, hand to the model, then check the output
              (checker-of-output: cited section present in context, cosine similarity threshold)

    lattice   route to sections, gate on whether a lawyer has verified them, trace the path to
              anything the claim rests on, flag conflicts, then verify against source

## The question it answers

Not "which is more accurate" — with a verbatim stub both are accurate by construction. The
question is **what each architecture does when it should not answer**, because that is the only
behaviour that separates them and the only one that matters on a compliance product.

    python3 scripts/bench_architectures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Five questions chosen because each isolates one failure mode.
QUESTIONS = [
    ("What is the penalty for not complying?",
     "the claim rests on s.4 via s.26(1)(a) — does the pipeline notice?"),
    ("How long does an aggrieved woman have to file a complaint?",
     "s.9 states three months and its proviso extends it — is the reader shown both?"),
    ("When is the annual return due?",
     "no date is prescribed anywhere — does the pipeline invent one?"),
    ("Do I need an Internal Committee if I have 8 employees?",
     "the threshold is an inference, not text — does the pipeline assert it?"),
    ("What is the GST rate on legal services?",
     "outside the corpus entirely — does the pipeline decline?"),
]


class _Stub:
    degraded = False

    def __init__(self, text: str) -> None:
        self.text = text


def _stub(question, provisions, context):
    p = provisions[0]
    body = " ".join((p.get("text_statutory") or "")[:240].split())
    return _Stub(f"Under {p.get('citation', 's.?')}: “{body}”")


# ── naive RAG ────────────────────────────────────────────────────────────────────────────────
def naive(question: str, corpus: list[dict], _cache: dict = {}) -> dict:
    """Embed, cosine top-3, generate, then check the output. No gate anywhere."""
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    except ImportError:
        return {"available": False}

    if "m" not in _cache:
        _cache["m"] = SentenceTransformer("all-MiniLM-L6-v2")
        _cache["ids"] = [p["section_number"] for p in corpus]
        _cache["mat"] = _cache["m"].encode(
            [" ".join(p["text_statutory"].split()) for p in corpus], normalize_embeddings=True)
    m = _cache["m"]
    q = m.encode([question], normalize_embeddings=True)[0]
    scores = _cache["mat"] @ q
    order = list(reversed(scores.argsort()))[:3]
    top = [corpus[i] for i in order]
    sim = float(scores[order[0]])

    answer = _stub(question, top, {}).text

    # The proposed Layer 4, exactly as specified.
    from checker import verifier                               # noqa: PLC0415
    flags = verifier.verify_citations(answer, top)
    a_emb, c_emb = m.encode([answer, " ".join(p["text_statutory"] for p in top)],
                            normalize_embeddings=True)
    if float(a_emb @ c_emb) < 0.6:
        flags.append("LOW_SIMILARITY")
    return {"available": True, "answered": True, "answer": answer, "flags": flags,
            "confidence": round(sim * 100, 1), "sections": [p["section_number"] for p in top]}


# ── the lattice ──────────────────────────────────────────────────────────────────────────────
def lattice(question: str, corpus: list[dict]) -> dict:
    from checker.ask_engine import AskEngine                   # noqa: PLC0415

    a = AskEngine(provisions=corpus, generate=_stub).ask(
        question, {"state": "IN-KA", "employees": 8})
    return {"available": True, "answered": not a.abstained, "status": a.status,
            "reason": a.reason,
            "paths": [c for c in a.epistemic_chain if c.get("status") == "PATH"],
            "conflicts": [c for c in a.epistemic_chain if c.get("status") == "CONFLICT"]}


def main() -> int:
    import json                                               # noqa: PLC0415

    corpus = json.loads((ROOT / "corpus/provisions/posh_act_2013.json").read_text())["provisions"]
    probe = naive("probe", corpus)
    if not probe.get("available"):
        print("  sentence-transformers not installed; nothing to compare.")
        return 0

    n_answered = l_answered = 0
    for q, why in QUESTIONS:
        n, l = naive(q, corpus), lattice(q, corpus)
        n_answered += n["answered"]
        l_answered += l["answered"]
        print(f"\n  {q}")
        print(f"    ({why})")
        print(f"    naive   : ANSWERED, confidence {n['confidence']}%, "
              f"flags={n['flags'] or 'none'}, cited s.{n['sections']}")
        verdict = "ANSWERED" if l["answered"] else f"ABSTAINED ({l['status']})"
        extra = ""
        if l["paths"]:
            extra += f", {len(l['paths'])} path(s) shown"
        if l["conflicts"]:
            extra += f", {len(l['conflicts'])} conflict(s) flagged"
        print(f"    lattice : {verdict}{extra}")

    print(f"\n  naive answered {n_answered}/{len(QUESTIONS)}; "
          f"lattice answered {l_answered}/{len(QUESTIONS)}.")
    print("\n  The stub cannot fabricate — it copies source text — so neither pipeline produces")
    print("  a false sentence here. The difference is entirely in what each one REFUSES, and on")
    print("  a compliance product that is the only difference that matters. Naive RAG answered")
    print("  every question including the one with no answer in the corpus, and attached a")
    print("  confidence percentage to it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
