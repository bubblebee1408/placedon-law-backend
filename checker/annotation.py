"""The gold set: how lawyer labour becomes training data without becoming opinion.

The plan this implements says "start from high-agreement extraction tasks". It never
says how agreement is *measured*, and that omission is the whole problem. Hiring
lawyers to label does not by itself produce ground truth -- it produces one person's
reading, at scale and at cost. Two things have to be true before a label is gold:

  1. At least two annotators labelled the item INDEPENDENTLY.
  2. Where they disagreed, a named adjudicator resolved it on the record.

A single annotator's label is an opinion. This module will not export it as truth, and
that refusal is the point: an SFT set built from unadjudicated single labels teaches a
model one lawyer's habits and reports them as accuracy.

## Why agreement is measured, not assumed

Raw percent agreement flatters any task with a dominant class. If 90% of NCLT orders
are "admitted", two annotators who always guess "admitted" agree 90% of the time and
have demonstrated nothing. Cohen's kappa corrects for agreement expected by chance, so
a high-baseline field must clear a real bar. Fields that cannot clear it are not
labelled harder -- they are removed from the schema, because a field humans cannot
agree on is a field the model cannot be scored on.

## The discipline, unchanged

- **Disagreement is preserved, never averaged.** There is no majority vote here. Two
  lawyers reading a clause differently is a finding about the clause, and voting it
  away destroys the only signal that the schema is wrong.
- **Absent is not empty.** An annotator who marked a field "not present in this
  document" has said something; one who skipped it has not. They never merge.
- **Adjudication is attributed.** Every resolved disagreement carries who resolved it
  and why, because "the gold set says X" must always be answerable with "who decided,
  and on what basis".
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Status(str, Enum):
    SINGLE = "SINGLE"                 # one annotation — never gold
    AGREED = "AGREED"                 # independent annotators matched
    DISPUTED = "DISPUTED"             # they differed; not gold until adjudicated
    ADJUDICATED = "ADJUDICATED"       # differed, then resolved by a named human


# A field humans agree on less than this is not scoreable. Landis & Koch call
# 0.61-0.80 "substantial"; we take the bottom of that band as the floor for a field
# to enter the schema at all.
KAPPA_FLOOR = 0.61

SKIPPED = object()   # sentinel: annotator did not address this field at all


@dataclass(frozen=True)
class Annotation:
    """One annotator's independent reading of one document."""
    doc_id: str
    annotator: str                     # a person, never "model" — see adjudicate()
    values: dict                       # field -> value, or None meaning "not present"
    labelled_on: date
    notes: str = ""

    def value(self, fieldname: str):
        """None means 'annotator says this is not in the document'.
        SKIPPED means 'annotator did not address it'. They are different facts."""
        return self.values.get(fieldname, SKIPPED)


@dataclass(frozen=True)
class Adjudication:
    doc_id: str
    fieldname: str
    resolved_value: object
    adjudicator: str
    basis: str                         # WHY — the clause, the rule, the reasoning
    resolved_on: date


@dataclass
class GoldItem:
    """One document, its independent annotations, and any adjudications."""
    doc_id: str
    annotations: list[Annotation] = field(default_factory=list)
    adjudications: list[Adjudication] = field(default_factory=list)

    def annotators(self) -> tuple[str, ...]:
        return tuple(sorted({a.annotator for a in self.annotations}))

    def _considered(self, fieldname: str) -> list[Annotation]:
        return [a for a in self.annotations if a.value(fieldname) is not SKIPPED]

    def status(self, fieldname: str) -> Status:
        considered = self._considered(fieldname)
        if len(considered) < 2:
            return Status.SINGLE
        distinct = {json.dumps(a.value(fieldname), sort_keys=True, default=str)
                    for a in considered}
        if len(distinct) == 1:
            return Status.AGREED
        if any(x.fieldname == fieldname for x in self.adjudications):
            return Status.ADJUDICATED
        return Status.DISPUTED

    def gold_value(self, fieldname: str):
        """The defensible value, or raise. Never guesses, never votes."""
        st = self.status(fieldname)
        if st is Status.AGREED:
            return self._considered(fieldname)[0].value(fieldname)
        if st is Status.ADJUDICATED:
            adj = next(x for x in self.adjudications if x.fieldname == fieldname)
            return adj.resolved_value
        raise NotGold(
            f"{self.doc_id}.{fieldname} is {st.value}: "
            + ("only one annotator considered it — a single reading is an opinion"
               if st is Status.SINGLE else
               "annotators disagree and no adjudication is on record"))

    def is_gold(self, fields: tuple[str, ...]) -> bool:
        return all(self.status(f) in (Status.AGREED, Status.ADJUDICATED) for f in fields)


class NotGold(Exception):
    """Raised rather than returning a plausible value. Fails loud, by design."""


