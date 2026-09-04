"""A retrieval eval set for structural chunk selection — with an honest boundary.

T5 in docs/NEXT_MOVE_PLAN_2026_09_04.md. MODEL_DEVELOPMENT_PLAN §6 step 1: "you
cannot improve retrieval you cannot measure." This is the measurement — a frozen
set of (question → expected chunk path) cases and a precision@1 scorer over the
deterministic selector (`ground_span.select_chunk`).

## The boundary that keeps the score honest

Some question→chunk mappings are *structural*: "the paid-up capital limit for a
small company" points at s.2(85)(i) by the text's own layout, no legal judgement
required. Those are SCORED.

Others require a practitioner to say what the right span even is — e.g. which
provision governs a borderline fact pattern, or whether a proviso carves out a
case. Guessing those and scoring against the guess would manufacture a green
number that means nothing. So every such case is marked `NEEDS_LAWYER`, carries
`expected_path=None`, and is EXCLUDED from the score. They are not failures; they
are the H-B ask in the runbook — the exact list a reviewing lawyer resolves.

The harness therefore reports three things a reader must not conflate: the
precision on what we could score, and the list of what only a lawyer can label,
and the individual misses. A high precision on five structural cases is not a
claim about the whole retrieval problem — it is a claim about five cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from checker.ground_span import select_chunk
from checker.lexical_rank import BM25
from checker.structural_index import chunks_for_section


def bm25_select(question, chunks):
    """Rank a section's chunks for a question with BM25; return the top Chunk.

    The dependency-free alternative to the naive term-overlap selector. Returns
    None when nothing scores above zero, same contract as select_chunk.
"""
    if not chunks:
        return None
    bm = BM25([(c.path, c.text) for c in chunks])
    top = bm.top(question)
    return next((c for c in chunks if c.path == top), None) if top else None


@dataclass(frozen=True)
class EvalCase:
    question: str
    section: str                    # the section whose chunks are the candidates
    expected_path: str | None       # None <=> needs_lawyer (excluded from score)
    needs_lawyer: bool = False
    note: str = ""


# Structural cases: the mapping from question to chunk is fixed by the statute's
# own layout, not by legal interpretation. These are SCORED.
_SCORED: tuple[EvalCase, ...] = (
    EvalCase("the paid-up share capital limit for a small company",
             "2", "2(85)(i)",
             note="the capital limb of the small-company definition"),
    EvalCase("the turnover limit for a small company in the preceding financial year",
             "2", "2(85)(ii)",
             note="the turnover limb"),
    EvalCase("by when must the first annual general meeting be held",
             "96", "96(1)/proviso[1]",
             note="the first-AGM nine-month proviso"),
    EvalCase("the definition of a subsidiary company",
             "2", "2(87)",
             note="s.2(87) defines subsidiary; structural, if s.2(87) is chunked"),
    EvalCase("the definition of a small company",
             "2", "2(85)",
             note="the small-company definition head"),
    # Definition cases: "which clause defines term X" is textually determined --
    # the clause literally reads '"X" means ...'. Each expected path was derived
    # programmatically (not guessed) by matching the quoted defined term, so these
    # are genuinely structural, not legal judgement. They widen the measurement
    # from 5 to a real signal without needing the H-B lawyer labels.
    EvalCase("the definition of a foreign company", "2", "2(42)"),
    EvalCase("the definition of a private company", "2", "2(68)"),
    EvalCase("the definition of a public company", "2", "2(71)"),
    EvalCase("the definition of a Government company", "2", "2(45)"),
    EvalCase("the definition of a listed company", "2", "2(52)"),
    EvalCase("the definition of a One Person Company", "2", "2(62)"),
    EvalCase("the definition of net worth", "2", "2(57)"),
    EvalCase("the definition of free reserves", "2", "2(43)"),
)

# Cases whose correct span is a matter of legal judgement. NOT scored. Each is a
# concrete question for the reviewing lawyer (runbook H-B).
_NEEDS_LAWYER: tuple[EvalCase, ...] = (
    EvalCase("does a company limited by guarantee count toward the small-company test",
             "2", None, needs_lawyer=True,
             note="which limb/proviso governs guarantee companies — interpretation"),
    EvalCase("if turnover is unknown, does the small-company status default either way",
             "2", None, needs_lawyer=True,
             note="the treatment of an unknown figure is a reasoning question, not a span"),
    EvalCase("which proviso of s.96 lets the Registrar extend the AGM time",
             "96", None, needs_lawyer=True,
             note="requires reading each proviso's effect — confirm the exact one"),
)

CASES: tuple[EvalCase, ...] = _SCORED + _NEEDS_LAWYER


@dataclass
class EvalResult:
    scored: int
    correct: int
    misses: list[tuple[str, str, str | None]] = field(default_factory=list)  # (q, expected, got)
    needs_lawyer: list[str] = field(default_factory=list)

    @property
    def precision_at_1(self) -> float:
        return self.correct / self.scored if self.scored else 0.0


def run(cases: tuple[EvalCase, ...] = CASES, *, selector=select_chunk) -> EvalResult:
    """Score `selector` on the structural cases; list the lawyer-gated ones.

    selector(question, chunks) -> Chunk|None. Defaults to the naive term-overlap
    selector (the 0.20 baseline); pass bm25_select for the BM25 ranker.
