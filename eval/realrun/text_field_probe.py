#!/usr/bin/env python3
"""Does a real model misbind a TEXT or DATE field? Evidence, not assumption.

`checker/field_binding.py` refuses FACT_MISBOUND for the four mutually-exclusive
money fields only. Widening it to text and date fields was proposed and declined,
because the shape of the failure had never been observed -- only imagined.
`checker/shadow.py` carries one hand-written instance of it as a surviving leak:

    {"financial_year": {"value": "2015-16",
                        "span": "incorporated on 2015-04-01"}}

A span that names the incorporation date, filed under the financial year. It
passes every gate. But a leak an author wrote to prove a harness can see one is
not evidence that a model produces it, and building a checker against an imagined
bug is the error this repository keeps correcting for.

So this is a measuring instrument, not a gate. It:

  1. puts six documents in front of a real model, each built so that two text or
     date fields sit close enough together to be confused,
  2. captures the RAW proposal -- every fact the model offered, verbatim span and
     all, BEFORE `reasoning.review()` drops anything,
  3. classifies each text/date fact by whether its span positively names a
     DIFFERENT text/date field.

## Why it classifies with the same asymmetry as field_binding

MISBOUND only when the span names another field and not its own. A span naming
nothing is UNNAMED and is not evidence of anything -- the same rule
`field_binding` was built on, because a bare quotation from a table is not an
error and counting it as one would manufacture the evidence this is supposed to
gather.

## Nothing here is scored by a model

Classification is substring membership over a fixed term list. A model asked
whether a span names the right field brings the weights that produced the span.

    PYTHONPATH=$PWD python3 eval/realrun/text_field_probe.py --run     # local
    PYTHONPATH=$PWD python3 eval/realrun/text_field_probe.py --test    # offline
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field as _field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from checker import bundles, orchestrator                          # noqa: E402
from checker.document_extract import DATE_FIELDS, TEXT_FIELDS      # noqa: E402
from checker.reasoning import Proposal                             # noqa: E402

# ── classification verdicts. Same three as field_binding, deliberately ───────
BOUND = "BOUND"          # the span names the field it was filed under
UNNAMED = "UNNAMED"      # the span names no field at all. Not evidence.
MISBOUND = "MISBOUND"    # the span names a DIFFERENT field. This is the evidence.
NO_SPAN = "NO_SPAN"      # the model quoted nothing. Unmeasurable, not clean.

# Two DIFFERENT shapes of the same error, and they must never be conflated:
SPAN_MISBINDING = "span-names-another-field"    # what field_binding.py checks
VALUE_CONFUSION = "value-belongs-to-another-field"   # visible without any span

# A verdict needs a sample. Below this many spans there is nothing to have found
# and nothing to have failed to find -- the same discipline run.py applies to a
# leak rate over cases that errored.
MIN_SPANS_FOR_A_VERDICT = 3

NON_MONEY_FIELDS = DATE_FIELDS + TEXT_FIELDS

# How Indian corporate documents name these fields. Lower-cased substring match:
# the list is for READING a model's output, never for refusing it.
_TERMS: dict[str, tuple[str, ...]] = {
    "document_date": ("dated", "date of this", "passed on", "held on",
                      "this resolution"),
    "incorporation_date": ("incorporated on", "date of incorporation",
                           "incorporation", "certificate of incorporation"),
    "financial_year": ("financial year", "f.y.", "fy ", "year ended",
                       "year ending", "for the year"),
    "company_class": ("private limited", "public limited", "small company",
                      "one person company", "private company", "public company"),
    "cin": ("cin", "corporate identity number"),
}

# Named in these documents, never extracted. A span quoting one of them for a
# text field is the same error wearing different clothes.
_NOT_A_FIELD: dict[str, tuple[str, ...]] = {
    "registration number": ("registration no", "registration number",
                            "gstin", "pan ", "tan "),
    "meeting date": ("previous meeting", "last meeting", "adjourned meeting"),
}


@dataclass(frozen=True)
class TextCase:
    cid: str
    text: str
    document_date: date | None
    why: str
    confusable: tuple[str, ...]      # the pair(s) built to be confused
    # What each field's value IS in this document, in every rendering a model
    # might plausibly emit. This is not a scoring key for correctness -- it is
    # how a value filed under the WRONG field is recognised without a span.
    truth: dict[str, tuple[str, ...]] = _field(default_factory=dict)


# ── the documents ────────────────────────────────────────────────────────────
# Each puts two text/date fields within a sentence or two of each other, in the
# shape a real Indian corporate document would. None is nonsense; a model that
# reads carefully can answer every one of them correctly.
TEXT_CASES: tuple[TextCase, ...] = (
    TextCase("T01",
             "BOARD RESOLUTION dated 14 June 2024. The Company was incorporated "
             "on 01 April 2015 under the Companies Act, 2013. RESOLVED that the "
             "accounts be adopted.",
             date(2024, 6, 14),
             "two dates, four words apart in role and nine months apart in "
             "prominence. Either can be read as 'the date of the document'.",
             ("document_date", "incorporation_date"),
             {"document_date": ("14 june 2024", "2024-06-14", "14-06-2024", "june 14 2024"), "incorporation_date": ("01 april 2015", "2015-04-01", "01-04-2015", "1 april 2015", "1-4-2015")}),

    TextCase("T02",
             "BOARD RESOLUTION dated 14 June 2024. The Company, incorporated on "
             "01 April 2015, has adopted the audited accounts for the financial "
             "year 2023-24. The comparative figures are for 2022-23.",
             date(2024, 6, 14),
             "the financial year is stated explicitly AND an incorporation date "
             "that looks like the start of one (01 April) sits beside it. This "
             "is the exact shape shadow.py carries as a hand-written leak.",
             ("financial_year", "incorporation_date"),
             {"document_date": ("14 june 2024", "2024-06-14", "14-06-2024", "june 14 2024"), "incorporation_date": ("01 april 2015", "2015-04-01", "01-04-2015", "1 april 2015", "1-4-2015"),
              "financial_year": ("2023-24", "2023-2024", "fy 2023-24")}),

    TextCase("T03",
             "BOARD RESOLUTION dated 14 June 2024. ACME WORKS PRIVATE LIMITED, "
             "CIN U74999KA2019PTC123456, Registration No. 123456 of 2019, GSTIN "
             "29AABCA1234A1Z5. RESOLVED that the registers be updated.",
             date(2024, 6, 14),
             "a CIN and a registration number sit adjacent, both alphanumeric, "
             "both six digits deep. The registration number is not a field we "
             "extract, so quoting it for cin is a binding error with no sibling "
             "field to absorb it.",
             ("cin",),
             {"document_date": ("14 june 2024", "2024-06-14", "14-06-2024", "june 14 2024"),
              "cin": ("u74999ka2019ptc123456",)}),

    TextCase("T04",
             "BOARD RESOLUTION dated 14 June 2024. The Company is a private "
             "limited company and a small company within the meaning of section "
             "2(85). Its holding company, ACME HOLDINGS PUBLIC LIMITED, is a "
             "public limited company.",
             date(2024, 6, 14),
             "two company classes in one document, belonging to two companies. "
             "A single company_class slot must not silently take the holding "
             "company's class, and the span would name it plainly if it did.",
             ("company_class",),
             {"document_date": ("14 june 2024", "2024-06-14", "14-06-2024", "june 14 2024"),
              "company_class": ("private limited", "private limited company",
                                "small company", "private")}),

    TextCase("T05",
             "MINUTES OF THE BOARD MEETING held on 14 June 2024. The minutes of "
             "the previous meeting held on 12 March 2024 were confirmed. The "
             "Company was incorporated on 01 April 2015.",
             date(2024, 6, 14),
             "three dates: this meeting, the previous meeting, and "
             "incorporation. The previous meeting's date is not a field at all, "
             "which makes it the easiest one to file under document_date.",
             ("document_date", "incorporation_date"),
             {"document_date": ("14 june 2024", "2024-06-14", "14-06-2024", "june 14 2024"), "incorporation_date": ("01 april 2015", "2015-04-01", "01-04-2015", "1 april 2015", "1-4-2015")}),

    TextCase("T06",
             "BOARD RESOLUTION dated 14 June 2024.\n\nPARTICULARS\n"
             "Date of incorporation\nFinancial year\nClass of company\nCIN\n\n"
             "VALUE\n01-04-2015\n2023-24\nPrivate Limited\nU74999KA2019PTC123456"
             "\n\nRESOLVED that the accounts be adopted.",
             date(2024, 6, 14),
             "the flattened two-column table -- the habitat in which the money "
             "misbinding was first observed -- built for text fields instead. "
             "Every label is separated from its value by three other labels.",
             ("incorporation_date", "financial_year", "company_class", "cin"),
             {"document_date": ("14 june 2024", "2024-06-14", "14-06-2024", "june 14 2024"), "incorporation_date": ("01 april 2015", "2015-04-01", "01-04-2015", "1 april 2015", "1-4-2015"),
              "financial_year": ("2023-24", "2023-2024"),
              "company_class": ("private limited", "private limited company"),
              "cin": ("u74999ka2019ptc123456",)}),
)


def _flat(s: str) -> str:
    """Words only, space-padded, so a term matches whole words and never a
    fragment of one. Match with the padding intact: stripping it is what let
    'pan' match inside 'company'."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", str(s or "").lower())) + " "


