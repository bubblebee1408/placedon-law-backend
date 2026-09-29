"""One harness, every routable model, on the two tasks PLAN_22 E1 and E2 name.

## What it does NOT do

**It never edits checker/router.py.** PLAN_22 D2: a model is promoted only when its 95%
interval clears the incumbent's AND a person edits the table. This script produces the
interval. The person is still the person. It reads `router._PREFERENCE` to find out which
models are served and writes nothing back.

**It never asks a model to score anything.** Every number here is computed by comparing
strings and offsets: a sentence traced or it did not, a span matched byte for byte or it
did not, a clause was found or was missed. An LLM judge would be a model marking a model's
homework, and PLAN_22 E1-E5 says deterministic scoring for that reason.

## The two tasks

**Research (E1).** `checker.cross_section_eval.CASES` -- the frozen 70 plain-English
questions, each with the section that answers it. Used rather than a fresh 60 because it
is already frozen, already the retrieval eval, and sharing one set is what makes E1 and E3
comparable. Metrics: traced-sentence rate, refusal rate, rupees per task.

**Clause extraction (E2).** The CUAD test split: 102 contracts, 41 clause types each,
labelled with verbatim spans. ONE call per contract, not per clause -- 41 calls a contract
is 4,182 calls a model, which is neither affordable nor necessary, since the model is
shown the clause list and asked which are present. Metrics: per-clause F1, exact-span
rate, rupees per task.

## The budget

Azure bills a student-credit pot that no counter in this repository can read (PLAN_22 D5,
`router.estimate_inr`). So the guard here is denominated in CALLS, which is the thing that
can actually be counted, and it is a PRE-FLIGHT: the plan is printed and refused before
the first request, never discovered halfway through. `--max-calls` is the ceiling and it
has a deliberately small default.

Run:  PYTHONPATH=. python3 scripts/bakeoff_models.py --test          # offline, gated
      PYTHONPATH=. python3 scripts/bakeoff_models.py --plan          # what it would spend
      PYTHONPATH=. python3 scripts/bakeoff_models.py --run --contracts 5
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checker.interval import bootstrap_ci, wilson  # noqa: E402

CUAD = Path(__file__).resolve().parents[1] / "corpus" / "benchmark" / "cuad" / "test.json"
REPORTS = Path(__file__).resolve().parents[1] / "reports"

# Small on purpose. A bake-off that quietly spends an afternoon of credit is a bake-off
# nobody runs twice.
DEFAULT_MAX_CALLS = 200

# CUAD contracts run to 100k+ characters and a narration prompt is not a place to discover
# that. Truncation is RECORDED per contract, because a clause the model never saw is a
# false negative caused by this constant and not by the model.
MAX_CONTRACT_CHARS = 18_000

RULE = ("ADOPTION RULE (PLAN_22 D2): a challenger is adopted only when its 95% interval "
        "lies entirely above the incumbent's AND a person edits checker/router.py. "
        "Overlapping intervals are 'not resolvable at this n', never a win. This script "
        "does not edit the router.")


# ── the clause question set, read from CUAD itself ───────────────────────────

def clause_types(doc: dict) -> list[str]:
    """The 41 clause labels, taken from the data rather than typed out here."""
    qas = doc["data"][0]["paragraphs"][0]["qas"]
    return [q["id"].split("__", 1)[1] if "__" in q["id"] else q["question"][:40]
            for q in qas]


def gold(doc: dict, limit: int | None = None) -> list[dict]:
    """(title, context, {clause: [spans]}) per contract, spans verbatim from the labels."""
    out = []
    for entry in doc["data"][:limit]:
        para = entry["paragraphs"][0]
        by_clause: dict[str, list[str]] = {}
        for q in para["qas"]:
            name = q["id"].split("__", 1)[1] if "__" in q["id"] else q["question"][:40]
            texts = [a["text"] for a in q["answers"]]
            if texts:
                by_clause[name] = texts
        out.append({"title": entry.get("title", ""), "context": para["context"],
                    "clauses": by_clause})
    return out


# ── scoring: strings and offsets only ────────────────────────────────────────

@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def f1(self) -> float:
        p = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0
        r = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0
        return round(2 * p * r / (p + r), 4) if (p + r) else 0.0


def norm(s: str) -> str:
    """Whitespace-insensitive comparison. NOT case- or word-insensitive: a span is evidence."""
    return re.sub(r"\s+", " ", s or "").strip()


def span_exact(proposed: str, context: str) -> bool:
    """A proposed span is exact when it occurs VERBATIM in the contract it came from."""
    return bool(proposed) and norm(proposed) in norm(context)


def score_contract(proposed: dict[str, list[str]], truth: dict[str, list[str]],
                   context: str) -> tuple[dict[str, Counts], int, int]:
    """Per-clause TP/FP/FN, plus (exact spans, proposed spans).

    A clause counts as found when the model proposed a span for it AND that span occurs in
    the contract. A quote that is not in the document is not a weaker answer, it is a
    different failure, and counting it as a hit is how a hallucination scores a point.
    """
    per: dict[str, Counts] = {}
    exact = total = 0
    for clause in set(proposed) | set(truth):
        c = per.setdefault(clause, Counts())
        got = [s for s in proposed.get(clause, []) if s]
        want = truth.get(clause, [])
        total += len(got)
        real = [s for s in got if span_exact(s, context)]
        exact += len(real)
        if real and want:
            c.tp += 1
        elif real and not want:
            c.fp += 1
        elif want and not real:
            c.fn += 1
    return per, exact, total


# ── a 429 is a minute, not a verdict ─────────────────────────────────────────

RETRY_BASE_SECONDS = 25.0


def with_backoff(call, *, sleep=None, tries: int = 3, base: float = RETRY_BASE_SECONDS):
    """Wrap a model callable so Azure's own rate limit waits instead of scoring zero.

    Measured 29-09-2026: eight two-token calls in a row succeeded while twelve full
    narration prompts returned HTTP 429, so what binds is tokens-per-minute. Without this
    a bake-off measures Azure's quota and calls it the model's refusal rate -- the single
    easiest way to publish a wrong number here.

    `sleep` is INJECTED and defaults to None, so the gated tests exercise every branch and
    never wait. A library that sleeps on its own is a library that hangs a test suite.
    """
    def _c(prompt: str) -> str:
        last = None
        for i in range(tries):
            try:
                return call(prompt)
            except Exception as e:                               # noqa: BLE001
                from checker.azure_model import RateLimited
                if not isinstance(e, RateLimited) or sleep is None or i == tries - 1:
                    raise
                last = e
                sleep(base * (i + 1))
        raise last                                               # pragma: no cover
    return _c


# ── the arms: whatever route() would serve, read and never written ───────────

def served_models() -> list[tuple[str, str]]:
    """(provider, model) for the narration chain, in the router's own order."""
    from checker.router import _PREFERENCE, LOW, NARRATION, TEXT, TaskProfile
    return [(p, m) for p, m, _w in _PREFERENCE[TaskProfile(TEXT, LOW, NARRATION)]]


