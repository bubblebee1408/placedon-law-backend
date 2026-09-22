"""Retrieval bake-off: the incumbent (RRF) vs Voyage rerank vs voyage-law-2 dense.

Ready to run the moment VOYAGE_API_KEY exists; refuses cleanly without it. It spends
real (small) money, so it runs only with --run.

    python3 scripts/bakeoff_retrieval.py            # plan + cost estimate; no calls
    python3 scripts/bakeoff_retrieval.py --run      # the bake-off (live Voyage calls)
    python3 scripts/bakeoff_retrieval.py --test     # offline self-test, no network

## The eval, and the incumbent

`checker/cross_section_eval.CASES` -- the frozen 70 plain-English questions, each
labelled with the section that governs it. The incumbent is `checker/fusion.search`
(Reciprocal Rank Fusion of BM25 and MiniLM dense), recorded at p@1 0.80 / recall@5
0.97 in docs/ABLATION_CORRECTED.md. It is RE-MEASURED here in the same run rather
than quoted, so all three arms are scored on one day's corpus.

## The three arms

    RRF             fusion.search(question, 5)
    VOYAGE_RERANK   rerank-2.5 over the RRF top-20 pool (POOL, fixed before any run);
                    its recall is capped by the pool, and the cap is printed
    VOYAGE_DENSE    voyage-law-2: every section embedded as `document`, each question
                    as `query`, cosine top-5

Both Voyage arms read EXACTLY the text MiniLM reads (`dense_index._corpus()`: heading
plus the first 1,200 characters of the body), so a difference is a difference in the
model, not in what it was shown. A longer-text configuration is a separate bake-off.

## The adoption rule (printed with every run)

A challenger is adopted only if its p@1 Wilson 95% interval lies entirely ABOVE the
incumbent's (non-overlapping), and its recall@5 interval does not lie entirely below
the incumbent's. Overlapping intervals are "not resolvable at n=70", never a win.
McNemar on the paired p@1 outcomes is printed as supporting information only. The
run also prints the smallest p@1 count that could count as a win at this n -- and
that recall@5 cannot be won at all when the incumbent sits near 0.97.

## Fail closed

No key -> exit 2. Dense (MiniLM) unavailable -> exit 2: RRF cannot run, and scoring
the challengers against BM25 alone would be a different bake-off. A Voyage service
error mid-run -> exit 3 and NO numbers: a half-run is not a result.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import voyage_model as vm  # noqa: E402
from checker.interval import mcnemar, wilson  # noqa: E402

POOL = 20              # rerank candidate depth, fixed before any measurement
TOP_K = 5
EMBED_BATCH = 128      # sections per embeddings request; ~40K tokens, under law-2's 120K
CHARS_PER_TOKEN = 4    # for the ESTIMATE only; the run records Voyage's own usage
INCUMBENT = "RRF"
REFUSED, ABORTED = 2, 3

RULE = ("ADOPTION RULE: a challenger is adopted only if its p@1 Wilson 95% interval "
        "lies entirely above the incumbent's (non-overlapping), and its recall@5 "
        "interval does not lie entirely below. Overlap = not resolvable, never a win.")


# ── scoring ───────────────────────────────────────────────────────────────────
def score(cases, tops: list[list[str]]) -> dict:
    hits1 = [bool(t) and t[0] == c.section for c, t in zip(cases, tops)]
    hits5 = [c.section in t[:TOP_K] for c, t in zip(cases, tops)]
    n = len(cases)
    return {"n": n, "p1": sum(hits1), "r5": sum(hits5), "hits1": hits1, "hits5": hits5,
            "p1_ci": wilson(sum(hits1), n), "r5_ci": wilson(sum(hits5), n)}


def verdict(ch_ci: tuple[float, float], inc_ci: tuple[float, float]) -> str:
    if ch_ci[0] > inc_ci[1]:
        return "WIN"
    if ch_ci[1] < inc_ci[0]:
        return "LOSS"
    return "OVERLAP"


def adopt(ch: dict, inc: dict) -> bool:
    return (verdict(ch["p1_ci"], inc["p1_ci"]) == "WIN"
            and verdict(ch["r5_ci"], inc["r5_ci"]) != "LOSS")


def min_k_to_win(inc_k: int, n: int) -> int | None:
    """Smallest challenger count whose Wilson interval clears the incumbent's."""
    hi = wilson(inc_k, n)[1]
    return next((k for k in range(n + 1) if wilson(k, n)[0] > hi), None)