def classify(field: str, span: str) -> tuple[str, tuple[str, ...]]:
    """Does `span` name `field`, name another field, or name nothing?

    Returns (verdict, names_found). Same asymmetry as `field_binding.check`:
    silence is not contradiction, so UNNAMED is never counted as evidence.
    """
    if field not in _TERMS:
        return UNNAMED, ()
    text = _flat(span)
    own = tuple(t for t in _TERMS[field] if t.strip() and _flat(t) in text)
    if own:
        return BOUND, own
    others: list[str] = []
    for other, terms in _TERMS.items():
        if other == field:
            continue
        others += [f"{other}:{t.strip()}" for t in terms if _flat(t) in text]
    for label, terms in _NOT_A_FIELD.items():
        others += [f"{label}:{t.strip()}" for t in terms if _flat(t) in text]
    return (MISBOUND, tuple(others)) if others else (UNNAMED, ())


def _canon(v) -> str:
    """Digits and letters only, lower-cased. '01-04-2015' and '01 April 2015'
    are different renderings of one date and must compare as written, not as
    parsed -- parsing a model's output is repairing it."""
    return "".join(ch for ch in str(v or "").lower() if ch.isalnum())


def value_confusion(case: TextCase, field: str, value) -> tuple[str, str]:
    """Is `value` this document's value for a DIFFERENT field?

    This needs no span, which is the point: a model that emits bare values still
    reveals a binding error when it files the incorporation date under
    document_date. Returns (other_field, rendering) or ("", "").

    Same asymmetry again -- a value matching nothing in the truth table is not
    reported. A model is free to say something we did not anticipate; only a
    value that provably belongs to another named field counts.
    """
    got = _canon(value)
    if not got or not case.truth:
        return "", ""
    if any(_canon(t) == got for t in case.truth.get(field, ())):
        return "", ""                       # it is this field's own value
    for other, renderings in case.truth.items():
        if other == field:
            continue
        for r in renderings:
            if _canon(r) == got:
                return other, r
    return "", ""


