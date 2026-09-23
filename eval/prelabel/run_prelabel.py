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
# Every request that leaves the machine counts, including the ones a rate limit
# refused: a retry spends throughput even when it returns nothing.
MAX_ATTEMPTS = 90

# Measured 23-09-2026 on the Azure for Students deployment: llama-3-3-70b answered
# HTTP 429 to a 19,852-token document and answered a 13,070-token one fine twelve
# seconds later. The pace is the deployment's throughput, not politeness.
PACE_SECONDS = 12.0
RETRY_ATTEMPTS = 3
# Capacity 20 on the student deployment is ~20k tokens a minute, and the two
# largest documents in the corpus are ~20k tokens each: they need a nearly idle
# window, not a polite pause. 25 s and 60 s were not enough on 23-09-2026.
RETRY_BACKOFF_SECONDS = (45.0, 90.0)

# Read timeouts, per model. gpt-5-mini spends hidden reasoning tokens before it
# emits anything, and on 23-09-2026 four documents were lost to a 180 s read
# timeout that had nothing to do with what the model could read.
TIMEOUT_SECONDS = {MODEL_A: 180, MODEL_B: 420}

# Azure's own code for it. A rate limit is the deployment's throughput; it says
# nothing about the document and must not be recorded as a model that read it.
RATE_LIMIT_MARKERS = ("429", "ratelimitreached")

REPORTS = Path(__file__).resolve().parents[2] / "reports"
DOCS = Path(__file__).resolve().parents[2] / "docs"

# Where a field's disagreements are already a known open question, point at the
# ledger row rather than opening a second one. Each entry is a row that exists in
# research/TASKS.md today; nothing is invented here.
def _company_classes() -> tuple:
    """The classes the product's own type accepts, read from the type itself."""
    import typing

    from checker.company_profile import CompanyClass
    return tuple(typing.get_args(CompanyClass))


# Fields whose value is a CLOSED set. Read from the declared type rather than
# retyped here, so this cannot drift away from what the product accepts.
DECLARED_VOCABULARY = {"company_class": _company_classes()}


def in_declared_vocabulary(field_name: str, value: object) -> bool | None:
    """True / False / None — None meaning the field has no closed vocabulary.

    Not a judgement about the document. It answers one mechanical question: would
    `CompanyProfile` accept this string at all? "public" yes; "TITAN COMPANY
    LIMITED" no. That distinction is what separates a value the gate dropped
    wrongly from a value the gate admitted wrongly, and both were in this corpus
    on the same field on 23-09-2026.
    """
    allowed = DECLARED_VOCABULARY.get(field_name)
    if allowed is None:
        return None
    return str(value or "").strip().lower() in allowed


KNOWN_OPEN_TASKS = {
    "company_class": ("research/TASKS.md L-007 — map document wording to "
                      "CompanyClass, or keep the extracted class display-only. "
                      "Open since 14-09-2026, founder-owned, blocked on an "
                      "interpretive decision"),
}

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
    # What the model said BEFORE any gate touched it. Kept because a refusal that
    # cannot be replayed cannot be judged -- the R03 lesson from
    # docs/OVERNIGHT_REPORT_2026_09_14.md §3.
    proposed: dict = field(default_factory=dict)


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
            sides[name] = cmp.Side(cmp.REFUSED, value, str(span or ""),
                                   r.violation,
                                   r.detail.split(":", 1)[-1].strip())
    return sides, tuple(refusals)


def extract_one(doc: Document, model: str, caller) -> Extraction:
    """One document to one model. An exception becomes an ERROR, never an answer."""
    try:
        proposal, meta = caller(doc.text, model=model)
    except Exception as e:                                       # noqa: BLE001
        return Extraction(doc.doc_id, model, False,
                          error=f"{type(e).__name__}: {e}"[:300])
    sides, refusals = sides_from(proposal, doc.text)
    proposed = {name: {"value": _jsonable(item.get("value")
                                          if isinstance(item, dict) else item),
                       "span": (item.get("span")
                                if isinstance(item, dict) else None)}
                for name, item in (proposal.facts or {}).items()}
    return Extraction(doc.doc_id, model, True, sides, refusals, dict(meta),
                      proposed=proposed)


