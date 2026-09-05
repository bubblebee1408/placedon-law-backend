"""Schema-constrained extraction: the shape a model is allowed to propose.

`model_adapter.py` holds the line that a model's output is not an answer until
`claim_verifier` checks it. This module pushes that line one layer earlier, to the
*shape* of the output: a model proposing a CIN, a DIN or a statutory reference must
propose something that could exist, and a deterministic validator decides whether it
does. Nothing here calls a model. Nothing here trusts one.

## Why this exists

The external advice that prompted it recommended fine-tuning an 8B model and serving
it behind vLLM guided decoding. Fine-tuning is a recorded non-goal (`docs/NON_GOALS.md`:
"no data rights, no budget, and not the moat") and is not adopted. But the *principle*
underneath guided decoding is sound and was missing here: a field should be rejected at
parse time when it cannot possibly be valid, rather than travelling downstream to be
argued about later. That principle needs no model, no GPU and no dependency — it needs
a grammar and a checker, which is what this is.

## The discipline, unchanged from the rest of the system

- **A malformed field is never repaired.** `docs/SOURCE_DEFECTS.md` records four
  transcription defects in the official text preserved verbatim; the same rule holds
  for a proposed value. We reject and say why. Silent repair is how a wrong CIN becomes
  a confident wrong answer about a different company.
- **Absent is not invalid, and neither is zero.** A field the extractor did not find is
  ABSENT. A field it found and got wrong is INVALID. Folding those together would tell a
  caller "no CIN in this document" when the truth is "a CIN was proposed and it was
  malformed", and only one of those is a defect in the source.
- **A structurally valid identifier is not a true one.** `check_digit`-style validation
  proves a string *could* be a CIN, never that the company exists. Every result says
  which of the two it is asserting, so no caller can mistake well-formed for verified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

# ── field verdicts ──────────────────────────────────────────────────────────
class Verdict(str, Enum):
    WELL_FORMED = "WELL_FORMED"   # matches the grammar; existence NOT asserted
    MALFORMED = "MALFORMED"       # proposed, and cannot be what it claims to be
    ABSENT = "ABSENT"             # not proposed at all — not a defect


# ── the grammars ────────────────────────────────────────────────────────────
# CIN, 21 chars: listing status | industry | state | year | ownership | serial.
# e.g. U74999KA2019PTC123456
_CIN = re.compile(r"^([LU])(\d{5})([A-Z]{2})(\d{4})(PLC|PTC|SGC|GAP|GOI|NPL|OPC|FLC|ULL|ULT)(\d{6})$")
_DIN = re.compile(r"^\d{8}$")

# The ownership codes above are the ones this module will vouch for. A code outside
# the set is MALFORMED rather than silently accepted: an unknown code means either a
# transcription error or a company class we do not model, and both need a human.

# State codes are NOT validated against a list here. The MCA has added and renamed
# state/UT codes over time, and a stale allow-list would reject a valid new code —
# rejecting real data is worse than accepting a well-formed impossible one, because
# the latter fails later at the registry and the former fails silently here.

_SECTION = re.compile(r"^\d{1,3}[A-Z]{0,2}$")             # 96, 149, 188, 2, 447, 135A
_SUBSECTION = re.compile(r"^\(?\d{1,2}\)?$")               # (1), 85
_CLAUSE = re.compile(r"^\(?[a-z]{1,2}\)?$")                # (a), (i) handled as roman below
_ROMAN = re.compile(r"^\(?(?:x{0,3})(?:ix|iv|v?i{0,3})\)?$", re.I)

_INCORPORATION_FLOOR = date(1857, 1, 1)   # first Indian Companies Act


@dataclass(frozen=True)
class Field:
    """One proposed value and what we are willing to say about it."""
    name: str
    raw: str | None
    verdict: Verdict
    reason: str
    normalised: str | None = None

    @property
    def usable(self) -> bool:
        return self.verdict is Verdict.WELL_FORMED


def _absent(name: str) -> Field:
    return Field(name, None, Verdict.ABSENT,
                 "not proposed — absence is not a defect, and not a denial")


def validate_cin(raw: str | None) -> Field:
    """A CIN is well-formed, or it is malformed. It is never repaired.

    The year is checked against the incorporation floor and against the future,
    because a 4-digit year is the one component whose corruption produces a
    string that still looks entirely plausible.
    """
    if raw is None or not raw.strip():
        return _absent("cin")
    s = raw.strip().upper().replace(" ", "").replace("-", "")
    m = _CIN.match(s)
    if not m:
        return Field("cin", raw, Verdict.MALFORMED,
                     "does not match the 21-character CIN grammar "
                     "(L|U + 5-digit industry + 2-letter state + 4-digit year + "
                     "ownership code + 6-digit serial)")
    year = int(m.group(4))
    if year < _INCORPORATION_FLOOR.year:
        return Field("cin", raw, Verdict.MALFORMED,
                     f"incorporation year {year} predates Indian company registration")
    if year > date.today().year:
        return Field("cin", raw, Verdict.MALFORMED,
                     f"incorporation year {year} is in the future")
    return Field("cin", raw, Verdict.WELL_FORMED,
                 "matches the CIN grammar — well-formed; existence NOT verified "
                 "against the registry", normalised=s)


def validate_din(raw: str | None) -> Field:
    """A DIN is exactly eight digits. Leading zeros are significant and preserved."""
    if raw is None or not raw.strip():
        return _absent("din")
    s = raw.strip().replace(" ", "").replace("-", "")
    if not _DIN.match(s):
        return Field("din", raw, Verdict.MALFORMED,
                     "a DIN is exactly eight digits; leading zeros are significant "
                     "and must not be stripped")
    return Field("din", raw, Verdict.WELL_FORMED,
                 "matches the DIN grammar — well-formed; existence NOT verified",
                 normalised=s)


@dataclass(frozen=True)
class SectionRef:
    """A statutory reference decomposed into the units the Act itself uses.

    Kept structural rather than free text so it can be compared with the paths
    `structural_chunk.py` produces — "2(85)(i)" from a model and "2(85)(i)" from
    the corpus must be the same object, or citation checking is string luck.
    """
    section: str
    subsection: str | None = None
    clauses: tuple[str, ...] = ()

    def path(self) -> str:
        p = self.section
        if self.subsection is not None:
            p += f"({self.subsection})"
        for c in self.clauses:
            p += f"({c})"
        return p


def validate_section_ref(raw: str | None) -> tuple[Field, SectionRef | None]:
    """Parse 's.2(85)(i)' / 'Section 188(1)(a)' / '96' into a structural path.

    Returns the verdict AND the decomposition, because a caller that only gets a
    boolean has to re-parse to use it, and two parsers disagree eventually.
    """
    if raw is None or not raw.strip():
        return _absent("section_ref"), None
    s = raw.strip()
    s = re.sub(r"^(?:section|sec\.?|s\.)\s*", "", s, flags=re.I).replace(" ", "")
    parts = re.findall(r"\(([^()]*)\)", s)
    head = s.split("(")[0]
    if not _SECTION.match(head):
        return Field("section_ref", raw, Verdict.MALFORMED,
                     f"'{head}' is not a section number of the Companies Act 2013"), None

    subsection: str | None = None
    clauses: list[str] = []
    for i, p in enumerate(parts):
        if i == 0 and _SUBSECTION.match(p):
            subsection = p
        elif _CLAUSE.match(p) or _ROMAN.match(p):
            clauses.append(p)
        else:
            return Field("section_ref", raw, Verdict.MALFORMED,
                         f"'({p})' is not a sub-section, clause or roman sub-clause"), None

    ref = SectionRef(head, subsection, tuple(clauses))
    return Field("section_ref", raw, Verdict.WELL_FORMED,
                 "parses to a structural path — well-formed; whether the Act "
                 "contains it is NOT asserted here", normalised=ref.path()), ref


# ── the extraction record ───────────────────────────────────────────────────
@dataclass(frozen=True)
class Extraction:
    """What an extractor proposed, and what survived validation.

    `admissible` is deliberately strict: any MALFORMED field poisons the record.
    A record with a good company name and a malformed CIN is not "mostly right" —
    it is a record that may belong to a different company, and merging it into the
    entity graph on the strength of the name is exactly the entity-resolution error
    that produces confident nonsense.
    """
    fields: tuple[Field, ...]
    section_refs: tuple[SectionRef, ...] = ()
    source_id: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def get(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def malformed(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.verdict is Verdict.MALFORMED)

    @property
    def admissible(self) -> bool:
        """True only if nothing proposed was malformed AND a source is named."""
        return not self.malformed and self.source_id is not None

    def refusal_reason(self) -> str | None:
        if self.source_id is None:
            return ("no source id: an extraction with no document behind it cannot be "
                    "checked, so it is not admitted")
        if self.malformed:
            names = ", ".join(f"{f.name} ({f.reason})" for f in self.malformed)
            return f"malformed field(s) not repaired: {names}"
        return None


def validate_extraction(proposed: dict, source_id: str | None = None) -> Extraction:
    """Validate a proposed extraction. No model, no network, no repair.

    `proposed` is whatever an extractor emitted. Unknown keys are ignored rather
    than rejected — an extractor that volunteers extra fields is not a defect, but
    nothing unvalidated is ever promoted into `fields`.
    """
    fields: list[Field] = []
    refs: list[SectionRef] = []
    warnings: list[str] = []

    fields.append(validate_cin(proposed.get("cin")))
    fields.append(validate_din(proposed.get("din")))

    raw_sections = proposed.get("section_refs") or proposed.get("sections") or []
    if isinstance(raw_sections, str):
        raw_sections = [raw_sections]
    for r in raw_sections:
        f, ref = validate_section_ref(r)
        fields.append(f)
        if ref is not None:
            refs.append(ref)

    extra = set(proposed) - {"cin", "din", "section_refs", "sections"}
    if extra:
        warnings.append(
            f"unvalidated key(s) ignored, not promoted: {', '.join(sorted(extra))}")

    return Extraction(tuple(fields), tuple(refs), source_id, tuple(warnings))


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    # ── CIN ──
    good = validate_cin("U74999KA2019PTC123456")
    check(good.verdict is Verdict.WELL_FORMED, "a real-shaped CIN is well-formed")
    check("NOT verified" in good.reason, "...and it refuses to claim the company exists")
    check(validate_cin("u74999ka2019ptc123456").normalised == "U74999KA2019PTC123456",
          "case and spacing are normalised, not rejected")
    check(validate_cin("U74999KA2019XXX123456").verdict is Verdict.MALFORMED,
          "an unknown ownership code is malformed, not waved through")
    check(validate_cin("U74999KA1700PTC123456").verdict is Verdict.MALFORMED,
          "a year before company registration existed is malformed")
    check(validate_cin("U74999KA2099PTC123456").verdict is Verdict.MALFORMED,
          "a future incorporation year is malformed")
    check(validate_cin("U74999KA2019PTC12345").verdict is Verdict.MALFORMED,
          "a short serial is malformed (never zero-padded into validity)")
    check(validate_cin(None).verdict is Verdict.ABSENT, "a missing CIN is ABSENT")
    check(validate_cin("   ").verdict is Verdict.ABSENT, "whitespace is ABSENT, not malformed")

    # ── DIN ──
    check(validate_din("00123456").normalised == "00123456",
          "a DIN keeps its leading zeros")
    check(validate_din("123456").verdict is Verdict.MALFORMED, "a 6-digit DIN is malformed")
    check(validate_din("0012345A").verdict is Verdict.MALFORMED, "a non-numeric DIN is malformed")

    # ── section refs ──
    f, ref = validate_section_ref("s.2(85)(i)")
    check(f.verdict is Verdict.WELL_FORMED and ref.path() == "2(85)(i)",
          "'s.2(85)(i)' parses to the structural path 2(85)(i)")
    f2, ref2 = validate_section_ref("Section 188(1)(a)")
    check(ref2 is not None and ref2.path() == "188(1)(a)", "'Section 188(1)(a)' parses")
    f3, ref3 = validate_section_ref("96")
    check(ref3 is not None and ref3.subsection is None, "a bare section has no sub-section")
    f4, _ = validate_section_ref("s.2(85)(zz9)")
    check(f4.verdict is Verdict.MALFORMED, "a nonsense clause is malformed")
    f5, _ = validate_section_ref("s.9999")
    check(f5.verdict is Verdict.MALFORMED, "a 4-digit section number is malformed")
    check(validate_section_ref("s.135A")[1].section == "135A",
          "an inserted section like 135A is accepted")

    # ── the record ──
    ok = validate_extraction({"cin": "U74999KA2019PTC123456",
                              "section_refs": ["s.188(1)"]}, source_id="DOC-1")
    check(ok.admissible, "a clean extraction with a source is admissible")

    bad = validate_extraction({"cin": "NOTACIN", "section_refs": ["s.188"]},
                              source_id="DOC-1")
    check(not bad.admissible, "one malformed field poisons the whole record")
    check("malformed field" in (bad.refusal_reason() or ""),
          "...and the refusal names the field and the reason")

    nosrc = validate_extraction({"cin": "U74999KA2019PTC123456"}, source_id=None)
    check(not nosrc.admissible, "an extraction with no source id is not admissible")
    check("no source id" in (nosrc.refusal_reason() or ""),
          "...and says so, rather than blaming the fields")

    absent_only = validate_extraction({}, source_id="DOC-2")
    check(absent_only.admissible,
          "an extraction that proposed nothing is admissible-but-empty (absent != invalid)")
    check(all(f.verdict is Verdict.ABSENT for f in absent_only.fields),
          "...and every field reads ABSENT")

    extra = validate_extraction({"cin": "U74999KA2019PTC123456", "outcome": "admitted"},
                                source_id="DOC-3")
    check(extra.warnings and "outcome" in extra.warnings[0],
          "an unvalidated key is warned about and never promoted")
    check(extra.get("outcome") is None, "...and does not appear as a validated field")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