# ── what was served, scored against the document ─────────────────────────────
CORRECT_SERVED = "CORRECT_SERVED"
WRONG_SERVED = "WRONG_SERVED"
UNSCORED = "UNSCORED"     # the case has no truth for this field. Not evidence.
NOT_EXACT = "NOT_EXACT"   # contains a true rendering without equalling one. For a
                          # human to read; never counted as wrong.


def served_score(case: TextCase, field: str, value) -> str:
    """Is a value that passed every gate actually this document's value?

    The misbinding verdicts above judge a proposal's SHAPE. This judges what a
    lawyer would read. Compared as written (`_canon`), never parsed, and only for
    fields the case carries truth for -- a field with none is UNSCORED, not wrong.
    """
    if field not in case.truth:
        return UNSCORED
    got = _canon(value)
    truths = [_canon(t) for t in case.truth[field]]
    if got and got in truths:
        return CORRECT_SERVED
    # 'a private limited company and a small company' names the true class and
    # more. That is not provably wrong, so it is not scored as wrong.
    if got and any(t and t in got for t in truths):
        return NOT_EXACT
    return WRONG_SERVED


class ReplayExhausted(RuntimeError):
    """The gates asked for an attempt the stored run never made."""


def replay_model(stored: dict):
    """A model that says exactly what a stored run's model said, and nothing else.

    Replayed through today's gates, a stricter check can refuse an attempt the
    original run accepted and ask for a correction that was never made. That
    raises: inventing the missing answer would score the replay, not the model.
    """
    by_text = {}
    for r in stored.get("rows", []):
        case = next((c for c in TEXT_CASES if c.cid == r.get("cid")), None)
        if case is not None:
            by_text[case.text] = iter(r.get("raw_proposals") or [])

    def model(text_: str) -> Proposal:
        # A correction is sent as the document followed by a brief, so the case is
        # the one whose text BEGINS the prompt -- the longest, should one case's
        # text ever prefix another's.
        key = max((t for t in by_text if text_.startswith(t)), key=len, default=None)
        attempt = next(by_text[key], None) if key is not None else None
        if attempt is None:
            raise ReplayExhausted("no stored attempt left for this document")
        return Proposal(facts=attempt.get("facts") or {},
                        narration=attempt.get("narration") or None)

    return model


