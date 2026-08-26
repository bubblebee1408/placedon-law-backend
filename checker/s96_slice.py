"""s.96 end to end: source, amendment, commencement, dated text, evidence card.

The first vertical slice. One provision, carried the whole way:

    source packet -> amendment event -> commencement instrument
      -> dated reconstruction -> AGM deadline -> evidence card -> review

Nothing here is s.96-specific except the witness constants. The machinery —
`checker/witness_span.py`, `checker/commencement.py`, `checker/agm.py` — is
general; s.96 is the first provision to have all three available at once.

## Why this section

It is the section the product is built around, and until 27 Aug 2026 it could
not be reconstructed for any date before 13 June 2018: its amendment span is one
of the handful whose closing bracket India Code omits. Both halves of that gap
are now closed by primary instruments rather than by inference — the boundary by
Act 1 of 2018 s.26, which states the substituted text in full, and the effective
date by S.O. 2422(E), which appoints 13 June 2018 for section 26.

## What the card must never do

Assert a deadline without the provision text it was computed from; assert a date
without the instrument that fixed it; or present a reconstruction as verified
when a hash does not match. Every field carries its source, and the card refuses
to render as COMPLETE when any is missing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import date

# The witness, quoted from Act 1 of 2018 s.26 ("Amendment of section 96").
# Held as constants because they are evidence: changing them changes what the
# reconstruction claims, and that should require editing a file a human reads.
AMENDING_ACT = "Act 1 of 2018"
AMENDING_CLAUSE = 26
AMENDMENT_WEF = date(2018, 6, 13)
PRIOR_WORDING = "Provided that"
REPLACEMENT_TEXT = (
    "Provided that annual general meeting of an unlisted company may be held at "
    "any place in India if consent is given in writing or by electronic mode by "
    "all the members in advance: Provided further that")
MARKER = 1

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"


def _sha(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class SourcePacket:
    section: str
    title: str
    current_text: str
    current_sha256: str
    stored_sha256: str | None
    source_url: str | None
    fetched_at: str | None
    amending_act: str | None = None
    amending_clause: int | None = None
    amending_text: str | None = None
    amending_sha256: str | None = None
    amending_url: str | None = None
    commencement_identifier: str | None = None
    commencement_date: str | None = None
    commencement_sha256: str | None = None
    commencement_list_item: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.problems and all(
            (self.amending_text, self.amending_sha256,
             self.commencement_identifier, self.commencement_sha256))


def build_packet(section: str = "96") -> SourcePacket:
    from checker.section_index import section_by_number
    from checker.commencement import load_cached
    from checker.corroborate import Corroborator
    from scripts.batch1_omissions import _clause_for_section

    rec = section_by_number(section)
    if rec is None:
        return SourcePacket(section, "", "", "", None, None, None,
                            problems=[f"s.{section} is not in the corpus"])

    content = rec.get("content") or ""
    p = SourcePacket(
        section=section, title=rec.get("title", ""), current_text=content,
        current_sha256=_sha(content), stored_sha256=rec.get("sha256"),
        source_url=rec.get("source_url"), fetched_at=rec.get("fetched_at"),
    )
    # The stored hash was taken at ingestion. If it no longer matches, the record
    # changed after we vouched for it, and nothing downstream may rely on it.
    if p.stored_sha256 and not p.current_sha256.endswith(p.stored_sha256):
        p.problems.append(
            f"stored hash {p.stored_sha256[:16]}… does not match the content now held")

    try:
        c = Corroborator()
        w = c.witness_text(AMENDING_ACT)
        if w:
            text, url = w
            clause = _clause_for_section(text, section)
            if clause:
                p.amending_act = AMENDING_ACT
                p.amending_clause = AMENDING_CLAUSE
                p.amending_text = clause[:1200]
                p.amending_sha256 = _sha(clause)
                p.amending_url = url
            else:
                p.problems.append(f"{AMENDING_ACT} names no clause for s.{section}")
        else:
            p.problems.append(f"no copy of {AMENDING_ACT} is held")
    except Exception as exc:                      # network or cache failure
        p.problems.append(f"amending Act unavailable: {exc}")

    n = load_cached(AMENDMENT_WEF.isoformat())
    if n is None:
        p.problems.append(f"no commencement notification held for {AMENDMENT_WEF}")
    elif AMENDING_CLAUSE not in n.sections:
        p.problems.append(
            f"{n.identifier} does not list section {AMENDING_CLAUSE} of the "
            f"amending Act; the effective date is not supported")
    else:
        from scripts.find_commencement import list_item_for
        p.commencement_identifier = n.identifier
        p.commencement_date = n.date
        p.commencement_sha256 = n.sha256
        p.commencement_list_item = list_item_for(n.text, AMENDING_CLAUSE)
    return p


@dataclass
class DatedText:
    as_of: str
    text: str | None
    fidelity: str
    basis: str
    amendments_in_force: int
    note: str = ""


def text_as_of(packet: SourcePacket, when: date) -> DatedText:
    """The provision as it stood on `when`, with the basis for saying so."""
    from checker.as_of import section_as_of
    from checker.witness_span import apply_prior, resolve

    if not packet.current_text:
        return DatedText(when.isoformat(), None, "ABSTAIN", "no source text", 0)

    if when >= AMENDMENT_WEF:
        rec = {"content": packet.current_text, "footnote": "", "section_id": packet.section}
        r = section_as_of(rec, when)
        return DatedText(
            when.isoformat(), packet.current_text, "EXACT",
            basis=(f"on or after {AMENDMENT_WEF}, the substituted proviso is in force "
                   f"per {packet.commencement_identifier or 'an unverified instrument'}"),
            amendments_in_force=1,
            note="" if packet.commencement_identifier else
                 "commencement instrument not held; the date is unverified")

    res = resolve(packet.current_text, MARKER,
                  replacement=REPLACEMENT_TEXT, prior=PRIOR_WORDING)
    if not res.resolved:
        return DatedText(when.isoformat(), None, "PARTIAL",
                         basis=f"span unresolved: {res.status}", amendments_in_force=0,
                         note=res.note)
    before = apply_prior(packet.current_text, res)
    return DatedText(
        when.isoformat(), before, "EXACT",
        basis=(f"before {AMENDMENT_WEF}, the proviso read {PRIOR_WORDING!r}; the span "
               f"boundary is stated by {AMENDING_ACT} s.{AMENDING_CLAUSE}, not inferred"),
        amendments_in_force=0,
        note=res.note)


@dataclass
class EvidenceCard:
    section: str
    title: str
    question: str
    as_of: str
    packet: SourcePacket
    dated: DatedText
    deadline: str | None
    binding_limb: str | None
    constraints: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    status: str = INCOMPLETE
    review: str = "PENDING"

    def render(self) -> str:
        L = [
            "=" * 72,
            f"EVIDENCE CARD — s.{self.section}  {self.title}",
            "=" * 72,
            f"  question        : {self.question}",
            f"  as of           : {self.as_of}",
            "",
            "  SOURCE",
            f"    current text  : {len(self.packet.current_text)} chars  "
            f"{self.packet.current_sha256[:26]}…",
            f"    retrieved     : {self.packet.source_url or '(no url)'}",
            f"    fetched       : {self.packet.fetched_at or '(unrecorded)'}",
            "",
            "  AMENDMENT",
            f"    instrument    : {self.packet.amending_act or '(none)'} "
            f"s.{self.packet.amending_clause or '?'}",
            f"    clause hash   : {(self.packet.amending_sha256 or '-')[:26]}…",
            "",
            "  COMMENCEMENT",
            f"    notification  : {self.packet.commencement_identifier or '(none held)'}"
            f"  {self.packet.commencement_date or ''}",
            f"    list item     : {self.packet.commencement_list_item or '-'}",
            f"    hash          : {(self.packet.commencement_sha256 or '-')[:26]}…",
            "",
            "  TEXT AS OF THIS DATE",
            f"    fidelity      : {self.dated.fidelity}",
            f"    basis         : {self.dated.basis}",
            f"    amendments    : {self.dated.amendments_in_force} in force",
            "",
            "  COMPUTATION",
            f"    deadline      : {self.deadline or '(none)'}",
            f"    binding limb  : {self.binding_limb or '(none)'}",
        ]
        for c in self.constraints:
            L.append(f"      - {c}")
        if self.missing_facts:
            L.append("")
            L.append("  MISSING FACTS")
            L += [f"      - {m}" for m in self.missing_facts]
        if self.unresolved:
            L.append("")
            L.append("  UNRESOLVED — not decided by this system")
            L += [f"      - {u}" for u in self.unresolved]
        if self.packet.problems:
            L.append("")
            L.append("  SOURCE PROBLEMS")
            L += [f"      - {p}" for p in self.packet.problems]
        L += ["", f"  STATUS          : {self.status}",
              f"  REVIEW          : {self.review}",
              ""]
        if self.status != COMPLETE:
            L.append("  This card is INCOMPLETE. The deadline shown, if any, is not")
            L.append("  supported end to end and must not be relied on.")
            L.append("")
        return "\n".join(L)

    def to_json(self) -> str:
        d = asdict(self)
        d["packet"] = {k: v for k, v in d["packet"].items() if k != "current_text"}
        return json.dumps(d, indent=1, default=str)


# Recorded, not decided. See docs/COMPLIANCE_MECHANICS.md §4.
UNRESOLVED_NOTES = (
    "Whether a Registrar's extension under the third proviso to s.96(1) also "
    "displaces the fifteen-month limb, or only the six-month limb, is not stated "
    "in the section. This system extends neither without an order as input.",
)


def card(*, financial_year_end: date, as_of: date, is_first_agm: bool = False,
         previous_agm: date | None = None,
         is_one_person_company: bool = False) -> EvidenceCard:
    """The whole slice: source, amendment, commencement, dated text, deadline."""
    from checker.agm import compute

    p = build_packet("96")
    d = text_as_of(p, as_of)

    q = (f"AGM deadline for a financial year ending {financial_year_end}"
         + (" (One Person Company)" if is_one_person_company else "")
         + (" — first AGM" if is_first_agm else ""))

    deadline = binding = None
    constraints: list[str] = []
    missing: list[str] = []

    if d.text is None:
        missing.append(f"the text of s.96 as it stood on {as_of} could not be "
                       "reconstructed, so no deadline is computed from it")
    else:
        r = compute(source_text=d.text, financial_year_end=financial_year_end,
                    is_first_agm=is_first_agm, previous_agm=previous_agm,
                    is_one_person_company=is_one_person_company)
        constraints = [
            f"{c.label}: {c.interval_text} from {c.anchor_label} ({c.anchor}) "
            f"= {c.deadline}" for c in r.constraints]
        missing = list(r.missing_facts)
        if r.binding:
            deadline = r.binding.deadline.isoformat()
            binding = r.binding.label
        for n in r.notes:
            constraints.append(n)

    status = COMPLETE if (p.complete and d.fidelity == "EXACT"
                          and (deadline or is_one_person_company)
                          and not missing) else INCOMPLETE

    return EvidenceCard(
        section="96", title=p.title, question=q, as_of=as_of.isoformat(),
        packet=p, dated=d, deadline=deadline, binding_limb=binding,
        constraints=constraints, missing_facts=missing,
        unresolved=list(UNRESOLVED_NOTES), status=status,
    )


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

    print("s96_slice")

    p = build_packet("96")
    check(p.current_text and p.title, f"the source packet loads ({p.title})")
    check(p.current_sha256.startswith("sha256:"), "the current text is hashed")
    check(p.amending_act == AMENDING_ACT and p.amending_sha256,
          "the amending clause is attached with its hash")
    check(p.commencement_identifier == "S.O. 2422(E)",
          f"the commencement instrument is identified ({p.commencement_identifier})")
    check(p.commencement_list_item and "26" in p.commencement_list_item,
          f"the exact list item is quoted ({p.commencement_list_item})")
    check(p.complete, f"the packet is complete ({p.problems})")

    import re as _re

    def plain(s):
        return _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", s or ""))

    before = text_as_of(p, date(2018, 6, 12))
    on = text_as_of(p, date(2018, 6, 13))
    after = text_as_of(p, date(2026, 1, 1))

    check(before.fidelity == "EXACT" and on.fidelity == "EXACT",
          "both sides of the boundary reconstruct EXACT")
    check("unlisted company may be held at any place" not in plain(before.text),
          "the substituted proviso is absent the day before commencement")
    check("unlisted company may be held at any place" in plain(on.text),
          "...and present on the commencement date itself")
    check(plain(on.text) == plain(after.text),
          "a later date returns the same text; no further amendment intervenes")
    check(len(plain(before.text)) < len(plain(on.text)),
          f"the earlier text is shorter ({len(plain(before.text))} vs "
          f"{len(plain(on.text))})")
    check("not inferred" in before.basis,
          "the earlier text states that its boundary came from the instrument")

    # The parts of the section outside the amended span must not move.
    for anchor in ("fifteen months shall elapse", "nine months", "six months",
                   "National Holiday"):
        check(anchor in plain(before.text) and anchor in plain(on.text),
              f"{anchor!r} is unchanged across the boundary")

    # Cards.
    c = card(financial_year_end=date(2026, 3, 31), as_of=date(2026, 3, 31),
             previous_agm=date(2025, 5, 10))
    check(c.status == COMPLETE, f"a fully-sourced card is COMPLETE ({c.status})")
    check(c.deadline == "2026-08-10",
          f"the fifteen-month limb binds ({c.deadline})")
    check(c.binding_limb and "fifteen" in c.binding_limb,
          "the binding limb is named, not just the date")
    r = c.render()
    for must in ("S.O. 2422(E)", "Act 1 of 2018", "sha256:", "UNRESOLVED",
                 "REVIEW          : PENDING"):
        check(must in r, f"the card shows {must!r}")

    hist = card(financial_year_end=date(2017, 3, 31), as_of=date(2018, 6, 12),
                previous_agm=date(2016, 8, 20))
    check(hist.dated.fidelity == "EXACT",
          "a card dated before the amendment still reconstructs EXACT")
    check(hist.deadline == "2017-09-30", f"and computes from that text ({hist.deadline})")

    opc = card(financial_year_end=date(2026, 3, 31), as_of=date(2026, 3, 31),
               is_one_person_company=True)
    check(opc.deadline is None, "an OPC card carries no deadline")
    check(any("One Person Company" in x for x in opc.constraints),
          "...and says why")

    # A card must not claim COMPLETE when its evidence is missing.
    broken = build_packet("96")
    broken.commencement_identifier = None
    broken.commencement_sha256 = None
    broken.problems.append("commencement withheld for this test")
    d2 = text_as_of(broken, date(2026, 1, 1))
    fake = EvidenceCard(section="96", title="x", question="q", as_of="2026-01-01",
                        packet=broken, dated=d2, deadline="2026-09-30",
                        binding_limb="six months")
    check(fake.status == INCOMPLETE,
          "a card missing its commencement instrument is INCOMPLETE")
    check("must not be relied on" in fake.render(),
          "...and says so in terms a reader cannot miss")

    check(any("Registrar" in u for u in c.unresolved),
          "the Registrar-extension question is carried as unresolved, not decided")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--card" in sys.argv:
        print(card(financial_year_end=date(2026, 3, 31), as_of=date(2026, 3, 31),
                   previous_agm=date(2025, 5, 10)).render())
    else:
        _test()