class Pacer:
    """Keep at least `gap` seconds between two calls to the SAME deployment.

    The 429 that stopped the first live run is a per-deployment throughput limit.
    Pacing every call against one clock makes llama wait out gpt-5-mini's latency
    as well as its own and buys nothing; this waits only the remainder of the gap
    that deployment actually owes.
    """

    def __init__(self, gap: float, *, clock=time.monotonic, sleeper=time.sleep):
        self.gap = gap
        self._clock = clock
        self._sleep = sleeper
        self._last: dict = {}

    def wait(self, model: str) -> None:
        if self.gap <= 0:
            return None
        last = self._last.get(model)
        now = self._clock()
        if last is not None:
            owed = self.gap - (now - last)
            if owed > 0:
                self._sleep(owed)
        self._last[model] = self._clock()
        return None


# One JSON object per extraction, appended as it is made. Named like the other
# append-only ledgers in this repository (corpus/.asks.jsonl, corpus/.checks.jsonl).
CHECKPOINT = Path(__file__).resolve().parents[2] / "corpus" / ".prelabel_checkpoint.jsonl"


def _checkpoint_key(row: dict) -> tuple:
    return (row.get("document"), row.get("model"))


def load_checkpoint(path: Path) -> dict:
    """Stored extractions, keyed by (document, model). A missing file is empty.

    A malformed line is SKIPPED, not repaired and not fatal: the file is written
    by a process that may be killed mid-line, and half a JSON object is the
    ordinary way that ends.
    """
    out: dict = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("document") and row.get("model"):
            out[_checkpoint_key(row)] = row
    return out


def append_checkpoint(path: Path, ex: Extraction) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    row = {"document": ex.doc_id, "model": ex.model, "ok": ex.ok,
           "error": ex.error, "meta": ex.meta, "proposed": ex.proposed}
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()


def replay(row: dict, doc: Document) -> Extraction:
    """A stored extraction, put back through the SAME gates. Spends nothing.

    The gates run again rather than their verdict being stored, so a resumed run
    and an uninterrupted one cannot drift apart: if a gate changed between them,
    the change applies to every document, not only to the ones bought after it.
    """
    proposal = Proposal(facts=dict(row.get("proposed") or {}))
    sides, refusals = sides_from(proposal, doc.text)
    return Extraction(doc.doc_id, row["model"], True, sides, refusals,
                      dict(row.get("meta") or {}),
                      proposed=dict(row.get("proposed") or {}))


def is_rate_limited(error: str) -> bool:
    low = str(error).lower()
    return any(m in low for m in RATE_LIMIT_MARKERS)


def extract_with_retry(doc: Document, model: str, caller, *,
                       attempts: int = RETRY_ATTEMPTS,
                       sleeper=time.sleep) -> tuple[Extraction, int]:
    """(Extraction, attempts made). A rate limit is retried; nothing else is.

    An HTTP 400 or a content filter is an answer about the request, and repeating
    it spends credit to be told the same thing. A 429 is the deployment's
    throughput, and accepting it as "this model could not read this document"
    would quietly drop the largest documents in the corpus -- which are the real
    filings, and the whole point of the corpus.
    """
    last = Extraction(doc.doc_id, model, False, error="no attempt made")
    for n in range(attempts):
        last = extract_one(doc, model, caller)
        if last.ok or not is_rate_limited(last.error):
            return last, n + 1
        if n + 1 < attempts:
            wait = RETRY_BACKOFF_SECONDS[min(n, len(RETRY_BACKOFF_SECONDS) - 1)]
            sleeper(wait)
    return last, attempts