def rescore(stored: dict) -> dict:
    """Re-run a stored probe result through today's gates. No model is called."""
    return probe_all(replay_model(stored)) | {"model": stored.get("model"),
                                              "rescored_from": stored.get("model")}


def capture(model):
    """Wrap a model so every raw proposal it returns is kept, verbatim.

    The orchestrator hands review a proposal and returns only what survived. The
    question here is what the model SAID, which is upstream of that -- including
    the attempts review threw away, because a misbinding that some other gate
    happens to catch is still a misbinding the model produced.
    """
    seen: list[dict] = []

    def wrapped(text: str) -> Proposal:
        p = model(text)
        seen.append({"facts": {k: dict(v) if isinstance(v, dict)
                               else {"value": v, "span": None}
                               for k, v in (p.facts or {}).items()},
                     "narration": p.narration or ""})
        return p

    return wrapped, seen


def probe_one(case: TextCase, model) -> dict:
    """One document through the real orchestrator, with the raw proposals kept."""
    wrapped, seen = capture(model)
    t0 = time.time()
    verdict, error, served_facts = "", "", {}
    try:
        out = orchestrator.run(intent=bundles.capabilities()[0],
                               document=case.text,
                               document_date=case.document_date, model=wrapped)
        verdict = out.verdict
        if out.served and out.review is not None:
            served_facts = dict(out.review.facts)
    except orchestrator.OrchestrationRefused as e:
        verdict, error = "REFUSED_BEFORE_CALL", str(e)[:80]
    except Exception as e:                                        # noqa: BLE001
        verdict, error = "ERROR", f"{type(e).__name__}: {e}"[:120]

    findings = []
    for attempt, prop in enumerate(seen, start=1):
        for fname, item in prop["facts"].items():
            if fname not in NON_MONEY_FIELDS:
                continue
            span = item.get("span")
            v, names = classify(fname, span or "")
            other, rendering = value_confusion(case, fname, item.get("value"))
            findings.append({"attempt": attempt, "field": fname,
                             "value": item.get("value"), "span": span,
                             "verdict": v if span else NO_SPAN,
                             "names_found": list(names),
                             "span_in_document": bool(span)
                             and str(span) in case.text,
                             "value_belongs_to": other,
                             "value_rendering": rendering})
    served = {}
    for fname, item in served_facts.items():
        if fname not in NON_MONEY_FIELDS or not isinstance(item, dict):
            continue
        value = item.get("value")
        served[fname] = {"value": value, "span": item.get("span"),
                         "score": served_score(case, fname, value),
                         "belongs_to": value_confusion(case, fname, value)[0]}
    return {"cid": case.cid, "confusable": list(case.confusable),
            "orchestrator_verdict": verdict, "error": error,
            "attempts": len(seen), "raw_proposals": seen,
            "findings": findings, "served": served,
            "seconds": round(time.time() - t0, 1)}


def probe_all(model) -> dict:
    rows = [probe_one(c, model) for c in TEXT_CASES]
    facts = [f | {"cid": r["cid"]} for r in rows for f in r["findings"]]
    spans = [f for f in facts if f["span"]]
    misbound = [f for f in spans if f["verdict"] == MISBOUND]
    confused = [f for f in facts if f["value_belongs_to"]]

    # The span shape is what `field_binding.py` would be widened to catch, and it
    # is only observable when the model quotes something. Zero misbindings over
    # zero spans is not a negative result; it is a measurement that was never
    # taken, and reporting it as "no evidence" would be the same overclaim as a
    # leak rate computed over cases that errored.
    if len(spans) < MIN_SPANS_FOR_A_VERDICT:
        span_verdict = "UNMEASURABLE"
    elif misbound:
        span_verdict = "EVIDENCE_FOUND"
    else:
        span_verdict = "NO_EVIDENCE"
    value_verdict = "EVIDENCE_FOUND" if confused else "NO_EVIDENCE"

    # What a lawyer would read. Nothing served and scored is not a clean result.
    served = [s | {"cid": r["cid"], "field": f}
              for r in rows for f, s in r["served"].items()]
    scored = [s for s in served if s["score"] != UNSCORED]
    wrong = [s for s in scored if s["score"] == WRONG_SERVED]
    not_exact = [s for s in scored if s["score"] == NOT_EXACT]
    served_verdict = ("UNMEASURABLE" if not scored
                      else "EVIDENCE_FOUND" if wrong else "NO_EVIDENCE")
    return {"rows": rows,
            "served_scored": len(scored),
            "served_unscored": len(served) - len(scored),
            "wrong_served": wrong,
            "not_exact_served": not_exact,
            "wrong_served_verdict": served_verdict,
            "cases": len(rows),
            "cases_errored": sum(r["orchestrator_verdict"] == "ERROR"
                                 for r in rows),
            "text_date_facts_proposed": len(facts),
            "spans_present": len(spans),
            "misbound": misbound,
            "value_confused": confused,
            "span_misbinding": span_verdict,
            "value_confusion": value_verdict,
            "verdict": ("EVIDENCE_FOUND"
                        if span_verdict == "EVIDENCE_FOUND"
                        or value_verdict == "EVIDENCE_FOUND"
                        else span_verdict)}


