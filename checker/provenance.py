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
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

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

# Where a registration record may say an instrument came from. Exact host names, not a suffix
# match -- "ends with gov.in" would admit any host under gov.in, and "contains egazette" admits
# egazette.gov.in.example.com. India Code's old indiacode.nic.in is absent on purpose: it is dead
# (CLAUDE.md), so no download came from it.
#
# Two sets, because a record may attest a narrower class than "official". The 880(E) record
# attests "the host was the Gazette or India Code"; a file from the ministry's own site is official
# but is not what that record attests, so its guard passes GAZETTE_OR_INDIA_CODE_HOSTS.
GAZETTE_OR_INDIA_CODE_HOSTS = frozenset({
    "egazette.gov.in", "www.egazette.gov.in",
    "indiacode.gov.in", "www.indiacode.gov.in",
})
OFFICIAL_SOURCE_HOSTS = GAZETTE_OR_INDIA_CODE_HOSTS | frozenset({"mca.gov.in", "www.mca.gov.in"})

# Unicode categories that are invisible, or that a URL parser edits away: controls,
# format characters (U+200B, U+FEFF, the bidi marks) and every kind of space.
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})


def _unspaced(value: str) -> bool:
    """False when the value carries whitespace, a control, or an invisible character.

    urlsplit() strips leading and trailing spaces and control characters, and removes
    tab, CR and LF from anywhere in the address. So `" https://egazette.gov.in/x "`
    parses as a clean Gazette URL -- and then the record stores, and a reader is
    served, the string WITH the spaces, which is a different address from the one
    that was checked. Refusing is the fail-closed half of the choice: a checker that
    edits its input silently is checking something the caller never passed it.

    `str.isspace()` is not enough on its own: U+200B ZERO WIDTH SPACE, U+FEFF and the
    bidi marks are not whitespace to Python, they are invisible on screen, and they
    survive a copy-and-paste out of a PDF or a web page -- which is exactly how an
    address reaches this function. Unicode category Cc (control), Cf (format) and
    Zs/Zl/Zp (separators) covers them by definition rather than by a list that has to
    be remembered.
    """
    return not any(ch.isspace() or unicodedata.category(ch) in _INVISIBLE_CATEGORIES
                   for ch in value)