def azure_models() -> list[str]:
    from checker.router import AZURE
    return [m for p, m in served_models() if p == AZURE]


# ── task 1: research answers ─────────────────────────────────────────────────

# The contract is DATA, and it is delimited. The first version concatenated it raw and
# public_only refused all six calls -- correctly: an undelimited prompt is one where
# nothing can be told apart from our own instructions, so nothing in it can be cleared.
# That refusal is the firewall working, and the fix is to wrap, never to unwrap the guard.
CLAUSE_PROMPT = (
    "You are shown a commercial contract and a list of clause types.\n"
    "For each clause type that is PRESENT, quote the exact words from the contract that "
    "are the clause. Copy them verbatim; do not paraphrase, summarise or renumber.\n"
    "If a clause type is absent, omit it entirely. Do not guess.\n"
    "Answer as one JSON object mapping clause type to a list of verbatim quotes, and "
    "nothing else.\n\nCLAUSE TYPES:\n{clauses}\n\nCONTRACT:\n{contract}\n"
)


def clause_prompt(contract: str, clauses: list[str], *, wrap=None) -> str:
    """The prompt, with the contract wrapped as untrusted evidence."""
    if wrap is None:
        from checker.prompt_safety import wrap_untrusted as wrap
    return CLAUSE_PROMPT.format(clauses="\n".join(f"- {x}" for x in clauses),
                                contract=wrap(contract, "contract"))


