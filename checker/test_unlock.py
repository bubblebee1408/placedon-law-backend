"""
Does verification actually unlock the pipeline?

I have twice told the founder that one lawyer-hour setting `verified_by` on 30 sections turns
every abstention into a cited answer "with no code change". That was an assertion, not a tested
claim — and everything downstream of the gate has never executed, because the gate has never
opened.

This test opens it, against a copy of the real corpus, and checks what actually happens. It
makes no API call: the LLM is stubbed, because what needs proving is the *plumbing* either side
of it — that a verified packet passes pre-flight, that a grounded answer survives the post-check,
and that a fabricated one still dies.

Run: python3 checker/test_unlock.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import retrieval, verifier  # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"
LAWYER = "Adv. Test, verified 2026-08-09"


def verified_copy() -> list[dict]:
    """The real corpus, with verified_by set. Never written back to disk."""
    provisions = json.loads(CORPUS.read_text())["provisions"]
    return [{**p, "verified_by": LAWYER, "verified_at": "2026-08-09"} for p in provisions]


def patched_retrieve(question: str, corpus: list[dict], *, top_k: int = 3):
    """retrieval.retrieve() against a supplied corpus rather than the file."""
    sections = retrieval.keyword_route(question)
    if sections:
        by_num = {p["section_number"]: p for p in corpus}
        hits = [by_num[n] for n in sections if n in by_num][:top_k]
        if hits:
            return hits, "keyword"
    scored = sorted(((retrieval._score(question, p), p) for p in corpus),
                    key=lambda x: x[0], reverse=True)
    hits = [p for s, p in scored[:top_k] if s > 0]
    return hits, "scan" if hits else "none"


if __name__ == "__main__":
    failures = 0

    def check(name: str, got, want) -> None:
        global failures
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}"
              + ("" if ok else f"\n         got={got!r} want={want!r}"))

    Q = "Do I need an Internal Committee?"

    # ── today: unverified ────────────────────────────────────────────────
    live, _ = retrieval.retrieve(Q)
    today = verifier.should_abstain(Q, live, None, state="IN-KA")
    check("today, unverified corpus → abstains", today.abstained, True)
    check("  ...and it names the sections it holds",
          all(p["citation"] for p in live), True)

    # ── the hypothetical lawyer-hour ─────────────────────────────────────
    corpus = verified_copy()
    provisions, stage = patched_retrieve(Q, corpus)
    check("verified corpus retrieves the same sections",
          [p["citation"] for p in provisions], [p["citation"] for p in live])

    pre = verifier.should_abstain(Q, provisions, None, state="IN-KA")
    check("verified packet passes pre-flight → clear to spend", pre.abstained, False)
    check("  ...so the LLM call becomes reachable with no code change", pre.confidence, "answer")

    # ── a grounded answer, stubbed. Only text the sections actually contain. ──
    grounded = (
        "Yes. Every employer of a workplace shall, by an order in writing, constitute a "
        "Committee to be known as the Internal Complaints Committee [s.4]. The Presiding "
        "Officer shall be a woman employed at a senior level at workplace [s.4]."
    )
    post = verifier.should_abstain(Q, provisions, grounded, state="IN-KA")
    check("grounded answer survives the post-check", post.abstained, False)

    # ── the fabrication that three specs propagated ──────────────────────
    fabricated = "You need one at 10 or more employees [s.4]."
    bad = verifier.should_abstain(Q, provisions, fabricated, state="IN-KA")
    check("fabricated '10 or more employees' still dies", bad.abstained, True)
    check("  ...and the figure is named", "10" in bad.unsupported_numbers, True)

    # ── a plausible-sounding invented deadline ───────────────────────────
    deadline_q = "When is the annual return due?"
    dp, _ = patched_retrieve(deadline_q, corpus)
    invented = "File it by 31 January each year [s.21]."
    dv = verifier.should_abstain(deadline_q, dp, invented, state="IN-KA")
    check("invented '31 January' deadline dies even on a verified corpus", dv.abstained, True)
    check("  ...which is the whole product, holding under verification",
          "31" in dv.unsupported_numbers, True)

    # ── payroll stays out of scope regardless of verification ────────────
    calc = verifier.should_abstain("Calculate my PF liability", provisions, None, state="IN-KA")
    check("payroll arithmetic still refused when verified", calc.abstained, True)

    # ── the real corpus was not mutated ──────────────────────────────────
    on_disk = json.loads(CORPUS.read_text())["provisions"]
    check("real corpus still unverified on disk",
          all(p["verified_by"] is None for p in on_disk), True)

    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    if not failures:
        print("\nThe claim holds: setting verified_by is the only change needed. The LLM call\n"
              "becomes reachable, a grounded answer passes, and a fabricated number still dies —\n"
              "including '31 January', which is the finding this product exists for.")
    raise SystemExit(1 if failures else 0)
