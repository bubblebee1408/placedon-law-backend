"""Which company is the bar about? A CIN is never a party -- a role is.

`buyer_sim.Q6` is the gap the simulation produced: a share purchase agreement names
the target, the seller, the acquirer and often a holdco, and the Master Data Strip
spec pins one "Active CIN" to the toolbar with nothing deciding which. Reconciling
the target's capital against the acquirer's register is a confident wrong answer,
and confident wrong answers are the only kind that matter.

## The correction: the question is per rule, not per document

There is no single company a deal document "is about", so asking which CIN to pin
is the wrong question. Each rule needs a different role:

    capital headroom      the ISSUER -- whoever is allotting
    encumbrance warranty  the TARGET -- whose shares or assets are warranted
    DIN reliance          the EXECUTING_ENTITY -- whose board is signing

`legal_ref` holds the same line for law: a provision number is never an identity.
Here a CIN is never a party. A role is, and a role has to be evidenced.

## Refusal is the default

A party with no span is UNGROUNDED, not a party -- `document_extract` already
refuses a field the document does not support and this is the same discipline
applied to identity. Two candidates for one role is AMBIGUOUS. No candidate is
ROLE_ABSENT, naming the role that is missing rather than falling back to whichever
CIN appeared first. The single-party case still resolves, because a board
resolution genuinely has one subject -- but it returns RESOLVED_SOLE_PARTY so the
assumption is visible downstream instead of hiding inside a default.

## A malformed CIN is reported, never repaired

OCR on a scanned execution page turns 0 into O, 1 into I and 5 into S. When the
standard confusions would fix a CIN, `inspect` says so and returns the *raw* value
regardless. Repairing a defective source is forbidden here (CLAUDE.md), and a
silently corrected CIN is a lookup against a different company.

Run: python3 checker/party_resolution.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _field
from datetime import date

# ── CIN structure ────────────────────────────────────────────────────────────
# L/U | 5-digit NIC activity | 2-letter state | 4-digit year | 3-letter ownership
# | 6-digit registration number. Twenty-one characters, fixed.
CIN_RE = re.compile(r"^([LU])(\d{5})([A-Z]{2})(\d{4})([A-Z]{3})(\d{6})$")
CIN_LEN = 21
_DIGIT_POS = set(range(1, 6)) | set(range(8, 12)) | set(range(15, 21))
_ALPHA_POS = {0} | {6, 7} | {12, 13, 14}

# Reported when unrecognised, never used to reject: an incomplete list of our own
# would produce false rejections, which is the failure this whole project refuses.
KNOWN_OWNERSHIP = {"PTC": "private", "PLC": "public", "OPC": "private",
                   "FTC": "private", "NPL": None, "SGC": "public",
                   "GAP": "public", "ULL": None, "ULT": None}

# Letter/digit confusions a scanner actually makes.
_TO_DIGIT = {"O": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5",
             "G": "6", "B": "8"}
_TO_ALPHA = {v: k for k, v in reversed(list(_TO_DIGIT.items()))}

# ── CIN inspection states ────────────────────────────────────────────────────
CIN_OK = "CIN_OK"
SUSPECT_OCR = "SUSPECT_OCR"                # malformed, but the confusions explain it
MALFORMED = "MALFORMED"
IMPOSSIBLE_YEAR = "IMPOSSIBLE_YEAR"        # incorporated after the document was made
CLASS_CONFLICT = "CLASS_CONFLICT"          # PTC against a company recorded as public
UNVERIFIED_COMPONENT = "UNVERIFIED_COMPONENT"   # shape fine, a code we do not know


@dataclass(frozen=True)
class CinReport:
    raw: str
    state: str
    issues: tuple[str, ...] = ()
    ocr_candidate: str | None = None       # what the confusions WOULD give. Never adopted.
    year: int | None = None
    ownership: str | None = None
    listed: bool | None = None

    @property
    def usable(self) -> bool:
        return self.state in (CIN_OK, UNVERIFIED_COMPONENT)


def inspect(raw: str, *, document_date: date | None = None,
            company_class: str | None = None) -> CinReport:
    """Structural check on a CIN. Reports; does not repair."""
    cin = (raw or "").strip().upper().replace(" ", "")
    m = CIN_RE.match(cin)

    if not m:
        candidate = _ocr_candidate(cin)
        if candidate:
            return CinReport(raw, SUSPECT_OCR,
                             (f"does not parse, but the standard scanner confusions "
                              f"would give {candidate}; confirm against the source "
                              f"page. Not adopted.",),
                             ocr_candidate=candidate)
        return CinReport(raw, MALFORMED,
                         (f"not a CIN: expected {CIN_LEN} characters as "
                          f"L/U + 5 digits + 2 letters + 4 digits + 3 letters + "
                          f"6 digits, got {len(cin)}",))

    listing, _nic, _state, year_s, ownership, _reg = m.groups()
    year, listed = int(year_s), listing == "L"
    issues: list[str] = []
    state = CIN_OK

    if document_date is not None and year > document_date.year:
        issues.append(f"the CIN records incorporation in {year}, after the document "
                      f"date {document_date}")
        state = IMPOSSIBLE_YEAR

    if ownership not in KNOWN_OWNERSHIP:
        issues.append(f"ownership code {ownership!r} is not one we recognise; "
                      f"the shape is valid, so this is reported, not rejected")
        if state == CIN_OK:
            state = UNVERIFIED_COMPONENT
    elif company_class:
        implied = KNOWN_OWNERSHIP[ownership]
        if implied and implied != company_class.lower():
            issues.append(f"the CIN's {ownership} implies a {implied} company, but "
                          f"the record says {company_class}")
            state = CLASS_CONFLICT

    return CinReport(raw, state, tuple(issues), None, year, ownership, listed)


def _ocr_candidate(cin: str) -> str | None:
    """Would the standard confusions make this parse? Answer only; never applied."""
    if len(cin) != CIN_LEN:
        return None
    out = []
    for i, ch in enumerate(cin):
        if i in _DIGIT_POS and ch in _TO_DIGIT:
            out.append(_TO_DIGIT[ch])
        elif i in _ALPHA_POS and ch in _TO_ALPHA:
            out.append(_TO_ALPHA[ch])
        else:
            out.append(ch)
    fixed = "".join(out)
    return fixed if fixed != cin and CIN_RE.match(fixed) else None


# ── roles ────────────────────────────────────────────────────────────────────
ISSUER = "ISSUER"
TARGET = "TARGET"
ACQUIRER = "ACQUIRER"
SELLER = "SELLER"
GUARANTOR = "GUARANTOR"
EXECUTING_ENTITY = "EXECUTING_ENTITY"
ROLES = (ISSUER, TARGET, ACQUIRER, SELLER, GUARANTOR, EXECUTING_ENTITY)

# Which role each reconciliation rule needs. This table is the whole correction.
RULE_NEEDS: dict[str, str] = {
    "capital_headroom": ISSUER,
    "charge_warranty": TARGET,
    "din_reliance": EXECUTING_ENTITY,
}


@dataclass(frozen=True)
class Party:
    """One company named in the document, in a role the document evidences."""
    cin: str
    role: str
    span: str | None = None          # the text that put it in this role
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")

    @property
    def grounded(self) -> bool:
        return bool(self.span)


# ── resolution verdicts ──────────────────────────────────────────────────────
RESOLVED = "RESOLVED"
RESOLVED_SOLE_PARTY = "RESOLVED_SOLE_PARTY"
AMBIGUOUS = "AMBIGUOUS"
ROLE_ABSENT = "ROLE_ABSENT"
UNGROUNDED = "UNGROUNDED"
UNUSABLE_CIN = "UNUSABLE_CIN"
UNKNOWN_RULE = "UNKNOWN_RULE"


@dataclass(frozen=True)
class Resolution:
    verdict: str
    rule: str
    role: str | None = None
    cin: str | None = None
    reason: str = ""
    candidates: tuple[str, ...] = _field(default_factory=tuple)

    @property
    def usable(self) -> bool:
        return self.verdict in (RESOLVED, RESOLVED_SOLE_PARTY)


def resolve(rule: str, parties: tuple[Party, ...], *,
            document_date: date | None = None,
            allow_sole_party: bool = True) -> Resolution:
    """Which company does this rule run against?"""
    role = RULE_NEEDS.get(rule)
    if role is None:
        return Resolution(UNKNOWN_RULE, rule,
                          reason=f"no role is declared for rule {rule!r}; a rule that "
                                 f"does not say whose register it needs cannot be run "
                                 f"on a multi-party document")

    matching = [p for p in parties if p.role == role]
    ungrounded = [p for p in matching if not p.grounded]
    grounded = [p for p in matching if p.grounded]

    if not matching:
        # The sole-party shortcut. A board resolution has one subject; an SPA does not.
        distinct = {p.cin for p in parties}
        if allow_sole_party and len(distinct) == 1:
            only = next(iter(distinct))
            rep = inspect(only, document_date=document_date)
            if not rep.usable:
                return Resolution(UNUSABLE_CIN, rule, role, only,
                                  "; ".join(rep.issues) or rep.state)
            return Resolution(
                RESOLVED_SOLE_PARTY, rule, role, only,
                f"the document names one company and no {role}; treating the sole "
                f"party as the subject. Stated rather than defaulted, because on a "
                f"deal document this assumption is the failure mode.")
        return Resolution(
            ROLE_ABSENT, rule, role,
            reason=f"no party is identified as the {role}, and the document names "
                   f"{len(distinct)} compan{'y' if len(distinct) == 1 else 'ies'}. "
                   f"Identify the {role} before running {rule}.",
            candidates=tuple(sorted(distinct)))

    if not grounded:
        return Resolution(
            UNGROUNDED, rule, role,
            reason=f"{len(ungrounded)} part{'y' if len(ungrounded) == 1 else 'ies'} "
                   f"carr{'ies' if len(ungrounded) == 1 else 'y'} the {role} role with "
                   f"no supporting text. A role asserted without a span is a guess "
                   f"about identity.",
            candidates=tuple(sorted(p.cin for p in ungrounded)))

    distinct = sorted({p.cin for p in grounded})
    if len(distinct) > 1:
        return Resolution(
            AMBIGUOUS, rule, role,
            reason=f"{len(distinct)} companies are evidenced as the {role}. Running "
                   f"{rule} against either would be a confident answer about the "
                   f"wrong company.",
            candidates=tuple(distinct))

    cin = distinct[0]
    rep = inspect(cin, document_date=document_date)
    if not rep.usable:
        return Resolution(UNUSABLE_CIN, rule, role, cin,
                          "; ".join(rep.issues) or rep.state)
    return Resolution(RESOLVED, rule, role, cin,
                      f"identified as the {role}: "
                      f"{next(p.span for p in grounded if p.cin == cin)!r}")


def subjects(parties: tuple[Party, ...], **kw) -> dict[str, Resolution]:
    """Resolve every rule at once -- what the strip would need to render."""
    return {rule: resolve(rule, parties, **kw) for rule in RULE_NEEDS}


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("party_resolution")
    TARGET_CIN = "U72200KA2021PTC145892"
    ACQ_CIN = "L27100MH1995PLC084781"
    DOC_DATE = date(2026, 6, 14)

    # ── CIN structure ────────────────────────────────────────────────────────
    check(inspect(TARGET_CIN).state == CIN_OK, "a well-formed CIN passes")
    r = inspect("U72200KA2021PTC14589")           # 20 chars
    check(r.state == MALFORMED and "21 characters" in r.issues[0],
          "a short CIN is malformed, and the message says what the shape is")

    # The one that matters: OCR damage is reported, not fixed.
    scanned = "U722OOKA2O21PTC145892"             # zeros read as letter O
    r = inspect(scanned)
    check(r.state == SUSPECT_OCR and r.ocr_candidate == TARGET_CIN,
          f"scanner damage is recognised ({scanned} -> {r.ocr_candidate})")
    check(r.raw == scanned and not r.usable,
          "...and the raw value is returned unrepaired, and is not usable -- a "
          "silently corrected CIN is a lookup against a different company")

    check(inspect("U72200KA2021XYZ145892").state == UNVERIFIED_COMPONENT,
          "an unrecognised ownership code is reported, not rejected -- an "
          "incomplete list of our own must not manufacture a false negative")
    check(inspect(TARGET_CIN, document_date=date(2019, 1, 1)).state == IMPOSSIBLE_YEAR,
          "a company incorporated in 2021 cannot be a party to a 2019 document")
    check(inspect(TARGET_CIN, company_class="public").state == CLASS_CONFLICT,
          "a PTC code against a company recorded as public is a conflict")
    check(inspect(TARGET_CIN, company_class="private").state == CIN_OK,
          "...and agrees when it agrees")
    check(inspect(ACQ_CIN).listed is True and inspect(TARGET_CIN).listed is False,
          "the listing prefix is read (L / U)")

    # ── the Q6 document: a four-party SPA ────────────────────────────────────
    spa_no_roles = tuple(
        Party(c, ACQUIRER if c == ACQ_CIN else SELLER, span="named in the preamble")
        for c in (TARGET_CIN, ACQ_CIN))
    res = resolve("charge_warranty", spa_no_roles, document_date=DOC_DATE)
    check(res.verdict == ROLE_ABSENT and res.role == TARGET,
          f"an SPA with no TARGET identified refuses rather than picking one "
          f"({res.verdict})")
    check(set(res.candidates) == {TARGET_CIN, ACQ_CIN},
          "...and lists the companies it found, so a human can say which")

    both_targets = (Party(TARGET_CIN, TARGET, span="the Target"),
                    Party(ACQ_CIN, TARGET, span="the Target Group"))
    res = resolve("charge_warranty", both_targets, document_date=DOC_DATE)
    check(res.verdict == AMBIGUOUS and len(res.candidates) == 2,
          "two evidenced targets is AMBIGUOUS, not first-wins")

    res = resolve("charge_warranty", (Party(TARGET_CIN, TARGET),),
                  document_date=DOC_DATE)
    check(res.verdict == UNGROUNDED,
          "a role asserted with no supporting span is a guess about identity")

    good = (Party(TARGET_CIN, TARGET, span="(the 'Target')"),
            Party(ACQ_CIN, ACQUIRER, span="(the 'Acquirer')"),
            Party(ACQ_CIN, ISSUER, span="the Acquirer shall allot"))
    res = resolve("charge_warranty", good, document_date=DOC_DATE)
    check(res.verdict == RESOLVED and res.cin == TARGET_CIN,
          f"once the roles are evidenced the warranty rule resolves to the target")
    check(resolve("capital_headroom", good, document_date=DOC_DATE).cin == ACQ_CIN,
          "...and the capital rule resolves to the ISSUER -- a different company in "
          "the same document, which is the whole point")

    # ── the single-company document still works ──────────────────────────────
    board = (Party(TARGET_CIN, EXECUTING_ENTITY, span="the Company"),)
    check(resolve("din_reliance", board, document_date=DOC_DATE).verdict == RESOLVED,
          "a board resolution with one named company resolves")
    sole = (Party(TARGET_CIN, SELLER, span="the Company"),)
    r2 = resolve("capital_headroom", sole, document_date=DOC_DATE)
    check(r2.verdict == RESOLVED_SOLE_PARTY,
          "a sole-party document resolves under a NAMED assumption, not a default")
    check(resolve("capital_headroom", sole, document_date=DOC_DATE,
                  allow_sole_party=False).verdict == ROLE_ABSENT,
          "...and the assumption can be switched off for deal documents")
    check(resolve("capital_headroom", (Party(scanned, SELLER, span="x"),),
                  document_date=DOC_DATE).verdict == UNUSABLE_CIN,
          "a sole party with an OCR-damaged CIN refuses rather than resolving")

    # ── a rule that does not declare its role cannot run ─────────────────────
    check(resolve("some_new_rule", good).verdict == UNKNOWN_RULE,
          "a rule with no declared role is refused -- the next rule someone adds "
          "cannot inherit whichever CIN happens to be first")

    # ── construction refuses nonsense ────────────────────────────────────────
    try:
        Party(TARGET_CIN, "COUNTERPARTY")
        check(False, "an unknown role is rejected")
    except ValueError:
        check(True, "an unknown role is rejected at construction")

    # ── the whole strip at once ──────────────────────────────────────────────
    s = subjects(good, document_date=DOC_DATE)
    check(len({r.cin for r in s.values() if r.usable}) == 2,
          f"one document, three rules, two different subject companies: "
          f"{ {k: v.cin for k, v in s.items()} }")
    check(s["din_reliance"].verdict == ROLE_ABSENT,
          "...and the third refuses, because nobody said who is executing")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