def adjudicate(item: GoldItem, fieldname: str, value, adjudicator: str,
               basis: str, on: date) -> GoldItem:
    """Resolve a disagreement on the record. Refuses to adjudicate a non-dispute."""
    if not adjudicator or adjudicator.strip().lower() in {"model", "llm", "auto", ""}:
        raise ValueError(
            "adjudication must be attributed to a person: a model resolving a "
            "disagreement between two lawyers is the labelling trap this system refuses")
    if not basis.strip():
        raise ValueError("adjudication requires a stated basis — 'who decided' is not "
                         "an answer without 'on what'")
    if item.status(fieldname) is not Status.DISPUTED:
        raise ValueError(f"{fieldname} is {item.status(fieldname).value}, not DISPUTED; "
                         "adjudicating an undisputed field would overwrite agreement")
    item.adjudications.append(
        Adjudication(item.doc_id, fieldname, value, adjudicator, basis, on))
    return item


# ── agreement ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Agreement:
    fieldname: str
    n: int                    # items where BOTH annotators considered the field
    observed: float           # raw percent agreement
    kappa: float | None       # None when undefined (single class seen by both)
    scoreable: bool
    note: str


def _key(v) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def cohens_kappa(items: list[GoldItem], fieldname: str,
                 a1: str, a2: str) -> Agreement:
    """Chance-corrected agreement between two named annotators on one field.

    kappa = (po - pe) / (1 - pe). Where both annotators used exactly one label across
    the whole set, pe = 1 and kappa is undefined -- reported as None with the reason,
    never as 0.0 or 1.0, because both would be a claim we cannot support.
    """
    pairs: list[tuple[str, str]] = []
    for it in items:
        v1 = next((a.value(fieldname) for a in it.annotations if a.annotator == a1), SKIPPED)
        v2 = next((a.value(fieldname) for a in it.annotations if a.annotator == a2), SKIPPED)
        if v1 is SKIPPED or v2 is SKIPPED:
            continue
        pairs.append((_key(v1), _key(v2)))

    n = len(pairs)
    if n == 0:
        return Agreement(fieldname, 0, 0.0, None, False,
                         "no item was considered by both annotators")

    po = sum(1 for x, y in pairs if x == y) / n
    c1, c2 = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    pe = sum((c1[k] / n) * (c2[k] / n) for k in set(c1) | set(c2))

    if abs(1.0 - pe) < 1e-9:
        return Agreement(fieldname, n, po, None, False,
                         "kappa undefined: both annotators used a single label, so "
                         "chance agreement is total and observed agreement proves nothing")

    kappa = (po - pe) / (1.0 - pe)
    ok = kappa >= KAPPA_FLOOR
    return Agreement(fieldname, n, po, kappa, ok,
                     f"kappa {kappa:.2f} {'clears' if ok else 'is below'} the "
                     f"{KAPPA_FLOOR} floor"
                     + ("" if ok else " — the field is not scoreable and should be "
                                      "removed or redefined, not labelled harder"))


# ── export ──────────────────────────────────────────────────────────────────
def to_sft(items: list[GoldItem], fields: tuple[str, ...], instruction: str,
           text_of: dict) -> list[dict]:
    """Export ONLY defensible items to a chat-format SFT set.

    Items that are not gold are skipped, not downgraded and not filled in. The count
    of what was skipped is the caller's business, so `sft_report` returns it rather
    than this function silently shrinking the dataset.
    """
    out = []
    for it in items:
        if not it.is_gold(fields):
            continue
        if it.doc_id not in text_of:
            continue
        target = {f: it.gold_value(f) for f in fields}
        out.append({
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": text_of[it.doc_id]},
                {"role": "assistant",
                 "content": json.dumps(target, sort_keys=True, default=str)},
            ],
            "provenance": {
                "doc_id": it.doc_id,
                "annotators": list(it.annotators()),
                "adjudicated": sorted({a.fieldname for a in it.adjudications}),
            },
        })
    return out


