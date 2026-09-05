"""
The atomic claim: the unit this system is willing to be held to.

Answer-level scoring hides the thing that matters. "Section 188 applies because the counterparty is
a related party and the transaction exceeds the prescribed threshold" reads as one correct answer
and is really three propositions, one of which may be invented, sharing a single citation. Nobody
auditing the answer can tell which. So a claim here is ONE proposition, and a claim that bundles is
rejected rather than accepted with a warning -- a warning on a legal assertion is a warning nobody
reads.

The claim types are not decoration. A LEGAL_TRIGGER must cite law. A MISSING_FACT must NOT, because
it is a statement about the absence of evidence and citing evidence for an absence is incoherent.
That asymmetry is enforced.

Run: python3 checker/claim_schema.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Claim", "ClaimError", "CLAIM_TYPES", "SUPPORT_LEVELS",
           "LEGAL_TRIGGER", "FACT_INFERENCE", "PROCEDURAL_REQUIREMENT", "MISSING_FACT"]

LEGAL_TRIGGER = "LEGAL_TRIGGER"                # a provision applies / imposes a requirement
FACT_INFERENCE = "FACT_INFERENCE"              # a fact read off the document
PROCEDURAL_REQUIREMENT = "PROCEDURAL_REQUIREMENT"
MISSING_FACT = "MISSING_FACT"                  # something the document does not say

CLAIM_TYPES = (LEGAL_TRIGGER, FACT_INFERENCE, PROCEDURAL_REQUIREMENT, MISSING_FACT)

DIRECT, INFERRED, UNSUPPORTED, MISSING = "DIRECT", "INFERRED", "UNSUPPORTED", "MISSING"
SUPPORT_LEVELS = (DIRECT, INFERRED, UNSUPPORTED, MISSING)

CONFIDENCE = ("HIGH", "MEDIUM", "LOW")

# Types that assert law and therefore must point at law.
MUST_CITE = (LEGAL_TRIGGER, PROCEDURAL_REQUIREMENT)

MAX_CLAIM_CHARS = 320
# Conjunctions that in practice join two independent propositions. "and" alone is far too common in
# legal prose ("books and papers", "loss of office") to treat as a bundling signal.
_BUNDLING = re.compile(
    r"\b(?:and also|furthermore|moreover|in addition,|additionally|as well as the|"
    r"whereas|;\s*(?:it|the company|the board)\b)", re.I)
_SENTENCE_END = re.compile(r"[.!?]\s+[A-Z(]")


class ClaimError(ValueError):
    """A claim that cannot be audited. Never downgraded to a warning."""


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    claim_type: str
    evidence_ids: tuple[str, ...] = ()
    support: str = UNSUPPORTED
    confidence: str = "LOW"

    def __post_init__(self) -> None:
        if self.claim_type not in CLAIM_TYPES:
            raise ClaimError(f"{self.claim_type!r} is not a claim type; one of {CLAIM_TYPES}")
        if self.support not in SUPPORT_LEVELS:
            raise ClaimError(f"{self.support!r} is not a support level")
        if self.confidence not in CONFIDENCE:
            raise ClaimError(f"{self.confidence!r} is not a confidence level")
        if not self.text.strip():
            raise ClaimError(f"{self.claim_id}: a claim with no text cannot be verified")

        if self.claim_type in MUST_CITE and not self.evidence_ids:
            raise ClaimError(
                f"{self.claim_id}: a {self.claim_type} must cite at least one evidence id. An "
                "uncited legal assertion is exactly what this system exists to prevent.")
        if self.claim_type == MISSING_FACT and self.evidence_ids:
            raise ClaimError(
                f"{self.claim_id}: a MISSING_FACT must not cite evidence -- it asserts an absence, "
                "and citing evidence for an absence is incoherent.")

        for reason in atomicity_problems(self.text):
            raise ClaimError(f"{self.claim_id}: not atomic -- {reason}")

    def to_dict(self) -> dict:
        return dict(claim_id=self.claim_id, text=self.text, claim_type=self.claim_type,
                    evidence_ids=list(self.evidence_ids), support=self.support,
                    confidence=self.confidence)


def atomicity_problems(text: str) -> list[str]:
    """Why this text is not one proposition. Empty means it looks atomic.

    This cannot be decided perfectly without parsing the sentence, so it errs toward letting
    borderline claims through: a false rejection blocks a true statement, which is its own harm.
    What it catches reliably is the common shapes -- multiple sentences, and explicit joiners.
    """
    t = " ".join(text.split())
    out = []
    if len(t) > MAX_CLAIM_CHARS:
        out.append(f"{len(t)} chars, over the {MAX_CLAIM_CHARS} limit -- likely several claims")
    if _SENTENCE_END.search(t):
        out.append("more than one sentence -- split it, one proposition per claim")
    m = _BUNDLING.search(t)
    if m:
        out.append(f"joins propositions with {m.group(0)!r}")
    return out


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    c = Claim("c1", "Section 188 requires Board approval for a related party transaction.",
              LEGAL_TRIGGER, ("ev1",), DIRECT, "HIGH")
    check(c.claim_id == "c1", "a well-formed legal claim is accepted")

    try:
        Claim("c2", "Section 188 applies.", LEGAL_TRIGGER)
        check(False, "an uncited legal trigger must raise")
    except ClaimError as e:
        check("must cite at least one evidence id" in str(e),
              "a LEGAL_TRIGGER without a citation is refused")

    try:
        Claim("c3", "The document does not state the arm's length basis.", MISSING_FACT, ("ev1",))
        check(False, "a cited MISSING_FACT must raise")
    except ClaimError as e:
        check("asserts an absence" in str(e), "a MISSING_FACT may not cite evidence")

    check(Claim("c4", "The document does not state the nature of the relationship.",
                MISSING_FACT).support == UNSUPPORTED, "an uncited MISSING_FACT is fine")

    try:
        Claim("c5", "Section 188 applies. The transaction also exceeds the threshold.",
              LEGAL_TRIGGER, ("ev1",))
        check(False, "a two-sentence claim must raise")
    except ClaimError as e:
        check("more than one sentence" in str(e), "multiple sentences are rejected")

    try:
        Claim("c6", "Section 188 applies and also Section 177 requires audit committee approval.",
              LEGAL_TRIGGER, ("ev1",))
        check(False, "an 'and also' bundle must raise")
    except ClaimError as e:
        check("joins propositions" in str(e), "explicit joiners are rejected")

    # "and" alone is ordinary legal prose and must NOT trip the check.
    check(Claim("c7", "Section 189 requires a register of contracts and arrangements.",
                LEGAL_TRIGGER, ("ev1",)).text.count("and") == 1,
          "a plain 'and' inside a legal phrase is not treated as bundling")

    long_text = "x" * (MAX_CLAIM_CHARS + 1)
    check(any("over the" in r for r in atomicity_problems(long_text)), "over-long text is flagged")
    check(atomicity_problems("Section 173 requires four Board meetings a year.") == [],
          "a single proposition has no atomicity problems")

    for bad in (("c8", "t", "NONSENSE", ("ev1",)),):
        try:
            Claim(*bad); check(False, "an invented claim type must raise")
        except ClaimError:
            check(True, "an invented claim type is rejected")

    try:
        Claim("c9", "   ", FACT_INFERENCE)
        check(False, "empty text must raise")
    except ClaimError:
        check(True, "a claim with no text is rejected")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
