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

# How the SOURCE behaved when we asked for it. A separate axis from the evidence states above:
# those grade an artifact we hold, these grade an attempt to obtain one. Conflating the two is the
# mistake that put a retry schedule against a WAF -- see docs/ACQUISITION_POLICY.md.
ACCESSIBLE = "ACCESSIBLE"
BLOCKED = "BLOCKED"          # 403 / WAF. Not bypassed -- see CLAUDE.md.
UNREACHABLE = "UNREACHABLE"  # timeout / DNS failure / connection refused: the host never answered.
NOT_FOUND = "NOT_FOUND"      # 404 from a host that DID answer.

ACCESSIBILITY_STATES = (ACCESSIBLE, BLOCKED, UNREACHABLE, NOT_FOUND)


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

    def __post_init__(self) -> None:
        # A typo'd accessibility is worse than a crash: it silently falls outside RETRYABLE, so the
        # source is quietly never retried and nobody is told why.
        if self.accessibility not in ACCESSIBILITY_STATES:
            raise ProvenanceError(
                f"{self.accessibility!r} is not an accessibility state; one of {ACCESSIBILITY_STATES}")

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
    source_id="EGAZETTE_MEETINGS_BOARD_RULES_2014",
    source_title="The Companies (Meetings of Board and its Powers) Rules, 2014 — principal Rules",
    source_url="https://egazette.gov.in/WriteReadData/2014/159201.pdf",
    official=True,
    accessibility=ACCESSIBLE,
    retrieved_on="2026-08-21",
    local_artifact="corpus/sources/companies_meetings_board_powers_rules_2014.pdf",
    artifact_sha256="b8b2e01b3d151ee038215c81d4fb10d802e4b84b8762ac385c2347417597167c",
    human_reviewed=False,
    notes="ACQUIRED from eGazette after every India Code route failed. Found via the Gazette's "
          "own notification-date search (31 MAR 2014), which returned content id 159201; the "
          "document is served from the static WriteReadData path under that id. 22 pages. "
          "Identity confirmed by scripts/acquire_rules.py: VERIFIED_PRINCIPAL, carrying "
          "'Short title and commencement', no amending language, no consolidation markers. "
          "The document states its own notification as G.S.R. 240(E) dated 31st March 2014, "
          "which CONFIRMS what was previously held only as an unverified third-party lead. "
          "human_reviewed stays False until a person reads it -- can_promote() enforces that.",
)

# Kept as a SEPARATE record from the host outage above, because the two failures need opposite
# responses and were conflated in the first write-up of this attempt (corrected 2026-08-21).
INDIACODE_DISCOVERY = SourceRecord(
    source_id="INDIACODE_DYNAMIC_DISCOVERY",
    source_title="India Code dynamic discovery (/handle/, /simple-search, /oai/, /rest/)",
    source_url="https://www.indiacode.nic.in/handle/123456789/1362/simple-search?searchradio=rules",
    official=True,
    accessibility=BLOCKED,
    retrieved_on=None,
    human_reviewed=False,
    notes="HTTP 403 on 2026-08-21. curl merely times out, which reads as an outage; a request "
          "path that actually receives the response gets 403, so this is a deliberate block, not "
          "downtime. DO NOT schedule automated retries against it -- repeated probing of a source "
          "that has refused us is exactly what the WAF exists to stop. The static "
          "/bitstream/*.pdf paths on the same host serve 200 and are unaffected. Consequence: the "
          "Rules' static address cannot be discovered by us automatically.",
)

# An unverified lead, recorded so it is not re-researched, and NOT treated as fact.
# Third-party sources state the principal Rules were notified by G.S.R. 240(E) dated 31-03-2014,
# and that later amendments (G.S.R. 398(E), 590(E), 409(E)) refer back to them. None of this has
# been read off an official document by us. It is a search hint for whoever retrieves the file,
# and a thing to CHECK against the document, never a thing to assert.
PRINCIPAL_RULES_LEAD = {
    "claimed_notification": "G.S.R. 240(E)",
    "claimed_date": "31-03-2014",
    "claimed_amendments": ["G.S.R. 398(E)", "G.S.R. 590(E)", "G.S.R. 409(E)"],
    # RESOLVED for the notification and date on 2026-08-21: the acquired gazette states
    # "G.S.R. 240 (E)" and "31st March, 2014" in its own text, so this is no longer a third-party
    # claim. The AMENDMENT list below has NOT been checked against anything and stays a lead.
    "evidence_state": CORROBORATED,
    "resolved_by": "EGAZETTE_MEETINGS_BOARD_RULES_2014",
    "caution": "Notification and date confirmed from the document. The amendment list remains "
               "unverified -- do not treat it as established.",
}

