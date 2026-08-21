"""
Verify each claim against the pack it was supposed to come from.

**What this is not.** Without a model, this cannot decide entailment, and it does not pretend to.
It checks a NECESSARY condition: that the distinctive words of a claim actually occur in the
evidence it cites. Passing is not proof of support -- a claim can lift the right vocabulary and
still assert something the provision does not say. Failing IS decisive: if the terms are absent,
the cited text cannot support the claim.

Calling a lexical overlap check "entailment" would be precisely the overclaim this repo exists to
prevent, so the verdicts are named for what was actually established:

  LEXICAL_CANDIDATE -- the claim's distinctive terms are present in cited, admissible evidence.
                       This is a TRIAGE result, not grounding. See below.
  PARTIAL           -- some are present; a material term is not
  UNSUPPORTED       -- the cited text is real but does not carry the claim's terms
  INVALID_CITATION  -- the claim cites something that is not in the pack at all
  CONTRADICTED      -- the cited text or an accepted claim negates it
  MISSING           -- the claim asserts an absence, so there is nothing to ground
  SUPPORTED         -- entailment established. **This module never returns it.**

**Why SUPPORTED is unreachable here.** It used to be the top lexical verdict, and that was a lie
told by a variable name: `corpus/benchmark/entailment_v1.json` holds four claims about s.173, and
this checker cannot distinguish any of them. The claim that restates the provision and the claim
that swaps "thirty days" for "ninety days" BOTH score coverage 1.000, because "ninety" happens to
appear elsewhere in s.173. Reporting one of those as SUPPORTED while the other is equally scored is
not a near miss; it is the checker having no opinion and a confident label.

So the lexical path now tops out at LEXICAL_CANDIDATE, and `establishes_support()` is False for it.
SUPPORTED is reserved for a verdict an entailment checker has confirmed. Nothing in this repo can
produce one today, and that is the honest state rather than a gap to paper over.

Contradiction detection is the known weak point of claim-level checkers, and this implementation is
deliberately conservative: it fires only on direct polarity conflict between two claims about the
same provision. The interface exists so a better implementation can replace it; the current one
says plainly how little it catches.

Run: python3 checker/claim_verifier.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.claim_schema import Claim, MISSING_FACT
from checker.evidence_pack import EvidencePack

__all__ = ["ClaimVerification", "verify_claim", "verify_all", "VERDICTS", "establishes_support",
           "SUPPORTED", "LEXICAL_CANDIDATE", "PARTIAL", "UNSUPPORTED", "CONTRADICTED", "MISSING",
           "INVALID_CITATION"]

SUPPORTED = "SUPPORTED"                    # reserved: requires entailment; never returned here
LEXICAL_CANDIDATE = "LEXICAL_CANDIDATE"    # terms present -- triage only, NOT grounding
PARTIAL, UNSUPPORTED = "PARTIAL", "UNSUPPORTED"
CONTRADICTED, MISSING = "CONTRADICTED", "MISSING"
# Kept separate from UNSUPPORTED deliberately. They look alike in a summary and call for opposite
# fixes: an INVALID_CITATION means the model pointed at something that is not in the pack, which is
# a fabrication or a retrieval mismatch; UNSUPPORTED means it pointed at real evidence that does
# not carry the claim, which is a reasoning error. Collapsing them hides which one you have.
INVALID_CITATION = "INVALID_CITATION"
VERDICTS = (SUPPORTED, LEXICAL_CANDIDATE, PARTIAL, UNSUPPORTED, CONTRADICTED, MISSING,
            INVALID_CITATION)

# The only verdict that may authorise a legal statement. Deliberately a function rather than a
# constant set membership test at each call site: callers must ask the question, and a new verdict
# added later cannot silently default to "yes".
def establishes_support(verdict: str) -> bool:
    """Whether this verdict permits asserting the claim as grounded in law.

    LEXICAL_CANDIDATE is False. That is the whole point: word overlap survived, nothing was
    established, and a caller that treats triage as grounding is the failure this module exists
    to prevent.
    """
    return verdict == SUPPORTED

# Words too common in statute to distinguish one provision from another. A claim that overlaps a
# provision only on these has demonstrated nothing.
_STOP = frozenset("""
a an the of to in for or and be is are as by with on that this such any may shall not no its his
her their it they which who whom where when if then than there here under over upon into from at
company companies board director directors section sub subsection rule rules act provided further
person persons case cases manner prescribed appointed made make making shall_be
""".split())

_NEGATION = re.compile(r"\b(?:not|never|no|nor|without|neither|cannot|need not|shall not)\b", re.I)


@dataclass(frozen=True)
class ClaimVerification:
    claim_id: str
    verdict: str
    issues: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    coverage: float = 0.0

    def to_dict(self) -> dict:
        return dict(claim_id=self.claim_id, verdict=self.verdict, issues=list(self.issues),
                    supporting_evidence_ids=list(self.supporting_evidence_ids),
                    coverage=round(self.coverage, 3))


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def _negated(text: str) -> bool:
    return bool(_NEGATION.search(text))


def verify_claim(claim: Claim, pack: EvidencePack,
                 others: tuple[Claim, ...] = ()) -> ClaimVerification:
    if claim.claim_type == MISSING_FACT:
        return ClaimVerification(claim.claim_id, MISSING,
                                 ("asserts an absence; nothing to ground",))

    usable = {p.key: p for p in pack.usable}
    withheld = {p.key for p in pack.provisions} - set(usable)

    issues, support_ids = [], []
    bad = [e for e in claim.evidence_ids if e not in usable and e not in withheld]
    if bad:
        # Decisive on its own: the model pointed somewhere that does not exist here.
        return ClaimVerification(
            claim.claim_id, INVALID_CITATION,
            (f"cites evidence absent from the pack: {', '.join(bad)}",))

    on_withheld = [e for e in claim.evidence_ids if e in withheld]
    if on_withheld:
        issues.append(f"relies on withheld material: {', '.join(on_withheld)}")

    cited = [usable[e] for e in claim.evidence_ids if e in usable]
    if not cited:
        # Everything it cited exists but none of it is admissible -- a claim resting entirely on
        # material a reviewer withheld.
        return ClaimVerification(claim.claim_id, UNSUPPORTED,
                                 tuple(issues or ("no admissible evidence cited",)))

    want = _terms(claim.text)
    if not want:
        return ClaimVerification(claim.claim_id, UNSUPPORTED,
                                 tuple(issues + ["claim carries no distinctive terms to check"]))

    have: set[str] = set()
    for p in cited:
        body = _terms(p.reading_text or p.raw_text) | _terms(p.ref.title)
        hit = want & body
        if hit:
            support_ids.append(p.key)
            have |= hit

    coverage = len(have) / len(want)
    missing_terms = sorted(want - have)[:6]

    # Conservative contradiction: two claims about the same provision that disagree in polarity.
    for o in others:
        if o.claim_id == claim.claim_id or not (set(o.evidence_ids) & set(claim.evidence_ids)):
            continue
        if _negated(o.text) != _negated(claim.text) and _terms(o.text) & want:
            issues.append(f"polarity conflict with {o.claim_id}")
            return ClaimVerification(claim.claim_id, CONTRADICTED, tuple(issues),
                                     tuple(support_ids), coverage)

    if coverage >= 0.6 and not issues:
        verdict = LEXICAL_CANDIDATE
    elif coverage >= 0.3:
        verdict = PARTIAL
        issues.append(f"terms not found in cited text: {', '.join(missing_terms)}")
    else:
        verdict = UNSUPPORTED
        issues.append(f"cited text does not carry the claim's terms: {', '.join(missing_terms)}")
    if on_withheld and verdict == LEXICAL_CANDIDATE:
        verdict = PARTIAL
    return ClaimVerification(claim.claim_id, verdict, tuple(issues), tuple(support_ids), coverage)


def verify_all(claims: tuple[Claim, ...], pack: EvidencePack) -> tuple[ClaimVerification, ...]:
    return tuple(verify_claim(c, pack, claims) for c in claims)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    from checker.claim_schema import FACT_INFERENCE, LEGAL_TRIGGER
    from checker.retrieve import MODE_MODEL, retrieve

    pack, _ = retrieve("s.173", mode=MODE_MODEL)
    key = pack.usable[0].key

    good = Claim("c1", "Every company shall hold the first meeting of the Board of Directors "
                       "within thirty days of incorporation.", LEGAL_TRIGGER, (key,), "DIRECT")
    v = verify_claim(good, pack)
    check(v.verdict == LEXICAL_CANDIDATE,
          f"a claim lifted from the provision reaches LEXICAL_CANDIDATE, not SUPPORTED ({v.verdict})")
    check(not establishes_support(v.verdict),
          "...and LEXICAL_CANDIDATE does NOT establish support -- triage is not grounding")
    check(establishes_support(SUPPORTED), "only SUPPORTED establishes support")
    check(not any(establishes_support(x) for x in VERDICTS if x != SUPPORTED),
          "no other verdict establishes support")
    check(v.supporting_evidence_ids == (key,), "the supporting evidence is named")
    check(v.coverage > 0.6, f"coverage reported: {v.coverage:.2f}")

    bogus = Claim("c2", "The company must obtain prior approval from the Reserve Bank before "
                        "declaring dividend on preference shares.", LEGAL_TRIGGER, (key,))
    vb = verify_claim(bogus, pack)
    check(vb.verdict in (UNSUPPORTED, PARTIAL),
          f"a claim the provision does not carry is not a candidate ({vb.verdict})")
    check(any("does not carry" in i or "not found" in i for i in vb.issues),
          "...and the issue names the missing terms")

    miss = Claim("c3", "The document does not state the meeting date.", MISSING_FACT)
    check(verify_claim(miss, pack).verdict == MISSING, "a MISSING_FACT verifies as MISSING")

    # Contradiction, the conservative case.
    a = Claim("c4", "The Board shall hold four meetings every year.", LEGAL_TRIGGER, (key,))
    b = Claim("c5", "The Board shall not hold four meetings every year.", LEGAL_TRIGGER, (key,))
    res = verify_all((a, b), pack)
    check(any(r.verdict == CONTRADICTED for r in res), "opposite claims on one provision conflict")

    fake = Claim("c6", "Section 999 requires quarterly filings with the Registrar.",
                 LEGAL_TRIGGER, ("ACT:COMPANIES_ACT_2013:S999",))
    vf = verify_claim(fake, pack)
    check(vf.verdict == INVALID_CITATION and any("absent from the pack" in i for i in vf.issues),
          "a citation to something not in the pack is INVALID_CITATION, not merely UNSUPPORTED")
    check(vf.verdict != UNSUPPORTED,
          "...kept distinct: fabricated citation and failed grounding need different fixes")

    stopword_only = Claim("c7", "The company shall be a company under the Act.",
                          FACT_INFERENCE, (key,))
    vs = verify_claim(stopword_only, pack)
    check(vs.verdict != LEXICAL_CANDIDATE,
          "overlap on statutory boilerplate alone does not establish support")

    check(all(v.verdict in VERDICTS for v in verify_all((good, bogus, miss), pack)),
          "verify_all returns only valid verdicts")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