def parse_clause_reply(raw: str) -> dict[str, list[str]]:
    """The JSON object in a reply, or {}. A reply we cannot read is not a clause found."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        if isinstance(v, str):
            out[str(k)] = [v]
        elif isinstance(v, list):
            out[str(k)] = [x for x in v if isinstance(x, str)]
    return out


def run_research(model_for, cases, *, answer_fn=None, evidence_fn=None,
                 on_call=None) -> dict:
    """Every case through the real pipeline.

    `model_for(origins)` is a FACTORY and not a callable, because the public_only clearance
    is bound per question: the origins are whichever published corpus files that question's
    evidence came from. It returns None when retrieval abstained, and the pipeline then
    refuses before any model is reached.
    """
    from agents import research_question as rq
    answer_fn = answer_fn or rq.answer
    evidence_fn = evidence_fn or rq.evidence
    written = traced = refused = errored = 0
    inr = 0.0
    per = []
    for c in cases:
        if on_call:
            on_call()
        ev = evidence_fn(c.question)
        call = model_for(tuple(o for _, o in ev))
        t = time.time()
        try:
            o = answer_fn(c.question, model=call, available=("azure",))
        except Exception as e:                                   # noqa: BLE001
            errored += 1
            per.append({"q": c.question[:60], "status": "ERROR",
                        "error": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        n_w = len(o.summary.sentences) if o.summary else 0
        n_t = len(o.summary.traced) if o.summary else 0
        written += n_w
        traced += n_t
        refused += 1 if o.status == rq.REFUSED else 0
        inr += o.route.est_cost_inr if o.route else 0.0
        per.append({"q": c.question[:60], "section": c.section, "status": o.status,
                    "code": o.code, "written": n_w, "traced": n_t,
                    "seconds": round(time.time() - t, 2)})
    n = len(cases)
    return {"n": n, "completed": n - errored,
            "completion_rate": round((n - errored) / n, 4) if n else 0.0,
            "rates_are_over": ("COMPLETED tasks only. A task that errored contributed no "
                               "sentences, so a high traced rate beside a high error count "
                               "is a rate over the survivors -- read the two together."),
            "sentences_written": written, "sentences_traced": traced,
            "traced_rate": round(traced / written, 4) if written else 0.0,
            "traced_ci": wilson(traced, written) if written else (0.0, 0.0),
            "refusals": refused,
            "refusal_rate": round(refused / n, 4) if n else 0.0,
            "refusal_ci": wilson(refused, n) if n else (0.0, 0.0),
            "errors": errored,
            "rupees_total_inr": round(inr, 4),
            "rupees_per_task_inr": round(inr / n, 6) if n else 0.0,
            "per_case": per}


# ── task 2: clause extraction ────────────────────────────────────────────────

def run_clauses(model_call, contracts, clauses, *, on_call=None, wrap=None) -> dict:
    totals: dict[str, Counts] = {}
    exact = proposed = errored = truncated = 0
    per = []
    for c in contracts:
        if on_call:
            on_call()
        ctx = c["context"][:MAX_CONTRACT_CHARS]
        truncated += 1 if len(c["context"]) > MAX_CONTRACT_CHARS else 0
        prompt = clause_prompt(ctx, clauses, wrap=wrap)
        t = time.time()
        try:
            raw = model_call(prompt)
        except Exception as e:                                   # noqa: BLE001
            errored += 1
            per.append({"title": c["title"][:50], "error":
                        f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        got = parse_clause_reply(raw)
        counts, ex, tot = score_contract(got, c["clauses"], ctx)
        for k, v in counts.items():
            agg = totals.setdefault(k, Counts())
            agg.tp += v.tp
            agg.fp += v.fp
            agg.fn += v.fn
        exact += ex
        proposed += tot
        per.append({"title": c["title"][:50], "proposed": tot, "exact": ex,
                    "gold_clauses": len(c["clauses"]),
                    "seconds": round(time.time() - t, 2)})
    f1s = {k: v.f1() for k, v in sorted(totals.items())}
    macro = round(sum(f1s.values()) / len(f1s), 4) if f1s else 0.0
    tp = sum(v.tp for v in totals.values())
    fp = sum(v.fp for v in totals.values())
    fn = sum(v.fn for v in totals.values())
    micro = Counts(tp, fp, fn).f1()
    return {"n_contracts": len(contracts), "clause_types": len(clauses),
            "truncated_contracts": truncated, "errors": errored,
            "per_clause_f1": f1s, "macro_f1": macro, "micro_f1": micro,
            "macro_f1_ci": (bootstrap_ci(list(f1s.values()), lambda s: sum(s) / len(s))
                            if len(f1s) > 1 else (macro, macro)),
            "tp": tp, "fp": fp, "fn": fn,
            "spans_proposed": proposed, "spans_exact": exact,
            "exact_span_rate": round(exact / proposed, 4) if proposed else 0.0,
            "exact_span_ci": wilson(exact, proposed) if proposed else (0.0, 0.0),
            "per_contract": per}


# ── the budget, checked before the first request and not during ──────────────

@dataclass
class Plan:
    models: list[str]
    cases: int
    contracts: int
    max_calls: int
    calls: int = field(init=False)

    def __post_init__(self) -> None:
        self.calls = len(self.models) * (self.cases + self.contracts)

    @property
    def affordable(self) -> bool:
        return self.calls <= self.max_calls

    def render(self) -> str:
        per = self.cases + self.contracts
        lines = [f"PLAN: {len(self.models)} model(s) x ({self.cases} research + "
                 f"{self.contracts} contracts) = {self.calls} calls",
                 f"      {per} calls per model, ceiling {self.max_calls}"]
        if not self.affordable:
            lines += ["",
                      f"REFUSED: {self.calls} calls exceeds --max-calls {self.max_calls}.",
                      "Nothing was sent. Azure bills a student-credit pot this repository",
                      "cannot read (PLAN_22 D5), so the ceiling is denominated in calls --",
                      "the thing that can actually be counted. Lower --cases/--contracts",
                      "or raise --max-calls deliberately."]
        return "\n".join(lines)


def render(report: dict) -> str:
    """The markdown table. Intervals on every rate, because a rate without one is a story."""
    out = ["# Model bake-off — " + report["date"], "", RULE, "",
           "## Research (E1) — " + report["research_set"], "",
           "| model | n | completed | traced-sentence rate | 95% CI | refusal rate | 95% CI | Rs/task |",
           "|---|---|---|---|---|---|---|---|"]
    for name, r in report["research"].items():
        lo, hi = r["traced_ci"]
        rlo, rhi = r["refusal_ci"]
        out.append(f"| `{name}` | {r['n']} | {r['completed']}/{r['n']} | "
                   f"{r['traced_rate']:.3f} "
                   f"({r['sentences_traced']}/{r['sentences_written']}) | "
                   f"[{lo:.3f}, {hi:.3f}] | {r['refusal_rate']:.3f} | "
                   f"[{rlo:.3f}, {rhi:.3f}] | "
                   f"{r['rupees_per_task_inr']:.4f} |")
    out += ["", "## Clause extraction (E2) — CUAD test split", "",
            "| model | contracts | macro F1 | 95% CI | micro F1 | exact-span rate | 95% CI | err |",
            "|---|---|---|---|---|---|---|---|"]
    for name, c in report["clauses"].items():
        lo, hi = c["macro_f1_ci"]
        elo, ehi = c["exact_span_ci"]
        out.append(f"| `{name}` | {c['n_contracts']} | {c['macro_f1']:.3f} | "
                   f"[{lo:.3f}, {hi:.3f}] | {c['micro_f1']:.3f} | "
                   f"{c['exact_span_rate']:.3f} ({c['spans_exact']}/"
                   f"{c['spans_proposed']}) | [{elo:.3f}, {ehi:.3f}] | {c['errors']} |")
    out += ["", "**Every rate is over COMPLETED tasks.** A task that errored contributed "
                "no sentences and no spans, so a high traced rate beside a low completed "
                "count is a rate over the survivors, and the two must be read together.",
            "", "Rupees are Rs 0.00 for every Azure row by `router.estimate_inr`'s own "
                "rule: zero against MONTHLY_CAP_INR, **not** zero cost. Azure for Students "
                "credit is a separate pot no counter here watches.", ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    from checker.cross_section_eval import CASES

    def arg(name, default):
        return type(default)(argv[argv.index(name) + 1]) if name in argv else default

    n_cases = arg("--cases", len(CASES))
    n_contracts = arg("--contracts", 5)
    max_calls = arg("--max-calls", DEFAULT_MAX_CALLS)
    models = azure_models()

    plan = Plan(models, n_cases, n_contracts, max_calls)
    print(plan.render())
    # Exit 2 whenever the plan is unaffordable, --plan included: a command that prints
    # REFUSED and exits 0 is a trap for anything that reads exit codes.
    if not plan.affordable:
        return 2
    if "--plan" in argv:
        return 0
    if "--run" not in argv:
        print("\n(add --run to spend it, or --plan to see this without running)")
        return 0
    if not CUAD.is_file():
        print(f"\nCUAD is not held: {CUAD}. Run scripts/acquire_cuad.py first.")
        return 3

    from checker import azure_model, public_only
    from datetime import date
    doc = json.loads(CUAD.read_text())
    contracts = gold(doc, limit=n_contracts)
    clauses = clause_types(doc)
    cases = list(CASES)[:n_cases]
    spent = [0]

    report = {"date": date.today().isoformat(), "rule": RULE,
              "research_set": "checker/cross_section_eval.CASES",
              "cuad": {"file": str(CUAD.relative_to(Path(__file__).resolve().parents[1])),
                       "contracts_scored": len(contracts), "clause_types": len(clauses),
                       "licence": "CC BY 4.0, The Atticus Project"},
              "plan": {"calls": plan.calls, "max_calls": max_calls},
              "research": {}, "clauses": {}}

    for m in models:
        name = f"azure:{m}"
        print(f"\n== {name} ==")
        res = run_research(
            lambda origins, _m=m: (
                with_backoff(azure_model.as_text_model(origin=origins, model=_m),
                             sleep=time.sleep)
                if origins else None),
            cases, on_call=lambda: spent.__setitem__(0, spent[0] + 1))
        report["research"][name] = res
        print(f"   research: traced {res['traced_rate']:.3f} "
              f"refusals {res['refusal_rate']:.3f} errors {res['errors']}")

        # Clause extraction. The contract is UNTRUSTED text and CUAD is a published
        # benchmark held in this repository, so it clears public_only like any corpus file.
        cuad_origin = public_only.clear_file(CUAD)

        def clause_call(prompt: str, _m=m, _o=cuad_origin) -> str:
            spent[0] += 1
            return azure_model.narrate(prompt, origin=_o, model=_m)

        cl = run_clauses(with_backoff(clause_call, sleep=time.sleep), contracts, clauses)
        report["clauses"][name] = cl
        print(f"   clauses:  macro F1 {cl['macro_f1']:.3f} "
              f"exact-span {cl['exact_span_rate']:.3f} errors {cl['errors']}")

    REPORTS.mkdir(exist_ok=True)
    j = REPORTS / f"bakeoff_{report['date']}.json"
    md = REPORTS / f"bakeoff_{report['date']}.md"
    j.write_text(json.dumps(report, indent=2) + "\n")
    md.write_text(render(report))
    print(f"\nwrote {j}\nwrote {md}\ncalls spent: {spent[0]}")
    return 0


# ── the 3-item offline fixture. No network, no Azure, no corpus. ─────────────

FIXTURE_CONTRACTS = [
    {"title": "alpha", "context": "This Agreement is governed by the laws of Delaware. "
                                  "The term is three years from the Effective Date.",
     "clauses": {"Governing Law": ["governed by the laws of Delaware"],
                 "Agreement Date": ["three years from the Effective Date"]}},
    {"title": "beta", "context": "Neither party may assign this Agreement without consent.",
     "clauses": {"Anti-Assignment": ["may assign this Agreement without consent"]}},
    {"title": "gamma", "context": "The Supplier shall deliver the Goods to the Buyer.",
     "clauses": {}},
]
FIXTURE_CLAUSES = ["Governing Law", "Agreement Date", "Anti-Assignment", "Audit Rights"]


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

    # ── a quote that is not in the document is not a weaker answer ───────────
    ctx = FIXTURE_CONTRACTS[0]["context"]
    check(span_exact("governed by the laws of Delaware", ctx), "a verbatim span is exact")
    check(span_exact("governed  by the\nlaws of Delaware", ctx),
          "...and stays exact across whitespace, which is formatting and not evidence")
    check(not span_exact("governed by the laws of New York", ctx),
          "...while a span that is NOT in the contract is not exact -- the difference "
          "between a quote and an invention")
    check(not span_exact("", ctx), "an empty span is not a span")

    per, ex, tot = score_contract(
        {"Governing Law": ["governed by the laws of Delaware"],
         "Audit Rights": ["the Buyer may audit the Supplier"]},        # invented
        FIXTURE_CONTRACTS[0]["clauses"], ctx)
    check(per["Governing Law"].tp == 1, "a real clause, quoted verbatim, is a true positive")
    check(per["Audit Rights"].tp == 0 and per["Audit Rights"].fp == 0
          and per["Audit Rights"].fn == 0,
          "...while a clause 'found' with an invented quote scores NO true positive -- "
          "counting it would let a hallucination earn a point")
    check(per["Agreement Date"].fn == 1, "a labelled clause nobody proposed is a miss")
    check((ex, tot) == (1, 2),
          f"exact-span counts both halves: 1 of 2 proposed spans was real ({ex}/{tot})")

    c = Counts(tp=1, fp=1, fn=1)
    check(c.f1() == 0.5, f"F1 of one hit, one false alarm and one miss is 0.5 ({c.f1()})")
    check(Counts().f1() == 0.0, "F1 of nothing is 0.0, not a division by zero")

    # ── reading a reply ─────────────────────────────────────────────────────
    check(parse_clause_reply('{"Governing Law": ["x"]}') == {"Governing Law": ["x"]},
          "a JSON object is read")
    check(parse_clause_reply('sure! {"A": "one"} hope that helps')== {"A": ["one"]},
          "...out of a chatty reply, and a bare string becomes a one-item list")
    for junk in ("", "no json here", "[1,2]", "{not json}"):
        check(parse_clause_reply(junk) == {},
              f"...and an unreadable reply is NO clauses, never a guess ({junk[:18]!r})")

    # ── the contract goes in DELIMITED, or public_only refuses the whole call ─
    seen_wrap = []
    pr = clause_prompt("THE CONTRACT BODY", ["Governing Law"],
                       wrap=lambda body, meta: seen_wrap.append((body, meta))
                       or f"<source {meta}>\n{body}\n</source>")
    check(seen_wrap and seen_wrap[0][0] == "THE CONTRACT BODY",
          "the contract is passed to wrap_untrusted, not concatenated raw")
    check("<source" in pr and "</source>" in pr and "Governing Law" in pr,
          "...so the prompt carries a delimited block AND the clause list. The first "
          "version skipped this and public_only refused all six live calls, correctly")

    # ── the budget is refused BEFORE anything is sent ────────────────────────
    p_ok = Plan(["a"], 10, 5, 200)
    p_no = Plan(["a", "b"], 70, 5, 100)
    check(p_ok.calls == 15 and p_ok.affordable, f"a small plan is affordable ({p_ok.calls})")
    check(p_no.calls == 150 and not p_no.affordable,
          f"...and 2 models x 75 tasks exceeds a 100-call ceiling ({p_no.calls})")
    check(Plan(["a"], 1, 1, 1).affordable is False,
          "the ceiling is inclusive-exclusive the obvious way: 2 calls against a 1 ceiling "
          "is refused")
    check("REFUSED" in p_no.render() and "Nothing was sent" in p_no.render(),
          "...saying so, and saying nothing was sent -- the guard is pre-flight, so a run "
          "cannot discover the ceiling halfway through")

    # ── the clause arm, end to end, offline ─────────────────────────────────
    calls = []

    def stub(prompt: str) -> str:
        calls.append(prompt)
        i = len(calls) - 1
        return json.dumps({k: v[:1] for k, v in FIXTURE_CONTRACTS[i]["clauses"].items()})

    res = run_clauses(stub, FIXTURE_CONTRACTS, FIXTURE_CLAUSES)
    check(len(calls) == 3, f"one call per contract, not one per clause ({len(calls)})")
    check(FIXTURE_CLAUSES[0] in calls[0] and "Audit Rights" in calls[0],
          "...and the prompt lists every clause type, which is why one call can do")
    check(res["exact_span_rate"] == 1.0,
          f"a model quoting the contract verbatim scores 1.0 exact-span "
          f"({res['exact_span_rate']})")
    check(res["micro_f1"] == 1.0, f"...and F1 1.0 when it finds exactly the labelled "
                                  f"clauses ({res['micro_f1']})")
    check(res["errors"] == 0 and res["n_contracts"] == 3, "three contracts, no errors")

    def liar(prompt: str) -> str:
        return json.dumps({"Audit Rights": ["a clause that appears in no contract"]})

    bad = run_clauses(liar, FIXTURE_CONTRACTS, FIXTURE_CLAUSES)
    check(bad["exact_span_rate"] == 0.0 and bad["micro_f1"] == 0.0,
          "a model that invents every span scores 0.0 on both -- the scorer is not "
          "measuring enthusiasm")
    check(bad["fn"] == 3, f"...and every labelled clause it missed is counted ({bad['fn']})")

    def boom(prompt: str) -> str:
        raise RuntimeError("transport died")

    err = run_clauses(boom, FIXTURE_CONTRACTS, FIXTURE_CLAUSES)
    check(err["errors"] == 3 and err["spans_proposed"] == 0,
          "a transport failure is counted as an ERROR, never as a model that found nothing")

    # ── a rate limit waits; anything else does not ──────────────────────────
    from checker.azure_model import RateLimited
    waits, tries = [], []

    def flaky(prompt: str) -> str:
        tries.append(1)
        if len(tries) < 3:
            raise RateLimited("Azure HTTP 429: slow down")
        return "ok"

    got = with_backoff(flaky, sleep=waits.append, base=10.0)("p")
    check(got == "ok" and len(tries) == 3, "a 429 is retried until it succeeds")
    check(waits == [10.0, 20.0],
          f"...waiting longer each time rather than hammering the same minute ({waits})")

    waits.clear()
    def always(prompt: str) -> str:
        raise RateLimited("Azure HTTP 429: slow down")
    try:
        with_backoff(always, sleep=waits.append, tries=2, base=1.0)("p")
        check(False, "a persistent 429 eventually raises")
    except RateLimited:
        check(len(waits) == 1,
              f"...after the bounded number of waits, not forever ({waits})")

    waits.clear()
    def broken(prompt: str) -> str:
        raise RuntimeError("the key is wrong")
    try:
        with_backoff(broken, sleep=waits.append)("p")
        check(False, "a non-429 failure is not retried")
    except RuntimeError:
        check(not waits, "a non-429 failure raises at once -- waiting would not fix a bad key")

    check(with_backoff(lambda p: "fine", sleep=None)("p") == "fine",
          "...and with no sleep injected the wrapper is a pass-through, so the gate never waits")

    # ── the research arm, offline, with the pipeline stubbed ────────────────
    class _Sent:
        def __init__(self, traced): self.traced = traced

    class _Sum:
        def __init__(self, t, d): self.sentences = tuple(
            [_Sent(True)] * t + [_Sent(False)] * d)
        @property
        def traced(self): return tuple(s for s in self.sentences if s.traced)

    class _Route:
        provider, model, est_cost_inr = "azure", "m", 0.0

    class _Out:
        def __init__(self, status, t, d):
            self.status, self.code, self.route = status, None, _Route()
            self.summary = _Sum(t, d)

    class _C:
        def __init__(self, q, s): self.question, self.section = q, s

    cases = [_C("q1", "96"), _C("q2", "173"), _C("q3", "149")]
    plan_answers = [_Out("ANSWERED", 3, 0), _Out("PARTIAL", 1, 1), _Out("REFUSED", 0, 0)]
    seen = []

    def fake_answer(q, *, model=None, available=None):
        seen.append(model)
        return plan_answers[len(seen) - 1]

    r = run_research(lambda origins: "MODEL" if origins else None, cases,
                     answer_fn=fake_answer, evidence_fn=lambda q: (("s", "o"),))
    check(r["sentences_written"] == 5 and r["sentences_traced"] == 4,
          f"written and traced are counted from the summary, not inferred from the status "
          f"({r['sentences_traced']}/{r['sentences_written']})")
    check(r["traced_rate"] == 0.8, f"traced-sentence rate is 4/5 ({r['traced_rate']})")
    check(r["refusal_rate"] == round(1 / 3, 4), f"refusal rate is 1/3 ({r['refusal_rate']})")
    lo, hi = r["traced_ci"]
    check(lo < r["traced_rate"] < hi and (hi - lo) > 0.2,
          f"...and every rate carries a Wilson interval, wide at n=5 ([{lo:.2f}, {hi:.2f}])")
    check(seen[0] == "MODEL", "the model is built per question from that question's origins")

    r2 = run_research(lambda origins: None, cases, answer_fn=fake_answer.__func__
                      if hasattr(fake_answer, "__func__") else fake_answer,
                      evidence_fn=lambda q: ())
    check(r2["n"] == 3, "a question whose retrieval abstained still counts as a task")

    # ── it must not be able to promote anything ─────────────────────────────
    # Scanned ABOVE `def _test(` only. Scanning the whole file would match this very
    # list of forbidden tokens, which is how a self-referential check passes by accident
    # -- the same trap scripts/ingest_companies_act.py's "no logic" check fell into.
    body = Path(__file__).read_text().split("def _test(")[0]
    check("_PREFERENCE[" in body,
          "it READS the router's preference table, which is the point of the arms")
    for w in ("_PREFERENCE[TaskProfile", "_PREFERENCE.update", "_PREFERENCE.pop",
              "_PREFERENCE ="):
        check(f"{w} =" not in body and f"{w}=" not in body or w == "_PREFERENCE[TaskProfile",
              f"...and never assigns to it ({w!r})")
    import ast as _ast
    tree = _ast.parse(body)
    writes = []
    for n in _ast.walk(tree):
        if isinstance(n, (_ast.Assign, _ast.AugAssign)):
            for t in ([n.targets] if isinstance(n, _ast.Assign) else [[n.target]]):
                for x in t:
                    if isinstance(x, _ast.Subscript) and isinstance(x.value, _ast.Name) \
                            and x.value.id == "_PREFERENCE":
                        writes.append(n.lineno)
                    if isinstance(x, _ast.Attribute) and isinstance(x.value, _ast.Name) \
                            and x.value.id in {"router", "_PREFERENCE"}:
                        writes.append(n.lineno)
    check(not writes,
          f"AST agrees: no assignment anywhere targets the router or its table {writes}")
    opened = [n.lineno for n in _ast.walk(tree)
              if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
              and n.func.attr == "write_text"]
    check(len(opened) <= 2,
          f"...and it writes at most the two report files, nothing else ({len(opened)})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        raise SystemExit(main(sys.argv))