def paired(ch: dict, inc: dict) -> tuple[int, int, float]:
    b = sum(c and not i for c, i in zip(ch["hits1"], inc["hits1"]))
    c = sum(i and not c_ for c_, i in zip(ch["hits1"], inc["hits1"]))
    return b, c, mcnemar(b, c)


def render(results: dict) -> str:
    inc = results[INCUMBENT]
    n = inc["n"]
    out = [f"Retrieval bake-off on the frozen {n}-case cross_section_eval", ""]
    for name, r in results.items():
        (a, b), (c, d) = r["p1_ci"], r["r5_ci"]
        out.append(f"  {name:14} p@1 {r['p1']:>2}/{n} = {r['p1'] / n:.2f} [{a:.2f}, {b:.2f}]   "
                   f"recall@5 {r['r5']:>2}/{n} = {r['r5'] / n:.2f} [{c:.2f}, {d:.2f}]")
    out.append("")
    for name, r in results.items():
        if name == INCUMBENT:
            continue
        bb, cc, p = paired(r, inc)
        out.append(f"  {name}: p@1 {verdict(r['p1_ci'], inc['p1_ci'])}, recall@5 "
                   f"{verdict(r['r5_ci'], inc['r5_ci'])} -> "
                   f"{'ADOPT' if adopt(r, inc) else 'NOT ADOPTED'}   "
                   f"(McNemar: {bb} only-challenger vs {cc} only-RRF, p={p:.3f}; information only)")
    k = min_k_to_win(inc["p1"], n)
    k5 = min_k_to_win(inc["r5"], n)
    out += ["", RULE,
            f"At n={n}: a challenger needs p@1 >= {k}/{n} to count as a win"
            if k is not None else f"At n={n}: no p@1 count can clear the incumbent",
            f"         recall@5 >= {k5}/{n}" if k5 is not None else
            f"         recall@5 cannot be WON at n={n} (incumbent {inc['r5']}/{n}); "
            f"only a LOSS is detectable"]
    return "\n".join(out)


# ── the arms ──────────────────────────────────────────────────────────────────
def sections() -> dict[str, str]:
    """The text MiniLM embeds, section number -> text (dense_index._corpus)."""
    from checker import dense_index
    return {num: text for num, _title, text in dense_index._corpus()}


def rrf_arm(question: str, k: int = TOP_K) -> list[str]:
    from checker import fusion
    return [num for num, _, _ in fusion.search(question, k)]


class Ledger:
    """Every Voyage call's recorded usage, so the run's spend is observed."""

    def __init__(self):
        self.calls: list[vm.VoyageCall] = []

    def add(self, call: vm.VoyageCall) -> None:
        self.calls.append(call)

    @property
    def tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)

    @property
    def cost_inr(self) -> float:
        return round(sum(c.cost_inr for c in self.calls), 4)


def rerank_arm(texts: dict[str, str], pool_fn, ledger: Ledger, _transport=None):
    def run(question: str) -> list[str]:
        pool = pool_fn(question, POOL)
        ranked, call = vm.rerank(question, [texts[s] for s in pool],
                                 top_k=min(TOP_K, len(pool)),
                                 _transport=_transport)
        ledger.add(call)
        return [pool[i] for i, _ in ranked]
    return run


def _cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def dense_arm(texts: dict[str, str], questions: list[str], ledger: Ledger,
              _transport=None):
    nums = list(texts)
    doc_vecs: list[list[float]] = []
    for i in range(0, len(nums), EMBED_BATCH):
        vecs, call = vm.embed([texts[s] for s in nums[i:i + EMBED_BATCH]],
                              input_type="document", _transport=_transport)
        ledger.add(call)
        doc_vecs += vecs
    q_vecs: list[list[float]] = []
    for i in range(0, len(questions), EMBED_BATCH):
        vecs, call = vm.embed(questions[i:i + EMBED_BATCH], input_type="query",
                              _transport=_transport)
        ledger.add(call)
        q_vecs += vecs
    by_q = dict(zip(questions, q_vecs))

    def run(question: str) -> list[str]:
        q = by_q[question]
        order = sorted(range(len(nums)), key=lambda j: (-_cosine(q, doc_vecs[j]), nums[j]))
        return [nums[j] for j in order[:TOP_K]]
    return run