def text(res: dict) -> str:
    L = ["", "TEXT/DATE FIELD MISBINDING PROBE — via checker/orchestrator.py",
         "=" * 74]
    for r in res["rows"]:
        L.append(f"  {r['cid']}  {r['orchestrator_verdict']:<24}"
                 f"{r['attempts']} attempt(s), {r['seconds']}s"
                 + (f"  [{r['error']}]" if r["error"] else ""))
        if not r["findings"]:
            L.append("        (no text/date field proposed)")
        for f in r["findings"]:
            tail = (f"   <-- this is the {f['value_belongs_to']} "
                    f"({f['value_rendering']!r})" if f["value_belongs_to"] else "")
            L.append(f"        {f['verdict']:<9}{f['field']:<20}"
                     f"value={f['value']!r}  span={f['span']!r}{tail}")
    L += ["",
          f"  text/date facts proposed : {res['text_date_facts_proposed']}",
          f"  of those, carrying a span: {res['spans_present']}",
          "",
          f"  {SPAN_MISBINDING:<32}{len(res['misbound']):>3}   "
          f"{res['span_misbinding']}",
          f"  {VALUE_CONFUSION:<32}{len(res['value_confused']):>3}   "
          f"{res['value_confusion']}"]
    if res["span_misbinding"] == "UNMEASURABLE":
        L += ["",
              f"  NO VERDICT ON THE SPAN SHAPE. {res['spans_present']} span(s) "
              f"were produced across {res['text_date_facts_proposed']} facts, "
              f"below the floor of {MIN_SPANS_FOR_A_VERDICT}.",
              "  field_binding.py keys on the span. With no spans there is "
              "nothing it could have caught and nothing it could have missed,",
              "  so this run neither supports nor refutes widening it. That is "
              "not a negative result -- it is an unmeasured one."]
    elif res["span_misbinding"] == "NO_EVIDENCE":
        L += ["", "  A negative result is the finding. field_binding.py must "
                  "NOT be widened on it."]
    L += ["",
          f"  {'served, scored vs the document':<32}{res['served_scored']:>3}   "
          f"({res['served_unscored']} served with no truth to score against)",
          f"  {'served a wrong value':<32}{len(res['wrong_served']):>3}   "
          f"{res['wrong_served_verdict']}"]
    for w in res["wrong_served"]:
        L.append(f"  SERVED A WRONG VALUE  {w['cid']}  {w['field']}={w['value']!r}  "
                 f"span={w['span']!r}"
                 + (f"  <-- this is the {w['belongs_to']}" if w["belongs_to"] else ""))
    for n in res["not_exact_served"]:
        L.append(f"  not exact (read it)   {n['cid']}  {n['field']}={n['value']!r}")
    return "\n".join(L)