SOURCES = {s.source_id: s for s in (INDIACODE_PDF, INDIACODE_SECTION_VIEW,
                                    BOARD_MEETING_RULES_2014, INDIACODE_DISCOVERY)}

# Only an outage is retryable. BLOCKED and NOT_FOUND both mean the server answered us, and an
# answer does not change because it was asked for twice.
RETRYABLE = (UNREACHABLE,)


def is_retryable(accessibility: str) -> bool:
    """Whether an automated retry against a source in this state is appropriate.

    A host that is down may be retried; it may come back. A source that returned 403 may not:
    re-probing something that has refused us is abusive regardless of intent, and it is what the
    WAF is there to stop. A 404 may not either, for a different reason -- the server answered, and
    what it said was "not at this address". The address is what is wrong, and repeating a request
    cannot fix an address; only re-discovery or human retrieval can. That is also all a 404 means:
    India Code reshuffles file paths between releases, so a 404 at an exact known URL is evidence
    about the URL and evidence of nothing whatever about whether the instrument exists.
    """
    return accessibility in RETRYABLE


def should_retry(s: SourceRecord) -> bool:
    """Whether an automated retry against this source is appropriate. See is_retryable()."""
    return is_retryable(s.accessibility)


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

    # Week 2.1 closed: the Rules were acquired from eGazette on 2026-08-21 after every India Code
    # route failed. These assertions used to encode the not-acquired state; they now guard the
    # acquired one, and the retry-policy property they protected is tested against the source that
    # is still blocked.
    r = BOARD_MEETING_RULES_2014
    check(r.accessibility == ACCESSIBLE, "the Rules source is ACCESSIBLE -- acquired")
    check(r.artifact_present(), "the Rules PDF is stored in-repo")
    check(r.artifact_matches_hash(), "the stored Rules PDF still hashes to the recorded value")
    check(not r.human_reviewed, "human_reviewed stays False until a person reads it")
    good3, why3 = can_promote([r])
    check(not good3 and "no human review" in why3,
          "an unreviewed artifact cannot reach VERIFIED, however official its source")

    check(not should_retry(INDIACODE_DISCOVERY), "a 403 source is NEVER retried automatically")
    check(INDIACODE_DISCOVERY.accessibility == BLOCKED, "dynamic discovery stays recorded BLOCKED")
    check(should_retry(SourceRecord("x", "t", "u", True, UNREACHABLE)),
          "a downed host may still be retried")

    # The notification and date are now read off the document itself, so they are no longer a
    # third-party claim. The amendment list never was checked and must not drift into fact.
    check(PRINCIPAL_RULES_LEAD["evidence_state"] == CORROBORATED,
          "the G.S.R. number and date are confirmed from the acquired document")
    check(PRINCIPAL_RULES_LEAD["resolved_by"] == "EGAZETTE_MEETINGS_BOARD_RULES_2014",
          "...and the record says which artifact confirmed them")
    check("amendment list remains" in PRINCIPAL_RULES_LEAD["caution"],
          "the unchecked amendment list is still flagged as unverified")
    check(not Claim("r1", "Rule 3 requires X", INFERRED, [r]).servable(),
          "nothing built on the unacquired Rules is servable")

    # A 404 is its own state. Folding it into UNREACHABLE would schedule retries of a URL we
    # already know is the wrong URL; folding it into BLOCKED would imply we had been refused.
    stale = SourceRecord(
        source_id="STALE_ADDRESS_EXAMPLE",
        source_title="an exact address that no longer resolves to a document",
        source_url="https://www.indiacode.nic.in/bitstream/123456789/0000/0/gone.pdf",
        official=True,
        accessibility=NOT_FOUND,
        notes="Illustrative. No 404 has actually been observed for the Rules.",
    )
    check(NOT_FOUND in ACCESSIBILITY_STATES, "NOT_FOUND is a first-class accessibility state")
    check(NOT_FOUND not in (UNREACHABLE, BLOCKED), "NOT_FOUND is not an alias of the other two")
    check(not should_retry(stale), "a 404 at an exact address is not usefully retried")
    check(is_retryable(UNREACHABLE) and not is_retryable(NOT_FOUND) and not is_retryable(BLOCKED),
          "only an outage is retryable")
    good4, _ = can_promote([stale])
    check(not good4, "a 404 source supports nothing")
    # The point of the state: it says the ADDRESS is wrong, not that the instrument is absent.
    check(Claim("n1", "the Rules exist", UNRESOLVED, [stale]).state == UNRESOLVED,
          "a 404 leaves existence UNRESOLVED, it does not disprove existence")

    try:
        SourceRecord(source_id="x", source_title="x", source_url="x", official=True,
                     accessibility="MAYBE")
        check(False, "invented accessibility state must raise")
    except ProvenanceError:
        check(True, "invented accessibility state rejected")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