def estimate(texts: dict[str, str], questions: list[str]) -> dict:
    """A PRE-RUN estimate from character counts; the run records real usage."""
    tok = lambda s: max(1, len(s) // CHARS_PER_TOKEN)       # noqa: E731
    avg_doc = sum(tok(t) for t in texts.values()) / max(1, len(texts))
    dense = sum(tok(t) for t in texts.values()) + sum(tok(q) for q in questions)
    rer = sum(tok(q) * POOL + avg_doc * POOL for q in questions)
    return {"dense_tokens": int(dense), "rerank_tokens": int(rer),
            "inr": round(vm.cost_inr(vm.LAW, int(dense)) + vm.cost_inr(vm.RERANK, int(rer)), 2)}


def pool_ceiling(cases, pool_fn) -> int:
    return sum(c.section in pool_fn(c.question, POOL) for c in cases)


def run_bakeoff(cases, arms: dict) -> dict:
    return {name: score(cases, [fn(c.question) for c in cases]) for name, fn in arms.items()}


def main(argv: list[str]) -> int:
    from checker.cross_section_eval import CASES
    if not vm.available():
        print("REFUSED: VOYAGE_API_KEY is not set. Put it in .env (never in a shell "
              "history); nothing was called and no Voyage number exists.")
        return REFUSED
    from checker import fusion
    ok, why = fusion.available()
    if not ok:
        print(f"REFUSED: the incumbent cannot run ({why}). Scoring Voyage against "
              f"BM25 alone would be a different bake-off.")
        return REFUSED
    texts = sections()
    questions = [c.question for c in CASES]
    est = estimate(texts, questions)
    print(f"Plan: {len(CASES)} questions, {len(texts)} sections, pool {POOL}. Estimated "
          f"~{est['dense_tokens']:,} embedding + ~{est['rerank_tokens']:,} rerank tokens "
          f"~ Rs {est['inr']} at list price (free allowances not deducted).")
    print(RULE)
    if "--run" not in argv:
        print("Dry plan only. Re-run with --run to make the calls.")
        return 0
    ledger = Ledger()
    try:
        arms = {INCUMBENT: rrf_arm,
                "VOYAGE_RERANK": rerank_arm(texts, rrf_arm, ledger),
                "VOYAGE_DENSE": dense_arm(texts, questions, ledger)}
        results = run_bakeoff(CASES, arms)
    except (vm.VoyageError, vm.VoyageBadResponse) as e:
        print(f"ABORTED after {len(ledger.calls)} calls (Rs {ledger.cost_inr}): {e}\n"
              f"No numbers are reported from a partial run.")
        return ABORTED
    ceiling = pool_ceiling(CASES, rrf_arm)
    print(render(results))
    print(f"\nRerank pool ceiling: {ceiling}/{len(CASES)} gold sections are in the RRF "
          f"top-{POOL}; VOYAGE_RERANK cannot exceed it.")
    print(f"Voyage usage: {len(ledger.calls)} calls, {ledger.tokens:,} tokens, "
          f"Rs {ledger.cost_inr} at list price.")
    out = ROOT / "reports" / f"bakeoff_retrieval_{date.today().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "eval": "checker/cross_section_eval.CASES", "n": len(CASES), "pool": POOL,
        "models": {"rerank": vm.RERANK, "dense": vm.LAW}, "docs": vm.DOC_URLS,
        "rule": RULE, "pool_ceiling": ceiling,
        "usage": {"calls": len(ledger.calls), "tokens": ledger.tokens,
                  "cost_inr_list": ledger.cost_inr},
        "arms": {k: {**{x: v[x] for x in ("p1", "r5", "p1_ci", "r5_ci")},
                     "adopt": k != INCUMBENT and adopt(v, results[INCUMBENT])}
                 for k, v in results.items()}}, indent=2) + "\n")
    print(f"Recorded: {out.relative_to(ROOT)}")
    return 0


