"""
The PoSH extract for a Board's Report. BACKLOG P-1.

Rule 8(5)(x) of the Companies (Accounts) Rules 2014, as amended by G.S.R. 357(E) with effect
from 14 July 2025, requires the Board's Report to carry a statement on the constitution of the
Internal Committee *and* three numbers: complaints received in the year, complaints disposed of
during the year, and cases pending for more than ninety days. FY 2025-26 is the first financial
year those numbers are required, and Board's Reports for it are due at AGMs by 30 September 2026.

Three design decisions, all of which say no to something:

**We never store, ask for, or print the contents of a complaint.** Only counts. s.16 of the PoSH
Act prohibits publication of the contents of a complaint, the identity of the aggrieved woman,
the respondent, or the witnesses. A complaint register is therefore the single worst dataset a
small vendor could hold — maximum sensitivity, statutory publication bar, and no operational need
on our side, because Rule 8(5)(x) asks for integers. If a customer wants a register, they should
keep it themselves, off our infrastructure. This is not caution; it is the reading of s.16.

**We refuse to draft the compliance statement for a defective committee.** That sentence is a
representation to the Registrar of Companies in a filed document. If `ic_order.validate()` finds
a blocking failure of s.4(2), the extract still generates — with the numbers, and with the
failures — but the statement itself is withheld and replaced by an explanation. Printing "the
company has complied" over a committee with no external member would be manufacturing a false
statement in a statutory filing, which is a materially worse thing than an unhelpful tool.

**We abstain for One Person Companies and Small Companies.** Rule 8(6) says Rule 8 does not apply
to them. Whether Rule 8A requires an IC statement anyway is disputed — the full text we hold
shows no such clause, two secondary sources say otherwise, and it is Question 6 in the lawyer
pack. Until that is answered we say we do not know, because the alternative is telling a small
company either to file something it need not file or to omit something it must.

Run: python3 checker/board_report.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.ic_order import Issue, Member, validate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSH = ROOT / "corpus/provisions/posh_act_2013.json"
MCA = ROOT / "corpus/provisions/companies_accounts_rules_2014.json"

INQUIRY_DAYS = 90
CITE_INQUIRY = "s.11(4), PoSH Act 2013"
CITE_RULE = "Rule 8(5)(x), Companies (Accounts) Rules 2014"
CITE_EXEMPT = "Rule 8(6), Companies (Accounts) Rules 2014"
CITE_PENALTY = "s.134(8), Companies Act 2013"


@dataclass(frozen=True)
class Counts:
    """The three numbers, plus the opening balance needed to check them against each other."""

    opening_pending: int
    received: int
    disposed: int
    pending_over_90: int

    @property
    def closing_pending(self) -> int:
        return self.opening_pending + self.received - self.disposed


@dataclass(frozen=True)
class Extract:
    counts: Counts
    issues: list[Issue]
    may_state_compliance: bool
    committee_issues: list[Issue]

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "blocking"]


class Exempt(Exception):
    """Raised for OPC / Small Company. Carries the reason, because the reason is the answer."""


def _quote(path: Path, citation: str, field: str = "text_display") -> str:
    """Pull a provision's text from a corpus file rather than retyping it here."""
    for p in json.loads(path.read_text())["provisions"]:
        if p["citation"] == citation:
            return p.get(field) or ""
    raise KeyError(citation)


def inquiry_deadline_text() -> str:
    """Verbatim from the ingested PoSH Act. This is the sentence box (c) counts breaches of."""
    for p in json.loads(POSH.read_text())["provisions"]:
        if p["section_number"] == 11:
            body = " ".join(p["text_display"].split())
            marker = "The inquiry under sub-section (1) shall be completed within a period of"
            i = body.find(marker)
            if i >= 0:
                return body[i : body.index(".", i + len(marker)) + 1]
    return ""


def check_counts(c: Counts, *, has_lawful_ic: bool) -> list[Issue]:
    """
    Arithmetic and statutory consistency. Every issue here is something a Registrar could see on
    the face of the filing, so it is better found now than in an adjudication order.
    """
    issues: list[Issue] = []

    for label, value in (("opening", c.opening_pending), ("received", c.received),
                         ("disposed", c.disposed), ("pending over ninety days",
                                                    c.pending_over_90)):
        if value < 0:
            issues.append(Issue("blocking", f"The count of {label} complaints cannot be "
                                            f"negative.", CITE_RULE))
    if issues:
        return issues

    if c.disposed > c.opening_pending + c.received:
        issues.append(Issue(
            "blocking",
            f"You report disposing of {c.disposed} complaints but only had "
            f"{c.opening_pending + c.received} available to dispose of "
            f"({c.opening_pending} carried forward plus {c.received} received). These numbers "
            f"cannot all be right, and they are being filed with the Registrar.",
            CITE_RULE))

    # Only meaningful once the closing balance is coherent. If `disposed` already exceeds what
    # was available, `closing_pending` is negative and this check fires with a message that
    # reads as nonsense — "0 pending beyond ninety days, but only -3 are pending at all". One
    # clear blocking issue beats two, where the second is an artefact of the first.
    if c.closing_pending >= 0 and c.pending_over_90 > c.closing_pending:
        issues.append(Issue(
            "blocking",
            f"You report {c.pending_over_90} cases pending beyond ninety days, but only "
            f"{c.closing_pending} are pending at all. A case cannot be overdue and closed.",
            CITE_RULE))

    if c.received > 0 and not has_lawful_ic:
        issues.append(Issue(
            "blocking",
            f"You received {c.received} complaint(s) during the year, and the committee below "
            f"does not satisfy section 4(2). Complaints were handled by a body that was not a "
            f"lawfully constituted Internal Committee. Do not file this without advice.",
            "s.4(2), PoSH Act 2013"))

    if c.pending_over_90 > 0:
        issues.append(Issue(
            "flag",
            f"Every one of these {c.pending_over_90} cases is an inquiry that has run past the "
            f"statutory limit — “{inquiry_deadline_text()}” Box (c) is not a neutral "
            f"statistic. You are reporting {c.pending_over_90} breach(es) of section 11(4) to "
            f"the Registrar, in your own filing, over your directors' signatures.",
            CITE_INQUIRY))

    if c.closing_pending == 0 and c.received == 0 and c.opening_pending == 0:
        issues.append(Issue(
            "flag",
            "A nil return is a perfectly ordinary thing to file. It is worth being sure it means "
            "no complaints were made, rather than that no route existed to make one — s.19 "
            "requires the employer to display the penal consequences and the committee order at "
            "a conspicuous place.",
            "s.19(b), PoSH Act 2013"))

    return issues