# ── the ledger ────────────────────────────────────────────────────────────────
@dataclass
class Ledger:
    """What was spent, measured. Never estimated into a number that looks measured."""
    calls: dict = field(default_factory=dict)
    tokens_in: dict = field(default_factory=dict)
    tokens_out: dict = field(default_factory=dict)
    unmeasured: dict = field(default_factory=dict)
    priced_inr: float = 0.0
    attempts: int = 0
    rate_limited: dict = field(default_factory=dict)

    def spend_attempts(self, n: int, model: str = "") -> None:
        """Requests that left the machine, answered or refused."""
        self.attempts += n
        if model and n > 1:
            self.rate_limited[model] = self.rate_limited.get(model, 0) + (n - 1)

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

    def would_exceed(self, extra: int = 1) -> str:
        if self.priced_inr > SPEND_CAP_INR:
            return (f"priced spend ₹{self.priced_inr} is over the ₹{SPEND_CAP_INR} "
                    f"job cap")
        if self.attempts + extra > MAX_ATTEMPTS:
            return (f"{self.attempts + extra} requests would pass the "
                    f"{MAX_ATTEMPTS}-request ceiling for this job")
        return ""

    def as_dict(self) -> dict:
        return {
            "calls_by_model": dict(self.calls),
            "tokens_in_by_model": dict(self.tokens_in),
            "tokens_out_by_model": dict(self.tokens_out),
            "calls_with_an_unmeasured_token_count": dict(self.unmeasured),
            "requests_made": self.attempts,
            "rate_limited_retries_by_model": dict(self.rate_limited),
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
            "request_ceiling": MAX_ATTEMPTS,
        }


def _pricing_names() -> tuple[str, ...]:
    from backend.budget import PRICING
    return tuple(PRICING)


# ── the run ───────────────────────────────────────────────────────────────────
def run(docs, caller, *, model_a: str = MODEL_A, model_b: str = MODEL_B,
        pace: float = 0.0, budget: int = REVIEW_BUDGET_ROWS,
        progress=None, checkpoint: Path | None = None,
        resume: bool = False) -> dict:
    """Two extractions per document, gated, compared, ordered and cut.

    `caller(text, model=...) -> (Proposal, meta)`. Injected so the whole pipeline
    is testable without a network and without spending anything.
    """
    ledger = Ledger()
    extractions: list[Extraction] = []
    stopped = ""
    pacer = Pacer(pace)
    backoff = time.sleep if pace else (lambda _: None)
    stored = load_checkpoint(checkpoint) if (resume and checkpoint) else {}
    reused = 0

    for n, doc in enumerate(docs, start=1):
        for model in (model_a, model_b):
            # A stored SUCCESS is replayed for free. A stored FAILURE is not an
            # answer -- a timeout or a 429 is our side of the wire, and resuming
            # past it would freeze it into the record as the model's silence.
            row = stored.get((doc.doc_id, model))
            if row and row.get("ok"):
                extractions.append(replay(row, doc))
                reused += 1
                if progress:
                    progress(f"[{n}/{len(docs)}] {doc.doc_id} {model} "
                             f"replayed from the checkpoint (no call)")
                continue

            reason = ledger.would_exceed()
            if reason:
                stopped = reason
                break
            pacer.wait(model)
            ex, made = extract_with_retry(doc, model, caller, sleeper=backoff)
            extractions.append(ex)
            if checkpoint:
                append_checkpoint(checkpoint, ex)
            ledger.spend_attempts(made, model)
            if ex.ok:
                ledger.record(model, ex.meta)
            if progress:
                progress(f"[{n}/{len(docs)}] {doc.doc_id} {model} "
                         f"{'ok' if ex.ok else ex.error[:60]} "
                         f"(attempts={made}, requests={ledger.attempts})")
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
        "repeated_shapes": shape_summary(
            [_row_json(r, docs_by_id) for r in cmp.order(all_rows)]),
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
        "resumed_from_checkpoint": reused,
        "spend": ledger.as_dict(),
        "runs": [{"document": e.doc_id, "model": e.model, "ok": e.ok,
                  "error": e.error, "meta": e.meta, "proposed": e.proposed}
                 for e in extractions],
    }