def _test() -> None:
    import os
    import urllib.request
    from unittest import mock

    from checker.cross_section_eval import Case

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("bakeoff_retrieval")
    network: list = []
    guard = mock.patch.object(urllib.request, "urlopen",
                              side_effect=lambda *a, **k: network.append(1) or 1 / 0)
    guard.start()
    held = os.environ.pop("VOYAGE_API_KEY", None)
    try:
        # ── the adoption rule, on the incumbent's recorded numbers ───────────
        n = 70
        inc = {"p1": 56, "r5": 68, "p1_ci": wilson(56, n), "r5_ci": wilson(68, n),
               "hits1": [True] * 56 + [False] * 14, "hits5": [True] * 68 + [False] * 2, "n": n}

        def arm(p1, r5):
            return {"p1": p1, "r5": r5, "p1_ci": wilson(p1, n), "r5_ci": wilson(r5, n),
                    "hits1": [True] * p1 + [False] * (n - p1), "n": n,
                    "hits5": [True] * r5 + [False] * (n - r5)}
        check(not adopt(arm(62, 69), inc),
              "62/70 vs RRF's 56/70 overlaps -> NOT adopted, however it looks")
        k = min_k_to_win(56, n)
        check(k == 67 and adopt(arm(67, 68), inc) and not adopt(arm(66, 70), inc),
              f"at n=70 a p@1 win needs {k}/70; 66/70 is not enough")
        check(not adopt(arm(70, 50), inc), "a p@1 win with a recall@5 LOSS is not adopted")
        check(min_k_to_win(68, n) is None,
              "recall@5 at 68/70 cannot be won at n=70 -- and the script says so")
        text = render({INCUMBENT: inc, "X": arm(62, 69)})
        check("ADOPTION RULE" in text and "NOT ADOPTED" in text and "OVERLAP" in text
              and "only a LOSS is detectable" in text, "the rule and the verdict are printed")
        b, c, p = paired(arm(62, 69), inc)
        check((b, c) == (6, 0) and 0 < p < 1, f"McNemar counts discordant pairs ({b}, {c})")

        # ── scoring is on the frozen labels ──────────────────────────────────
        cases = (Case("q1", "173"), Case("q2", "185"), Case("q3", "188"))
        s = score(cases, [["173", "1"], ["1", "185"], ["1", "2", "3", "4", "5", "188"]])
        check((s["p1"], s["r5"]) == (1, 2), "p@1 counts rank 1; recall@5 ignores rank 6+")

        # ── the Voyage arms, through a fake transport ────────────────────────
        texts = {"173": "Section 173. Meetings of Board.", "185": "Section 185. Loans.",
                 "188": "Section 188. Related party."}
        seen: list = []

        def fake(endpoint, payload):
            seen.append((endpoint, payload))
            if endpoint == "embeddings":
                # Three signal dimensions, padded to the model's documented width:
                # parse_embeddings refuses any other, so a 3-float stub would fail the
                # rule rather than the arm under test.
                vec = lambda t: vm._stub_vec(                        # noqa: E731
                    *[1.0 if w in t.lower() else 0.0
                      for w in ("meeting", "loan", "related")])
                return {"model": vm.LAW, "usage": {"total_tokens": 5},
                        "data": [{"index": i, "embedding": vec(t)}
                                 for i, t in enumerate(payload["input"])]}
            docs = payload["documents"]
            order = sorted(range(len(docs)), key=lambda i: "loan" not in docs[i].lower())
            return {"model": vm.RERANK, "usage": {"total_tokens": 9},
                    "data": [{"index": i, "relevance_score": 1.0 - j / 10}
                             for j, i in enumerate(order[:payload.get("top_k", len(docs))])]}
        ledger = Ledger()
        dense = dense_arm(texts, ["board meeting rules", "loan to a director"], ledger, fake)
        check(dense("loan to a director")[0] == "185" and dense("board meeting rules")[0] == "173",
              "dense arm ranks by cosine between query and section vectors")
        kinds = [p["input_type"] for e, p in seen if e == "embeddings"]
        check(kinds == ["document", "query"], "sections go as `document`, questions as `query`")
        rr = rerank_arm(texts, lambda q, k: ["173", "188", "185"], ledger, fake)
        check(rr("loans")[0] == "185", "rerank arm maps result indices back to the pool's sections")
        check(ledger.tokens == 5 + 5 + 9 and ledger.cost_inr > 0,
              f"every call's usage is recorded ({ledger.tokens} tokens)")
        big = {str(i): "x" for i in range(EMBED_BATCH + 3)}
        seen.clear()
        dense_arm(big, ["q"], Ledger(), fake)
        check([len(p["input"]) for e, p in seen] == [EMBED_BATCH, 3, 1],
              "the corpus is embedded in batches of at most EMBED_BATCH")
        check(estimate(texts, ["q"])["inr"] >= 0, "a pre-run estimate is computed without calls")

        # ── refusals ─────────────────────────────────────────────────────────
        check(main(["--run"]) == REFUSED and not network,
              "with no VOYAGE_API_KEY, --run refuses (exit 2) and calls nothing")

        def broken(endpoint, payload):
            raise vm.VoyageServiceError("HTTP 500")
        try:
            run_bakeoff(cases, {"X": rerank_arm(texts, lambda q, k: ["173"], Ledger(), broken)})
            check(False, "a service error mid-run aborts")
        except vm.VoyageServiceError:
            check(True, "a service error mid-run propagates -- main() turns it into exit 3 "
                        "with no numbers, never into a miss")
    finally:
        guard.stop()
        if held is not None:
            os.environ["VOYAGE_API_KEY"] = held
    check(not network, "no network was touched")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        raise SystemExit(main(sys.argv[1:]))