def build(members: list[Member], counts: Counts, *,
          is_small_company: bool = False, is_opc: bool = False) -> Extract:
    if is_small_company or is_opc:
        kind = "One Person Company" if is_opc else "Small Company"
        raise Exempt(
            f"{_quote(MCA, CITE_EXEMPT)} You have told us this is a {kind}, so the three-number "
            f"disclosure in Rule 8(5)(x) does not reach you.\n\n"
            f"Whether the abridged Board's Report under Rule 8A still requires a statement on "
            f"the Internal Committee is genuinely unsettled. The full text of Rule 8A we hold "
            f"lists clauses (a) to (j) and contains no such clause; two secondary sources say "
            f"the statement is required anyway. We are not going to guess, because guessing "
            f"wrong means either filing something you need not file or omitting something you "
            f"must. It is Question 6 in the pack we are sending to an employment lawyer.\n\n"
            f"None of this affects the PoSH Act itself. Section 4 applies to every employer of a "
            f"workplace regardless of company size or class, and you can still generate the "
            f"Internal Committee order.")

    verdict = validate(members)
    lawful = not [i for i in verdict.issues if i.severity == "blocking"]
    return Extract(
        counts=counts,
        issues=check_counts(counts, has_lawful_ic=lawful),
        may_state_compliance=lawful,
        committee_issues=[i for i in verdict.issues if i.severity == "blocking"],
    )


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    LAWFUL = [
        Member("Ms A. Rao", True, "employee", "VP Engineering", True, True),
        Member("Ms B. Nair", True, "employee", "Finance", False, False),
        Member("Mr C. Das", False, "employee", "Design", False, False),
        Member("Ms D. Iyer", True, "external_ngo", "Vimochana", False, False),
    ]
    DEFECTIVE = LAWFUL[:3]           # no external member — fails s.4(2)(c)

    failures = 0

    def check(name: str, got, want) -> None:
        global failures
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  got={got!r}"))

    check("s.11(4) quoted from the ingested corpus, not retyped",
          inquiry_deadline_text(),
          "The inquiry under sub-section (1) shall be completed within a period of ninety days.")

    nil = build(LAWFUL, Counts(0, 0, 0, 0))
    check("nil return: no blocking issues", nil.blocking, [])
    check("  ...may state compliance", nil.may_state_compliance, True)
    check("  ...but asks whether nil means safe or silent",
          any("conspicuous place" in i.message for i in nil.issues), True)

    ok = build(LAWFUL, Counts(1, 4, 3, 0))
    check("ordinary year adds up", ok.blocking, [])
    check("  ...closing pending derived, not asked for", ok.counts.closing_pending, 2)

    over = build(LAWFUL, Counts(0, 5, 2, 2))
    check("pending>90 flagged as s.11(4) breaches",
          any(i.citation == CITE_INQUIRY for i in over.issues), True)
    check("  ...and it quotes the section verbatim",
          any("shall be completed within a period of ninety days" in i.message
              for i in over.issues), True)

    impossible = build(LAWFUL, Counts(0, 2, 5, 0))
    check("disposing more than you ever had is blocking",
          [i.severity for i in impossible.blocking], ["blocking"])

    overdue = build(LAWFUL, Counts(0, 3, 3, 1))
    check("more overdue than pending is blocking",
          any("cannot be overdue and closed" in i.message for i in overdue.blocking), True)

    bad_ic = build(DEFECTIVE, Counts(0, 2, 1, 0))
    check("complaints handled by a defective committee is blocking",
          any("not a lawfully constituted" in i.message for i in bad_ic.blocking), True)
    check("  ...and the compliance statement is withheld", bad_ic.may_state_compliance, False)

    quiet_bad_ic = build(DEFECTIVE, Counts(0, 0, 0, 0))
    check("defective committee with no complaints: still no compliance statement",
          quiet_bad_ic.may_state_compliance, False)
    check("  ...but not blocked on the numbers", quiet_bad_ic.blocking, [])

    check("negative counts rejected",
          any("cannot be negative" in i.message for i in build(LAWFUL, Counts(0, -1, 0, 0)).blocking),
          True)

    for flag in ({"is_small_company": True}, {"is_opc": True}):
        try:
            build(LAWFUL, Counts(0, 0, 0, 0), **flag)
            check(f"{flag} abstains", False, True)
        except Exempt as e:
            check(f"{list(flag)[0]} abstains with Rule 8(6) quoted",
                  "This rule shall not apply" in str(e), True)
            check("  ...and says the Rule 8A question is open",
                  "Question 6" in str(e), True)
            check("  ...and does not imply the PoSH Act stops applying",
                  "Section 4 applies to every employer" in str(e), True)

    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