def shape_summary(rows) -> list[dict]:
    """Group the founder's rows by (field, outcome), mechanically.

    No interpretation: a count, and the distinct values each model produced,
    verbatim. Seven rows that are the same mistake seven times read very
    differently from seven unrelated ones, and the difference is visible from the
    values alone without anyone having to characterise them.
    """
    groups: dict = {}
    for r in rows:
        key = (r["field"], r["outcome"])
        g = groups.setdefault(key, {"field": r["field"], "outcome": r["outcome"],
                                    "count": 0, "model_a_values": [],
                                    "model_b_values": [], "documents": []})
        g["count"] += 1
        g["documents"].append(r["document"])
        for side, bucket in ((r["model_a"], "model_a_values"),
                             (r["model_b"], "model_b_values")):
            shown = _shown_value(side)
            if shown not in g[bucket]:
                g[bucket].append(shown)
    return sorted(groups.values(), key=lambda g: (-g["count"], g["field"]))


def _shown_value(side) -> str:
    vocab = side.get("in_declared_vocabulary")
    mark = ("" if vocab is None
            else " [a CompanyClass value]" if vocab
            else " [NOT a CompanyClass value]")
    if side["state"] == cmp.ADMITTED:
        return f"{side['value']}{mark}"
    if side["state"] == cmp.REFUSED:
        return f"(dropped by {side['refused_by']}) {side['value']}{mark}"
    return "(said nothing)"


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
        "model_a": _side_json(row.a, row.field),
        "model_b": _side_json(row.b, row.field),
        "document_text_at_anchor": anchor.quote if anchor else
            "(no anchor: no admitted span to locate)",
        "verdict": "",
        "label": (cmp.AGREEMENT_LABEL if row.outcome == cmp.AGREE else ""),
    }


def _side_json(side, field_name: str = "") -> dict:
    return {"state": side.state, "value": _jsonable(side.value),
            "span": side.span, "refused_by": side.refusal,
            "detail": side.detail,
            "in_declared_vocabulary": (
                in_declared_vocabulary(field_name, side.value)
                if side.state in (cmp.ADMITTED, cmp.REFUSED) else None)}


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
    """The value AND the span it was read from.

    Without the span a contradiction is unsettleable: two models reading two
    different sentences of the same notice is the ordinary case on a 60-page AGM
    notice, and "which sentence did each of them read" is the first question a
    reviewer asks. It belongs in the cell, not only in the JSON.
    """
    vocab = side.get("in_declared_vocabulary")
    flag = ""
    if vocab is False:
        flag = "<br>**not a value `CompanyClass` accepts**"
    elif vocab is True and side["state"] == cmp.REFUSED:
        flag = "<br>*(this IS a value `CompanyClass` accepts)*"
    if side["state"] == cmp.ADMITTED:
        return (f"`{_cell(side['value'], 40)}`{flag}<br>read from "
                f"“{_cell(side['span'], 110)}”")
    if side["state"] == cmp.REFUSED:
        return (f"— proposed `{_cell(side['value'], 28)}`, dropped by "
                f"`{side['refused_by']}`{flag}<br>gate said: "
                f"{_cell(side['detail'], 120)}<br>from "
                f"“{_cell(side['span'], 110)}”")
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
      f"{', '.join(result['temperature_sent'][b])} |")
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

    shapes = result.get("repeated_shapes") or []
    if shapes:
        w("## The same shape, repeated")
        w("")
        w("Grouped by field and outcome, counted mechanically, with the distinct "
          "values each model produced shown verbatim. Nothing here is "
          "characterised — read the values. A row that recurs across many "
          "documents is one thing to settle, not many.")
        w("")
        w("| Field | Outcome | Rows | A · llama-3-3-70b produced | "
          "B · gpt-5-mini produced | Already open as |")
        w("|---|---|---:|---|---|---|")
        for g in shapes:
            w(f"| `{g['field']}` | {g['outcome']} | {g['count']} | "
              f"{_cell('; '.join(g['model_a_values']), 190)} | "
              f"{_cell('; '.join(g['model_b_values']), 190)} | "
              f"{_cell(KNOWN_OPEN_TASKS.get(g['field'], '—'), 170)} |")
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
      f"₹{s['spend_cap_inr']} job cap.** {s['unpriced_note']} A ceiling of "
      f"{s['request_ceiling']} requests bounds the credit spend that the rupee cap "
      f"cannot see; {s['requests_made']} requests were made.")
    if s["rate_limited_retries_by_model"]:
        w("")
        w("Rate-limited retries (HTTP 429, the deployment's throughput — not a "
          "model that could not read the document): "
          + ", ".join(f"`{k}` ×{v}"
                      for k, v in sorted(s["rate_limited_retries_by_model"].items()))
          + ".")
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

    def call(text: str, *, model: str):
        return azure_model.extract(text, model=model,
                                   timeout=TIMEOUT_SECONDS.get(model, 180))
    return call