def official_source_url(url: object, hosts: frozenset[str] = OFFICIAL_SOURCE_HOSTS) -> bool:
    """True only for an https address on one of `hosts`, with no credentials or odd port.

    `hosts` lets a caller narrow the set to what its record attests (see
    GAZETTE_OR_INDIA_CODE_HOSTS). It may only narrow: a set naming any host outside
    OFFICIAL_SOURCE_HOSTS raises, so no caller can widen "official" by passing its own list.

    A plain-http copy of a Gazette notification is a copy anyone on the path could have edited, so
    it is not a source this system may point to, however official the host name.
    """
    if not frozenset(hosts) <= OFFICIAL_SOURCE_HOSTS:
        raise ProvenanceError(
            f"hosts may only narrow the official set; not official: "
            f"{sorted(frozenset(hosts) - OFFICIAL_SOURCE_HOSTS)}")
    if not isinstance(url, str) or not url or not _unspaced(url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username is not None or parts.password is not None:
        return False
    if port not in (None, 443):
        return False
    return (parts.hostname or "") in hosts


class ProvenanceError(ValueError):
    """Raised on an unsupportable evidence claim. Never downgraded to a warning."""


# ── registration records: is this instrument usable law? (A-001) ────────────────────────────────
#
# scripts/register_*.py each hold one instrument and each answer the same question:
# may what this file says be served? Two human checks -- the right instrument, the
# clause verbatim -- were the whole answer until A-001, and neither of them says where
# the file came from. A record was attested, and its figures served, with that question
# unanswered. The rule below is P-1's, shared rather than copied, because four scripts
# with four copies of it drift and the drift is invisible until it serves something.
#
#   the classifier's own outcome is VERIFIED_INSTRUMENT, and
#   both human checks are recorded, and the status says so, and
#   the source is EITHER recorded -- an https download address on the host class the
#   record attests, with its date -- OR corroborated: a copy fetched from such a host
#   that is byte-identical, or carries the record's own clause verbatim.
#
# A recorded source that fails is a contradiction and is refused whatever the
# corroboration says. Provenance never stands in for a human check, and a human check
# never stands in for provenance.

VERIFIED_INSTRUMENT = "VERIFIED_INSTRUMENT"   # the classifier outcome a record must carry
PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"  # a record's status before review
HUMAN_CHECKS = ("identity_checked_by", "identity_checked_at",
                "verbatim_clause_checked_by", "verbatim_clause_checked_at")
# What a corroborating copy must be. "not-found" and "blocked" are outcomes of a search,
# not a corroboration, and anything looser than verbatim is not a match.
CORROBORATING_MATCHES = ("identical", "text-identical")
_SHA256_FIELD = re.compile(r"sha256:[0-9a-f]{64}")
# A date-only entry is read as midnight UTC; a person entering today's date from India
# can be up to a day "ahead" of that.
CLOCK_SLACK = timedelta(days=1)

# Outcomes of recording a download source. Every one of them but SOURCE_RECORDED leaves
# the record on disk exactly as it was.
NO_RECORD = "NO_RECORD"
SOURCE_REFUSED = "SOURCE_REFUSED"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
SOURCE_RECORDED = "SOURCE_RECORDED"
SOURCE_UNCHANGED = "SOURCE_UNCHANGED"

# One exit contract for every register script, and one sentence that describes it. They
# disagreed before: NO_RECORD exited 1, which the usage line called "recorded but not
# usable", when nothing had been recorded at all.
_CLI_EXIT = {CORROBORATED: 0, PENDING_HUMAN_REVIEW: 1,
             NO_RECORD: 2, SOURCE_REFUSED: 2, SOURCE_CONFLICT: 2}
EXIT_WORDING = ("Exit 0 only when the record is usable law afterwards; 1 when it is "
                "recorded but not usable; 2 when the request is refused or there is no "
                "registration to act on, and then nothing is written.")


def cli_exit(outcome: str) -> int:
    """The shell status for a register script's outcome. Unknown outcomes are not usable."""
    return _CLI_EXIT.get(outcome, 1)


def repo_path(named: object) -> tuple[Path | None, str | None]:
    """(path inside this repository, problem). Exactly one of the two is None.

    Records write repo-relative paths, and `ROOT / named` does NOT confine: pathlib
    treats an absolute right-hand side as the whole path, so "/etc/hosts" escapes, and
    "../../../etc/hosts" resolves outside. Either way the guard would then be reading,
    or reporting on, a file that is not part of the evidence this repository holds --
    and an escaping path that happens not to exist reads as a harmless absence.
    Symlinks are followed before the check, so a link out of the tree is caught too.
    """
    if not isinstance(named, str) or not named:
        return None, "no path recorded"
    if Path(named).is_absolute():
        return None, f"{named} is an absolute path; records name files inside the repository"
    try:
        resolved = (ROOT / named).resolve()
        resolved.relative_to(ROOT.resolve())
    except (ValueError, OSError):
        return None, f"{named} resolves outside the repository"
    return resolved, None


def repo_relative(path: Path) -> str | None:
    """`path` written the way a record must: relative to this repository, or None.

    None means the file is outside the tree -- which is the normal case for a fresh
    download sitting in ~/Downloads, and the reason register() says to copy it in
    rather than recording an address the guard will refuse.
    """
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except (ValueError, OSError):
        return None


_DIGESTS: dict[tuple[str, int, int], str] = {}


def file_digest(path: Path) -> str | None:
    """sha256 of a file, or None when it is not there. Memoised per process.

    The key carries size and mtime_ns as well as the path, so a file that changes
    under us gets a new digest rather than the one we happen to remember. Without the
    memo every served figure re-hashes every artifact it rests on -- ~3.5 ms a call
    measured on this corpus, on a path that runs once per obligation row.
    """
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    cached = _DIGESTS.get(key)
    if cached is not None:
        return cached
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    digest = "sha256:" + h.hexdigest()
    _DIGESTS[key] = digest
    return digest


def parse_when(value: object) -> datetime | None:
    """An ISO date or date-time as an aware datetime, or None. Naive means UTC.

    Whitespace is refused rather than trimmed, for the reason in _unspaced(): the value
    is stored as given, so what is checked must be what is stored.
    """
    if not isinstance(value, str) or not value or not _unspaced(value):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def source_conflict(rec: dict, downloaded_from: object, downloaded_at: object) -> str | None:
    """Why recording this source would silently replace a different one, or None.

    Recording the same source again is not a conflict.
    """
    old = (rec.get("downloaded_from"), rec.get("downloaded_at"))
    if old == (None, None) or old == (downloaded_from, downloaded_at):
        return None
    return ("a different download source is already recorded\n"
            f"  recorded : {old[0]} on {old[1]}\n"
            f"  given    : {downloaded_from} on {downloaded_at}\n"
            "Nothing was written. Pass --replace to overwrite the recorded source.")


def split_source_flags(args: list[str]) -> tuple[list[str], str | None, str | None] | None:
    """(remaining args, --from, --at); None when the flags are malformed."""
    rest: list[str] = []
    got: dict[str, str] = {}
    i = 0
    while i < len(args):
        if args[i] in ("--from", "--at"):
            if i + 1 >= len(args) or args[i] in got:
                return None
            got[args[i]] = args[i + 1]
            i += 2
            continue
        rest.append(args[i])
        i += 1
    if len(got) == 1:
        return None                     # an address without a date, or the reverse
    return rest, got.get("--from"), got.get("--at")


@dataclass(frozen=True)
class SourcePolicy:
    """What one registration record must show about where its artifact came from.

    `hosts` is the class of host the record's own attests_to names -- not every official
    host. `published` is the instrument's own date: no copy of it can have been
    downloaded earlier. `clause_field` is where the record keeps the verbatim clause a
    text-identical copy has to carry, because "rule 8" and "the operative clause" live
    under different keys in different records.
    """

    hosts: frozenset[str]
    published: date
    clause_field: str = "operative_clause"

    def __post_init__(self) -> None:
        # Raises when the set names a host outside the official one, so a policy cannot
        # widen "official" by construction.
        official_source_url("", hosts=self.hosts)

    def source_problem(self, url: object, at: object) -> str | None:
        """Why this (address, date) pair is not a usable download source, or None."""
        if not official_source_url(url, hosts=self.hosts):
            return (f"{url!r} is not an https address on a host this record attests "
                    f"({', '.join(sorted(self.hosts))})")
        when = parse_when(at)
        if when is None:
            return f"{at!r} is not an ISO date (YYYY-MM-DD or a full timestamp)"
        if when.date() < self.published:
            return f"{at} is before the instrument was published ({self.published.isoformat()})"
        if when > datetime.now(timezone.utc) + CLOCK_SLACK:
            return f"{at} is in the future"
        return None

    def corroboration_problem(self, rec: dict) -> str | None:
        """Why the record's corroborating copy does not corroborate, or None."""
        copy_ = rec.get("corroborating_copy")
        if not copy_:
            return "no corroborating copy from an official host"
        if not isinstance(copy_, dict):
            return "corroborating_copy is not a record"
        problem = self.source_problem(copy_.get("url"), copy_.get("retrieved_at"))
        if problem:
            return f"corroborating copy: {problem}"
        sha = copy_.get("sha256")
        if not isinstance(sha, str) or not _SHA256_FIELD.fullmatch(sha):
            return "corroborating copy has no well-formed sha256"
        match = copy_.get("match")
        if match not in CORROBORATING_MATCHES:
            return f"corroborating copy match is {match!r}, not one of {CORROBORATING_MATCHES}"
        if match == "identical" and sha != rec.get("artifact_sha256"):
            return "corroborating copy is called identical but its sha256 is not the held artifact's"
        if match == "text-identical" and (not rec.get(self.clause_field)
                                          or copy_.get("matched_clause")
                                          != rec.get(self.clause_field)):
            return ("corroborating copy is called text-identical but does not carry the held "
                    "operative clause verbatim")
        # A copy kept on disk is evidence only while it is still those bytes. Nothing
        # re-read it before this: the file could be replaced, or another file moved
        # into its name, and the record would go on corroborating.
        path, digest, unusable = self._local_copy(copy_)
        if unusable:
            return unusable
        if digest is not None and digest != sha:
            return (f"the stored copy {copy_['local_copy']} no longer hashes to the recorded "
                    f"value ({digest} on disk, {sha} recorded)")
        return None

    def artifact_problem(self, rec: dict | None) -> str | None:
        """Why the HELD artifact cannot carry this record's claim, or None.

        Everything else here checks a copy or an address. This checks the file the
        answer rests on, which was hashed once at registration and, until now, never
        read again: swap it, truncate it or delete it and the figure went on being
        served with the clause of a file that is no longer there.

        An absent artifact REFUSES rather than leaving a note, unlike an absent
        corroborating copy: the copy is a record of evidence gathered elsewhere, and
        its URL and hash were written down when it was fetched. The held artifact is
        the evidence itself, and nothing stands in for it.
        """
        if not isinstance(rec, dict) or not rec:
            return "no registration on record"
        sha = rec.get("artifact_sha256")
        if not isinstance(sha, str) or not _SHA256_FIELD.fullmatch(sha):
            return f"the recorded artifact hash {sha!r} is not a sha256"
        named = rec.get("local_artifact")
        if not isinstance(named, str) or not named:
            return ("the record does not name the file it holds, so the artifact cannot be "
                    "re-read (add local_artifact)")
        path, problem = repo_path(named)
        if problem:
            return f"the held artifact {named} cannot be read: {problem}"
        digest = file_digest(path)
        if digest is None:
            return f"the held artifact {named} is not on disk"
        if digest != sha:
            return (f"the held artifact {named} no longer hashes to the recorded value "
                    f"({digest} on disk, {sha} recorded)")
        return None

    def _local_copy(self, copy_: dict) -> tuple[Path | None, str | None, str | None]:
        """(path, sha256 on disk, problem) for a record's stored copy.

        The digest is None when the record names no copy or the file is not there; the
        problem is set only when the path itself is unusable, which is a refusal and
        not an absence.
        """
        named = copy_.get("local_copy")
        if not isinstance(named, str) or not named:
            return None, None, None
        path, problem = repo_path(named)
        if problem:
            return None, None, f"the stored copy {named} cannot be read: {problem}"
        return path, file_digest(path), None

    def local_copy_note(self, rec: dict | None) -> str | None:
        """What to say about a stored copy the record names but no longer holds.

        Not a gap: the corroboration is the URL and the hash recorded AT FETCH TIME,
        and deleting a file does not unsay them. But a record that names a local file
        it does not have is making a claim about this repository that is no longer
        true, and whoever reads the served figure should be told rather than left to
        find out.
        """
        if not isinstance(rec, dict):
            return None
        copy_ = rec.get("corroborating_copy")
        if not isinstance(copy_, dict):
            return None
        path, digest, unusable = self._local_copy(copy_)
        if unusable or path is None or digest is not None:
            return None
        return (f"the corroborating copy {copy_['local_copy']} is not on disk; the "
                f"corroboration rests on the address and hash recorded when it was fetched")

    def provenance_problem(self, rec: dict) -> str | None:
        """None when the record says where the artifact came from, or an official copy
        corroborates it. A recorded source that fails is a contradiction, and is refused
        whatever the corroboration says."""
        if rec.get("downloaded_from") is not None or rec.get("downloaded_at") is not None:
            problem = self.source_problem(rec.get("downloaded_from"), rec.get("downloaded_at"))
            return None if problem is None else f"the recorded download source is refused: {problem}"
        problem = self.corroboration_problem(rec)
        if problem is None:
            return None
        return f"where the file was downloaded from is not recorded, and {problem}"

    def attestation_gaps(self, rec: dict | None, *,
                         human_checks: tuple[str, ...] = HUMAN_CHECKS) -> list[str]:
        """Everything that keeps this record from being usable law. Empty means attested."""
        if not isinstance(rec, dict) or not rec:
            return ["no registration on record"]
        gaps = []
        # The classifier's outcome first. register() never writes a record for anything
        # but VERIFIED_INSTRUMENT, so any other value was put there by hand, and two
        # reviewer names do not overrule an identity check that failed.
        if rec.get("classification") != VERIFIED_INSTRUMENT:
            gaps.append(f"classification is {rec.get('classification')!r}, "
                        f"not {VERIFIED_INSTRUMENT}")
        gaps += [k for k in human_checks if not rec.get(k)]
        if rec.get("status") != CORROBORATED:
            gaps.append("status is not CORROBORATED")
        # Kept apart from the source gap, and prefixed so a caller can tell them
        # apart: "we cannot say where this file came from" and "this is not the file
        # that was checked" are different sentences to put in front of a reader.
        artifact = self.artifact_problem(rec)
        if artifact:
            gaps.append(f"artifact: {artifact}")
        problem = self.provenance_problem(rec)
        if problem:
            gaps.append(f"source: {problem}")
        return gaps

    def source_of(self, rec: dict | None) -> str | None:
        """The address a served figure may point to: the recorded download, else the
        corroborating copy. None when neither holds up -- the caller still decides
        whether the record is attested at all."""
        if not isinstance(rec, dict) or self.provenance_problem(rec) is not None:
            return None
        if rec.get("downloaded_from"):
            return str(rec["downloaded_from"])
        return str(rec["corroborating_copy"]["url"])

    def record_source(self, rec: dict | None, downloaded_from: object, downloaded_at: object,
                      *, replace: bool = False) -> tuple[str, dict | None, str]:
        """(outcome, the record to write or None, what to print).

        Pure: it never writes and never mutates `rec`, so a refusal cannot leave half a
        source behind. SOURCE_RECORDED is the only outcome carrying a record to write.
        """
        if rec is None:
            return NO_RECORD, None, "no registration on record — run register first"
        problem = self.source_problem(downloaded_from, downloaded_at)
        if problem:
            return (SOURCE_REFUSED, None,
                    f"download source refused: {problem}\nNothing was written.")
        conflict = None if replace else source_conflict(rec, downloaded_from, downloaded_at)
        if conflict:
            return SOURCE_CONFLICT, None, conflict
        if (rec.get("downloaded_from"), rec.get("downloaded_at")) == (downloaded_from,
                                                                      downloaded_at):
            return (SOURCE_UNCHANGED, None,
                    f"already recorded: downloaded from {downloaded_from} on {downloaded_at}")
        return (SOURCE_RECORDED,
                rec | {"downloaded_from": downloaded_from, "downloaded_at": downloaded_at},
                f"recorded: downloaded from {downloaded_from} on {downloaded_at}")


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

    # ── where an instrument may be recorded as coming from (A-001) ───────────
    for url in ("https://egazette.gov.in/WriteReadData/2025/268124.pdf",
                "https://indiacode.gov.in/handle/123456789/508916",
                "https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/rules.html",
                "https://EGAZETTE.gov.in/WriteReadData/2025/268124.pdf"):
        check(official_source_url(url), f"an official https address is accepted ({url})")
    for url, why in (
            ("http://egazette.gov.in/WriteReadData/2025/268124.pdf", "plain http"),
            ("https://taxguru.in/company-law/gsr-880e.html", "a commentary site"),
            ("https://egazette.gov.in.example.com/x.pdf", "a lookalike host"),
            ("https://example.com/?u=https://egazette.gov.in/x.pdf", "an official URL in a query"),
            ("https://someone@egazette.gov.in/x.pdf", "credentials in the address"),
            ("https://egazette.gov.in:8443/x.pdf", "a non-default port"),
            ("https://indiacode.nic.in/handle/123456789/2114", "India Code's dead domain"),
            ("egazette.gov.in/WriteReadData/2025/268124.pdf", "no scheme"),
            ("", "an empty string"),
            (None, "no value"),
            (42, "not a string")):
        check(not official_source_url(url), f"{why} is refused ({url!r})")

    # A record may attest a narrower class of host than "official". The caller passes it.
    mca = "https://www.mca.gov.in/x.pdf"
    check(official_source_url(mca), "the ministry's site is official by default")
    check(not official_source_url(mca, hosts=GAZETTE_OR_INDIA_CODE_HOSTS),
          "...but not a Gazette or India Code host")
    check(official_source_url("https://egazette.gov.in/x.pdf", hosts=GAZETTE_OR_INDIA_CODE_HOSTS)
          and official_source_url("https://indiacode.gov.in/x", hosts=GAZETTE_OR_INDIA_CODE_HOSTS),
          "...while the Gazette and India Code are")
    check(GAZETTE_OR_INDIA_CODE_HOSTS < OFFICIAL_SOURCE_HOSTS,
          "the narrower set is a strict subset of the official one")
    try:
        official_source_url("https://egazette.gov.in/x", hosts=frozenset({"evil.example"}))
        check(False, "a host set wider than the official one must raise")
    except ProvenanceError:
        check(True, "a host set wider than the official one is refused, not trusted")

    # Whitespace around (or inside) an address. urlsplit drops leading and trailing
    # spaces and removes tab/CR/LF anywhere, so the address CHECKED here would not be
    # the address stored in the record and served to a reader. Refuse rather than
    # strip: a checker that quietly edits its input is checking something else.
    # The escapes below are spelled out rather than pasted: an invisible character in
    # source reads as an ordinary space to the next person, which is how the label on
    # this very check came to say "non-breaking space" beside what looked like one.
    for bad, why in ((" https://egazette.gov.in/x.pdf", "a leading space"),
                     ("https://egazette.gov.in/x.pdf ", "a trailing space"),
                     ("https://egazette.gov.in/x.pdf\n", "a trailing newline"),
                     ("https://egazette.gov.in/Write\tReadData/x.pdf", "an embedded tab"),
                     ("https://egazette.gov.in/x\u00a0y.pdf", "an embedded U+00A0 no-break space"),
                     ("https://egazette.gov.in/x\u200by.pdf", "an embedded U+200B zero-width space"),
                     ("https://egazette.gov.in/x\ufeffy.pdf", "an embedded U+FEFF byte-order mark"),
                     ("https://egazette.gov.in/x\u200ey.pdf", "an embedded U+200E direction mark")):
        check(not official_source_url(bad),
              f"{why} is refused, not silently stripped ({bad!r})")

    # ── SourcePolicy: what a registration record must show about its source ───
    gaz = "https://egazette.gov.in/WriteReadData/2025/268124.pdf"
    P880 = SourcePolicy(GAZETTE_OR_INDIA_CODE_HOSTS, date(2025, 12, 1))
    check(P880.source_problem(gaz, "2025-12-02") is None,
          "a Gazette address with a date after publication is a usable source")
    check("not an https address" in (P880.source_problem("https://www.mca.gov.in/x.pdf",
                                                         "2025-12-02") or ""),
          "...the ministry's own site is not, for a record attesting the Gazette class")
    check("before the instrument was published" in (P880.source_problem(gaz, "2025-11-30") or ""),
          "...a download dated before publication is refused")
    check("in the future" in (P880.source_problem(gaz, "2999-01-01") or ""),
          "...and one dated in the future")
    check("not an ISO date" in (P880.source_problem(gaz, "last week") or ""),
          "...and a date that is not a date")
    check(P880.source_problem(gaz, " 2025-12-02") is not None,
          "...and a date carrying whitespace, which would be stored with it")
    try:
        SourcePolicy(frozenset({"evil.example"}), date(2025, 12, 1))
        check(False, "a policy naming a non-official host must raise")
    except ProvenanceError:
        check(True, "a policy may only narrow the official host set")

    # A real file this repository holds, so the record can be checked end to end: the
    # held artifact is re-read now, and a record naming no file cannot be checked at all.
    held_artifact = "corpus/sources/gsr880e_2025.pdf"
    held_hash = file_digest(ROOT / held_artifact)
    check(isinstance(held_hash, str) and held_hash.startswith("sha256:"),
          f"the fixture artifact is present and hashable ({held_artifact})")
    copy_ok = {"url": gaz, "retrieved_at": "2026-09-17T05:40:14Z", "sha256": held_hash,
               "match": "identical"}
    rec_ok = {"classification": VERIFIED_INSTRUMENT, "artifact_sha256": held_hash,
              "local_artifact": held_artifact,
              "identity_checked_by": "R", "identity_checked_at": "2026-01-01T00:00:00Z",
              "verbatim_clause_checked_by": "R",
              "verbatim_clause_checked_at": "2026-01-01T00:00:00Z",
              "status": CORROBORATED, "corroborating_copy": copy_ok}
    check(P880.corroboration_problem(rec_ok) is None,
          "an identical copy from an attested host corroborates")
    check(P880.provenance_problem(rec_ok) is None and P880.attestation_gaps(rec_ok) == [],
          f"...so the record has no gaps ({P880.attestation_gaps(rec_ok)})")
    check(P880.source_of(rec_ok) == gaz,
          "...and the address a served figure may point to is the copy's")
    recorded = {k: v for k, v in rec_ok.items() if k != "corroborating_copy"} | {
        "downloaded_from": "https://indiacode.gov.in/x.pdf", "downloaded_at": "2025-12-02"}
    check(P880.attestation_gaps(recorded) == [] and P880.source_of(recorded)
          == "https://indiacode.gov.in/x.pdf",
          "a recorded download address stands in its own right, and is what is served")
    check(any("source:" in g for g in P880.attestation_gaps(
              {k: v for k, v in rec_ok.items() if k != "corroborating_copy"})),
          "a record with neither a recorded source nor a copy has a source gap")
    check(any("classification" in g for g in P880.attestation_gaps(
              rec_ok | {"classification": "WRONG_INSTRUMENT"})),
          "the classifier's outcome is part of the attestation")
    check(P880.attestation_gaps(None) == ["no registration on record"]
          and P880.source_of(None) is None,
          "no record is every gap at once, and names no source")

    # A text-identical copy must carry the record's own clause, from the field the
    # record keeps it in -- rule 8 lives under a different key from a G.S.R. clause.
    clause = "Every listed company ... shall have whole-time key managerial personnel."
    P203 = SourcePolicy(GAZETTE_OR_INDIA_CODE_HOSTS, date(2014, 3, 31),
                        clause_field="operative_clause_rule_8")
    text_copy = copy_ok | {"match": "text-identical", "sha256": "sha256:" + "cd" * 32,
                           "matched_clause": clause}
    kmp = {"classification": VERIFIED_INSTRUMENT, "artifact_sha256": held_hash,
           "operative_clause_rule_8": clause, "corroborating_copy": text_copy}
    check(P203.corroboration_problem(kmp) is None,
          "a text-identical copy carrying the clause from the record's own field corroborates")
    check(P203.corroboration_problem(kmp | {"operative_clause_rule_8": "something else"})
          is not None,
          "...and does not when the clause differs")
    check(P880.corroboration_problem(kmp) is not None,
          "...and a policy reading another field finds no clause to compare")

    # ── a stored copy is evidence only while it is still those bytes ─────────
    # The copy's sha256 is what was fetched. local_copy names a file kept beside the
    # held artifact, and nothing re-read it: rename the file, change the file, and the
    # record went on corroborating. Present-and-different is a refusal; absent is not,
    # because the corroboration is the URL and hash recorded AT FETCH TIME and a
    # missing file does not unsay them -- but the record must stop implying it holds
    # a file it does not, so the absence is reported.
    import tempfile as _tempfile
    # Inside the repository: a record names repo-relative paths, and a path outside the
    # tree is refused outright (see the confinement checks below).
    with _tempfile.TemporaryDirectory(dir=ROOT, prefix=".p2_copy_test_") as _td:
        stored = Path(_td) / "gazette_copy.pdf"
        stored.write_bytes(b"%PDF-1.4 the bytes that were fetched")
        stored_rel = str(stored.relative_to(ROOT))
        stored_sha = "sha256:" + hashlib.sha256(stored.read_bytes()).hexdigest()
        with_local = {k: v for k, v in rec_ok.items() if k != "corroborating_copy"} | {
            "artifact_sha256": stored_sha,
            "corroborating_copy": copy_ok | {"sha256": stored_sha,
                                             "local_copy": stored_rel}}
        check(P880.corroboration_problem(with_local) is None
              and P880.local_copy_note(with_local) is None,
              "a stored copy that still hashes to the recorded value corroborates, quietly")
        stored.write_bytes(b"%PDF-1.4 somebody replaced this file")
        problem = P880.corroboration_problem(with_local)
        check(problem is not None and "no longer" in problem,
              f"...a stored copy whose bytes changed does NOT corroborate ({problem})")
        check(any(g.startswith("source:") for g in P880.attestation_gaps(with_local)),
              "...and the record is refused, not merely noted")
        stored.unlink()
        check(P880.corroboration_problem(with_local) is None,
              "a copy no longer on disk still corroborates: the URL and hash were "
              "recorded when it was fetched, and deleting a file does not unsay them")
        note = P880.local_copy_note(with_local)
        check(note is not None and "not on disk" in note and stored_rel in note,
              f"...but the record must not silently claim a local file it lost ({note})")
    check(P880.local_copy_note(rec_ok) is None and P880.local_copy_note(None) is None,
          "a record that claims no local copy has nothing to report")

    # ── the HELD artifact: the file the answer actually rests on ─────────────
    # Everything above checks a COPY. The artifact itself was hashed once, at
    # registration, and never read again: swap the file, truncate it, delete it, and
    # the figure went on being served with the clause of a file that is no longer
    # there. The corroborating copy is a RECORD of evidence; the held artifact IS the
    # evidence, so an absent one refuses rather than leaving a note.
    #
    # The fixture lives inside the repository because the guard accepts only
    # repo-relative paths -- which is the next check down.
    with _tempfile.TemporaryDirectory(dir=ROOT, prefix=".p2_artifact_test_") as _atd:
        art = Path(_atd) / "instrument.pdf"
        art.write_bytes(b"%PDF-1.4 the instrument as registered\n" + b"x" * 4096)
        rel = str(art.relative_to(ROOT))
        art_sha = "sha256:" + hashlib.sha256(art.read_bytes()).hexdigest()
        base = {k: v for k, v in rec_ok.items() if k != "corroborating_copy"} | {
            "artifact_sha256": art_sha, "local_artifact": rel,
            "downloaded_from": "https://egazette.gov.in/x.pdf", "downloaded_at": "2025-12-02"}
        check(P880.artifact_problem(base) is None and P880.attestation_gaps(base) == [],
              f"the held artifact, present and hashing to its record, is usable "
              f"({P880.attestation_gaps(base)})")

        whole = art.read_bytes()
        art.write_bytes(whole[:100] + bytes([whole[100] ^ 0x01]) + whole[101:])
        problem = P880.artifact_problem(base)
        check(problem is not None and "no longer hashes" in problem,
              f"...one byte different and it is refused ({problem})")
        check(any(g.startswith("artifact:") for g in P880.attestation_gaps(base))
              and not any(g.startswith("source:") for g in P880.attestation_gaps(base)),
              "...named as the artifact, not as a missing source: a reader must not be "
              "told the provenance is missing when the FILE is wrong")

        art.write_bytes(whole[:200])
        check(P880.artifact_problem(base) is not None,
              "...a truncated artifact is refused")
        art.unlink()
        gone = P880.artifact_problem(base)
        check(gone is not None and "not on disk" in gone,
              f"...and an artifact that is not there at all is refused, not noted ({gone})")

        # Path safety, for the held artifact and for a stored copy alike.
        outside = Path(_atd) / "outside_link.pdf"
        try:
            outside.symlink_to("/etc/hosts")
        except OSError:                                  # pragma: no cover
            outside = None
        for label, named in (("an absolute path", "/etc/hosts"),
                             ("a path escaping the repository", "../../../etc/hosts"),
                             ("a symlink out of the repository",
                              str(outside.relative_to(ROOT)) if outside else None)):
            if named is None:                            # pragma: no cover
                continue
            bad_art = P880.artifact_problem(base | {"local_artifact": named})
            check(bad_art is not None and ("outside the repository" in bad_art
                                           or "absolute" in bad_art),
                  f"{label} is refused as a held artifact ({bad_art})")
            bad_copy = {k: v for k, v in rec_ok.items()} | {
                "corroborating_copy": copy_ok | {"local_copy": named}}
            problem_copy = P880.corroboration_problem(bad_copy)
            check(problem_copy is not None,
                  f"...and refused as a stored copy, rather than read as merely absent "
                  f"({problem_copy})")

    nameless = {k: v for k, v in rec_ok.items() if k != "local_artifact"}
    check(any(g.startswith("artifact:") and "does not name" in g
              for g in P880.attestation_gaps(nameless)),
          f"a record that does not name the file it holds cannot be checked, so it is "
          f"refused ({P880.attestation_gaps(nameless)})")

    # The digest is memoised on (path, size, mtime) -- and must not outlive the file
    # it describes, or the whole check becomes a cache of a past truth.
    with _tempfile.TemporaryDirectory(dir=ROOT, prefix=".p2_memo_test_") as _mtd:
        f = Path(_mtd) / "a.bin"
        f.write_bytes(b"one")
        first = file_digest(f)
        check(file_digest(f) == first, "the same file hashes to the same value")
        f.write_bytes(b"two different bytes")
        check(file_digest(f) != first,
              "...and a file that changed hashes to a different one: the memo keys on "
              "size and mtime, so it cannot serve a stale digest")

    # ── recording a source: pure, so nothing is written on a refusal ──────────
    outcome, written, msg = P880.record_source(None, gaz, "2025-12-02")
    check(outcome == NO_RECORD and written is None, f"no record to record against ({outcome})")
    outcome, written, msg = P880.record_source(rec_ok, "https://taxguru.in/x.pdf", "2025-12-02")
    check(outcome == SOURCE_REFUSED and written is None and "refused" in msg,
          f"a commentary site is refused and nothing is written ({outcome})")
    outcome, written, msg = P880.record_source(rec_ok, gaz, "2025-12-02")
    check(outcome == SOURCE_RECORDED and written["downloaded_from"] == gaz
          and rec_ok.get("downloaded_from") is None,
          "a good source yields a NEW record; the one passed in is not mutated")
    check(all(written[k] == rec_ok[k] for k in rec_ok),
          "...and every other field is carried through unchanged")
    outcome, written, msg = P880.record_source(written, gaz, "2025-12-02")
    check(outcome == SOURCE_UNCHANGED and written is None,
          "recording the same source again writes nothing")
    with_src = rec_ok | {"downloaded_from": gaz, "downloaded_at": "2025-12-02"}
    outcome, written, msg = P880.record_source(with_src, "https://indiacode.gov.in/y.pdf",
                                               "2025-12-03")
    check(outcome == SOURCE_CONFLICT and written is None and "--replace" in msg,
          f"a different recorded source is not silently replaced ({outcome})")
    outcome, written, _ = P880.record_source(with_src, "https://indiacode.gov.in/y.pdf",
                                             "2025-12-03", replace=True)
    check(outcome == SOURCE_RECORDED and written["downloaded_from"].endswith("y.pdf"),
          "...unless --replace is given")

    # ── the CLI contract these scripts share ─────────────────────────────────
    check(split_source_flags(["--source", "--from", gaz, "--at", "2025-12-02"])
          == (["--source"], gaz, "2025-12-02"), "--from and --at are lifted out of the args")
    check(split_source_flags(["--source", "--from", gaz]) is None
          and split_source_flags(["--at", "2025-12-02"]) is None,
          "...and an address without a date, or the reverse, is malformed")
    check(split_source_flags(["--from", gaz, "--from", gaz, "--at", "x"]) is None,
          "...and a flag repeated is malformed")
    check(split_source_flags(["file.pdf"]) == (["file.pdf"], None, None),
          "...while no flags at all is fine")
    # An exit status a shell can act on, and a usage line that says the same thing.
    check((cli_exit(CORROBORATED), cli_exit(PENDING_HUMAN_REVIEW)) == (0, 1),
          "0 is usable law, 1 is recorded but not usable")
    check(cli_exit(NO_RECORD) == cli_exit(SOURCE_REFUSED) == cli_exit(SOURCE_CONFLICT) == 2,
          "and 2 is every outcome that writes nothing -- including NO_RECORD, which "
          "used to exit 1 while the usage line called 1 'recorded but not usable'")
    check("nothing is written" in EXIT_WORDING and "no registration" in EXIT_WORDING,
          f"...and the shared usage wording says so ({EXIT_WORDING})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
