"""
Internal Committee constitution order — validate a proposed committee, then draft the order.

s.4(1) makes the document itself the statutory act: the employer must constitute the Committee
**"by an order in writing"**. So this is not a nice-to-have template — producing it is how the
duty is discharged.

Every rule below is read off the verbatim text in `corpus/provisions/posh_act_2013.json`
(s.4, sha256-pinned), not from a summary. Where the Act is genuinely ambiguous we say so and
take the conservative reading rather than picking one silently.

No LLM. Deterministic, so it costs ₹0 to run (DECISIONS D-3).

Run:  python3 checker/ic_order.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"

# ── What s.4 actually requires, clause by clause ─────────────────────────────
# (1)     "by an order in writing" — the document is the act
# (1) pv  IC at all administrative units where offices are at different places
# (2)(a)  Presiding Officer: a WOMAN employed at a SENIOR level, from amongst the employees
# (2)(b)  NOT LESS THAN TWO members from amongst employees
# (2)(c)  ONE member from an NGO/association committed to the cause of women
# (2) pv  "at least one-half of the total Members so nominated shall be women"
# (3)     term "not exceeding three years"
MIN_EMPLOYEE_MEMBERS = 2
MIN_EXTERNAL_MEMBERS = 1
MAX_TERM_YEARS = 3

CITE = {
    "order":      "s.4(1), PoSH Act 2013",
    "branches":   "s.4(1) proviso, PoSH Act 2013",
    "presiding":  "s.4(2)(a), PoSH Act 2013",
    "employees":  "s.4(2)(b), PoSH Act 2013",
    "external":   "s.4(2)(c), PoSH Act 2013",
    "half_women": "s.4(2) proviso, PoSH Act 2013",
    "tenure":     "s.4(3), PoSH Act 2013",
}


@dataclass(frozen=True)
class Member:
    name: str
    is_woman: bool
    source: Literal["employee", "external_ngo"]
    designation: str = ""
    senior_level: bool = False
    presiding: bool = False


@dataclass(frozen=True)
class Issue:
    severity: Literal["blocking", "flag"]
    message: str
    citation: str


@dataclass(frozen=True)
class Validation:
    issues: list[Issue] = field(default_factory=list)

    @property
    def is_lawful(self) -> bool:
        return not any(i.severity == "blocking" for i in self.issues)

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "blocking"]


def validate(members: list[Member], *, term_years: int = MAX_TERM_YEARS,
             multi_site: bool = False) -> Validation:
    """Check a proposed committee against s.4(2) and s.4(3). Citations on every finding."""
    issues: list[Issue] = []

    presiding = [m for m in members if m.presiding]
    if len(presiding) != 1:
        issues.append(Issue(
            "blocking",
            f"The order must name exactly one Presiding Officer; {len(presiding)} were marked.",
            CITE["presiding"]))
    else:
        po = presiding[0]
        if not po.is_woman:
            issues.append(Issue(
                "blocking",
                f"The Presiding Officer must be a woman. {po.name} is not marked as one. "
                f"The Act is unqualified on this point.",
                CITE["presiding"]))
        if po.source != "employee":
            issues.append(Issue(
                "blocking",
                f"The Presiding Officer must be employed at the workplace. {po.name} is external.",
                CITE["presiding"]))
        elif not po.senior_level:
            issues.append(Issue(
                "blocking",
                f"The Presiding Officer must be employed at a senior level. {po.name} is not "
                f"marked senior. If no senior woman is available here, the Act lets you nominate "
                f"one from another office of the same employer — it does not let you drop the "
                f"requirement.",
                CITE["presiding"]))

    employee_members = [m for m in members if m.source == "employee" and not m.presiding]
    if len(employee_members) < MIN_EMPLOYEE_MEMBERS:
        issues.append(Issue(
            "blocking",
            f"Not less than two Members must come from amongst the employees, besides the "
            f"Presiding Officer. You have {len(employee_members)}.",
            CITE["employees"]))

    external = [m for m in members if m.source == "external_ngo"]
    if len(external) < MIN_EXTERNAL_MEMBERS:
        issues.append(Issue(
            "blocking",
            "One Member must come from an NGO or association committed to the cause of women, or "
            "be a person familiar with issues relating to sexual harassment. This is the member "
            "companies most often leave out.",
            CITE["external"]))

    # The proviso reads: "at least one-half of the total Members so nominated shall be women."
    # Whether "Members so nominated" includes the Presiding Officer is genuinely unclear — the
    # proviso sits under (c), after (a) names the PO separately. We take the conservative
    # reading (count everyone) and flag the ambiguity rather than resolve it ourselves.
    women = sum(1 for m in members if m.is_woman)
    if members and women * 2 < len(members):
        issues.append(Issue(
            "blocking",
            f"At least half of those nominated must be women. You have {women} of "
            f"{len(members)}.",
            CITE["half_women"]))
    issues.append(Issue(
        "flag",
        "We counted the Presiding Officer toward the one-half requirement. The proviso says "
        "\"Members so nominated\" and sits under clause (c), so a narrower reading counting only "
        "clauses (b) and (c) is arguable. We took the stricter reading; a lawyer should confirm.",
        CITE["half_women"]))

    if term_years > MAX_TERM_YEARS:
        issues.append(Issue(
            "blocking",
            f"Members hold office for a period not exceeding three years. You specified "
            f"{term_years}.",
            CITE["tenure"]))

    if multi_site:
        issues.append(Issue(
            "flag",
            "You told us you have offices at more than one location. A separate Internal "
            "Committee is required at every administrative unit or office — one central "
            "committee does not cover the others.",
            CITE["branches"]))

    return Validation(issues)


def draft_order(company: str, members: list[Member], *, on: date,
                term_years: int = MAX_TERM_YEARS, state: str = "") -> str:
    """The order in writing that s.4(1) requires. Plain text; the caller renders it."""
    po = next((m for m in members if m.presiding), None)
    others = [m for m in members if not m.presiding]
    until = on.replace(year=on.year + term_years)

    def line(m: Member) -> str:
        role = ("Presiding Officer" if m.presiding
                else "Member (external)" if m.source == "external_ngo" else "Member")
        desig = f", {m.designation}" if m.designation else ""
        return f"  {m.name}{desig} — {role}"

    body = [
        f"{company.upper()}",
        f"ORDER CONSTITUTING THE INTERNAL COMMITTEE",
        f"Dated {on:%d %B %Y}" + (f" · {state}" if state else ""),
        "",
        "In exercise of the obligation under section 4(1) of the Sexual Harassment of Women at",
        "Workplace (Prevention, Prohibition and Redressal) Act, 2013, which requires every",
        "employer of a workplace to constitute a Committee by an order in writing, the Internal",
        "Committee is hereby constituted as follows:",
        "",
    ]
    if po:
        body.append(line(po))
    body += [line(m) for m in others]
    body += [
        "",
        f"The Presiding Officer and every Member shall hold office from {on:%d %B %Y} until",
        f"{until:%d %B %Y}, being a period not exceeding three years from the date of their",
        "nomination [s.4(3)].",
        "",
        "The penal consequences of sexual harassment and this order shall be displayed at a",
        "conspicuous place at the workplace [s.19(b)].",
        "",
        "",
        "_______________________",
        "For and on behalf of the employer",
        "",
        "---",
        "Drafted by placedon.com from the text of the PoSH Act 2013 as published on India Code.",
        "Not legal advice, and not yet reviewed by a lawyer — have counsel check it before it is",
        "signed.",
    ]
    return "\n".join(body)


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    # Assert the rules match the corpus rather than trusting the constants above.
    corpus = json.loads(CORPUS.read_text())
    s4 = next(p for p in corpus["provisions"] if p["section_number"] == 4)["text_display"]
    corpus_checks = [
        ("s.4(1) requires an order in writing", "by an order in writing" in s4),
        ("s.4(2)(a) requires a woman at senior level",
         "a woman employed at a senior level" in s4),
        ("s.4(2)(b) says not less than two", "not less than two Members" in s4),
        ("s.4(2) proviso requires one-half women",
         "at least one-half of the total Members so nominated shall be women" in s4),
        ("s.4(3) caps the term at three years", "not exceeding three years" in s4),
    ]

    ok_committee = [
        Member("Ms A. Rao", True, "employee", "VP Engineering", senior_level=True, presiding=True),
        Member("Ms B. Nair", True, "employee", "Finance Lead"),
        Member("Mr C. Das", False, "employee", "Design"),
        Member("Ms D. Iyer", True, "external_ngo", "Vimochana"),
    ]

    cases = [
        ("a lawful committee passes", validate(ok_committee).is_lawful, True),
        ("male Presiding Officer blocks",
         validate([Member("Mr X", False, "employee", senior_level=True, presiding=True),
                   *ok_committee[1:]]).is_lawful, False),
        ("non-senior Presiding Officer blocks",
         validate([Member("Ms A", True, "employee", presiding=True),
                   *ok_committee[1:]]).is_lawful, False),
        ("missing external member blocks",
         validate(ok_committee[:3]).is_lawful, False),
        ("only one employee member blocks",
         validate([ok_committee[0], ok_committee[1], ok_committee[3]]).is_lawful, False),
        ("under half women blocks",
         validate([ok_committee[0],
                   Member("Mr P", False, "employee"), Member("Mr Q", False, "employee"),
                   Member("Mr R", False, "external_ngo")]).is_lawful, False),
        ("four-year term blocks", validate(ok_committee, term_years=4).is_lawful, False),
        ("no Presiding Officer at all blocks",
         validate([m for m in ok_committee if not m.presiding]).is_lawful, False),
    ]

    failures = 0
    print("=== rules match the ingested text ===")
    for name, got in corpus_checks:
        failures += (not got)
        print(f"[{'PASS' if got else 'FAIL'}] {name}")

    print("\n=== validation ===")
    for name, got, want in cases:
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")

    print("\n=== every finding carries a citation ===")
    all_issues = validate(ok_committee[:2], term_years=9, multi_site=True).issues
    cited = all(i.citation for i in all_issues)
    failures += (not cited)
    print(f"[{'PASS' if cited else 'FAIL'}] {len(all_issues)} findings, all cited")

    print("\n=== the ambiguity is disclosed, not resolved silently ===")
    flagged = any("a lawyer should confirm" in i.message for i in validate(ok_committee).issues)
    failures += (not flagged)
    print(f"[{'PASS' if flagged else 'FAIL'}] one-half proviso ambiguity surfaced")

    print("\n" + "─" * 78)
    print(draft_order("Acme Software Pvt Ltd", ok_committee,
                      on=date(2026, 8, 8), state="Bengaluru, Karnataka"))
    print("─" * 78)

    total = len(corpus_checks) + len(cases) + 2
    print(f"\n{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)