def render_only(json_path: Path) -> tuple[Path, Path]:
    """Re-render the human list from a stored run. Spends nothing.

    The JSON is the record of what the models said; the Markdown is one view of
    it. Re-rendering must never need another call, or a wording fix would cost
    another 58 requests -- and worse, a second run's answers would quietly replace
    the ones the founder was reviewing.
    """
    result = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return write_outputs(result)


def main(argv: list[str]) -> int:
    if "--test" in argv:
        _test()
        return 0
    if "--render" in argv:
        j, m = render_only(Path(argv[argv.index("--render") + 1]))
        print(f"[prelabel] re-rendered from the stored run\n[prelabel] {j}\n"
              f"[prelabel] {m}")
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
    resume = "--resume" in argv
    print(f"[prelabel] {len(docs)} documents × 2 models"
          f"{' (resuming from the checkpoint)' if resume else ''}", flush=True)
    def say(line: str) -> None:
        print(f"[prelabel] {line}", flush=True)

    result = run(docs, _azure_caller(), pace=PACE_SECONDS, progress=say,
                 checkpoint=CHECKPOINT, resume=resume)
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

    doc2 = Document(
        doc_id="stub/two", path="corpus/testdocs/stub/two.txt", kind="specimen",
        title="ICSI SPECIMEN — stub", source="https://www.icsi.edu/x",
        text=doc.text + " Second specimen.", line_map=tuple(range(6, 9)))

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

    # ── the raw proposal is kept, so a refusal can be replayed ────────────────
    # OVERNIGHT_REPORT_2026_09_14 §3: "without them a refusal can be counted but
    # never replayed (R03)". A gate that drops 118 values has to be judgeable
    # afterwards from the record, without paying for the calls again.
    raw = [run_row for run_row in r["runs"]
           if run_row["model"] == MODEL_B and run_row["ok"]][0]
    check(raw["proposed"]["company_class"]["value"] == "public"
          and raw["proposed"]["net_worth_rupees"]["value"] == 40000000,
          "every raw proposal is stored, INCLUDING the values the gates dropped")
    check(all("proposed" in run_row for run_row in r["runs"] if run_row["ok"]),
          "no successful call is recorded without what the model actually said")

    # ── repeated shapes, counted mechanically ─────────────────────────────────
    shapes = r["repeated_shapes"]
    check(any(sh["field"] == "turnover_rupees" and sh["count"] == 1
              for sh in shapes),
          f"rows are grouped by (field, outcome) with a count ({shapes})")
    check(all(k in cmp.KNOWN_FIELDS for k in KNOWN_OPEN_TASKS)
          and all("research/TASKS.md" in v for v in KNOWN_OPEN_TASKS.values()),
          "a field pointed at an open task points at a real ledger row")
    one = [sh for sh in shapes if sh["field"] == "paid_up_capital_rupees"][0]
    check(one["model_b_values"] == ["(dropped by FACT_VALUE_UNSUPPORTED) 400000000"],  # noqa: E501
          f"the group shows what each model actually produced, verbatim ({one})")

    # ── the per-model timeout is declared, not assumed ────────────────────────
    check(TIMEOUT_SECONDS[MODEL_B] > TIMEOUT_SECONDS[MODEL_A],
          "the reasoning model is given the longer read timeout — four documents "
          "were lost to a 180 s read timeout on 23-09-2026")
    check(set(TIMEOUT_SECONDS) == {MODEL_A, MODEL_B},
          "every model this run uses has a declared timeout")

    # ── pacing is per deployment, not per call ────────────────────────────────
    # The rate limit that produced the 429 is the DEPLOYMENT's. Sleeping between
    # every call paces llama against gpt-5-mini's clock as well as its own, which
    # on this corpus doubled the wall time for no throughput gained.
    class FakeClock:
        def __init__(self) -> None:
            self.t = 0.0
            self.slept: list = []

        def now(self) -> float:
            return self.t

        def sleep(self, n: float) -> None:
            self.slept.append(round(n, 2))
            self.t += n

    fk = FakeClock()
    pacer = Pacer(10.0, clock=fk.now, sleeper=fk.sleep)
    pacer.wait("A")
    check(fk.slept == [], "the first call to a deployment does not wait")
    fk.t = 3.0
    pacer.wait("B")
    check(fk.slept == [], "a different deployment has its own clock")
    fk.t = 7.0
    pacer.wait("A")
    check(fk.slept == [3.0],
          f"the wait is only the remainder of that deployment's gap ({fk.slept})")
    pacer.wait("A")
    check(fk.slept == [3.0, 10.0],
          f"back-to-back on one deployment waits the full gap ({fk.slept})")
    check(Pacer(0.0, clock=fk.now, sleeper=fk.sleep).wait("A") is None
          and fk.slept == [3.0, 10.0],
          "a zero pace never sleeps — the tests must not spend wall clock")

    # ── a rate limit is a retry, not an answer ────────────────────────────────
    # Measured 23-09-2026: the Azure for Students llama-3-3-70b deployment answered
    # HTTP 429 RateLimitReached to a 19,852-token document and answered the same
    # document class fine after a pause. A 429 is the deployment's throughput, not
    # the model's reading, and treating it as "no answer" would silently drop the
    # largest documents in the corpus -- which are the real filings.
    slept: list = []
    tries: list = []

    def limited_twice(text: str, *, model: str):
        tries.append(model)
        if len(tries) < 3:
            raise RuntimeError('Azure HTTP 429: {"error":{"code":"RateLimitReached"}}')
        return replies[MODEL_A], {"temperature": 0, "tokens_in": 5, "tokens_out": 1}

    ex, attempts = extract_with_retry(doc, MODEL_A, limited_twice,
                                      sleeper=slept.append)
    check(ex.ok and attempts == 3,
          f"a rate-limited call is retried and the later answer is used "
          f"({attempts} attempts)")
    check(len(slept) == 2 and slept[1] > slept[0],
          f"the wait grows between attempts ({slept})")

    other: list = []

    def broken(text: str, *, model: str):
        other.append(model)
        raise RuntimeError("Azure HTTP 400: unsupported_value temperature")

    ex, attempts = extract_with_retry(doc, MODEL_A, broken, sleeper=other.append)
    check(not ex.ok and attempts == 1 and len(other) == 1,
          "an error that is NOT a rate limit is not retried — it is an answer "
          "about the request, and repeating it would only spend credit")

    always: list = []

    def never_ok(text: str, *, model: str):
        always.append(model)
        raise RuntimeError("Azure HTTP 429: RateLimitReached")

    ex, attempts = extract_with_retry(doc, MODEL_A, never_ok, sleeper=lambda _: None)
    check(not ex.ok and attempts == RETRY_ATTEMPTS and "429" in ex.error,
          f"retries are bounded at {RETRY_ATTEMPTS} and the last error is kept "
          f"verbatim ({attempts})")

    check(is_rate_limited("Azure HTTP 429: RateLimitReached")
          and is_rate_limited("ModelUnavailable: ... 429 ...")
          and not is_rate_limited("Azure HTTP 400: content_filter"),
          "a rate limit is recognised by Azure's own code, not by guesswork")

    led = Ledger()
    led.spend_attempts(RETRY_ATTEMPTS)
    check(led.attempts == RETRY_ATTEMPTS,
          "every request that left the machine counts against the ceiling, "
          "including the ones that were rate-limited")

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
    led.attempts = MAX_ATTEMPTS
    check("request ceiling" in led.would_exceed(),
          "the request ceiling stops a runaway that spends credit, not rupees")

    spent: list = []

    def counting(text: str, *, model: str):
        spent.append(model)
        return replies[MODEL_A], {"temperature": 0, "tokens_in": 1, "tokens_out": 1}

    r3 = run([doc] * 60, counting)
    check(len(spent) <= MAX_ATTEMPTS and r3["stopped_early"],
          f"a long run stops at the ceiling ({len(spent)} requests) and says so")

    # ── two different failures must not wear one label ────────────────────────
    # Measured 23-09-2026 across 7 real filings: llama proposed "Public" for
    # company_class and the gate dropped it because the literal word is not in the
    # span; gpt-5-mini proposed the company NAME and the gate ADMITTED it because
    # the name is in the span. Filing both as "the models disagreed" hides that
    # one value is a class our own type accepts and the other is not a class at
    # all. The vocabulary is read from checker.company_profile.CompanyClass, so it
    # cannot drift away from what the product actually accepts.
    check(DECLARED_VOCABULARY["company_class"] == ("private", "public", "opc"),
          f"the closed vocabulary is READ from CompanyClass, never retyped "
          f"({DECLARED_VOCABULARY})")
    check(in_declared_vocabulary("company_class", "Public") is True
          and in_declared_vocabulary("company_class", "TITAN COMPANY LIMITED")
          is False,
          "a class our type accepts and a company name are told apart")
    check(in_declared_vocabulary("turnover_rupees", 5) is None,
          "a field with no closed vocabulary is not judged against one")

    vocab_doc = Document(
        doc_id="stub/three", path="corpus/testdocs/stub/three.txt", kind="real",
        title="REAL FILED DOCUMENT — stub", source="https://example.gov.in/y",
        text="NOTICE of TITAN COMPANY LIMITED. The company is listed.",
        line_map=tuple(range(6, 9)))

    def vocab_reply(text: str, *, model: str):
        if model == MODEL_A:
            facts = {"company_class": {"value": "public",
                                       "span": "The company is listed"}}
        else:
            facts = {"company_class": {"value": "TITAN COMPANY LIMITED",
                                       "span": "NOTICE of TITAN COMPANY LIMITED"}}
        return Proposal(facts=facts), {"temperature": 0, "tokens_in": 1,
                                       "tokens_out": 1}

    rv = run([vocab_doc], vocab_reply)
    row = rv["disagreements_kept"][0]
    check(row["model_a"]["state"] == cmp.REFUSED
          and "does not appear in the quoted span" in row["model_a"]["detail"],
          f"the refused side says WHY in the gate's own words "
          f"({row['model_a']['detail'][:60]!r})")
    check(row["model_b"]["state"] == cmp.ADMITTED
          and row["model_b"]["in_declared_vocabulary"] is False,
          "the admitted side is flagged when the value is not one the declared "
          "type accepts — the gate let it through, and that is the finding")
    check(row["model_a"]["in_declared_vocabulary"] is True,
          "and the DROPPED value is flagged as one the type does accept")
    md_v = render_markdown(rv)
    check("not a value `CompanyClass` accepts" in md_v,
          "the human list says so on the row, in the table")
    check("L-007" in md_v,
          "and points at the ledger row this is already open as")

    # ── a checkpoint, because this run has been killed twice mid-flight ───────
    # 29 documents x 2 models is half an hour of wall clock, and a run that loses
    # everything when the process dies is a run that pays for the same answers
    # again. Each extraction is appended as it is made; a resume re-runs ONLY what
    # is missing or failed, and rebuilds the rest from the stored proposals
    # through the same gates, spending nothing.
    import tempfile as _tmp

    with _tmp.TemporaryDirectory() as td:
        ck = Path(td) / "ck.jsonl"
        died: list = []

        def dies_after_three(text: str, *, model: str):
            died.append(model)
            if len(died) > 3:
                raise KeyboardInterrupt("watchdog")
            return replies[model], {"temperature": 0, "tokens_in": 7,
                                    "tokens_out": 3}

        try:
            run([doc, doc2], dies_after_three, checkpoint=ck)
        except KeyboardInterrupt:
            pass
        lines = [json.loads(ln) for ln in ck.read_text().splitlines() if ln.strip()]
        check(len(lines) == 3 and all("proposed" in ln for ln in lines),
              f"every extraction is written to the checkpoint AS IT IS MADE, not "
              f"at the end ({len(lines)} of 4 survived the kill)")

        after: list = []

        def counting_resume(text: str, *, model: str):
            after.append((text[:12], model))
            return replies[model], {"temperature": 0, "tokens_in": 7,
                                    "tokens_out": 3}

        r5 = run([doc, doc2], counting_resume, checkpoint=ck, resume=True)
        check(len(after) == 1,
              f"a resume calls the model ONLY for what the checkpoint is missing "
              f"({len(after)} call(s), not 4)")
        check(r5["documents_compared"] == 2,
              "and the finished run covers every document")
        check(r5["spend"]["calls_by_model"].get(MODEL_A, 0)
              + r5["spend"]["calls_by_model"].get(MODEL_B, 0) == 1,
              "the ledger charges only the calls this resume actually made")
        check(r5["resumed_from_checkpoint"] == 3,
              f"the report says how many extractions were reused rather than "
              f"re-bought ({r5['resumed_from_checkpoint']})")

        # The rebuilt side must be the same side, or a resume quietly changes the
        # answers underneath the founder.
        fresh = run([doc, doc2], counting_resume)
        check([(x["field"], x["outcome"]) for x in r5["disagreements_kept"]]
              == [(x["field"], x["outcome"]) for x in fresh["disagreements_kept"]],
              "a resumed run yields the same rows as one that never stopped")

        # A FAILED checkpoint entry is retried, not treated as a settled answer.
        ck2 = Path(td) / "ck2.jsonl"
        ck2.write_text(json.dumps({
            "document": doc.doc_id, "model": MODEL_A, "ok": False,
            "error": "ModelUnavailable: Azure unreachable: timed out",
            "meta": {}, "proposed": {}}) + "\n")
        retried: list = []

        def note(text: str, *, model: str):
            retried.append(model)
            return replies[model], {"temperature": 0, "tokens_in": 1,
                                    "tokens_out": 1}

        run([doc], note, checkpoint=ck2, resume=True)
        check(MODEL_A in retried,
              "a checkpointed FAILURE is re-attempted — a timeout is not an "
              "answer, and resuming past it would freeze our impatience into "
              "the record")

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

    # Re-rendering is free and produces the same document from the same record.
    check(render_markdown(json.loads(blob)) == md,
          "the human list re-renders from the stored JSON alone — fixing the "
          "wording never costs another model call, and never swaps in a second "
          "run's answers underneath the founder")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