def sft_report(items: list[GoldItem], fields: tuple[str, ...]) -> dict:
    """What the export left behind, and why. Silent shrinkage is how a training set
    quietly becomes the easy cases only."""
    counts = Counter()
    for it in items:
        for f in fields:
            counts[it.status(f).value] += 1
    exported = sum(1 for it in items if it.is_gold(fields))
    return {
        "items": len(items),
        "exported": exported,
        "withheld": len(items) - exported,
        "field_status": dict(counts),
        "warning": (None if exported else
                    "nothing is gold — an SFT run on this set would train on nothing"),
    }


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    d = date(2026, 9, 5)
    F = ("outcome",)

    def ann(doc, who, **vals):
        return Annotation(doc, who, dict(vals), d)

    # ── single annotator is never gold ──
    solo = GoldItem("D1", [ann("D1", "adv_a", outcome="admitted")])
    check(solo.status("outcome") is Status.SINGLE, "one annotation is SINGLE")
    check(not solo.is_gold(F), "...and never gold")
    try:
        solo.gold_value("outcome"); check(False, "single value should raise")
    except NotGold as e:
        check("opinion" in str(e), "...and says a single reading is an opinion")

    # ── agreement ──
    agreed = GoldItem("D2", [ann("D2", "adv_a", outcome="admitted"),
                             ann("D2", "adv_b", outcome="admitted")])
    check(agreed.status("outcome") is Status.AGREED, "two matching reads are AGREED")
    check(agreed.gold_value("outcome") == "admitted", "...and yield the gold value")

    # ── dispute is preserved, not voted away ──
    disp = GoldItem("D3", [ann("D3", "adv_a", outcome="admitted"),
                           ann("D3", "adv_b", outcome="dismissed"),
                           ann("D3", "adv_c", outcome="admitted")])
    check(disp.status("outcome") is Status.DISPUTED,
          "2-vs-1 is DISPUTED, not resolved by majority")
    check(not disp.is_gold(F), "...and is withheld from the gold set")

    # ── adjudication ──
    try:
        adjudicate(disp, "outcome", "admitted", "model", "looked right", d)
        check(False, "a model adjudicating should be refused")
    except ValueError as e:
        check("attributed to a person" in str(e), "a model may not adjudicate")
    try:
        adjudicate(disp, "outcome", "admitted", "Sr. Adv. R", "", d)
        check(False, "empty basis should be refused")
    except ValueError:
        check(True, "adjudication without a stated basis is refused")

    adjudicate(disp, "outcome", "admitted", "Sr. Adv. R",
               "order para 14 records admission under IBC s.7", d)
    check(disp.status("outcome") is Status.ADJUDICATED, "resolved dispute is ADJUDICATED")
    check(disp.gold_value("outcome") == "admitted", "...and now yields a gold value")
    try:
        adjudicate(agreed, "outcome", "dismissed", "Sr. Adv. R", "reason", d)
        check(False, "adjudicating an agreed field should be refused")
    except ValueError as e:
        check("AGREED" in str(e), "an already-agreed field cannot be overwritten")

    # ── absent vs skipped ──
    mixed = GoldItem("D4", [ann("D4", "adv_a", outcome=None),
                            ann("D4", "adv_b", outcome=None)])
    check(mixed.status("outcome") is Status.AGREED and mixed.gold_value("outcome") is None,
          "'not present in the document' is a real, agreeable label")
    skipped = GoldItem("D5", [ann("D5", "adv_a", outcome=None), ann("D5", "adv_b")])
    check(skipped.status("outcome") is Status.SINGLE,
          "a skipped field is not an absent one — it does not count as a second read")

    # ── kappa: the dominant-class trap ──
    lopsided = [GoldItem(f"L{i}", [ann(f"L{i}", "adv_a", outcome="admitted"),
                                   ann(f"L{i}", "adv_b", outcome="admitted")])
                for i in range(20)]
    ag = cohens_kappa(lopsided, "outcome", "adv_a", "adv_b")
    check(ag.observed == 1.0, "100% raw agreement on a single-class set")
    check(ag.kappa is None and not ag.scoreable,
          "...but kappa is undefined and the field is NOT scoreable")
    check("proves nothing" in ag.note, "...and the note says why")

    # ── kappa: a genuinely mixed, mostly-agreeing set clears the floor ──
    mixed_set = []
    for i in range(20):
        v = "admitted" if i % 2 else "dismissed"
        other = v if i != 7 else ("admitted" if v == "dismissed" else "dismissed")
        mixed_set.append(GoldItem(f"M{i}", [ann(f"M{i}", "adv_a", outcome=v),
                                            ann(f"M{i}", "adv_b", outcome=other)]))
    ag2 = cohens_kappa(mixed_set, "outcome", "adv_a", "adv_b")
    check(ag2.kappa is not None and ag2.kappa > KAPPA_FLOOR and ag2.scoreable,
          f"a balanced high-agreement field is scoreable (kappa={ag2.kappa:.2f})")

    # ── kappa: coin-flip disagreement fails the floor ──
    noisy = []
    for i in range(20):
        noisy.append(GoldItem(f"N{i}", [ann(f"N{i}", "adv_a", outcome="admitted" if i % 2 else "dismissed"),
                                        ann(f"N{i}", "adv_b", outcome="admitted" if i % 3 else "dismissed")]))
    ag3 = cohens_kappa(noisy, "outcome", "adv_a", "adv_b")
    check(not ag3.scoreable, "a field annotators cannot agree on is not scoreable")
    check("removed or redefined" in ag3.note,
          "...and the fix offered is schema change, not more labelling")

    # ── export ──
    texts = {"D2": "…order text…", "D3": "…order text…", "D1": "…order text…"}
    sft = to_sft([solo, agreed, disp], F, "Extract the outcome.", texts)
    check(len(sft) == 2, "only the agreed and adjudicated items export")
    check(all(s["provenance"]["annotators"] for s in sft),
          "every exported row carries its annotators")
    check(any(s["provenance"]["adjudicated"] == ["outcome"] for s in sft),
          "...and records which fields were adjudicated")

    rep = sft_report([solo, agreed, disp], F)
    check(rep["withheld"] == 1 and rep["exported"] == 2,
          "the report states what was withheld rather than shrinking silently")
    check(sft_report([solo], F)["warning"] is not None,
          "an all-ungold set warns that training would see nothing")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
