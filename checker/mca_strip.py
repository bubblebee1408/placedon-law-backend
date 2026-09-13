"""The strip as a view model — where a chip cannot exist without its blindness.

`buyer_sim` measured the defect that repeats: **8 of the 8 cells that render a field
the Act leaves blind render it as settled.** Not one of them was wrong about the
number. Every one of them was silent about the width.

A guard in a test would have caught the eight cells that exist. This file makes the
defect unrepresentable instead — `Chip.__post_init__` raises when `blindness` is
empty, so a cell that has not been told how blind it is cannot be constructed, let
alone rendered. The same move `mca_reconcile` makes for legal conclusions.

## What the strip refuses to say

There is no green pill. `headline()` never contains "reconciled" and never reports
a bare conflict count, because "0 conflicts" is what the lawyer in Q10 relied on
before signing. When nothing conflicts the strip says how many fields it could not
settle, which is a different and truer sentence.

## Why party_resolution is load-bearing here

A deal document names several companies and we hold a register for some of them.
Each rule resolves its own subject (`RULE_NEEDS`), and a rule whose subject has no
register held **does not run** — it produces a refusal naming the company and the
role. That is the difference between "we checked" and "we checked something".

## Where the class split comes from

Not the aggregator. Authorised capital is registered as divided (s.4(1)(e)(i)) and
the division lives in the memorandum, which is a *document*. `Register.classes` is
therefore a separate input, and its absence makes the headroom rule refuse rather
than compute on an aggregate.

Run: python3 checker/mca_strip.py
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field
from datetime import date

from checker.mca_reconcile import (BLOCKING, INFORMATIONAL, MATERIAL, QUESTION,
                                   REFUSED, ClassCapital, Finding, capital_headroom,
                                   charge_warranty, din_reliance, worst)
from checker.mca_snapshot import (ABSENT, FIELDS, Assessment, Snapshot, assess)
from checker.party_resolution import (RULE_NEEDS, CinReport, Party,
                                      Resolution, inspect, subjects)

_LABELS = {"charges": "Active charges", "authorised_capital": "Authorised",
           "paid_up_capital": "Paid-up", "directors": "Directors",
           "din_status": "DIN status", "financial_statements": "Financials",
           "annual_return": "Annual return"}

# Words the strip may never render. "Reconciled" and a bare conflict count are what
# the general counsel in buyer_sim Q10 relied on before signing.
FORBIDDEN_HEADLINE = ("reconciled", "0 conflicts", "no conflicts", "all clear")


class ChipWithoutBlindness(ValueError):
    """A cell that does not know how blind it is may not be rendered."""


@dataclass(frozen=True)
class Chip:
    cin: str
    field: str
    label: str
    value: str
    state: str
    blindness: str

    def __post_init__(self) -> None:
        if not (self.blindness or "").strip():
            raise ChipWithoutBlindness(
                f"{self.field}: a chip must carry its blindness. Rendering a floor "
                f"as a settled figure is the defect this strip exists to not have.")


@dataclass(frozen=True)
class Register:
    """One company's register, plus the memorandum's capital clause."""
    snapshot: Snapshot
    # From the MOA, not from the aggregator: s.4(1)(e)(i) registers capital as
    # divided, and the division is in a document we are given, not in the payload.
    classes: tuple[ClassCapital, ...] | None = None


@dataclass(frozen=True)
class DocumentFacts:
    """What the draft in front of the lawyer says. Span refs, not conclusions."""
    allotment_shares: int | None = None
    allotment_class: str = "equity"
    allotment_clause: str = ""
    states_unencumbered: bool | None = None
    encumbrance_clause: str = ""
    signatory_din: str | None = None


@dataclass(frozen=True)
class Strip:
    as_of: date
    chips: tuple[Chip, ...]
    subjects: dict[str, Resolution]
    findings: tuple[Finding, ...]
    unrun: tuple[str, ...] = _field(default_factory=tuple)
    cins: tuple[CinReport, ...] = _field(default_factory=tuple)

    @property
    def severity(self) -> str:
        return worst(self.findings)

    def headline(self) -> str:
        blocking = [f for f in self.findings if f.severity == BLOCKING]
        material = [f for f in self.findings if f.severity == MATERIAL]
        unsettled = [f for f in self.findings if f.severity == QUESTION]
        n_unrun = len(self.unrun)

        # A strip with nothing to report because nothing RAN is the Q10 failure
        # wearing a different hat: the reader sees calm and infers a clean result.
        # It gets its own sentence, and it leads.
        if not self.findings:
            if n_unrun:
                return (f"no check ran — {n_unrun} could not, for want of a subject "
                        f"or a register")
            return "no check ran, and nothing was withheld: this strip had no inputs"

        tail = (f"; {n_unrun} check{'s' if n_unrun > 1 else ''} did not run"
                if n_unrun else "")
        if blocking:
            return (f"{len(blocking)} finding{'s' if len(blocking) > 1 else ''} to "
                    f"resolve before execution{tail}")
        if material:
            return (f"{len(material)} discrepanc{'ies' if len(material) > 1 else 'y'} "
                    f"between the draft and the register{tail}")
        return (f"nothing conflicts; {len(unsettled)} field"
                f"{'s' if len(unsettled) != 1 else ''} the register cannot "
                f"settle{tail}")


def _chips(reg: Register, as_of: date, agm_date: date | None) -> tuple[Chip, ...]:
    out = []
    for name in FIELDS:
        if name not in reg.snapshot.values:
            continue
        a = assess(reg.snapshot, name, as_of, agm_date=agm_date)
        if a.state == ABSENT:
            continue
        out.append(Chip(reg.snapshot.cin, name, _LABELS.get(name, name),
                        _render(reg.snapshot.values[name]), a.state, a.sentence()))
    return tuple(out)


def _render(v: object) -> str:
    if isinstance(v, (list, tuple)):
        return str(len(v))
    if isinstance(v, dict):
        return ", ".join(f"{k}: {x}" for k, x in v.items()) or "none"
    if isinstance(v, int) and v >= 100_000:
        return f"Rs {v / 10_000_000:.2f} Cr"
    return str(v)


def build(*, registers: tuple[Register, ...], parties: tuple[Party, ...],
          document: DocumentFacts, as_of: date, document_date: date | None = None,
          agm_date: date | None = None, allow_sole_party: bool = True) -> Strip:
    """Everything the strip renders, from the three lanes that feed it.

    `allow_sole_party` is the shortcut a board resolution needs and a deal document
    must not have: with it on, a document naming one company resolves every rule to
    that company. Turn it off for an SPA, where the assumption is the failure mode.
    """
    by_cin = {r.snapshot.cin: r for r in registers}
    resolved = subjects(parties, document_date=document_date,
                        allow_sole_party=allow_sole_party)

    # Identity before anything else. A CIN the scanner mangled is a lookup against
    # a different company, and it must be visible before any figure is.
    seen, cins = set(), []
    for pty in parties:
        if pty.cin not in seen:
            seen.add(pty.cin)
            cins.append(inspect(pty.cin, document_date=document_date))

    chips: list[Chip] = []
    for reg in registers:
        chips.extend(_chips(reg, as_of, agm_date))

    findings: list[Finding] = []
    unrun: list[str] = []

    for rule, res in resolved.items():
        if not res.usable:
            unrun.append(f"{rule}: {res.verdict} — {res.reason}")
            continue
        reg = by_cin.get(res.cin)
        if reg is None:
            # The honest gap a multi-party document creates: the role is resolved
            # and we simply hold no register for that company.
            unrun.append(f"{rule}: no register held for {res.cin}, which this "
                         f"document identifies as the {res.role}")
            continue
        findings.append(_run(rule, reg, document, as_of, agm_date))

    return Strip(as_of, tuple(chips), resolved, tuple(findings), tuple(unrun),
                 tuple(cins))


def _run(rule: str, reg: Register, doc: DocumentFacts, as_of: date,
         agm_date: date | None) -> Finding:
    snap = reg.snapshot

    def blind(field: str) -> Assessment:
        return assess(snap, field, as_of, agm_date=agm_date)

    if rule == "capital_headroom":
        if doc.allotment_shares is None:
            return Finding("authorised_capital", "The draft proposes no allotment",
                           REFUSED, INFORMATIONAL, "no allotment clause read",
                           _render(snap.values.get("authorised_capital")),
                           "nothing to test against the registered capital.",
                           ("s.64(1)",), blind("authorised_capital").sentence())
        return capital_headroom(new_shares=doc.allotment_shares,
                                class_name=doc.allotment_class, classes=reg.classes,
                                aggregate_authorised=snap.values.get("authorised_capital"),
                                issued_blindness=blind("paid_up_capital"),
                                clause_ref=doc.allotment_clause)

    if rule == "charge_warranty":
        raw = snap.values.get("charges")
        return charge_warranty(
            document_states_unencumbered=doc.states_unencumbered,
            registry_charges=tuple(raw) if raw is not None else None,
            blindness=blind("charges"), clause_ref=doc.encumbrance_clause)

    if rule == "din_reliance":
        if doc.signatory_din is None:
            return Finding("din_status", "The draft names no signatory DIN",
                           REFUSED, QUESTION, "not read", "not queried",
                           "identify the signatory before relying on the register.",
                           (), blind("din_status").sentence())
        status = (snap.values.get("din_status") or {}).get(doc.signatory_din)
        return din_reliance(din=doc.signatory_din, registry_status=status,
                            blindness=blind("din_status"))

    raise ValueError(f"no runner for rule {rule!r}")


def as_json(strip: Strip) -> dict:
    return {
        "as_of": strip.as_of.isoformat(),
        "headline": strip.headline(),
        "severity": strip.severity,
        "chips": [{"cin": c.cin, "field": c.field, "label": c.label,
                   "value": c.value, "state": c.state, "blindness": c.blindness}
                  for c in strip.chips],
        "subjects": {r: {"verdict": s.verdict, "role": s.role, "cin": s.cin,
                         "reason": s.reason, "candidates": list(s.candidates)}
                     for r, s in strip.subjects.items()},
        "findings": [{"field": f.field, "headline": f.headline, "verdict": f.verdict,
                      "severity": f.severity, "document_value": f.document_value,
                      "registry_value": f.registry_value, "question": f.question,
                      "citations": list(f.citations), "blindness": f.blindness}
                     for f in strip.findings],
        "cins": [{"raw": c.raw, "state": c.state, "issues": list(c.issues),
                  "ocr_candidate": c.ocr_candidate, "year": c.year,
                  "ownership": c.ownership, "listed": c.listed, "usable": c.usable}
                 for c in strip.cins],
        "not_run": list(strip.unrun),
        "evidence_grade": "SECONDARY",
        "no_model": True,
    }


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("mca_strip")
    from checker.party_resolution import (ACQUIRER, EXECUTING_ENTITY, ISSUER,
                                          TARGET)
    today, doc_date = date(2026, 9, 12), date(2026, 6, 14)
    target, acquirer = "U72200KA2021PTC145892", "L27100MH1995PLC084781"

    # ── the defect made unrepresentable ──────────────────────────────────────
    try:
        Chip(target, "charges", "Active charges", "0", "BOUNDED_BLIND", "")
        check(False, "a chip without blindness is refused")
    except ChipWithoutBlindness as e:
        check("floor" in str(e), "a chip that does not carry its blindness cannot be "
                                 "constructed -- the 8/8 defect is unrepresentable")

    t_snap = Snapshot(target, today, "MCA21 via contracted aggregator",
                      {"charges": [{"holder": "ICICI Bank"}],
                       "authorised_capital": 50_000_000,
                       "paid_up_capital": 32_000_000,
                       "din_status": {"08412345": "DEACTIVATED"}})
    registers = (Register(t_snap, (ClassCapital("equity", 10, 40_000_000, 32_000_000),)),)
    parties = (Party(target, TARGET, span="(the 'Target')"),
               Party(target, ISSUER, span="the Company shall allot"),
               Party(target, EXECUTING_ENTITY, span="for and on behalf of the Company"),
               Party(acquirer, ACQUIRER, span="(the 'Acquirer')"))
    doc = DocumentFacts(allotment_shares=1_000_000, allotment_clause="Cl 3.2",
                        states_unencumbered=True, encumbrance_clause="Cl 5.1",
                        signatory_din="08412345")

    s = build(registers=registers, parties=parties, document=doc, as_of=today,
              document_date=doc_date)

    check(len(s.chips) == 4 and all(c.blindness for c in s.chips),
          f"every chip that renders carries its blindness ({len(s.chips)} chips)")
    check(any("s.77" in c.blindness or "may raise" in c.blindness
              for c in s.chips if c.field == "charges"),
          "...and the charges chip states the window rather than a green tick")

    # ── the headline the spec could not write ────────────────────────────────
    h = s.headline().lower()
    check(not any(w in h for w in FORBIDDEN_HEADLINE),
          f"the headline says nothing about being reconciled: {s.headline()!r}")
    check(s.severity == BLOCKING and "before execution" in s.headline(),
          f"a Rs 1 Cr allotment against Rs 0.80 Cr of equity headroom is blocking "
          f"({s.severity})")

    quiet = build(registers=registers, parties=parties,
                  document=DocumentFacts(states_unencumbered=None), as_of=today,
                  document_date=doc_date)
    qh = quiet.headline().lower()
    check("nothing conflicts" in qh and "cannot settle" in qh,
          f"with nothing conflicting it counts what it could not settle, not what "
          f"it cleared: {quiet.headline()!r}")
    check(not any(w in qh for w in FORBIDDEN_HEADLINE),
          "...and still refuses the green sentence")

    # ── a rule whose subject we hold no register for does not run ────────────
    split = (Party(target, TARGET, span="(the 'Target')"),
             Party(acquirer, ISSUER, span="the Acquirer shall allot"))
    s2 = build(registers=registers, parties=split, document=doc, as_of=today,
               document_date=doc_date)
    check("2 checks did not run" in s2.headline(),
          f"the headline counts what did not run alongside what did: "
          f"{s2.headline()!r}")

    # The live case that produced this fix: parties resolve, we hold no register,
    # and the strip must not read as calm.
    none_held = build(registers=(), parties=parties, document=doc, as_of=today,
                      document_date=doc_date)
    check(not none_held.findings and "no check ran" in none_held.headline(),
          f"with no register held nothing runs, and the headline leads with that "
          f"rather than reporting zero conflicts: {none_held.headline()!r}")
    check(not any(w in none_held.headline().lower() for w in FORBIDDEN_HEADLINE),
          "...and it is still not allowed to sound like an all-clear")
    check(any("no register held for " + acquirer in u for u in s2.unrun),
          f"the headroom rule does not run against the target's register when the "
          f"ISSUER is the acquirer: {s2.unrun}")
    check(not any(f.field == "authorised_capital" for f in s2.findings),
          "...and no capital finding is produced, rather than one about the wrong "
          "company")

    # ── the sole-party shortcut, and switching it off for a deal ─────────────
    lone = (Party(target, TARGET, span="the Company"),)
    s3 = build(registers=registers, parties=lone, document=doc, as_of=today,
               document_date=doc_date)
    check(not s3.unrun and len(s3.findings) == 3,
          f"a single-company document runs every rule under the named sole-party "
          f"assumption ({len(s3.findings)} findings, unrun={s3.unrun})")
    s4 = build(registers=registers, parties=lone, document=doc, as_of=today,
               document_date=doc_date, allow_sole_party=False)
    check("did not run" in s4.headline(),
          f"a partial run names how many checks did not: {s4.headline()!r}")
    check(len(s4.unrun) == 2 and [f.field for f in s4.findings] == ["charges"],
          f"...and with the shortcut off only the role the document actually "
          f"evidenced survives -- TARGET runs, ISSUER and EXECUTING_ENTITY refuse "
          f"({len(s4.unrun)} not run). The shortcut supplies roles nobody named, "
          f"which is exactly what a deal document must not get")

    # ── the DIN correction survives the whole pipeline ───────────────────────
    din = next(f for f in s.findings if f.field == "din_status")
    check(din.severity == QUESTION and "s.167(1)" in din.citations,
          "the deactivated DIN reaches the strip as a question citing s.167(1), not "
          "as a block")

    # ── identity is checked before any figure is rendered ────────────────────
    from checker.party_resolution import SUSPECT_OCR
    scanned = "U722OOKA2O21PTC145892"
    s5 = build(registers=registers,
               parties=(Party(scanned, TARGET, span="(the 'Target')"),),
               document=doc, as_of=today, document_date=doc_date)
    bad_cin = s5.cins[0]
    check(bad_cin.state == SUSPECT_OCR and bad_cin.ocr_candidate == target,
          f"a scanner-damaged CIN is surfaced on the strip with the candidate named "
          f"({bad_cin.state})")
    check(bad_cin.raw == scanned and not bad_cin.usable,
          "...unrepaired and unusable, so no rule runs against a guess at identity")
    check(all("no register held" in u or "UNUSABLE_CIN" in u for u in s5.unrun)
          and not s5.findings,
          f"...and every rule declines rather than reconciling the wrong company: "
          f"{s5.unrun}")

    # ── the JSON keeps every refusal ─────────────────────────────────────────
    j = as_json(s)
    check(j["evidence_grade"] == "SECONDARY" and j["no_model"] is True,
          "the payload grades its own evidence and declares no model ran")
    check(all(c["blindness"] for c in j["chips"]),
          "no chip loses its blindness on the way out")
    check("not_run" in j and isinstance(j["subjects"], dict),
          "the payload carries what did not run and who each rule resolved to")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
