"""A company's own contract standards, as DATA, evaluated by pure functions.

PLAN_22 §6: playbook rules are "evaluated by CODE", and what comes out is a
**POTENTIAL_ISSUE -- never a legal defect**. That distinction is the whole design and not
a wording preference. A playbook says what THIS company usually accepts; it does not say
what the law requires. "Your standard is 3 years and this says 5" is a fact about the
company. "This clause is unenforceable" is legal advice, and nothing here is entitled to
say it -- not the rules, not the model that read the clause, and not the report.

So `Finding` carries no severity, no "violation", no "breach" and no "risk score". It
carries a STATUS, the rule that produced it, and the span it was decided on. A test asserts
the vocabulary, because the pressure to add `severity: HIGH` arrives the first time someone
builds a dashboard.

## The four statuses

    MATCHES        the clause is there and meets the standard
    DEVIATES       the clause is there and does not. The company's standard, not the law's
    MISSING        the standard expects a clause and none was extracted
    NEEDS_LAWYER   code cannot decide. An unverified value, an unparseable one, or a rule
                   that is deliberately a human's call

**NEEDS_LAWYER is not an error state.** It is the honest answer whenever the deterministic
test does not apply, and a playbook that never returns it is one that is guessing
somewhere.

## Why an unverified value can only be NEEDS_LAWYER

F12 requires every extracted value to be re-derivable from a verbatim span. A value that
failed that check has no evidence behind it, and running a numeric comparison on it would
produce a confident DEVIATES from a number the model may have invented. `evaluate` refuses
to grade an unverified value at all.

Run: PYTHONPATH=. python3 checker/playbook.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MATCHES = "MATCHES"
DEVIATES = "DEVIATES"
MISSING = "MISSING"
NEEDS_LAWYER = "NEEDS_LAWYER"
STATUSES = (MATCHES, DEVIATES, MISSING, NEEDS_LAWYER)

# What a finding IS, reported outward. One value, deliberately: a second one would be the
# beginning of a severity scale, and a severity scale is a legal opinion with a number on it.
POTENTIAL_ISSUE = "POTENTIAL_ISSUE"

EQUALS = "equals"
IN_LIST = "in_list"
MAX_YEARS = "max_years"
MAX_AMOUNT = "max_amount"
MUST_BE_PRESENT = "must_be_present"
MUST_BE_ABSENT_OR_APPROVED = "must_be_absent_or_approved"
TESTS = (EQUALS, IN_LIST, MAX_YEARS, MAX_AMOUNT, MUST_BE_PRESENT,
         MUST_BE_ABSENT_OR_APPROVED)

DRAFT = "DRAFT"
APPROVED = "APPROVED"


class PlaybookError(ValueError):
    """The playbook itself is wrong. Raised at load, never carried into a finding."""


# ── parsing the two quantities a contract states in words ────────────────────

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
          "twenty": 20, "thirty": 30}
_MULT = {"thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000,
         "crores": 10_000_000, "million": 1_000_000, "billion": 1_000_000_000}


def years(text: str | int | float | None) -> float | None:
    """Years as a number, or None when it cannot be read. None is NEEDS_LAWYER upstream."""
    if isinstance(text, (int, float)):
        return float(text)
    if not text:
        return None
    t = str(text).lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(year|month)", t)
    if m:
        n = float(m.group(1))
        return n / 12 if m.group(2) == "month" else n
    for word, n in _WORDS.items():
        if re.search(rf"\b{word}\s+(year|month)", t):
            return n / 12 if "month" in t else float(n)
    return None


def amount(text: str | int | float | None) -> float | None:
    """A money amount, Indian numbering included. None when unreadable."""
    if isinstance(text, (int, float)):
        return float(text)
    if not text:
        return None
    t = str(text).lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([a-z]+)?", t)
    if not m:
        return None
    n = float(m.group(1))
    word = (m.group(2) or "").strip()
    return n * _MULT.get(word, 1)


# ── the data ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rule:
    id: str
    clause: str
    test: str
    why: str
    value: object = None
    approved_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.test not in TESTS:
            raise PlaybookError(
                f"rule {self.id!r} has test {self.test!r}, which is not one of {TESTS}. "
                f"An unknown test cannot be evaluated, and defaulting it to 'pass' would "
                f"make the rule decorative.")


@dataclass(frozen=True)
class Playbook:
    id: str
    version: str
    status: str
    rules: tuple[Rule, ...]
    approved_by: str | None = None

    @property
    def is_draft(self) -> bool:
        return self.status != APPROVED


@dataclass(frozen=True)
class Finding:
    rule_id: str
    clause: str
    status: str
    why: str
    detail: str
    span: str | None = None
    playbook_status: str = DRAFT
    kind: str = POTENTIAL_ISSUE


@dataclass(frozen=True)
class Extracted:
    """One clause the model found: its type, the verbatim span, and the value read from it.

    `verified` is set by the caller AFTER quoted_span has confirmed the span occurs in the
    contract and the value is re-derivable from it. This module never sets it.
    """
    clause: str
    span: str | None = None
    value: object = None
    verified: bool = False


# ── the pure functions ───────────────────────────────────────────────────────

def evaluate(rule: Rule, found: Extracted | None, *, draft: bool = True) -> Finding:
    """One rule against one extracted clause. No I/O, no model, no mutation."""
    def out(status: str, detail: str) -> Finding:
        return Finding(rule.id, rule.clause, status, rule.why, detail,
                       span=(found.span if found else None),
                       playbook_status=DRAFT if draft else APPROVED)

    if rule.test == MUST_BE_ABSENT_OR_APPROVED:
        if found is None:
            return out(MATCHES, "the clause is absent, which is the standard")
        if str(found.value or found.span or "") in rule.approved_values:
            return out(MATCHES, f"present in an approved form: {found.value!r}")
        return out(NEEDS_LAWYER,
                   "present, and not in the approved list. Code cannot decide whether this "
                   "form is acceptable; a person has to look")

    if found is None:
        return out(MISSING, "the standard expects this clause and none was extracted")

    if not found.verified:
        # The one place this refuses to grade. A numeric comparison against a value with
        # no verbatim span behind it would produce a confident DEVIATES from a number the
        # model may have invented.
        return out(NEEDS_LAWYER,
                   "the value could not be re-derived from a verbatim span, so it is not "
                   "evidence and is not graded")

    if rule.test == MUST_BE_PRESENT:
        return out(MATCHES, "present, which is the standard")

    if rule.test == EQUALS:
        same = str(found.value).strip().lower() == str(rule.value).strip().lower()
        return out(MATCHES if same else DEVIATES,
                   f"{found.value!r} against the standard {rule.value!r}")

    if rule.test == IN_LIST:
        allowed = [str(v).strip().lower() for v in (rule.value or [])]
        ok = str(found.value).strip().lower() in allowed
        return out(MATCHES if ok else DEVIATES,
                   f"{found.value!r} against the accepted list {rule.value!r}")

    reader = years if rule.test == MAX_YEARS else amount
    got, cap = reader(found.value), reader(rule.value)
    if got is None or cap is None:
        return out(NEEDS_LAWYER,
                   f"{found.value!r} could not be read as a "
                   f"{'duration' if rule.test == MAX_YEARS else 'money amount'}")
    return out(MATCHES if got <= cap else DEVIATES,
               f"{found.value!r} ({got:g}) against the standard maximum "
               f"{rule.value!r} ({cap:g})")


def review(book: Playbook, extracted) -> tuple[Finding, ...]:
    """Every rule, against whatever was extracted. Order follows the playbook."""
    by_clause: dict[str, Extracted] = {}
    for e in extracted:
        by_clause.setdefault(e.clause, e)
    return tuple(evaluate(r, by_clause.get(r.clause), draft=book.is_draft)
                 for r in book.rules)


def load(path: str | Path) -> Playbook:
    """A playbook from JSON. A malformed one raises here rather than mis-grading later."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PlaybookError(f"{p}: {e}") from None
    for key in ("id", "version", "status", "rules"):
        if key not in raw:
            raise PlaybookError(f"{p}: playbook has no {key!r}")
    if raw["status"] not in (DRAFT, APPROVED):
        raise PlaybookError(
            f"{p}: status {raw['status']!r} is not {DRAFT} or {APPROVED}. A playbook is "
            f"one or the other; anything else would be read as approved by accident.")
    if raw["status"] == APPROVED and not raw.get("approved_by"):
        raise PlaybookError(
            f"{p}: status is {APPROVED} with no approved_by. An approval with no name on "
            f"it is not an approval.")
    rules = tuple(Rule(id=r["id"], clause=r["clause"], test=r["test"], why=r["why"],
                       value=r.get("value"),
                       approved_values=tuple(r.get("approved_values", ())))
                  for r in raw["rules"])
    if len({r.id for r in rules}) != len(rules):
        raise PlaybookError(f"{p}: two rules share an id; a finding could not be traced back")
    return Playbook(raw["id"], raw["version"], raw["status"], rules,
                    raw.get("approved_by"))


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

    def r(test, value=None, clause="Term", approved=()):
        return Rule(id=f"R-{test}", clause=clause, test=test, why="the company standard",
                    value=value, approved_values=tuple(approved))

    def e(value, *, verified=True, clause="Term", span="the span"):
        return Extracted(clause=clause, span=span, value=value, verified=verified)

    # ── the quantity readers ────────────────────────────────────────────────
    check(years("three years") == 3 and years("3 years") == 3, "years, in words or digits")
    check(years("36 months") == 3, "...and months become years")
    check(years("for ever") is None, "...and an unreadable duration is None, not 0")
    check(amount("Rs 40,00,000") == 4_000_000, "an Indian-formatted amount is read")
    check(amount("5 crore") == 50_000_000 and amount("2 lakh") == 200_000,
          "...crore and lakh included")
    check(amount("some money") is None, "...and an unreadable amount is None, not 0")

    # ── each test type ──────────────────────────────────────────────────────
    check(evaluate(r(MAX_YEARS, "3 years"), e("three years")).status == MATCHES,
          "max_years: three against a three-year standard MATCHES")
    f = evaluate(r(MAX_YEARS, "3 years"), e("five years"))
    check(f.status == DEVIATES, "max_years: five against three DEVIATES")
    check("5" in f.detail and "3" in f.detail,
          f"...and the detail shows both numbers, so a reader can see the comparison "
          f"({f.detail})")
    check(evaluate(r(MAX_AMOUNT, "1 crore"), e("Rs 50,00,000")).status == MATCHES,
          "max_amount: 50 lakh is under 1 crore")
    check(evaluate(r(MAX_AMOUNT, "1 crore"), e("2 crore")).status == DEVIATES,
          "...and 2 crore is over it")
    check(evaluate(r(EQUALS, "India"), e("india")).status == MATCHES,
          "equals is case-insensitive -- a contract saying 'India' and a standard saying "
          "'india' are the same standard")
    check(evaluate(r(EQUALS, "India"), e("Singapore")).status == DEVIATES, "...and differs")
    check(evaluate(r(IN_LIST, ["Mumbai", "Delhi"]), e("Delhi")).status == MATCHES,
          "in_list accepts a member")
    check(evaluate(r(IN_LIST, ["Mumbai", "Delhi"]), e("London")).status == DEVIATES,
          "...and deviates on a non-member")
    check(evaluate(r(MUST_BE_PRESENT), e("anything")).status == MATCHES,
          "must_be_present is satisfied by presence")
    check(evaluate(r(MUST_BE_PRESENT), None).status == MISSING,
          "...and MISSING by absence")

    # ── must_be_absent_or_approved, whose default is the opposite way round ──
    ab = r(MUST_BE_ABSENT_OR_APPROVED, clause="Non-Compete", approved=["mutual"])
    check(evaluate(ab, None).status == MATCHES,
          "must_be_absent_or_approved: ABSENT is the standard, so absence MATCHES")
    check(evaluate(ab, e("mutual", clause="Non-Compete")).status == MATCHES,
          "...an approved form matches")
    check(evaluate(ab, e("one-way, five years", clause="Non-Compete")).status
          == NEEDS_LAWYER,
          "...and an unapproved form is NEEDS_LAWYER, not DEVIATES: code has no view on "
          "whether THIS form is acceptable")

    # ── the refusal to grade an unverified value ────────────────────────────
    u = evaluate(r(MAX_YEARS, "3 years"), e("five years", verified=False))
    check(u.status == NEEDS_LAWYER,
          "an UNVERIFIED value is never graded -- it would have DEVIATED on a number with "
          "no span behind it, which is a confident finding from an invented figure")
    check("verbatim span" in u.detail, "...and the detail says why")
    check(evaluate(r(EQUALS, "India"), e("Singapore", verified=False)).status
          == NEEDS_LAWYER, "...on every test type, not only the numeric ones")

    # ── the vocabulary: a POTENTIAL_ISSUE, never a legal defect ─────────────
    book = Playbook("p", "1", DRAFT, (r(MAX_YEARS, "3 years"),))
    fs = review(book, [e("five years")])
    check(len(fs) == 1 and fs[0].status == DEVIATES, "review() runs every rule")
    check(all(x.kind == POTENTIAL_ISSUE for x in fs),
          "every finding is a POTENTIAL_ISSUE")
    check(not hasattr(fs[0], "severity") and not hasattr(fs[0], "risk"),
          "a Finding has no severity and no risk score -- a severity scale is a legal "
          "opinion with a number on it")
    # Scanned on what a finding SAYS, not on this file's prose. The docstring above names
    # the forbidden words in order to forbid them, so scanning the source would match its
    # own rule -- the same self-referential trap the "no logic" check in
    # scripts/ingest_companies_act.py once fell into.
    banned = ("violation", "breach", "unenforceable", "illegal", "non-compliant", "defect")
    every = []
    for t, v, val in ((MAX_YEARS, "3 years", "five years"), (MAX_AMOUNT, "1 crore", "2 crore"),
                      (EQUALS, "India", "Singapore"), (IN_LIST, ["Mumbai"], "London"),
                      (MUST_BE_PRESENT, None, "x"), (MUST_BE_ABSENT_OR_APPROVED, None, "y")):
        for found in (e(val), e(val, verified=False), None):
            every.append(evaluate(r(t, v), found))
    check(len({x.status for x in every}) >= 3,
          f"the probe reached at least three different statuses "
          f"({sorted({x.status for x in every})}), so it is scanning real output")
    hits = sorted({w for x in every for w in banned
                   if w in f"{x.status} {x.kind} {x.detail} {x.why}".lower()})
    check(not hits,
          f"...and NOTHING a finding says carries a legal verdict {hits}: a playbook "
          f"reports a company standard, not the law")
    check(not any(w in " ".join(STATUSES).lower() for w in banned),
          "...nor do the status names themselves")
    check(all(x.playbook_status == DRAFT for x in fs),
          "a DRAFT playbook stamps DRAFT on every finding it produces")
    check(review(Playbook("p", "1", APPROVED, (r(MAX_YEARS, "3 years"),), "a lawyer"),
                 [e("five years")])[0].playbook_status == APPROVED,
          "...and an APPROVED one stamps APPROVED")

    # ── a wrong playbook fails at load, not at grading time ─────────────────
    try:
        Rule(id="x", clause="Term", test="vibes", why="")
        check(False, "an unknown test is refused")
    except PlaybookError:
        check(True, "an unknown test is refused at construction -- defaulting it to 'pass' "
                    "would make the rule decorative")

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        def write(obj) -> Path:
            f = d / "pb.json"
            f.write_text(json.dumps(obj))
            return f

        good = {"id": "nda", "version": "1", "status": DRAFT,
                "rules": [{"id": "A", "clause": "Term", "test": MAX_YEARS,
                           "value": "3 years", "why": "standard"}]}
        pb = load(write(good))
        check(pb.is_draft and len(pb.rules) == 1, "a good playbook loads and reads DRAFT")
        for broken, why in (
            ({**good, "status": "ok"}, "a status that is neither DRAFT nor APPROVED"),
            ({**good, "status": APPROVED}, "APPROVED with no approved_by"),
            ({k: v for k, v in good.items() if k != "rules"}, "no rules key"),
            ({**good, "rules": good["rules"] * 2}, "two rules sharing an id"),
        ):
            try:
                load(write(broken))
                check(False, f"{why} is refused")
            except PlaybookError:
                check(True, f"refused at load: {why}")

    # ── the playbook that actually ships, loaded from disk ──────────────────
    real = Path(__file__).resolve().parent.parent / "playbooks" / "nda_v1.json"
    if real.is_file():
        nda = load(real)
        check(nda.is_draft and nda.status == DRAFT,
              "playbooks/nda_v1.json is DRAFT -- no in-house lawyer has approved it, and "
              "until one has, every finding from it is stamped DRAFT")
        check(8 <= len(nda.rules) <= 10, f"...with 8-10 rules ({len(nda.rules)})")
        check(all(r.test in TESTS for r in nda.rules), "...every test is one this evaluates")
        check(all(len(r.why) > 40 for r in nda.rules),
              "...and every rule says WHY, at length: a threshold with no reason behind it "
              "is one a reviewing lawyer cannot accept or reject")
        used = {r.test for r in nda.rules}
        check(len(used) >= 4, f"...exercising several rule types ({sorted(used)})")
        findings = review(nda, [])
        check({f.status for f in findings} <= {MISSING, MATCHES},
              "an EMPTY extraction against it yields only MISSING and MATCHES -- the "
              "must_be_absent rules match on absence, which is the point of them")
        check(all(f.kind == POTENTIAL_ISSUE and f.playbook_status == DRAFT
                  for f in findings),
              "...and every one is a DRAFT POTENTIAL_ISSUE")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
