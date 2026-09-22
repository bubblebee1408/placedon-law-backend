#!/usr/bin/env python3
"""D5 PRELABEL — two models read every public corpus document; a person reads the gaps.

    python3 eval/prelabel/run_prelabel.py --test     # stubs, no network, no spend
    python3 eval/prelabel/run_prelabel.py --live     # real Azure calls
    python3 eval/prelabel/run_prelabel.py --live --limit 3

**This produces no accuracy claim and no ground truth.** Two models agreeing is
not evidence that either is right; it is evidence that they agreed. Every
agreement is labelled `model-verified, NOT expert-verified`, and expert review
(`research/TASKS.md` H-001) remains required before any claim is made about any of
this. That is stated here, in the JSON, and in the Markdown, because a number
travels further than the caveat that came with it.

## The run

  * **Corpus**: `corpus/testdocs/` only (`eval/prelabel/corpus.py` refuses any
    other root). Public documents: real listed-company filings and ICSI
    specimens. Nothing private is read and nothing private is sent.
  * **Two models, same prompt**: `azure:llama-3-3-70b` and `azure:gpt-5-mini`
    through `eval/realrun/azure_model.py`, which imports `local_model._prompt`
    rather than copying it -- so a difference between the two is a difference in
    the models, never in what they were asked. gpt-5-mini answers HTTP 400 to
    temperature 0, so it is sent no temperature; llama is sent temperature 0.
    The temperature actually sent is recorded per call, never assumed.
  * **Every value passes the repository's own gates**: `checker.reasoning.review`
    -- span present, span yields the value, span names this field. A value that
    fails is **dropped, never repaired**, and which gate dropped it is recorded.
  * **A document where either model failed to answer produces no rows.** "Only
    one model supported this" is false when the other model never ran.

## Spend

The Azure deployments are not in `backend/budget.PRICING`, so `cost_inr` has no
rate for them and none is invented; they draw on the Azure for Students credit.
What is recorded is calls and tokens, per model, measured. The ₹500 job cap is
enforced against anything that IS priced, and a separate call ceiling stops a
runaway loop that costs credit rather than rupees.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from checker import bundles                                      # noqa: E402
from checker.reasoning import (FACT_MISBOUND, FACT_NOT_GROUNDED,  # noqa: E402,F401
                               FACT_VALUE_UNSUPPORTED, FACT_WITHOUT_SPAN,
                               Proposal, review)
from eval.prelabel import compare as cmp                          # noqa: E402
from eval.prelabel.corpus import Document, load_all, locate       # noqa: E402

MODEL_A = "azure:llama-3-3-70b"
MODEL_B = "azure:gpt-5-mini"

# The founder asked for about an hour of review. One row is a document, a field,
# two values and a look at the text: a minute is optimistic and it is the number
# the budget is stated in, so the cut is honest about being a cut.
REVIEW_BUDGET_ROWS = 60

# Hard stops. The rupee cap binds anything the repo prices; the call ceiling binds
# everything else, because credit spent is still spent.
SPEND_CAP_INR = 500.0
MAX_CALLS = 70

PACE_SECONDS = 1.0        # Azure for Students is rate-limited per minute

REPORTS = Path(__file__).resolve().parents[2] / "reports"
DOCS = Path(__file__).resolve().parents[2] / "docs"

NOT_A_CLAIM = (
    "Agreement between two models is NOT evidence that either is correct. Both "
    "can be wrong in the same way, and in this repository they already have been "
    "— Indian digit grouping has produced the same 10x misreading more than once. "
    "Nothing here is an accuracy measurement. Expert review by a practising "
    "Company Secretary (research/TASKS.md H-001) is still required.")


# ── one model, one document ───────────────────────────────────────────────────
@dataclass(frozen=True)
class Extraction:
    doc_id: str
    model: str
    ok: bool
    sides: dict = field(default_factory=dict)      # field -> compare.Side
    refusals: tuple = ()                           # (field, violation, detail)
    meta: dict = field(default_factory=dict)
    error: str = ""


def sides_from(proposal: Proposal, document: str) -> tuple[dict, tuple]:
    """Run the repository's gates and turn what survives into comparable sides.

    Three states, kept apart on purpose: ADMITTED (every gate passed), REFUSED
    (proposed, a gate dropped it, and which gate is recorded), ABSENT (the model
    said nothing). Collapsing REFUSED into ABSENT would hide the difference
    between a model that was wrong and a model that was silent.
    """
    reviewed = review(proposal, declared_intents=bundles.capabilities(),
                      document=document)
    sides: dict = {}
    for name, item in reviewed.facts.items():
        sides[name] = cmp.Side(cmp.ADMITTED, item.get("value"),
                               str(item.get("span") or ""))
    refusals = []
    for r in reviewed.refusals:
        name = r.detail.split(":", 1)[0].strip()
        refusals.append((name, r.violation, r.detail))
        if name not in sides:
            proposed = (proposal.facts or {}).get(name)
            value = proposed.get("value") if isinstance(proposed, dict) else proposed
            span = proposed.get("span") if isinstance(proposed, dict) else None
            sides[name] = cmp.Side(cmp.REFUSED, value, str(span or ""), r.violation)
    return sides, tuple(refusals)


def extract_one(doc: Document, model: str, caller) -> Extraction:
    """One document to one model. An exception becomes an ERROR, never an answer."""
    try:
        proposal, meta = caller(doc.text, model=model)
    except Exception as e:                                       # noqa: BLE001
        return Extraction(doc.doc_id, model, False,
                          error=f"{type(e).__name__}: {e}"[:300])
    sides, refusals = sides_from(proposal, doc.text)
    return Extraction(doc.doc_id, model, True, sides, refusals, dict(meta))


# ── the ledger ────────────────────────────────────────────────────────────────
@dataclass
class Ledger:
    """What was spent, measured. Never estimated into a number that looks measured."""
    calls: dict = field(default_factory=dict)
    tokens_in: dict = field(default_factory=dict)
    tokens_out: dict = field(default_factory=dict)
    unmeasured: dict = field(default_factory=dict)
    priced_inr: float = 0.0

    def record(self, model: str, meta: dict) -> None:
        self.calls[model] = self.calls.get(model, 0) + 1
        for key, store in (("tokens_in", self.tokens_in),
                           ("tokens_out", self.tokens_out)):
            n = meta.get(key)
            if isinstance(n, int):
                store[model] = store.get(model, 0) + n
            else:
                self.unmeasured[model] = self.unmeasured.get(model, 0) + 1
        self.priced_inr = round(self.priced_inr + self._price(model, meta), 4)

    @staticmethod
    def _price(model: str, meta: dict) -> float:
        """Rupees, only where the repository has a published rate for the model.

        `backend/budget.cost_inr` raises on a model it has no rate for, and that
        refusal is right: a made-up rate would turn credit spend into a rupee
        figure nobody could check. Unpriced calls are reported as unpriced.
        """
        from backend.budget import PRICING, cost_inr
        name = model.removeprefix("azure:")
        if name not in PRICING:
            return 0.0
        return cost_inr(name, meta.get("tokens_in") or 0, meta.get("tokens_out") or 0)

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    def would_exceed(self, extra_calls: int = 1) -> str:
        if self.priced_inr > SPEND_CAP_INR:
            return (f"priced spend ₹{self.priced_inr} is over the ₹{SPEND_CAP_INR} "
                    f"job cap")
        if self.total_calls + extra_calls > MAX_CALLS:
            return (f"{self.total_calls + extra_calls} calls would pass the "
                    f"{MAX_CALLS}-call ceiling for this job")
        return ""

    def as_dict(self) -> dict:
        return {
            "calls_by_model": dict(self.calls),
            "tokens_in_by_model": dict(self.tokens_in),
            "tokens_out_by_model": dict(self.tokens_out),
            "calls_with_an_unmeasured_token_count": dict(self.unmeasured),
            "priced_inr": self.priced_inr,
            "priced_by": "backend/budget.cost_inr",
            "unpriced_models": [m for m in self.calls
                                if m.removeprefix("azure:") not in _pricing_names()],
            "unpriced_note": (
                "These deployments are not in backend/budget.PRICING, so no rupee "
                "figure is computed for them. They are served on the Azure for "
                "Students credit. Tokens are reported; the rupee cost is OPEN, "
                "not zero."),
            "spend_cap_inr": SPEND_CAP_INR,
            "call_ceiling": MAX_CALLS,
        }


def _pricing_names() -> tuple[str, ...]:
    from backend.budget import PRICING
    return tuple(PRICING)


# ── the run ───────────────────────────────────────────────────────────────────
def run(docs, caller, *, model_a: str = MODEL_A, model_b: str = MODEL_B,
        pace: float = 0.0, budget: int = REVIEW_BUDGET_ROWS) -> dict:
    """Two extractions per document, gated, compared, ordered and cut.

    `caller(text, model=...) -> (Proposal, meta)`. Injected so the whole pipeline
    is testable without a network and without spending anything.
    """
    ledger = Ledger()
    extractions: list[Extraction] = []
    stopped = ""

    for doc in docs:
        for model in (model_a, model_b):
            reason = ledger.would_exceed()
            if reason:
                stopped = reason
                break
            ex = extract_one(doc, model, caller)
            extractions.append(ex)
            if ex.ok:
                ledger.record(model, ex.meta)
            if pace:
                time.sleep(pace)
        if stopped:
            break

    by_doc: dict = {}
    for ex in extractions:
        by_doc.setdefault(ex.doc_id, {})[ex.model] = ex

    comparisons, not_compared, all_rows, agreements = [], [], [], []
    for doc in docs:
        pair = by_doc.get(doc.doc_id) or {}
        a, b = pair.get(model_a), pair.get(model_b)
        if a is None or b is None:
            not_compared.append({"document": doc.doc_id,
                                 "reason": "not run" if stopped else "missing run",
                                 "detail": stopped or "no extraction recorded"})
            continue
        if not (a.ok and b.ok):
            broken = a if not a.ok else b
            not_compared.append({
                "document": doc.doc_id,
                "reason": f"{broken.model} returned no answer",
                "detail": broken.error,
                "why_no_rows": ("'only one model supported this' is not a true "
                                "statement when the other model never answered")})
            continue
        c = cmp.compare_document(doc.doc_id, a.sides, b.sides)
        comparisons.append(c)
        all_rows.extend(c.rows)
        agreements.extend(c.agreements)

    kept, cut = cmp.cut_to_budget(all_rows, budget)
    docs_by_id = {d.doc_id: d for d in docs}
    return {
        "generated": date.today().isoformat(),
        "not_an_accuracy_claim": NOT_A_CLAIM,
        "agreement_label": cmp.AGREEMENT_LABEL,
        "expert_review_task": "research/TASKS.md H-001",
        "models": {"A": model_a, "B": model_b},
        "temperature_sent": {
            m: sorted({str(e.meta.get("temperature")) for e in extractions
                       if e.model == m and e.ok}) or ["(no successful call)"]
            for m in (model_a, model_b)},
        "corpus": {"root": "corpus/testdocs", "documents_loaded": len(docs),
                   "real": sum(1 for d in docs if d.kind == "real"),
                   "specimen": sum(1 for d in docs if d.kind == "specimen")},
        "documents_compared": len(comparisons),
        "documents_not_compared": not_compared,
        "fields_per_document": len(cmp.KNOWN_FIELDS),
        "agreements": [_row_json(r, docs_by_id) for r in cmp.order(agreements)],
        "disagreements_kept": [_row_json(r, docs_by_id) for r in kept],
        "disagreements_cut": [_row_json(r, docs_by_id) for r in cut],
        "cut_summary": cmp.cut_summary(cut),
        "review_budget_rows": budget,
        "counts": {
            "agree": len(agreements),
            "disagree": sum(1 for r in all_rows if r.outcome == cmp.DISAGREE),
            "one_sided": sum(1 for r in all_rows if r.outcome == cmp.ONE_SIDED),
            "neither": sum(len(c.neither) for c in comparisons),
        },
        "gate_refusals": [
            {"document": ex.doc_id, "model": ex.model, "field": name,
             "violation": violation, "detail": detail}
            for ex in extractions for name, violation, detail in ex.refusals],
        "stopped_early": stopped,
        "spend": ledger.as_dict(),
        "runs": [{"document": e.doc_id, "model": e.model, "ok": e.ok,
                  "error": e.error, "meta": e.meta} for e in extractions],
    }


def _row_json(row, docs_by_id) -> dict:
    doc = docs_by_id.get(row.document)
    anchor = locate(doc, row.anchor_span) if doc and row.anchor_span else None
    return {
        "document": row.document,
        "file": doc.path if doc else "",
        "kind": doc.kind if doc else "",
        "anchor": (f"{doc.path}:{anchor.line}" if doc and anchor else ""),
        "anchor_line": anchor.line if anchor else None,
        "field": row.field,
        "priority": row.priority,
        "priority_reason": row.priority_reason,
        "outcome": row.outcome,
        "model_a": _side_json(row.a),
        "model_b": _side_json(row.b),
        "document_text_at_anchor": anchor.quote if anchor else
            "(no anchor: no admitted span to locate)",
        "verdict": "",
        "label": (cmp.AGREEMENT_LABEL if row.outcome == cmp.AGREE else ""),
    }


def _side_json(side) -> dict:
    return {"state": side.state, "value": _jsonable(side.value),
            "span": side.span, "refused_by": side.refusal}


def _jsonable(v):
    return v if isinstance(v, (str, int, float, bool, type(None))) else str(v)


# ── the human list ────────────────────────────────────────────────────────────
def _cell(text: str, width: int = 0) -> str:
    """Markdown-table-safe. A pipe inside a document quote would break the row."""
    out = " ".join(str(text or "").split()).replace("|", "\\|")
    if width and len(out) > width:
        out = out[:width - 1] + "…"
    return out


def _value_cell(side) -> str:
    if side["state"] == cmp.ADMITTED:
        return f"`{_cell(side['value'], 40)}`"
    if side["state"] == cmp.REFUSED:
        return (f"— proposed `{_cell(side['value'], 28)}`, dropped by "
                f"`{side['refused_by']}`")
    return "— (said nothing)"


def render_markdown(result: dict) -> str:
    a, b = result["models"]["A"], result["models"]["B"]
    c = result["counts"]
    L: list[str] = []
    w = L.append

    w(f"# Pre-label review list — {result['generated']}")
    w("")
    w("> **This is not an accuracy claim, and it is not ground truth.**")
    w(f"> {NOT_A_CLAIM}")
    w("")
    w("Two models read each public corpus document independently, with the same "
      "prompt and the same declared fields. Every value below survived this "
      "repository's own gates: the span must be present in the document, the span "
      "must yield the value, and the span must not name a different field. A value "
      "that failed a gate was **dropped, never repaired** — the drop is recorded, "
      "not corrected.")
    w("")
    w("Where both models produced the same supported value, the field is labelled "
      f"**{cmp.AGREEMENT_LABEL}**. Where they differ, or only one of them supports "
      "a value, there is a row below for a person to settle.")
    w("")

    w("## What ran")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| Model A | `{a}`, temperature "
      f"{', '.join(result['temperature_sent'][a])} |")
    w(f"| Model B | `{b}`, temperature "
      f"{', '.join(result['temperature_sent'][b])} (rejects temperature 0) |")
    w(f"| Corpus | `corpus/testdocs/` — {result['corpus']['documents_loaded']} "
      f"public documents ({result['corpus']['real']} real filings, "
      f"{result['corpus']['specimen']} ICSI specimens) |")
    w(f"| Documents compared | {result['documents_compared']} |")
    w(f"| Fields per document | {result['fields_per_document']} |")
    w(f"| Agreements | {c['agree']} — {cmp.AGREEMENT_LABEL} |")
    w(f"| Disagreements (both supported, different values) | {c['disagree']} |")
    w(f"| One-sided (only one model supported a value) | {c['one_sided']} |")
    w(f"| Neither model supported a value | {c['neither']} |")
    w("")
    w("Anchors are `file:line` in the corpus text file, reproducible with "
      "`sed -n '<line>p' <file>`. **No page numbers**: the repository's own page "
      "reader agrees with an independent reader on 0 of 14 corpus PDFs "
      "(`docs/OVERNIGHT_REPORT_2026_09_14.md` §4), so a page number here would "
      "look checkable and not be.")
    w("")

    nc = result["documents_not_compared"]
    if nc:
        w("## Documents not compared")
        w("")
        w("A one-sided row says one model supported a value and the other did not. "
          "That is false when the other model never answered, so these documents "
          "produce no rows at all.")
        w("")
        w("| Document | Why |")
        w("|---|---|")
        for row in nc:
            w(f"| `{_cell(row['document'])}` | {_cell(row['reason'])} — "
              f"{_cell(row['detail'], 150)} |")
        w("")

    w("## The list")
    w("")
    w(f"Sorted by how likely the field is to change an obligation row: the s.135 "
      f"CSR and s.2(85) small-company inputs first, then the date and period "
      f"fields that decide which year and which deadline those figures are tested "
      f"against, then identity. At equal priority a contradiction sorts before a "
      f"gap. **{len(result['disagreements_kept'])} rows kept**, a budget of "
      f"{result['review_budget_rows']}.")
    w("")
    cut = result["cut_summary"]
    if cut["cut_total"]:
        w(f"**{cut['cut_total']} rows were cut to keep this to about an hour.** "
          f"By field: "
          + ", ".join(f"`{k}` ×{v}" for k, v in sorted(cut["by_field"].items()))
          + ". By outcome: "
          + ", ".join(f"{k} ×{v}" for k, v in sorted(cut["by_outcome"].items()))
          + ". Every cut row is in the JSON under `disagreements_cut` — cut, not "
            "dropped.")
        w("")
    w("Verdict column is blank by design. No agent writes it.")
    w("")
    w("| # | Document | Anchor | Field | A · llama-3-3-70b | B · gpt-5-mini | "
      "What the document says there | Verdict |")
    w("|---:|---|---|---|---|---|---|---|")
    for n, r in enumerate(result["disagreements_kept"], start=1):
        w(f"| {n} | `{_cell(r['document'], 44)}` | `{_cell(r['anchor'], 52)}` | "
          f"`{r['field']}` | {_value_cell(r['model_a'])} | "
          f"{_value_cell(r['model_b'])} | "
          f"{_cell(r['document_text_at_anchor'], 240)} |  |")
    if not result["disagreements_kept"]:
        w("| — | — | — | — | — | — | no rows | |")
    w("")

    w("## Agreements — model-verified, NOT expert-verified")
    w("")
    w("Listed so the founder can see what the two models did not disagree about. "
      "**Agreement is not correctness.** These are not verified, and none of them "
      "may be cited as accurate.")
    w("")
    if result["agreements"]:
        w("| Document | Field | Value | Anchor |")
        w("|---|---|---|---|")
        for r in result["agreements"]:
            w(f"| `{_cell(r['document'], 44)}` | `{r['field']}` | "
              f"`{_cell(r['model_a']['value'], 40)}` | "
              f"`{_cell(r['anchor'], 52)}` |")
    else:
        w("None.")
    w("")

    w("## Cost")
    w("")
    s = result["spend"]
    w("| Model | Calls | Tokens in | Tokens out | ₹ |")
    w("|---|---:|---:|---:|---|")
    for m in (a, b):
        priced = m.removeprefix("azure:") in _pricing_names()
        w(f"| `{m}` | {s['calls_by_model'].get(m, 0)} | "
          f"{s['tokens_in_by_model'].get(m, 0)} | "
          f"{s['tokens_out_by_model'].get(m, 0)} | "
          f"{'₹' + str(s['priced_inr']) if priced else 'unpriced — see below'} |")
    w("")
    w(f"**₹ priced by `backend/budget.cost_inr`: ₹{s['priced_inr']} against the "
      f"₹{s['spend_cap_inr']} job cap.** {s['unpriced_note']} A call ceiling of "
      f"{s['call_ceiling']} bounds the credit spend that the rupee cap cannot see.")
    if result["stopped_early"]:
        w("")
        w(f"**The run stopped early:** {result['stopped_early']}")
    w("")

    if result["gate_refusals"]:
        w("## What the gates dropped")
        w("")
        w("Recorded, not repaired. A model proposed these and the repository "
          "refused them; they are evidence about the models, not about the "
          "documents.")
        w("")
        w("| Document | Model | Field | Gate |")
        w("|---|---|---|---|")
        for g in result["gate_refusals"][:120]:
            w(f"| `{_cell(g['document'], 44)}` | `{g['model']}` | "
              f"`{_cell(g['field'], 26)}` | `{g['violation']}` |")
        if len(result["gate_refusals"]) > 120:
            w("")
            w(f"({len(result['gate_refusals'])} in total; the rest are in the JSON "
              f"under `gate_refusals`.)")
        w("")

    w("---")
    w("")
    w(f"Machine-readable: `reports/prelabel_{result['generated']}.json`. "
      f"Produced by `eval/prelabel/run_prelabel.py --live`. "
      f"**{NOT_A_CLAIM}**")
    w("")
    return "\n".join(L)


def write_outputs(result: dict) -> tuple[Path, Path]:
    REPORTS.mkdir(exist_ok=True)
    j = REPORTS / f"prelabel_{result['generated']}.json"
    m = DOCS / f"PRELABEL_REVIEW_{result['generated']}.md"
    j.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    m.write_text(render_markdown(result), encoding="utf-8")
    return j, m


def _azure_caller():
    from eval.realrun import azure_model
    if not azure_model.available():
        raise SystemExit(
            "AZURE_AI_API_KEY / AZURE_AI_ENDPOINT are not set. Refusing to run: "
            "an empty result is indistinguishable from a corpus with nothing in it.")
    return azure_model.extract


def main(argv: list[str]) -> int:
    if "--test" in argv:
        _test()
        return 0
    if "--live" not in argv:
        docs = load_all()
        print(f"{len(docs)} public documents in corpus/testdocs. "
              f"{len(docs) * 2} calls would be made to {MODEL_A} and {MODEL_B}.")
        print("Nothing was sent. Re-run with --live to spend.")
        return 0

    limit = 0
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    docs = load_all()
    if limit:
        docs = docs[:limit]
    print(f"[prelabel] {len(docs)} documents × 2 models", flush=True)
    result = run(docs, _azure_caller(), pace=PACE_SECONDS)
    j, m = write_outputs(result)
    c = result["counts"]
    print(f"[prelabel] agree={c['agree']} disagree={c['disagree']} "
          f"one_sided={c['one_sided']} neither={c['neither']}")
    print(f"[prelabel] {j}\n[prelabel] {m}")
    return 0


# ── tests: stubs only. No network, no key, no spend. ──────────────────────────
def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok]   {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("prelabel.run_prelabel")

    doc = Document(
        doc_id="stub/one", path="corpus/testdocs/stub/one.txt", kind="real",
        title="REAL FILED DOCUMENT — stub", source="https://example.gov.in/x",
        text=("NOTICE. The Company is a public company. Its paid up share capital "
              "is Rs. 4,00,00,000 and its turnover for the year was Rs. 30,00,00,000, "
              "against in the previous year Rs. 25,00,00,000. "
              "CIN: L74999KA2019PLC123456. Dated 22 July 2025."),
        line_map=tuple(range(6, 9)))

    def fact(v, span):
        return {"value": v, "span": span}

    replies = {
        MODEL_A: Proposal(facts={
            "company_class": fact("public", "The Company is a public company"),
            "paid_up_capital_rupees": fact(
                40000000, "paid up share capital is Rs. 4,00,00,000"),
            # the current year
            "turnover_rupees": fact(
                300000000, "turnover for the year was Rs. 30,00,00,000"),
            "cin": fact("L74999KA2019PLC123456", "CIN: L74999KA2019PLC123456"),
        }),
        MODEL_B: Proposal(facts={
            "company_class": fact("public", "The Company is a public company"),
            # the 10x Indian-digit-grouping misreading this repository has already
            # seen twice. The gate catches it: the span states 40000000.
            "paid_up_capital_rupees": fact(
                400000000, "paid up share capital is Rs. 4,00,00,000"),
            # the PREVIOUS year's figure, correctly read from a span that names no
            # field. Both sides survive every gate and still contradict: this is
            # the disagreement no gate can settle, and the reason a person looks.
            "turnover_rupees": fact(
                250000000, "in the previous year Rs. 25,00,00,000"),
            # the paid-up figure filed as net worth: real span, real value, wrong
            # field. The binding gate drops it and it is NOT re-filed.
            "net_worth_rupees": fact(
                40000000, "paid up share capital is Rs. 4,00,00,000"),
            "document_date": fact("2025-07-22", "Dated 22 July 2025"),
        }),
    }

    calls: list[tuple] = []

    def stub(text: str, *, model: str):
        calls.append((model, len(text)))
        meta = {"model": model, "served_by": model, "parse": "OK",
                "temperature": 0 if model == MODEL_A else None,
                "tokens_in": 100, "tokens_out": 20}
        return replies[model], meta

    r = run([doc], stub)

    check([m for m, _ in calls] == [MODEL_A, MODEL_B],
          "each document goes to both models, once each")
    check(len({n for _, n in calls}) == 1,
          "both models are sent the SAME text — a difference is the model's")

    kept = r["disagreements_kept"]
    fields = {row["field"]: row for row in kept}
    check(r["counts"]["agree"] == 1 and r["agreements"][0]["field"] == "company_class",
          "a field both models supported identically is an agreement")
    check(r["agreements"][0]["label"] == cmp.AGREEMENT_LABEL,
          "the agreement carries the model-verified-NOT-expert-verified label")
    to = fields.get("turnover_rupees")
    check(to is not None and to["outcome"] == cmp.DISAGREE,
          "two supported values that contradict become a DISAGREE row")
    check(to["model_a"]["value"] == 300000000 and to["model_b"]["value"] == 250000000,
          "both raw values reach the row; neither is corrected and neither wins")
    check("Rs. 25,00,00,000" in doc.text and "Rs. 30,00,00,000" in doc.text,
          "the disagreement is real: the document states both figures")

    # The gate, end to end — and what it means for the comparison.
    pu = fields.get("paid_up_capital_rupees")
    check(pu is not None and pu["outcome"] == cmp.ONE_SIDED
          and pu["model_a"]["state"] == cmp.ADMITTED
          and pu["model_b"]["state"] == cmp.REFUSED
          and pu["model_b"]["refused_by"] == FACT_VALUE_UNSUPPORTED,
          "the 10x misreading is dropped by value-support, so the field becomes "
          "one-sided — and WHICH gate dropped it is on the row")
    check(pu["model_b"]["value"] == 400000000,
          "the refused value is still shown to the founder, unrepaired")
    check("net_worth_rupees" not in fields,
          "a field nobody supported produces no row — there is no value to settle")
    viol = {g["violation"] for g in r["gate_refusals"]}
    check(FACT_VALUE_UNSUPPORTED in viol and FACT_MISBOUND in viol,
          f"every gate that fired is recorded in the report ({sorted(viol)})")
    check(any(g["field"] == "net_worth_rupees"
              and g["violation"] == FACT_MISBOUND for g in r["gate_refusals"]),
          "a paid-up figure filed as net worth is refused as misbound, not re-filed")

    # Anchors.
    check(fields["turnover_rupees"]["anchor"].startswith("corpus/testdocs/")
          and "Rs. 30,00,00,000" in fields["turnover_rupees"]
          ["document_text_at_anchor"],
          "a row carries a file:line anchor and what the document says there")

    # Ordering and the blank verdict.
    check([row["field"] for row in kept][0] == "turnover_rupees",
          f"the highest-priority contradiction is the first row "
          f"({[row['field'] for row in kept][:3]})")
    check(all(row["verdict"] == "" for row in kept),
          "every verdict cell is blank")

    # ── a model that failed produces NO rows for that document ────────────────
    def half_dead(text: str, *, model: str):
        if model == MODEL_B:
            raise RuntimeError("Azure HTTP 429: RateLimitReached")
        return replies[MODEL_A], {"temperature": 0, "tokens_in": 1, "tokens_out": 1}

    r2 = run([doc], half_dead)
    check(not r2["disagreements_kept"] and r2["documents_not_compared"],
          "a document one model could not answer produces no rows at all")
    check("429" in r2["documents_not_compared"][0]["detail"],
          "the reason is Azure's own, recorded verbatim")
    check(r2["documents_compared"] == 0, "and it is not counted as compared")

    # ── spend guards ──────────────────────────────────────────────────────────
    led = Ledger()
    led.record(MODEL_A, {"tokens_in": 10, "tokens_out": 2})
    check(led.priced_inr == 0.0 and MODEL_A in led.as_dict()["unpriced_models"],
          "an Azure deployment has no repo price, so no rupee figure is invented")
    check("OPEN, not zero" in led.as_dict()["unpriced_note"],
          "the unpriced cost is reported as OPEN, never as zero")
    led.record("claude-haiku-4-5", {"tokens_in": 1_000_000, "tokens_out": 0})
    check(led.priced_inr > 90, f"a PRICED model is charged through "
                               f"backend/budget.cost_inr (₹{led.priced_inr})")
    led.priced_inr = SPEND_CAP_INR + 1
    check("₹500.0 job cap" in led.would_exceed(),
          "the ₹500 cap stops the run")
    led.priced_inr = 0.0
    led.calls = {MODEL_A: MAX_CALLS}
    check("call ceiling" in led.would_exceed(),
          "the call ceiling stops a runaway that spends credit, not rupees")

    spent: list = []

    def counting(text: str, *, model: str):
        spent.append(model)
        return replies[MODEL_A], {"temperature": 0, "tokens_in": 1, "tokens_out": 1}

    r3 = run([doc] * 60, counting)
    check(len(spent) <= MAX_CALLS and r3["stopped_early"],
          f"a long run stops at the ceiling ({len(spent)} calls) and says so")

    # ── the review budget ─────────────────────────────────────────────────────
    r4 = run([doc], stub, budget=1)
    check(len(r4["disagreements_kept"]) == 1
          and r4["cut_summary"]["cut_total"] == len(r4["disagreements_cut"]) > 0,
          "the list is cut to the budget and the cut is counted")
    check(r4["disagreements_cut"], "cut rows are still written, not dropped")

    # ── no accuracy claim anywhere in the rendered document ───────────────────
    md = render_markdown(r)
    check("NOT expert-verified" in md and "not evidence" in md.lower(),
          "the document says agreement is not evidence of correctness")
    check("research/TASKS.md H-001" in md,
          "the document names the expert-review task that is still required")
    # A substring ban is the wrong test: the words that would make a claim are the
    # same words the disclaimer needs in order to deny it. So every risky word must
    # sit inside a NEGATION, and an assertion of it fails.
    risky = ("accurate", "accuracy", "ground truth", "is correct", "proves",
             "proven", "confirms")
    negators = ("not", "never", "no ", "n't", "nothing", "neither")
    lower = md.lower()
    asserted = []
    for word in risky:
        at = lower.find(word)
        while at >= 0:
            before = lower[max(0, at - 70):at]
            if not any(neg in before for neg in negators):
                asserted.append(f"{word!r} @ …{md[max(0, at - 50):at + 20]}…")
            at = lower.find(word, at + 1)
    check(not asserted, f"every accuracy word in the document sits inside a "
                        f"negation — none is asserted ({asserted[:2]})")
    import re as _re
    pages = _re.findall(r"\bp(?:age|p|\.)\s*\d+", lower)
    check(not pages, f"no page number is claimed anywhere ({pages[:3]})")
    check("page number here would" in md,
          "and the document says why there is no page number")
    check(md.count("| Verdict |") == 1 and "|  |" in md,
          "the verdict column exists and is empty")

    # The JSON is JSON, and carries the same warning.
    blob = json.dumps(r)
    check(json.loads(blob)["not_an_accuracy_claim"] == NOT_A_CLAIM,
          "the machine file carries the same warning as the human one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
