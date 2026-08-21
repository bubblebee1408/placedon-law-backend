"""
Evidence states and source records.

Every legal claim this system makes rests on some artifact. The question that decides whether a
claim may be served is not "does it look right" but "what exactly backs it, and could I show that
to a lawyer". This module makes that question answerable in code rather than in prose.

The distinction that forced this: India Code publishes a section view whose URL carries both the
section number and the internal ID, which would confirm the section index from the source itself.
It returned 403. A third-party document quotes that URL with a value agreeing with the mapping
derived here. Agreement between two independent derivations is real evidence -- and it is NOT
verification, because the endpoint was never actually read. Prose blurs that. An enum does not.

The promotion rule is the point of the file: nothing reaches VERIFIED without an artifact that is
present locally, hashed, and human-reviewed. `can_promote` refuses; it does not warn.

Run: python3 checker/provenance.py
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Ordered weakest -> strongest. Nothing may skip to VERIFIED without meeting can_promote().
UNRESOLVED = "UNRESOLVED"                          # looked, found nothing conclusive
INFERRED = "INFERRED"                              # derived by this system, no external agreement
UNFETCHED_CORROBORATION = "UNFETCHED_CORROBORATION"  # an inaccessible source is reported to agree
CORROBORATED = "CORROBORATED"                      # a second accessible source agrees
VERIFIED = "VERIFIED"                              # hashed local artifact + human review
RETRACTED = "RETRACTED"                            # was asserted, since disproved

STATES = (UNRESOLVED, INFERRED, UNFETCHED_CORROBORATION, CORROBORATED, VERIFIED, RETRACTED)
SERVABLE = (CORROBORATED, VERIFIED)  # what may reach a user as a legal statement

ACCESSIBLE = "ACCESSIBLE"
BLOCKED = "BLOCKED"          # 403 / WAF. Not bypassed -- see CLAUDE.md.
UNREACHABLE = "UNREACHABLE"  # timeout / DNS / 404


class ProvenanceError(ValueError):
    """Raised on an unsupportable evidence claim. Never downgraded to a warning."""


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_title: str
    source_url: str
    official: bool
    accessibility: str
    retrieved_on: str | None = None
    local_artifact: str | None = None   # repo-relative
    artifact_sha256: str | None = None
    human_reviewed: bool = False
    notes: str = ""

    def artifact_path(self) -> Path | None:
        return ROOT / self.local_artifact if self.local_artifact else None

    def artifact_present(self) -> bool:
        p = self.artifact_path()
        return bool(p and p.is_file())

    def artifact_matches_hash(self) -> bool:
        """Whether the stored artifact still hashes to what was recorded.

        A source whose bytes changed under us is not the source that was reviewed.
        """
        p = self.artifact_path()
        if not (p and p.is_file() and self.artifact_sha256):
            return False
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == self.artifact_sha256


@dataclass(frozen=True)
class Claim:
    """Something asserted about the law, and what backs it."""
    claim_id: str
    statement: str
    state: str
    sources: list[SourceRecord] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ProvenanceError(f"{self.state!r} is not an evidence state; one of {STATES}")
        if self.state == VERIFIED:
            ok, why = can_promote(self.sources)
            if not ok:
                raise ProvenanceError(f"claim {self.claim_id!r} cannot be VERIFIED: {why}")

    def servable(self) -> bool:
        return self.state in SERVABLE


def can_promote(sources: list[SourceRecord]) -> tuple[bool, str]:
    """Whether these sources support VERIFIED.

    Requires at least one source that is present locally, hash-matching, and human-reviewed. An
    inaccessible URL supports UNFETCHED_CORROBORATION at most, however authoritative the publisher:
    a source nobody could read is not evidence of its own contents.
    """
    if not sources:
        return False, "no sources"
    for s in sources:
        if not s.human_reviewed:
            continue
        if not s.artifact_present():
            continue
        if not s.artifact_sha256:
            continue
        if not s.artifact_matches_hash():
            return False, f"{s.source_id}: artifact hash mismatch -- bytes changed since review"
        return True, ""
    reasons = []
    for s in sources:
        missing = []
        if not s.human_reviewed:
            missing.append("no human review")
        if not s.local_artifact:
            missing.append(f"no local artifact ({s.accessibility})")
        elif not s.artifact_present():
            missing.append("artifact file missing")
        if s.local_artifact and not s.artifact_sha256:
            missing.append("no hash")
        reasons.append(f"{s.source_id}: {', '.join(missing)}")
    return False, "; ".join(reasons)


# --- the sources actually behind the current section index -------------------------------------

INDIACODE_PDF = SourceRecord(
    source_id="INDIACODE_CA2013_PDF",
    source_title="The Companies Act, 2013 — full Act PDF, India Code",
    source_url="https://www.indiacode.nic.in/bitstream/123456789/2114/5/A2013-18.pdf",
    official=True,
    accessibility=ACCESSIBLE,
    retrieved_on="2026-08-19",
    local_artifact="corpus/sources/companies_act_2013_indiacode.pdf",
    artifact_sha256="d6e286d2a3feec89a7d432a5a572e91af9f0135411b03e57f72b7a8ef72139af",
    human_reviewed=True,
    notes="Arrangement of sections + body. Basis of the section index. 17 MVP sections read by hand.",
)

INDIACODE_SECTION_VIEW = SourceRecord(
    source_id="INDIACODE_SECTION_VIEW",
    source_title="India Code section view (URL carries sectionno and sectionId together)",
    source_url=("https://www.indiacode.nic.in/show-data?actid=AC_CEN_22_29_00008_201318_"
                "1517807327856&sectionId=49099&sectionno=173&orderno=177"),
    official=True,
    accessibility=BLOCKED,
    retrieved_on=None,
    human_reviewed=False,
    notes="HTTP 403 on 2026-08-21; direct request timed out. WAF not bypassed (CLAUDE.md). "
          "Quoted third-hand as sectionId=49099 for s.173, agreeing with the index derived here. "
          "Would upgrade the index from INFERRED to VERIFIED if it ever becomes readable.",
)

# Week 2.1 acquisition attempt, 2026-08-21. Recorded BEFORE any parsing, per the runbook: the
# outcome of an acquisition is provenance whether or not it succeeded, and an unrecorded failed
# attempt invites a second identical attempt later.
BOARD_MEETING_RULES_2014 = SourceRecord(
    source_id="INDIACODE_MEETINGS_BOARD_RULES_2014",
    source_title="The Companies (Meetings of Board and its Powers) Rules, 2014",
    source_url=("https://upload.indiacode.nic.in/showfile?actid=AC_CEN_22_29_00008_201318_"
                "1517807327856&type=rule&filename=The%20Companies%20(Meetings%20and%20Powers%20"
                "of%20Board)%20.pdf"),
    official=True,
    accessibility=UNREACHABLE,
    retrieved_on=None,
    human_reviewed=False,
    notes="NOT ACQUIRED 2026-08-21. upload.indiacode.nic.in (164.100.94.56) refuses connections "
          "-- ECONNREFUSED, i.e. the host is down, not blocking. On www.indiacode.nic.in static "
          "/bitstream/*.pdf serves (200) but every dynamic path (/handle/, /oai/, /rest/, "
          "sitemap) times out, so the Rules' bitstream path cannot be discovered. www.mca.gov.in "
          "returns 403. egazette.gov.in is reachable and is the next avenue, but needs a stateful "
          "search form. Dynamic India Code worked on 20 Aug, so this is intermittent: retry before "
          "concluding the document is gone. No unofficial mirror substituted -- see runbook.",
)

SOURCES = {s.source_id: s
           for s in (INDIACODE_PDF, INDIACODE_SECTION_VIEW, BOARD_MEETING_RULES_2014)}


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    check(INDIACODE_PDF.artifact_present(), "the PDF the index rests on is stored in-repo")
    # Re-fetched from India Code on 2026-08-21 and compared: byte-identical to the stored copy.
    # Confirms the artifact is authentic and unmodified since retrieval on 19 Aug.
    check(INDIACODE_PDF.artifact_matches_hash(), "stored PDF still hashes to the recorded value")

    good, why = can_promote([INDIACODE_PDF])
    check(good, f"hashed + reviewed local artifact supports VERIFIED ({why})")

    # The rule that matters: a blocked official source cannot carry a claim.
    bad, why = can_promote([INDIACODE_SECTION_VIEW])
    check(not bad, "403 official endpoint alone does NOT support VERIFIED")
    check("no human review" in why or "no local artifact" in why, f"and says why: {why}")

    try:
        Claim("c1", "s.173 is id 49099", VERIFIED, [INDIACODE_SECTION_VIEW])
        check(False, "constructing an unsupported VERIFIED claim must raise")
    except ProvenanceError as e:
        check("cannot be VERIFIED" in str(e), "unsupported VERIFIED claim raises at construction")

    c = Claim("c2", "s.173 maps to record 49099", UNFETCHED_CORROBORATION, [INDIACODE_SECTION_VIEW])
    check(not c.servable(), "UNFETCHED_CORROBORATION is not servable to a user")
    check(Claim("c3", "x", VERIFIED, [INDIACODE_PDF]).servable(), "VERIFIED is servable")
    check(Claim("c4", "x", CORROBORATED, [INDIACODE_PDF]).servable(), "CORROBORATED is servable")
    check(not Claim("c5", "x", INFERRED).servable(), "INFERRED is not servable")
    check(not Claim("c6", "x", RETRACTED, [INDIACODE_PDF]).servable(), "RETRACTED is not servable")

    try:
        Claim("c7", "x", "PROBABLY_FINE")
        check(False, "invented state must raise")
    except ProvenanceError:
        check(True, "invented evidence state rejected")

    # A source whose bytes changed since review must lose VERIFIED support.
    tampered = SourceRecord(**{**INDIACODE_PDF.__dict__, "artifact_sha256": "0" * 64})
    good2, why2 = can_promote([tampered])
    check(not good2 and "hash mismatch" in why2, "hash mismatch blocks promotion")

    # Week 2.1: the Rules are recorded as attempted-and-unreachable, not silently absent.
    r = BOARD_MEETING_RULES_2014
    check(r.accessibility == UNREACHABLE, "Rules source recorded UNREACHABLE (host down, not 403)")
    check(r.local_artifact is None and not r.artifact_present(), "no Rules artifact is claimed")
    good3, _ = can_promote([r])
    check(not good3, "an unacquired source cannot support VERIFIED")
    check(not Claim("r1", "Rule 3 requires X", INFERRED, [r]).servable(),
          "nothing built on the unacquired Rules is servable")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
