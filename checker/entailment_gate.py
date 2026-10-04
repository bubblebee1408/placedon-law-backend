"""The only path from a lexical verdict to SUPPORTED.

`checker/claim_verifier.py` never returns SUPPORTED, and says why in its own docstring: the
top lexical verdict used to be SUPPORTED, and that was a lie. Word overlap establishes that a
claim's distinctive terms appear in the cited text; it does not establish that the text says
the claim. Two provisions of s.173 can score identically on overlap while only one carries
the obligation. `establishes_support()` exists so a caller cannot mistake triage for
grounding.

This module is what that reservation was waiting for. It is the **single** function permitted
to promote a verdict to SUPPORTED, and `_test()` proves structurally -- by walking the AST of
every module in the repository -- that no other file both imports that constant and returns
it. That is `checker/rings.py`'s technique pointed at a verdict instead of an import, and for
the same reason: a convention relies on every future diff being read by someone who remembers
the rule.

## What it takes to be promoted, and why each part

Three conditions, all required:

  * **The cascade says True.** Not None. `checker/cascade.py` returns True / False / None, and
    None means no module could answer. A caller that reads abstention as support has invented
    an answer, which is the failure this whole file exists to prevent.
  * **The lexical verdict was at least a candidate.** The cascade reads a premise and a claim;
    it does not know whether the cited evidence is the right evidence. If the lexical check
    said CONTRADICTED or MISSING, entailment against that text is not a promotion, it is a
    category error.
  * **The gate is ENABLED.** See below.

## No LLM is a judge here

`docs/architecture/MODEL_PLAN.md`'s rule, and the reason the cascade is four deterministic modules rather
than a prompt: a model asked "does this text entail this claim?" produces a fluent answer with
no way to check it, and the whole product is the checking. Nothing in this module or anything
it calls touches a network.

## ENABLED, and what would turn it off

Measured on the frozen strict set (`entail_pairs_v2.all_pairs`, n=67, re-measured
2026-10-02) through the same composition a runtime reaches -- `cascade.judge_row` -- scored
by `metric_policy.evaluate_gate`:

    false accepts  2      ceiling 10     PASS
    F1             0.581  floor   0.40   PASS
    abstention     0.00   cap     0.25   PASS
    buckets        3      minimum 3      PASS

F1 was 0.625 until 02-10-2026, when `checker/entail_substitution.py` was added to the
cascade as a second gate. It cost one true positive on this set and bought the following,
measured over 400 real held provisions by `scripts/verifier_error_rates.py`:

    negation mutations accepted   264/268  ->  0/268
    shall -> may accepted         294/304  ->  9/304
    quantity changed accepted      11/98   ->  0/98

That is the trade this gate exists to make, and it is recorded here rather than in a
commit message because the number above is what a future reader will check against.

So it ships ENABLED. `docs/policy/METRIC_POLICY.md` requires shipping disabled if the bar is not met,
and `_test()` re-measures on every run: if the gate ever stops passing, the suite goes red
rather than quietly promoting claims on a verifier that no longer earns it.

Run: python3 checker/entailment_gate.py
"""
from __future__ import annotations

from checker import cascade
from checker.claim_verifier import (CONTRADICTED, LEXICAL_CANDIDATE, MISSING, PARTIAL,
                                    SUPPORTED, UNSUPPORTED)

# Verdicts a promotion may start from. CONTRADICTED and MISSING are absent deliberately:
# entailment against text the lexical check already rejected is not evidence of anything.
PROMOTABLE = frozenset({LEXICAL_CANDIDATE, PARTIAL, UNSUPPORTED})

ENABLED = True          # measured PASS; see the module docstring


def grade(premise: str, claim: str, lexical_verdict: str, *, enabled: bool | None = None) -> str:
    """The lexical verdict, promoted to SUPPORTED only if entailment is established.

    Returns `lexical_verdict` unchanged in every other case -- including abstention, which is
    not a weak yes.
    """
    on = ENABLED if enabled is None else enabled
    if not on:
        return lexical_verdict
    if lexical_verdict not in PROMOTABLE:
        return lexical_verdict
    if cascade.verdict(premise, claim).supported is not True:
        return lexical_verdict
    return SUPPORTED


def _measure():
    """Score the shipped composition on the frozen strict set. Returns (result, pairs)."""
    from checker.entail_pairs_v2 import all_pairs
    from checker.eval_taxonomy import bucket_of
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED
    from checker import metric_policy as mp

    pairs = [p for p in all_pairs()
             if p.label in (ENTAILED, NOT_ENTAILED) and p.source_span]
    return mp.evaluate_gate(cascade.judge_row, pairs, bucket_of), pairs


