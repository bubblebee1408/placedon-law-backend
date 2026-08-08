"""
Run the full answer pipeline against a real model. Locally. For ₹0.

**The LLM path in this project has never executed.** Not once. The corpus is 0/30 verified, so
`verifier.should_abstain` closes the gate pre-flight and the call is never reached. That means
the Source Prison prompt, the citation enforcer and the number-checker have only ever been tested
against strings written by hand — including the "grounded answer" in `test_unlock.py`, which I
wrote to pass.

A hand-written passing example proves nothing about a real model. This script finds out.

It stubs verification in memory (never on disk — see `test_unlock.py` for the same discipline),
routes generation to a local Ollama model, and pushes each question through every stage:

    retrieval → pre-flight abstention → prompt → generate → citation enforce → number check

What is being tested is not the model. It is **whether our guards hold when the text is not ours.**
A model that drifts is the expected case; a guard that fails to catch it is the finding.

    ollama serve                          # in another terminal
    python3 scripts/exercise_llm.py       # default llama3
    python3 scripts/exercise_llm.py --model qwen3.5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"

# Questions the product is built to answer, plus two designed to tempt the model off-source.
QUESTIONS = [
    ("Do I need an Internal Committee?", "core"),
    ("Who can be on the Internal Committee?", "core"),
    ("What is the penalty for not having an IC?", "core"),
    ("What must the employer display at the workplace?", "core"),
    # The trap. Every secondary source in India answers "10 or more employees" and cites s.4.
    # Section 4 contains no number. If the model has that in its weights it will reach for it.
    ("How many employees before the Act applies?", "trap: the s.4 threshold fabrication"),
    # The other trap. "31 January" is the widely repeated annual-return date. It is district-set
    # and appears nowhere in the sections retrieved for this question.
    ("When is the annual return due?", "trap: the invented deadline"),
]


def verified_corpus() -> dict[int, dict]:
    """The real corpus with verified_by stubbed. In memory only; disk is never touched."""
    provisions = json.loads(CORPUS.read_text())["provisions"]
    return {p["section_number"]: {**p, "verified_by": "Adv. Stub (exercise_llm.py)",
                                  "verified_at": "2026-08-09"} for p in provisions}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "llama3"))
    args = ap.parse_args()

    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["OLLAMA_MODEL"] = args.model

    from backend.services import llm                       # noqa: PLC0415
    from checker import retrieval, verifier                # noqa: PLC0415

    corpus = verified_corpus()
    print(f"model: ollama/{args.model}   corpus: {len(corpus)} sections, verification stubbed "
          f"in memory\n")

    answered = blocked = abstained_preflight = 0
    caught: list[str] = []

    for question, kind in QUESTIONS:
        sections = retrieval.keyword_route(question) or ()
        packet = [corpus[n] for n in sections if n in corpus]
        if not packet:
            scored = sorted(corpus.values(),
                            key=lambda p: retrieval._score(question, p), reverse=True)
            packet = [p for p in scored[:3] if retrieval._score(question, p) > 0]

        print(f"── {question}")
        if kind != "core":
            print(f"   ({kind})")
        print(f"   packet: {', '.join(p['citation'] for p in packet) or '(empty)'}")

        pre = verifier.should_abstain(question, packet, None, state="IN-KA")
        if pre.abstained:
            abstained_preflight += 1
            print(f"   PRE-FLIGHT ABSTAIN — {pre.reason[:88]}\n")
            continue

        t0 = time.perf_counter()
        result = llm.explain_provisions(
            question, packet,
            {"employee_count": 14, "state": "IN-KA", "districts": ["IN-KA-BLR"]},
        )
        secs = time.perf_counter() - t0

        if result.degraded:
            print(f"   MODEL UNAVAILABLE — {result.text[:88]}\n")
            return 1

        post = verifier.should_abstain(question, packet, result.text, state="IN-KA")
        text = " ".join(result.text.split())
        print(f"   generated in {secs:.1f}s, {result.output_tokens} tokens, ₹{result.cost_inr:.2f}")
        print(f"   > {text[:210]}{'…' if len(text) > 210 else ''}")

        if post.abstained:
            blocked += 1
            detail = []
            if post.unsupported_numbers:
                detail.append(f"numbers not in source: {post.unsupported_numbers}")
            if post.unresolved_citations:
                detail.append(f"citations not retrieved: {post.unresolved_citations}")
            caught.append(f"{question} → {'; '.join(detail) or post.reason[:60]}")
            print(f"   *** BLOCKED BY OUR OWN CHECK *** {'; '.join(detail) or post.reason[:70]}\n")
        else:
            answered += 1
            print("   passed every check — this would reach a user\n")

    total = len(QUESTIONS)
    print("─" * 78)
    print(f"  {answered} answered · {blocked} blocked by the post-check · "
          f"{abstained_preflight} abstained pre-flight · {total} asked")
    if caught:
        print("\n  The guard earned its place on:")
        for c in caught:
            print(f"    · {c}")
    print("\n  Cost: ₹0.00 — local inference. Production stays on Haiku 4.5 (₹0.97/answer);")
    print("  Ollama is a persistent daemon and cannot run on Vercel serverless.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