"""
    res = EvalResult(scored=0, correct=0)
    for c in cases:
        if c.needs_lawyer or c.expected_path is None:
            res.needs_lawyer.append(f"[s.{c.section}] {c.question} — {c.note}")
            continue
        res.scored += 1
        picked = selector(c.question, chunks_for_section(c.section))
        got = picked.path if picked else None
        if got == c.expected_path:
            res.correct += 1
        else:
            res.misses.append((c.question, c.expected_path, got))
    return res


def render(res: EvalResult) -> str:
    L = [f"retrieval precision@1: {res.correct}/{res.scored} = {res.precision_at_1:.2f}",
         f"excluded (NEEDS_LAWYER, H-B): {len(res.needs_lawyer)}"]
    for m in res.misses:
        L.append(f"  MISS  q={m[0]!r}  expected={m[1]}  got={m[2]}")
    for n in res.needs_lawyer:
        L.append(f"  LAWYER  {n}")
    return "\n".join(L)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("retrieval_eval")
    res = run()

    # ── the harness runs and scores the structural cases ────────────────────
    check(res.scored == len(_SCORED), f"every structural case is scored ({res.scored})")
    check(res.scored >= 3, "there are at least a few scored cases")

    # ── NEEDS_LAWYER cases are excluded, not scored, and surfaced ───────────
    check(len(res.needs_lawyer) == len(_NEEDS_LAWYER),
          f"lawyer-gated cases are excluded from the score ({len(res.needs_lawyer)})")
    check(all(c.expected_path is None for c in _NEEDS_LAWYER),
          "every lawyer-gated case carries no guessed expected path")
    check(res.scored + len(res.needs_lawyer) == len(CASES),
          "scored + excluded accounts for every case (nothing silently dropped)")

    # ── precision is MEASURED for two rankers, and the gain is asserted ──────
    # The self-test still verifies the tool, not a fixed quality bar. But now it
    # records TWO baselines -- naive term-overlap and dependency-free BM25 -- and
    # asserts BM25 does not regress below naive, because the whole point of adding
    # BM25 was to see whether a classical method beats 0.20 before committing to
    # an embedding dependency. It does (0.20 -> 0.60), and the residual misses are
    # semantic, which is the measured case for embeddings (see the misses below).
    naive = run(selector=select_chunk)
    bm25 = run(selector=bm25_select)
    check(0.0 <= naive.precision_at_1 <= 1.0 and 0.0 <= bm25.precision_at_1 <= 1.0,
          "both precisions are well-formed ratios")
    check(bm25.precision_at_1 >= naive.precision_at_1,
          f"BM25 does not regress below naive "
          f"(naive={naive.precision_at_1:.2f}, bm25={bm25.precision_at_1:.2f})")
    check(res.correct >= 1,
          f"the selector gets at least one structural case right (baseline={res.precision_at_1:.2f})")
    print(f"  [INFO] naive p@1={naive.precision_at_1:.2f}  bm25 p@1={bm25.precision_at_1:.2f}  "
          f"(residual BM25 misses are the embedding target)")

    # The measured baseline is LOW on whole-section lexical retrieval by design of
    # this naive selector -- e.g. "paid-up share capital limit for a small company"
    # retrieves s.2(64) (the DEFINITION of paid-up capital) over 2(85)(i). That is
    # the finding, not a failure: it quantifies why per-section natural-language
    # retrieval needs the embedding layer, and gives it a number to beat.
    got_turn = select_chunk("the turnover limit for a small company in the preceding "
                            "financial year", chunks_for_section("2"))
    check(got_turn and got_turn.path == "2(85)(ii)",
          "a well-anchored question (turnover limb) does select correctly")

    # ── render names both the score and the lawyer gaps ─────────────────────
    text = render(res)
    check("precision@1" in text and "NEEDS_LAWYER" in text,
          "the report shows the score AND the lawyer-gated exclusions")

    # ── frozen-set integrity: no case is both scored and lawyer-gated ───────
    for c in CASES:
        if c.needs_lawyer and c.expected_path is not None:
            check(False, f"case is lawyer-gated but carries an expected path: {c.question}")
            break
    else:
        check(True, "no case is simultaneously lawyer-gated and scored")

    print(render(res))
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