def _pr(pairs) -> tuple[int, int, int, int]:
    """(tp, fp, fn, tn) of the shipped cascade over `pairs`. Abstention counts as negative."""
    from checker.grounding_policy import ENTAILED
    tp = fp = fn = tn = 0
    for p in pairs:
        gold = p.label == ENTAILED
        got = cascade.judge_row(p) is True
        if gold and got:
            tp += 1
        elif gold:
            fn += 1
        elif got:
            fp += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def _test() -> int:
    import ast
    from pathlib import Path

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("entailment_gate")

    # ── behaviour ───────────────────────────────────────────────────────────
    check(grade("x", "y", CONTRADICTED) == CONTRADICTED,
          "a CONTRADICTED lexical verdict is never promoted -- entailment against text the "
          "lexical check rejected is a category error, not evidence")
    check(grade("x", "y", MISSING) == MISSING, "...and neither is MISSING")
    check(grade("x", "y", LEXICAL_CANDIDATE, enabled=False) == LEXICAL_CANDIDATE,
          "disabled, the gate returns the lexical verdict untouched")
    check(CONTRADICTED not in PROMOTABLE and MISSING not in PROMOTABLE,
          "the promotable set excludes both by construction, not by an if further down")

    # Abstention is not a weak yes. Driven through the real function with a premise and
    # claim the cascade cannot decide.
    _abstained = [None]

    class _NoAnswer:
        supported = None

    _real = cascade.verdict
    try:
        cascade.verdict = lambda p, c: _NoAnswer()          # type: ignore[assignment]
        check(grade("p", "c", LEXICAL_CANDIDATE) == LEXICAL_CANDIDATE,
              "an ABSTAINING cascade does not promote -- None is not a soft True")
    finally:
        cascade.verdict = _real                             # type: ignore[assignment]

    class _Yes:
        supported = True

    try:
        cascade.verdict = lambda p, c: _Yes()               # type: ignore[assignment]
        check(grade("p", "c", LEXICAL_CANDIDATE) == SUPPORTED,
              "a confirming cascade DOES promote -- the gate is not merely refusing everything")
    finally:
        cascade.verdict = _real                             # type: ignore[assignment]

    # ── structural: no other path can return SUPPORTED ──────────────────────
    # checker/rings.py's technique pointed at a verdict instead of an import. A comment
    # saying "only the gate promotes" relies on every future diff being read by someone who
    # remembers; an AST walk does not forget.
    root = Path(__file__).resolve().parent.parent
    offenders = []
    scanned = 0
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".claude/", "build/")) or rel in (
                "checker/entailment_gate.py", "checker/claim_verifier.py"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        scanned += 1
        # Does this module take SUPPORTED from claim_verifier?
        imports_it = any(
            isinstance(n, ast.ImportFrom) and (n.module or "").endswith("claim_verifier")
            and any(a.name == "SUPPORTED" for a in n.names)
            for n in ast.walk(tree))
        if not imports_it:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Return) and n.value is not None:
                names = {x.id for x in ast.walk(n.value) if isinstance(x, ast.Name)}
                if "SUPPORTED" in names:
                    offenders.append(f"{rel}:{n.lineno}")

    check(scanned > 150, f"the scan actually walked the repository ({scanned} modules)")
    check(not offenders,
          f"NO module other than this one returns claim_verifier.SUPPORTED ({offenders[:3]})")

    # The scan must be able to find one. Without this the check above passes on a broken
    # scanner -- the vacuity that a clean structural result is most prone to.
    _probe = ast.parse("from checker.claim_verifier import SUPPORTED\n"
                       "def f():\n    return SUPPORTED\n")
    _found = [n for n in ast.walk(_probe) if isinstance(n, ast.Return)
              and any(isinstance(x, ast.Name) and x.id == "SUPPORTED"
                      for x in ast.walk(n.value))]
    check(len(_found) == 1,
          "...and the scanner detects a synthetic offender, so the clean result is evidence")

    # ── the bar, re-measured on every run ───────────────────────────────────
    res, pairs = _measure()
    tp, fp, fn, tn = _pr(pairs)
    from checker.interval import wilson
    prec_lo, prec_hi = wilson(tp, tp + fp) if tp + fp else (0.0, 0.0)
    rec_lo, rec_hi = wilson(tp, tp + fn) if tp + fn else (0.0, 0.0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    print(f"\n  frozen strict set n={len(pairs)}  (tp {tp}, fp {fp}, fn {fn}, tn {tn})")
    print(f"  precision {precision:.3f}  95% CI [{prec_lo:.3f}, {prec_hi:.3f}]")
    print(f"  recall    {recall:.3f}  95% CI [{rec_lo:.3f}, {rec_hi:.3f}]")
    print(f"  F1 {res.f1:.3f} | false accepts {res.false_accepts} | "
          f"abstention {res.abstention:.2f} | buckets {len(res.buckets)}\n")

    check(res.passed,
          f"the shipped cascade PASSES docs/policy/METRIC_POLICY.md's four conditions "
          f"({res.failures})")
    check(ENABLED is res.passed,
          "ENABLED tracks the measurement: METRIC_POLICY requires shipping DISABLED if the "
          "bar is not met, and this asserts the flag was not left on by hand")
    check(tp + fn > 0 and tp + tn + fp + fn == len(pairs),
          f"every pair was classified, and the set has positives ({tp + fn})")

    print(f"{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