def _test() -> None:
    """Offline. Proves the instrument can SEE the shape before it is trusted.

    A probe that reports NO_EVIDENCE because it cannot detect anything produces a
    number that looks like a finding. So the classifier is driven over the leak
    shadow.py carries by hand, and the capture is driven through the real
    orchestrator with a stub whose fact review THROWS AWAY -- because what the
    model said is upstream of what survived.
    """
    ok = fail = 0

    def c(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("text_field_probe")

    # ── the shape this exists to look for ────────────────────────────────────
    v, names = classify("financial_year", "incorporated on 2015-04-01")
    c(v == MISBOUND and any("incorporation_date" in n for n in names),
      f"shadow.py's surviving leak classifies as MISBOUND ({v}, {names}) -- the "
      f"instrument can see the shape it is looking for")
    v, _ = classify("document_date", "the Company was incorporated on 01 April 2015")
    c(v == MISBOUND, "an incorporation span filed as the document date is MISBOUND")
    v, names = classify("cin", "Registration No. 123456 of 2019")
    c(v == MISBOUND and any("registration" in n for n in names),
      "a registration number filed as a CIN is MISBOUND, naming what it is")

    # ── and must not cry wolf, or it manufactures its own evidence ───────────
    c(classify("financial_year", "the financial year 2023-24")[0] == BOUND,
      "a correct financial_year span is BOUND")
    c(classify("document_date", "BOARD RESOLUTION dated 14 June 2024")[0] == BOUND,
      "a correct document_date span is BOUND")
    c(classify("incorporation_date", "01-04-2015")[0] == UNNAMED,
      "a bare date from a flattened table is UNNAMED, not MISBOUND -- the same "
      "asymmetry field_binding was built on: silence is not contradiction")
    c(classify("company_class",
               "a private limited company and a small company")[0] == BOUND,
      "a span naming the claimed class binds even with a second class present")
    # A term matches whole words, never a fragment. "pan " carried its trailing
    # space as the word boundary and the match stripped it, so "pan" was found
    # inside "comPANy": llama3's span 'Class of company' under company_class was
    # scored MISBOUND, twice, and counted as evidence.
    c(classify("company_class", "Class of company")[0] != MISBOUND,
      "'Class of company' does not name a registration number -- 'pan' is not "
      "a word inside 'company'")
    c(classify("cin", "a substantial resolution")[0] == UNNAMED,
      "...nor 'tan' inside 'substantial'")
    c(classify("cin", "PAN AAACA1234B of the Company")[0] == MISBOUND,
      "...while a real PAN is still named")
    c(classify("financial_year", "for F.Y. 2023-24")[0] == BOUND,
      "...and punctuation inside a term still matches ('F.Y.')")
    for money in ("paid_up_capital_rupees", "turnover_rupees"):
        c(classify(money, "turnover of Rs 15,00,00,000")[0] == UNNAMED,
          f"{money} is outside this probe -- field_binding already owns it")

    # ── the capture keeps what the model said, not what survived ────────────
    case = TEXT_CASES[0]

    def misbinds(_t: str) -> Proposal:
        return Proposal(facts={"financial_year": {
            "value": "2015-16", "span": "incorporated on 01 April 2015"}})

    row = probe_one(case, misbinds)
    c(row["findings"] and row["findings"][0]["verdict"] == MISBOUND,
      f"a misbinding stub is recorded through the real orchestrator "
      f"({row['orchestrator_verdict']})")
    c(row["raw_proposals"][0]["facts"]["financial_year"]["span"]
      == "incorporated on 01 April 2015",
      "...with the span kept VERBATIM, which is the whole evidentiary point")

    def unsupported(_t: str) -> Proposal:
        return Proposal(facts={"financial_year": {
            "value": "2023-24", "span": "this span is not in the document"}})

    row = probe_one(case, unsupported)
    c(not row["raw_proposals"][0]["facts"] == {} and row["findings"],
      "a fact review DROPS is still captured -- what the model said is upstream "
      "of what survived, and a misbinding another gate catches is still one the "
      "model produced")
    c(row["findings"][0]["span_in_document"] is False,
      "...and the record says whether the span was in the document at all")

    # ── a clean model produces no evidence, and that must read as none ──────
    def clean(_t: str) -> Proposal:
        return Proposal(facts={"document_date": {
            "value": "2024-06-14", "span": "BOARD RESOLUTION dated 14 June 2024"}})

    res = probe_all(clean)
    c(res["verdict"] == "NO_EVIDENCE" and not res["misbound"],
      "a clean model yields NO_EVIDENCE")
    c("must NOT be widened" in text(res),
      "...and the report says plainly that a negative result forbids widening "
      "the checker, rather than leaving the reader to infer it")
    c(all(r["findings"] for r in res["rows"]),
      f"every case contributed to the denominator -- "
      f"{res['text_date_facts_proposed']} facts over {len(TEXT_CASES)} cases; "
      f"the count exceeds the case count because a refused first pass earns one "
      f"correction, and BOTH attempts are what the model said")

    # ── the second shape: a bare value filed under the wrong field ──────────
    # gemma3:1b emits flat values with no spans at all, so the span shape is
    # invisible to it. The binding error is still there and still visible.
    t06 = [c_ for c_ in TEXT_CASES if c_.cid == "T06"][0]
    other, rendering = value_confusion(t06, "document_date", "01-04-2015")
    c(other == "incorporation_date",
      f"T06's incorporation date filed as the document date is caught without "
      f"any span at all ({other} / {rendering!r})")
    c(value_confusion(t06, "incorporation_date", "2023-24")[0] == "financial_year",
      "...and the financial year filed as the incorporation date likewise")
    c(value_confusion(t06, "document_date", "14 June 2024") == ("", ""),
      "a field holding its OWN value is not reported")
    c(value_confusion(t06, "document_date", "2024-06-14") == ("", ""),
      "...in any rendering of it -- comparison is on the text as written, "
      "because parsing a model's output is repairing it")
    c(value_confusion(t06, "company_class", "Limited Liability Company")
      == ("", ""),
      "a value belonging to no field in the document is NOT reported -- an "
      "invented class is a different failure, owned by a different gate")

    # ── and the discipline that stops an unmeasured run reading as a clean one ─
    def spanless(_t: str) -> Proposal:
        return Proposal(facts={"document_date": {"value": "01-04-2015",
                                                 "span": None}})

    res = probe_all(spanless)
    c(res["spans_present"] == 0 and res["span_misbinding"] == "UNMEASURABLE",
      f"a model that quotes nothing yields UNMEASURABLE on the span shape, not "
      f"NO_EVIDENCE ({res['span_misbinding']})")
    c("neither supports nor refutes" in text(res),
      "...and the report says so outright: field_binding keys on the span, so "
      "with no spans there is nothing it could have caught or missed")
    c(res["value_confusion"] == "EVIDENCE_FOUND" and res["value_confused"],
      "...while the value shape is still measured, because it needs no span")
    c(res["verdict"] == "EVIDENCE_FOUND",
      "the overall verdict follows whichever shape was actually found, and the "
      "two are never conflated -- they call for different fixes")

    # ── the documents themselves ────────────────────────────────────────────
    c(len(TEXT_CASES) >= 5, f"{len(TEXT_CASES)} documents, each built around a "
                            f"confusable pair")
    c(all(c_.confusable and c_.document_date for c_ in TEXT_CASES),
      "every case names the pair it confuses and carries a document date -- "
      "without one the orchestrator refuses before any model call and the "
      "document is never seen")
    c(all(any(f in NON_MONEY_FIELDS for f in c_.confusable) for c_ in TEXT_CASES),
      "every confusable pair is a text or date field; the money fields are "
      "field_binding's, not this probe's")

    # ── what was SERVED, scored against what the document says ──────────────
    # 14-09-2026: T05's previous-meeting date filed as document_date, quoting its
    # own sentence, passed every gate and SERVED -- and the misbinding counts above
    # could not see it, because the span names no other field. A probe that only
    # counts binding shapes misses the wrong answer a lawyer would actually read.
    t05 = [c_ for c_ in TEXT_CASES if c_.cid == "T05"][0]
    c(served_score(t05, "document_date", "2024-03-12") == WRONG_SERVED,
      "the previous meeting's date served as document_date scores WRONG_SERVED")
    c(served_score(t05, "document_date", "14 June 2024") == CORRECT_SERVED,
      "the document's own date, in any rendering, scores CORRECT_SERVED")
    c(served_score(t05, "cin", "U74999KA2019PTC123456") == UNSCORED,
      "a field the case has no truth for is UNSCORED, never WRONG -- the same "
      "asymmetry as every other verdict in this probe")

    # The first re-score of gpt-5-mini reported T04's company_class 'a private
    # limited company and a small company' as WRONG_SERVED. The document says both;
    # the truth table lists them separately, and exact matching called it wrong.
    # A value that CONTAINS a correct rendering is not provably wrong.
    t04 = [c_ for c_ in TEXT_CASES if c_.cid == "T04"][0]
    c(served_score(t04, "company_class",
                   "a private limited company and a small company") == NOT_EXACT,
      "a compound value containing the true class is NOT_EXACT, not WRONG")
    c(served_score(t04, "company_class", "Limited Liability Partnership") == WRONG_SERVED,
      "...while a class the document never states is still WRONG_SERVED")
    res = probe_all(lambda _t: Proposal(facts={"company_class": {
        "value": "a private limited company and a small company",
        "span": "The Company is a private limited company and a small company"}}))
    c(not res["wrong_served"] and res["not_exact_served"],
      "NOT_EXACT is reported on its own and never counted as a wrong answer")

    def wrong_date(_t: str) -> Proposal:
        return Proposal(facts={"document_date": {
            "value": "2024-03-12",
            "span": "the previous meeting held on 12 March 2024"}})

    row = probe_one(t05, wrong_date)
    c(row["served"].get("document_date", {}).get("score") == WRONG_SERVED,
      f"probe_one records the wrong value it was SERVED "
      f"({row['orchestrator_verdict']}, {row['served']})")
    res = probe_all(wrong_date)
    c(res["wrong_served"] and res["wrong_served_verdict"] == "EVIDENCE_FOUND",
      "probe_all reports a wrong served value as evidence")
    c("SERVED A WRONG VALUE" in text(res),
      "...and the report says so in words, not only in a count")

    res = probe_all(clean)
    c(not res["wrong_served"] and res["served_scored"] >= 1
      and res["wrong_served_verdict"] == "NO_EVIDENCE",
      f"a clean model serves nothing wrong ({res['served_scored']} scored)")
    res = probe_all(spanless)
    c(res["served_scored"] == 0 and res["wrong_served_verdict"] == "UNMEASURABLE",
      "nothing served and scored is UNMEASURABLE, not a clean result")

    # ── re-scoring a stored run replays what the model said; it invents nothing ─
    stored = {"model": "stub", "rows": [
        {"cid": "T05", "raw_proposals": [{"facts": {"document_date": {
            "value": "2024-03-12",
            "span": "the previous meeting held on 12 March 2024"}},
            "narration": ""}]},
        {"cid": "T01", "raw_proposals": []}]}
    again = rescore(stored)
    t05_row = [r for r in again["rows"] if r["cid"] == "T05"][0]
    c(t05_row["served"].get("document_date", {}).get("score") == WRONG_SERVED,
      "rescore replays the stored proposal through TODAY's gates and scores it")
    t01_row = [r for r in again["rows"] if r["cid"] == "T01"][0]
    c(t01_row["orchestrator_verdict"] == "ERROR" and not t01_row["served"],
      "a case with no stored answer is an ERROR in the replay -- never an empty "
      "answer the model did not give")
    c(again["rescored_from"] == "stub",
      "the re-scored result names the run it was replayed from")

    # The first --rescore of the real runs errored EVERY two-attempt case after one
    # attempt: the correction call does not send the bare document text, so a
    # lookup keyed on the exact text found nothing. A stub with one attempt per
    # case could not see it.
    two = {"model": "stub2", "rows": [{"cid": "T05", "raw_proposals": [
        {"facts": {"cin": {"value": "",
                           "span": "The Company was incorporated on 01 April 2015."},
                   "document_date": {
                       "value": "2024-06-14",
                       "span": "MINUTES OF THE BOARD MEETING held on 14 June 2024."}},
         "narration": ""},
        {"facts": {"document_date": {
            "value": "2024-06-14",
            "span": "MINUTES OF THE BOARD MEETING held on 14 June 2024."}},
         "narration": ""}]}]}
    t05_two = [r for r in rescore(two)["rows"] if r["cid"] == "T05"][0]
    c(t05_two["attempts"] == 2
      and t05_two["orchestrator_verdict"] == "SERVED_AFTER_CORRECTION"
      and t05_two["served"].get("document_date", {}).get("score") == CORRECT_SERVED,
      f"a refused first attempt replays its stored CORRECTION, not an exhaustion "
      f"({t05_two['orchestrator_verdict']}, {t05_two['attempts']} attempts, "
      f"{t05_two['error']})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
        raise SystemExit(0)
    if "--rescore" in sys.argv:
        # Stored proposals through today's gates. No model call; the measured file
        # is left as it was, and the replay is written beside it.
        src = Path(sys.argv[sys.argv.index("--rescore") + 1])
        result = rescore(json.loads(src.read_text()))
        print(text(result))
        src.with_name(src.stem + ".rescored.json").write_text(
            json.dumps(result, indent=1))
        raise SystemExit(0)
    if "--run" not in sys.argv:
        print(__doc__)
        raise SystemExit(0)
    from eval.realrun.local_model import MODEL

    # gemma3:1b never quotes, so the span shape is unmeasurable on it. A second
    # model is a second measurement, and it must not overwrite the first.
    name = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else MODEL
    if name.startswith("azure:"):
        # Models too large for the laptop's memory. See azure_model.py.
        from eval.realrun.azure_model import available, extract
        unreachable = "AZURE_AI_API_KEY / AZURE_AI_ENDPOINT are not set"
    else:
        from eval.realrun.local_model import available, extract
        unreachable = "ollama is not reachable at localhost:11434"

    if not available():
        print(f"{unreachable}. No run, no evidence.")
        raise SystemExit(2)

    def model(t: str) -> Proposal:
        p, _ = extract(t, model=name, timeout=300)
        return p

    result = probe_all(model) | {"model": name}
    print(json.dumps(result, indent=1) if "--json" in sys.argv else text(result))
    out = ("last_text_probe.json" if name == MODEL
           else f"last_text_probe.{name.replace(':', '_')}.json")
    Path(__file__).parent.joinpath(out).write_text(json.dumps(result, indent=1))
