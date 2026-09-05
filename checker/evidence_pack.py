"""
The evidence pack — the only thing a language model is ever shown.

Every other module in this repo can be wrong and be caught later. This one cannot, because it is
the boundary: whatever passes through it becomes, for the model, the entire universe of Indian
company law. A fact that is not in the pack must be unassertable; a fact that is in the pack but
cannot be relied on must be visibly marked as such rather than quietly omitted, because a
provision that silently disappears looks to the model exactly like a provision that does not
exist — and "s.16 says nothing about this" is a different (and wrong) answer from "s.16 was found
and its text cannot be relied on".

Three properties this file exists to hold:

1. **Closed world.** `prompt_block()` states the rule as a prohibition, not a preference. There is
   no phrasing in it that a model can read as permission to fill a gap from its own weights.

2. **Servability is inherited, not asserted.** A provision is usable for answering only when the
   evidence state of the source behind it is in `provenance.SERVABLE`. The four SD-002 sections
   (s.16, s.124, s.76A, s.329) are held at UNRESOLVED because the two renderings of the same
   publisher disagree about their amendment vintage — so they are unusable by the same rule that
   governs everything else, not by a special case bolted on top.

3. **No repair.** SD-001 left the editorial instruction "To be deleted" inside the corpus text of
   s.1. CLAUDE.md forbids repairing a defective government source. So the raw text is carried
   verbatim and a *separate* `reading_text` carries the cleaned rendering, with every
   transformation named in `derivations`. Both are in `to_dict()`. The defect is never invisible
   and the original is never lost.

On `as_of`: the pack states which version of the law it carries. What it carries is the current
consolidation as India Code rendered it on the ingestion date — nothing more. `checker/as_of.py`
can reconstruct a section at a past date, but that reconstruction is UNVERIFIED against any
external source (CLAUDE.md, "Known-invalid results"), so this pack refuses to describe itself as
point-in-time at all. If the caller asks for a date, the pack records the request and names it as
something it cannot supply.

Input is a plain list of dicts so this module is testable and wireable standalone:

    {"section_number": "173", "section_id": "49099", "title": "Meetings of Board",
     "defects": ()}

Run: python3 checker/evidence_pack.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The rest of the suite is run through scripts/run_tests.sh, which exports PYTHONPATH. This module
# is also meant to be runnable as a bare file, and `python3 checker/evidence_pack.py` puts
# checker/ on sys.path rather than the repo root, so `import checker.x` would die. Adding the root
# here makes both invocations work; it is a no-op when PYTHONPATH is already set.
if __package__ in (None, ""):  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(ROOT))

from checker import provenance as prov  # noqa: E402
from checker.legal_ref import ACT, LegalRef, parse_key  # noqa: E402

CORPUS_DIR = ROOT / "corpus/companies_act"
DEFAULT_INSTRUMENT = "COMPANIES_ACT_2013"


class EvidencePackError(ValueError):
    """Raised when a row cannot be packed safely. Never downgraded to a skipped row.

    A row we cannot identify is not a row we may quietly drop: the caller would then see a pack
    that is merely thin, with no way to tell that something was lost on the way in.
    """


# --- defects ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Defect:
    """A known problem with the source text of a provision, carried alongside it.

    `blocks_answering` is deliberately separate from the evidence state. The state answers "what
    backs this text"; the defect answers "what is wrong with this text". They usually agree, and
    when they do the provision is gated twice, which is the intent.
    """
    code: str
    summary: str
    warning: str
    blocks_answering: bool
    doc_ref: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "summary": self.summary, "warning": self.warning,
                "blocks_answering": self.blocks_answering, "doc_ref": self.doc_ref,
                "detail": self.detail}


SD_001 = "SD-001"
SD_002 = "SD-002"
SD_002_OPEN = "SD-002-OPEN"
EP_RECORD_MISSING = "EP-RECORD-MISSING"
EP_TEXT_EMPTY = "EP-TEXT-EMPTY"
EP_UNKNOWN_DEFECT = "EP-UNKNOWN-DEFECT"

DEFECTS: dict[str, Defect] = {
    SD_001: Defect(
        code=SD_001,
        summary="The corpus text of this provision contains the editorial instruction "
                "\"To be deleted\", which is not statutory text.",
        warning="Do not treat \"To be deleted\" as part of the law. It is India Code's own "
                "editorial matter, left in their JSON rendering and absent from their PDF of the "
                "same section. It is preserved verbatim in raw_text and removed only in "
                "reading_text.",
        blocks_answering=False,
        doc_ref="docs/SOURCE_DEFECTS.md#sd-001",
    ),
    SD_002: Defect(
        code=SD_002,
        summary="India Code's JSON rendering of this provision is at an EARLIER amendment vintage "
                "than the same publisher's PDF. The text held here is pre-amendment.",
        warning="This provision may not be used to answer. Its text is confirmed to be superseded "
                "wording (the 'fine' -> 'penalty' signature of the Companies (Amendment) Act 2020, "
                "and for s.329 text the PDF no longer carries). Which rendering is authoritative "
                "for a given date is unresolved until an independent publisher settles it.",
        blocks_answering=True,
        doc_ref="docs/SOURCE_DEFECTS.md#sd-002",
    ),
    SD_002_OPEN: Defect(
        code=SD_002_OPEN,
        summary="The cross-render check found unexplained divergence between the JSON corpus and "
                "the PDF for this provision, and nobody has inspected it.",
        warning="Not cleared, not condemned. Because the divergence is uninspected, this pack "
                "cannot say the two renderings agree, so the provision is not servable. Inspect it "
                "before relying on it.",
        blocks_answering=False,
        doc_ref="docs/SOURCE_DEFECTS.md#open-not-cleared",
    ),
    EP_RECORD_MISSING: Defect(
        code=EP_RECORD_MISSING,
        summary="No corpus record exists on disk for this provision.",
        warning="The provision was named by retrieval but its text was never loaded. Nothing may "
                "be said about its contents.",
        blocks_answering=True,
        doc_ref="checker/evidence_pack.py",
    ),
    EP_TEXT_EMPTY: Defect(
        code=EP_TEXT_EMPTY,
        summary="The corpus record for this provision carries no text.",
        warning="An empty record is not an empty provision. Nothing may be inferred from the "
                "absence of text here.",
        blocks_answering=True,
        doc_ref="checker/evidence_pack.py",
    ),
}

# SD-002, confirmed: the JSON corpus carries pre-amendment wording for exactly these four.
# docs/SOURCE_DEFECTS.md gives the diverging wording for each.
SD_002_SECTIONS = ("16", "124", "76A", "329")

# "Open, not cleared" in docs/SOURCE_DEFECTS.md: long unexplained cross-render runs that were never
# individually inspected. s.329 is omitted because it is already SD-002 above; s.67, s.378ZR, s.22,
# s.139 and s.186 are omitted because they WERE inspected and explained (PDF headings and
# structural matter). Withholding these five is a policy choice — the honest reading of "open, not
# cleared" is that we cannot claim the renderings agree — and it is confined to this tuple so it
# can be changed in one place when the inspections are done.
SD_002_OPEN_SECTIONS = ("236", "465", "247", "74", "78")

# SD-001. Detected from the text rather than assumed from the record id, so that a second
# occurrence elsewhere in the corpus would also be caught rather than silently served. The
# instruction is a standalone line in corpus/companies_act/184.json (Companies Act 2013, s.1).
EDITORIAL_INSTRUCTION = "To be deleted"
_EDITORIAL_RE = re.compile(r"(?<![A-Za-z])" + re.escape(EDITORIAL_INSTRUCTION) + r"(?![A-Za-z])")


# --- derived renderings -------------------------------------------------------------------------

@dataclass(frozen=True)
class Derivation:
    """One transformation applied to produce `reading_text`, and why it was applied.

    Recorded rather than performed silently: a reader comparing reading_text with raw_text must be
    able to account for every difference between them without guessing.
    """
    transform: str
    reason: str
    removed: str | None = None
    chars_before: int = 0
    chars_after: int = 0

    def to_dict(self) -> dict:
        return {"transform": self.transform, "reason": self.reason, "removed": self.removed,
                "chars_before": self.chars_before, "chars_after": self.chars_after}


# Layout-only markup in India Code's JSON. <sup>N</sup> is NOT in here: those are amendment
# markers, they carry legal meaning (this span was inserted/substituted), and checker/as_of.py
# navigates by them. Dropping them would flatten an amended provision into an unamended-looking one.
_BREAK_TAGS = re.compile(r"</?br\s*/?>|<hr\b[^>]*>", re.I)
_INLINE_TAGS = re.compile(r"</?(?:span|i|b|p|div)\b[^>]*>", re.I)


def _reading_text(raw: str) -> tuple[str, tuple[Derivation, ...]]:
    """A readable rendering of a corpus record, with every transformation recorded.

    Order matters: the editorial instruction is removed from the raw text first, so `removed`
    quotes the string exactly as it stands in the source.
    """
    derivations: list[Derivation] = []
    text = raw

    if _EDITORIAL_RE.search(text):
        before = len(text)
        text = _EDITORIAL_RE.sub("", text)
        derivations.append(Derivation(
            transform="REMOVE_EDITORIAL_INSTRUCTION",
            reason=f"{SD_001}: {EDITORIAL_INSTRUCTION!r} is India Code editorial matter, not "
                   f"statutory text. Removed from this reading rendering ONLY. The source is not "
                   f"repaired: raw_text still carries it verbatim.",
            removed=EDITORIAL_INSTRUCTION,
            chars_before=before, chars_after=len(text)))

    before = len(text)
    stripped = _BREAK_TAGS.sub("\n", text)
    stripped = _INLINE_TAGS.sub("", stripped)
    lines = [" ".join(ln.split()) for ln in stripped.splitlines()]
    stripped = "\n".join(ln for ln in lines if ln).strip()
    if stripped != text:
        derivations.append(Derivation(
            transform="STRIP_PRESENTATIONAL_MARKUP",
            reason="India Code's JSON embeds presentational HTML (span/hr/br) that is not part of "
                   "the enactment. Removed for legibility. Amendment markers <sup>N</sup> are "
                   "preserved: they record that a span was amended.",
            chars_before=before, chars_after=len(stripped)))
    return stripped, tuple(derivations)


# --- sources ------------------------------------------------------------------------------------

def _corpus_source(record_id: str, fetched_at: str | None, source_url: str | None) -> prov.SourceRecord:
    """The source record for one ingested corpus file.

    Note what is NOT claimed: `artifact_sha256` is left None even though the record carries a
    sha256 field, because that hash is over the fetched content, not over the file on disk, and
    `can_promote()` would be comparing it against the wrong thing. `human_reviewed` is False
    because these 527 records were not read by a human. Both omissions are what keeps any claim
    built on this source below VERIFIED.
    """
    return prov.SourceRecord(
        source_id="INDIACODE_SECTIONPAGE_JSON",
        source_title="India Code SectionPageContent JSON (ingested corpus record)",
        source_url=source_url or "https://www.indiacode.nic.in/SectionPageContent",
        official=True,
        accessibility=prov.ACCESSIBLE,
        retrieved_on=(fetched_at or "")[:10] or None,
        local_artifact=f"corpus/companies_act/{record_id}.json",
        artifact_sha256=None,
        human_reviewed=False,
        notes="Ingested rendering. Content hash is recorded in the record itself; the file is not "
              "hash-pinned here and the text has not been human-reviewed, so this source alone "
              "cannot reach VERIFIED.",
    )


# Why CORROBORATED and not VERIFIED for a clean provision: scripts/cross_validate_corpus.py
# compared every corpus record against INDIACODE_CA2013_PDF -- a hashed, human-reviewed, in-repo
# artifact -- and found median coverage 1.0000 with 456/464 at or above 0.99. That is a second
# accessible rendering agreeing, which is exactly CORROBORATED. It is NOT verification, and the
# reason is stated in docs/SOURCE_DEFECTS.md: both renderings are India Code, so a defect in their
# own source appears identically in both and is invisible to the check.
_CORROBORATION_NOTE = (
    "The corpus rendering of this provision agrees with India Code's own full-Act PDF "
    "(INDIACODE_CA2013_PDF, hashed and human-reviewed in-repo). Both renderings come from the SAME "
    "publisher, so this is corroboration between two renderings, not independent verification. "
    "Independent-publisher verification is PENDING.")

# The closed-world contract, kept in one place because it is the product's safety boundary in
# words. Every line is an instruction or a fact. Nothing here is softened: a model reads a
# softened prohibition as a licence.
CLOSED_WORLD_RULES = (
    "The provisions reproduced below are the ONLY law available to you. Rules:",
    "1. State no legal proposition that is not written in the text below.",
    "2. Cite no provision that is not listed below by its reference key.",
    "3. Do not complete, continue, or reconstruct any text that is withheld, empty, or marked "
    "unusable.",
    "4. Do not use anything you know about Indian law from outside this pack. Your prior "
    "knowledge of the Companies Act 2013 is not evidence here.",
    "5. If this pack does not contain what the question needs, answer exactly: INSUFFICIENT "
    "EVIDENCE — and name what is missing.",
    "6. Refer to every provision by its reference key. A bare section number is not an identity.",
)
WITHHELD_NOTICE = (
    "    Its text is held in the evidence pack record and is WITHHELD from this block. You may "
    "state that this provision was located and that its text cannot be relied on. You may not "
    "quote it, paraphrase it, summarise it, or answer from it.")
NO_RECORDED_GAPS = (
    "- No further gaps were recorded. This is not a statement that the pack is complete: it lists "
    "only what was asked for and not supplied.")
STATUS_INSUFFICIENT = (
    "STATUS: INSUFFICIENT EVIDENCE. This pack cannot support a legal answer. Reply with "
    "INSUFFICIENT EVIDENCE, state which provisions were found and why they cannot be relied on, "
    "and stop. Do not answer from any other source.")
STATUS_SUFFICIENT = (
    "STATUS: ANSWER ONLY FROM THE USABLE EVIDENCE ABOVE. For any part of the question that the "
    "usable evidence does not settle, write INSUFFICIENT EVIDENCE for that part and name what is "
    "missing.")

IDENTITY_NOTE = (
    "Provision identity: every provision here is named by an instrument-qualified key "
    "(e.g. ACT:COMPANIES_ACT_2013:S173). A bare provision number is not an identity -- the "
    "full-Act PDF reproduces subordinate Rules that renumber from 1, so \"56\" names both "
    "Companies Act s.56 and Meetings-of-Board Rules r.56. The number -> corpus record mapping was "
    "derived from INDIACODE_CA2013_PDF. India Code's section view, which would confirm the mapping "
    "from the source itself, returned HTTP 403 and has never been read, so the mapping is "
    "corroborated but NOT source-confirmed.")


# --- as_of --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class AsOf:
    """Which version of the law this pack carries -- or the admission that we do not know.

    There is no `as_of_date` field, and that absence is the design. The corpus is the current
    consolidation as rendered on the ingestion date; it is not a dated snapshot of the statute
    book, and SD-002 proves the point in the sharpest way available: at least four records are
    demonstrably at an EARLIER vintage than the rest, so a single date over the whole pack would
    be false for them. `checker/as_of.py` can roll a section back, but that engine is UNVERIFIED
    against any external source, so no output of it is described here as a point-in-time version.
    """
    basis: str
    point_in_time_verified: bool
    evidence_state: str
    corpus_fetched: tuple[str, ...]
    point_in_time_requested: str | None
    statement: str

    def to_dict(self) -> dict:
        return {"basis": self.basis, "point_in_time_verified": self.point_in_time_verified,
                "evidence_state": self.evidence_state, "corpus_fetched": list(self.corpus_fetched),
                "point_in_time_requested": self.point_in_time_requested,
                "statement": self.statement}


CURRENT_CONSOLIDATION = "CURRENT_CONSOLIDATION_AS_INGESTED"


def _build_as_of(fetched: tuple[str, ...], requested: date | str | None) -> AsOf:
    when = ", ".join(fetched) if fetched else "an unrecorded date"
    parts = [
        f"This pack carries the CURRENT CONSOLIDATION of the Companies Act 2013 as India Code "
        f"rendered it when the corpus was ingested ({when}). It is NOT a point-in-time version of "
        f"the law and carries no verified commencement or amendment date.",
        "The amendment vintage of individual provisions is not uniform and not fully known: "
        "SD-002 confirms that some records carry pre-amendment wording while the same publisher's "
        "PDF carries later wording. Those provisions are marked unusable in this pack.",
        "Point-in-time reconstruction exists in this system but is UNVERIFIED against any external "
        "source, so no statement here is a statement about the law as it stood on any past date.",
    ]
    req = None
    if requested is not None:
        req = requested.isoformat() if isinstance(requested, date) else str(requested)
        parts.append(
            f"A point-in-time answer was requested for {req}. This pack CANNOT supply one. Do not "
            f"treat any text below as the law as it stood on {req}.")
    return AsOf(
        basis=CURRENT_CONSOLIDATION,
        point_in_time_verified=False,
        # UNRESOLVED, not INFERRED: we did not derive a version and get no external agreement; we
        # looked at what vintage the corpus is and found nothing conclusive.
        evidence_state=prov.UNRESOLVED,
        corpus_fetched=fetched,
        point_in_time_requested=req,
        statement=" ".join(parts),
    )


# --- the pack -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class PackedProvision:
    ref: LegalRef
    corpus_record_id: str
    corpus_record_path: str | None
    raw_text: str | None
    reading_text: str | None
    derivations: tuple[Derivation, ...]
    claim: prov.Claim
    defects: tuple[Defect, ...]
    corpus_content_sha256: str | None = None

    @property
    def key(self) -> str:
        return self.ref.key()

    @property
    def blocking_defects(self) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.blocks_answering)

    @property
    def usable_for_answering(self) -> bool:
        """Two independent gates, both of which must open.

        The evidence state is the general rule (nothing outside provenance.SERVABLE may reach a
        user as a legal statement). The defect gate is the specific one. Either alone would be
        sufficient today; keeping both means a future source-state change cannot quietly re-enable
        a provision that is known to be defective, and vice versa.
        """
        if not self.claim.servable():
            return False
        if self.blocking_defects:
            return False
        return bool(self.raw_text)

    def unusable_reason(self) -> str:
        if self.usable_for_answering:
            return ""
        reasons = []
        if not self.claim.servable():
            reasons.append(f"evidence state {self.claim.state} is not servable "
                           f"(servable states: {', '.join(prov.SERVABLE)})")
        for d in self.blocking_defects:
            reasons.append(f"{d.code}: {d.summary}")
        if not self.raw_text:
            reasons.append("no text was loaded for this provision")
        return "; ".join(reasons)

    def to_dict(self) -> dict:
        return {
            "ref": self.key,
            "cite": self.ref.cite(),
            "instrument_type": self.ref.instrument_type,
            "instrument_id": self.ref.instrument_id,
            "title": self.ref.title,
            "corpus_record_id": self.corpus_record_id,
            "corpus_record_path": self.corpus_record_path,
            "corpus_content_sha256": self.corpus_content_sha256,
            "raw_text": self.raw_text,
            "reading_text": self.reading_text,
            "derivations": [d.to_dict() for d in self.derivations],
            "evidence_state": self.claim.state,
            "evidence_state_servable": self.claim.servable(),
            "evidence_statement": self.claim.statement,
            "evidence_notes": self.claim.notes,
            "sources": [{"source_id": s.source_id, "source_title": s.source_title,
                         "source_url": s.source_url, "official": s.official,
                         "accessibility": s.accessibility, "retrieved_on": s.retrieved_on,
                         "local_artifact": s.local_artifact, "human_reviewed": s.human_reviewed,
                         "notes": s.notes} for s in self.claim.sources],
            "defects": [d.to_dict() for d in self.defects],
            "usable_for_answering": self.usable_for_answering,
            "unusable_reason": self.unusable_reason(),
        }


@dataclass(frozen=True)
class EvidencePack:
    # The pack records the mode it was BUILT in. An adapter that took `mode` as an argument could
    # be lied to by its caller; a pack that attests to its own provenance cannot. MODE_REVIEW packs
    # contain material a human may inspect and a model may not, so this field is a safety boundary,
    # not metadata.
    provisions: tuple[PackedProvision, ...] = ()
    as_of: AsOf = field(default_factory=lambda: _build_as_of((), None))
    missing: tuple[str, ...] = ()
    query: str = ""
    mode: str = "MODEL"

    @property
    def usable(self) -> tuple[PackedProvision, ...]:
        return tuple(p for p in self.provisions if p.usable_for_answering)

    @property
    def unusable(self) -> tuple[PackedProvision, ...]:
        return tuple(p for p in self.provisions if not p.usable_for_answering)

    @property
    def insufficient_evidence(self) -> bool:
        """True when nothing in here can carry an answer.

        The rule is deliberately strict: a provision counts only if it is usable AND carries no
        defect at all. A defect-flagged provision may still be readable (SD-001's s.1 is), but a
        pack whose entire content is flagged is a pack that has to say so rather than let an
        answer be built on it and footnoted afterwards.
        """
        return not any(p.usable_for_answering and not p.defects for p in self.provisions)

    def to_dict(self) -> dict:
        return {
            "schema": "placedon.evidence_pack/1",
            "query": self.query,
            "as_of": self.as_of.to_dict(),
            "identity_note": IDENTITY_NOTE,
            "insufficient_evidence": self.insufficient_evidence,
            "provision_keys": [p.key for p in self.provisions],
            "usable_keys": [p.key for p in self.usable],
            "unusable_keys": [p.key for p in self.unusable],
            "mode": self.mode,
            "provisions": [p.to_dict() for p in self.provisions],
            "missing": list(self.missing),
        }

    def prompt_block(self) -> str:
        """The pack rendered for a model.

        Every sentence here is an instruction or a fact. There is no "try to", no "where
        possible", no "generally" -- a model reads a softened prohibition as a licence, and the one
        thing this system cannot survive is a fluent answer sourced from model weights.

        The text of an unusable provision is withheld from this block while remaining present in
        the pack record. A model shown superseded statutory text alongside a warning will use the
        text; the warning is not a strong enough counterweight to the text itself. What the model
        is told is that the provision was found and why it cannot be used, which is the fact the
        answer needs.
        """
        L: list[str] = ["=== EVIDENCE PACK — CLOSED WORLD ===", *CLOSED_WORLD_RULES]
        if self.query:
            L += ["", f"QUESTION PUT TO THE SYSTEM: {self.query}"]
        L += ["", "VERSION OF THE LAW CARRIED BY THIS PACK", self.as_of.statement,
              "", "PROVISION IDENTITY", IDENTITY_NOTE,
              "", f"USABLE EVIDENCE ({len(self.usable)})"]
        if not self.usable:
            L.append("NONE. No provision in this pack may be used to answer.")
        for p in self.usable:
            src = ", ".join(s.source_id for s in p.claim.sources) or "none recorded"
            L += ["", f"--- {p.key} | {p.ref.title}",
                  f"    evidence state: {p.claim.state} (servable)",
                  f"    source: {src}; corpus record {p.corpus_record_id}"]
            L += [f"    DEFECT {d.code}: {d.summary} {d.warning}" for d in p.defects]
            if p.derivations:
                L.append("    rendering: " + " ".join(f"[{d.transform}] {d.reason}"
                                                      for d in p.derivations))
            L.append("    text:")
            L += [f"        {line}" for line in (p.reading_text or "").splitlines()]

        L += ["", f"FOUND BUT NOT USABLE AS EVIDENCE ({len(self.unusable)})"]
        if not self.unusable:
            L.append("NONE.")
        for p in self.unusable:
            L += ["", f"--- {p.key} | {p.ref.title}",
                  f"    evidence state: {p.claim.state} (NOT servable)",
                  f"    why it cannot be used: {p.unusable_reason()}"]
            L += [f"    DEFECT {d.code}: {d.summary} {d.warning}" for d in p.defects]
            L.append(WITHHELD_NOTICE)

        L += ["", "NOT IN THIS PACK"]
        L += [f"- {m}" for m in self.missing] or [NO_RECORDED_GAPS]
        L += ["", STATUS_INSUFFICIENT if self.insufficient_evidence else STATUS_SUFFICIENT,
              "=== END OF EVIDENCE PACK ==="]
        return "\n".join(L)


# --- building -----------------------------------------------------------------------------------

def _normalise_defects(raw_defects) -> list[Defect]:
    """Turn whatever retrieval attached to a row into Defect objects.

    An unrecognised code is kept as an opaque flagged defect rather than dropped. CLAUDE.md:
    preserve uncertainty, never silently drop an unresolved marker. A dropped defect code is
    exactly that -- a marker that something is wrong, deleted on the way to the model.
    """
    out: list[Defect] = []
    for d in raw_defects or ():
        if isinstance(d, Defect):
            out.append(d)
            continue
        code, detail = (d, "") if isinstance(d, str) else (
            str(d.get("code", "")), str(d.get("detail", ""))) if isinstance(d, dict) else (str(d), "")
        known = DEFECTS.get(code)
        if known is not None:
            out.append(known if not detail else Defect(**{**known.__dict__, "detail": detail}))
        else:
            out.append(Defect(
                code=code or EP_UNKNOWN_DEFECT,
                summary=f"Unrecognised defect code {code!r} attached upstream.",
                warning="This pack does not know what this defect means. It is carried through "
                        "rather than discarded; treat the provision as questionable.",
                blocks_answering=False,
                doc_ref="", detail=detail))
    return out


def _read_record(section_id: str) -> dict | None:
    path = CORPUS_DIR / f"{section_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _pack_one(row: dict) -> PackedProvision:
    number = str(row.get("section_number") or "").strip()
    section_id = str(row.get("section_id") or "").strip()
    if not number:
        raise EvidencePackError(f"row has no section_number, so it has no identity: {row!r}")
    if not section_id:
        raise EvidencePackError(
            f"row for provision {number!r} has no section_id; the number alone is not an identity "
            f"(checker/legal_ref.py)")

    ref = LegalRef(
        instrument_type=row.get("instrument_type") or ACT,
        instrument_id=row.get("instrument_id") or DEFAULT_INSTRUMENT,
        number=number,
        title=str(row.get("title") or ""),
        source_id=section_id,
    )
    parse_key(ref.key())  # reject a malformed identity here, not in the prompt

    defects = _normalise_defects(row.get("defects"))
    codes = {d.code for d in defects}

    # The pack applies the known-defect registry itself instead of trusting the row. Retrieval may
    # legitimately not know about SD-002; the boundary must not depend on an upstream module
    # remembering to flag a provision that may not be served.
    if ref.instrument_id == DEFAULT_INSTRUMENT:
        if number in SD_002_SECTIONS and SD_002 not in codes:
            defects.append(DEFECTS[SD_002])
        if number in SD_002_OPEN_SECTIONS and SD_002_OPEN not in codes:
            defects.append(DEFECTS[SD_002_OPEN])

    record = _read_record(section_id)
    raw = record.get("content") if record else None
    if record is None:
        defects.append(DEFECTS[EP_RECORD_MISSING])
    elif not raw:
        defects.append(DEFECTS[EP_TEXT_EMPTY])

    reading, derivations = _reading_text(raw) if raw else (None, ())
    if raw and _EDITORIAL_RE.search(raw) and SD_001 not in {d.code for d in defects}:
        defects.append(DEFECTS[SD_001])

    sources: list[prov.SourceRecord] = []
    if record is not None:
        sources.append(_corpus_source(section_id, record.get("fetched_at"),
                                      record.get("source_url")))
        sources.append(prov.INDIACODE_PDF)

    blocking = [d for d in defects if d.blocks_answering]
    open_divergence = [d for d in defects if d.code == SD_002_OPEN]
    if record is None or not raw:
        state, notes = prov.UNRESOLVED, "No text is held for this provision."
    elif blocking:
        state = prov.UNRESOLVED
        notes = ("The two renderings of this provision from the same publisher disagree, so no "
                 "source here supports its text: " + "; ".join(d.code for d in blocking))
    elif open_divergence:
        state = prov.UNRESOLVED
        notes = ("Cross-render divergence for this provision is unexplained and uninspected, so "
                 "agreement between the renderings cannot be claimed.")
    else:
        state = prov.CORROBORATED
        notes = _CORROBORATION_NOTE

    claim = prov.Claim(
        claim_id=ref.key(),
        statement=f"The text carried in this pack for {ref.cite()} is corpus record "
                  f"{section_id} of the Companies Act 2013 as rendered by India Code.",
        state=state,
        sources=sources,
        notes=notes,
    )

    return PackedProvision(
        ref=ref,
        corpus_record_id=section_id,
        corpus_record_path=f"corpus/companies_act/{section_id}.json" if record else None,
        raw_text=raw,
        reading_text=reading,
        derivations=derivations,
        claim=claim,
        defects=tuple(defects),
        corpus_content_sha256=(record or {}).get("sha256"),
    )


def build_pack(rows: list[dict], *, query: str = "", mode: str = "MODEL",
               requested_sections: tuple[str, ...] = (),
               withheld_notices: tuple[str, ...] = (),
               point_in_time_request: date | str | None = None,
               instrument_id: str = DEFAULT_INSTRUMENT) -> EvidencePack:
    """Build the pack from retrieved rows.

    `requested_sections` lets the caller name what it asked for, so the pack can say a provision
    was sought and not found. A gap that nobody records is a gap the model will fill.

    `withheld_notices` carries already-formed sentences about material that EXISTS and is not
    admitted. They are kept separate from `requested_sections` because that argument formats bare
    section numbers into Act keys -- passing a prose notice through it produced the mangled
    "ACT:COMPANIES_ACT_2013:SRULE:...:R15". Two different kinds of gap, two different arguments.
    """
    provisions = tuple(_pack_one(r) for r in rows)

    fetched = tuple(sorted({(s.retrieved_on or "") for p in provisions for s in p.claim.sources
                            if s.source_id == "INDIACODE_SECTIONPAGE_JSON" and s.retrieved_on}))
    as_of = _build_as_of(fetched, point_in_time_request)

    missing: list[str] = []
    have = {p.ref.number for p in provisions}
    for n in requested_sections:
        n = str(n).strip()
        if n and n not in have:
            key = LegalRef(ACT, instrument_id, n).key()
            missing.append(f"{key} was requested and is NOT in this pack. Its text is unknown to "
                           f"you; say so rather than reconstructing it.")
    missing.extend(str(n) for n in withheld_notices if str(n).strip())

    for p in provisions:
        if not p.usable_for_answering:
            missing.append(f"{p.key} was located but its text may not be used: "
                           f"{p.unusable_reason()}")
    if as_of.point_in_time_requested:
        missing.append(f"The law as it stood on {as_of.point_in_time_requested}. This pack carries "
                       f"the current consolidation only and no verified point-in-time version "
                       f"exists in this system.")
    if not provisions:
        missing.append("No provision was retrieved at all. This pack is empty.")

    return EvidencePack(provisions=provisions, as_of=as_of, missing=tuple(missing),
                        query=query, mode=mode)


# --- self-test ------------------------------------------------------------------------------------

def _test() -> None:
    from checker.section_index import section_by_number
    ok = fail = 0

    def check(c: bool, label: str) -> None:
        nonlocal ok, fail
        if c:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    def row(number: str, defects: tuple = ()) -> dict:
        """A row shaped exactly as retrieval will hand it over."""
        rec = section_by_number(number)
        assert rec is not None, number
        return {"section_number": number, "section_id": rec["section_id"],
                "title": rec["title"], "defects": defects}

    # 1 — a pack that cannot support an answer says so.
    empty = build_pack([])
    check(empty.insufficient_evidence, "empty pack reports insufficient_evidence")
    check("INSUFFICIENT EVIDENCE" in empty.prompt_block(),
          "empty pack's prompt block orders an INSUFFICIENT EVIDENCE reply")
    check(any("empty" in m for m in empty.missing), "empty pack names its own emptiness in missing")

    clean = build_pack([row("173")])
    check(not clean.insufficient_evidence, "one clean provision is sufficient evidence")
    only_defective = build_pack([row("16"), row("124")])
    check(only_defective.insufficient_evidence,
          "pack of only defect-flagged provisions reports insufficient_evidence")
    s1 = build_pack([row("1")])
    check(s1.insufficient_evidence,
          "a lone SD-001 provision is readable but still leaves the pack insufficient")
    mixed = build_pack([row("16"), row("173")])
    check(not mixed.insufficient_evidence, "one clean provision beside a defective one suffices")

    # 2 — nothing outside provenance.SERVABLE is usable, and SD-002 stays visible.
    sd2 = build_pack([row(n) for n in SD_002_SECTIONS])
    check(len(sd2.provisions) == 4 and not sd2.usable,
          "all four SD-002 provisions are present and none is usable")
    check(all(p.claim.state not in prov.SERVABLE for p in sd2.provisions),
          "SD-002 provisions are held at a non-servable evidence state")
    check(all(any(d.code == SD_002 for d in p.defects) for p in sd2.provisions),
          "every SD-002 provision carries the SD-002 defect")
    d = sd2.to_dict()
    check(all(pd["raw_text"] for pd in d["provisions"]),
          "SD-002 text remains VISIBLE in the pack record rather than being suppressed")
    check(len(d["unusable_keys"]) == 4 and not d["usable_keys"],
          "to_dict separates unusable keys from usable ones")
    block = sd2.prompt_block()
    check("ACT:COMPANIES_ACT_2013:S16" in block and "FOUND BUT NOT USABLE" in block,
          "prompt block names the unusable provision instead of hiding it")
    fine = "punishable with fine"
    check(fine in " ".join(sd2.provisions[0].raw_text.split()).lower()
          and fine not in " ".join(block.split()).lower(),
          "the superseded wording is in the pack record but withheld from the prompt block")
    check(all(p.claim.state != prov.VERIFIED for p in mixed.provisions),
          "no provision in any pack claims VERIFIED")
    clean_p = clean.provisions[0]
    check(clean_p.claim.state == prov.CORROBORATED and clean_p.claim.servable(),
          "a clean provision is CORROBORATED — two renderings of one publisher, not verification")
    check("not independent verification" in clean_p.claim.notes,
          "and says in the record that this is not independent verification")

    # 3 — SD-001: flagged, cleaned only in a derived field, source not repaired.
    p1 = s1.provisions[0]
    check(any(dd.code == SD_001 for dd in p1.defects), "SD-001 flagged on s.1")
    check(EDITORIAL_INSTRUCTION in p1.raw_text,
          "the editorial instruction is preserved verbatim in raw_text")
    check(EDITORIAL_INSTRUCTION not in (p1.reading_text or ""),
          "the reading rendering drops it")
    der = [x for x in p1.derivations if x.transform == "REMOVE_EDITORIAL_INSTRUCTION"]
    check(len(der) == 1 and der[0].removed == EDITORIAL_INSTRUCTION and SD_001 in der[0].reason,
          "the transformation records what was removed and why")
    raw_disk = json.loads((CORPUS_DIR / "184.json").read_text())["content"]
    check(p1.raw_text == raw_disk, "raw_text is byte-identical to the corpus record on disk")
    check(EDITORIAL_INSTRUCTION in s1.to_dict()["provisions"][0]["raw_text"],
          "the raw text stays recoverable through to_dict()")
    check(p1.usable_for_answering, "SD-001 does not by itself make a provision unusable")
    marked = build_pack([row("173")]).provisions[0]
    check("<sup>" in (marked.reading_text or "") or "<sup>" not in (marked.raw_text or ""),
          "amendment markers survive the markup strip")

    # 4 — to_dict is JSON-safe and carries no bare provision number as an identifier.
    full = build_pack([row("173"), row("1"), row("16")], query="How often must the Board meet?",
                      requested_sections=("173", "175"))
    dumped = json.dumps(full.to_dict())
    check(len(dumped) > 1000, "to_dict() serialises to JSON")
    round_tripped = json.loads(dumped)
    check(round_tripped["schema"] == "placedon.evidence_pack/1", "JSON round-trips")

    bare = re.compile(r"^\d{1,3}[A-Z]{0,3}$")
    offenders: list[str] = []

    def scan(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if bare.match(str(k)):
                    offenders.append(f"{path}.{k} (bare number used as a key)")
                if k in ("section_number", "section", "number", "sectionno"):
                    offenders.append(f"{path}.{k} (bare-number identifier field)")
                scan(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{path}[{i}]")

    scan(round_tripped, "pack")
    check(not offenders, f"no bare section numbers as identifiers in to_dict() ({offenders[:3]})")
    check(all(parse_key(k).number for k in round_tripped["provision_keys"]),
          "every provision is identified by a parseable qualified key")
    check(round_tripped["provisions"][0]["ref"] == "ACT:COMPANIES_ACT_2013:S173",
          "the qualified key is the provision's identity in the output")

    # 5 — the prompt block forbids going beyond the pack, without softening.
    pb = full.prompt_block()
    for phrase in ("the ONLY law available to you", "Cite no provision that is not listed",
                   "Do not use anything you know about Indian law from outside this pack",
                   "INSUFFICIENT EVIDENCE"):
        check(phrase in pb, f"prompt block states: {phrase!r}")
    hedges = ("if possible", "try to", "generally", "where practical", "you may assume",
              "best effort", "feel free", "as needed", "use your judgment")
    found = [h for h in hedges if h in pb.lower()]
    check(not found, f"prompt block contains no hedging a model could read as permission ({found})")
    check("ACT:COMPANIES_ACT_2013:S175 was requested and is NOT in this pack" in pb,
          "prompt block names a requested provision that was not retrieved")
    check("NOT IN THIS PACK" in pb, "prompt block has an explicit missing section")

    # as_of — honest about a version we cannot verify.
    a = full.as_of
    check(a.point_in_time_verified is False, "as_of never claims a verified point-in-time version")
    check(a.basis == CURRENT_CONSOLIDATION, "as_of records the current consolidation as its basis")
    check(a.evidence_state == prov.UNRESOLVED and a.evidence_state not in prov.SERVABLE,
          "the version question itself carries a non-servable evidence state")
    check("UNVERIFIED" in a.statement and "NOT a point-in-time version" in a.statement,
          "as_of says in words that no point-in-time version is claimed")
    check(bool(a.corpus_fetched), f"as_of records the ingestion date(s): {a.corpus_fetched}")
    dated = build_pack([row("173")], point_in_time_request=date(2018, 1, 1))
    check(dated.as_of.point_in_time_requested == "2018-01-01",
          "a point-in-time request is recorded, not silently ignored")
    check(any("2018-01-01" in m for m in dated.missing),
          "and the requested date is listed among what the pack does not have")
    check("CANNOT supply one" in dated.prompt_block(),
          "the prompt block refuses the point-in-time request outright")

    # boundary behaviour
    try:
        build_pack([{"section_number": "173", "title": "Meetings of Board", "defects": ()}])
        check(False, "a row without section_id must raise")
    except EvidencePackError as e:
        check("not an identity" in str(e), "a row with a number but no record id is rejected")
    try:
        build_pack([{"section_id": "49099", "title": "x", "defects": ()}])
        check(False, "a row without section_number must raise")
    except EvidencePackError:
        check(True, "a row with no provision number is rejected")

    ghost = build_pack([{"section_number": "999", "section_id": "no_such_record",
                         "title": "A provision with no corpus file", "defects": ()}])
    gp = ghost.provisions[0]
    check(any(dd.code == EP_RECORD_MISSING for dd in gp.defects) and not gp.usable_for_answering,
          "a provision with no corpus record is flagged and unusable, not dropped")
    check(ghost.insufficient_evidence, "a pack of only unloadable provisions is insufficient")

    kept = build_pack([row("173", defects=("SOME-UPSTREAM-CODE",))]).provisions[0]
    check(any(dd.code == "SOME-UPSTREAM-CODE" for dd in kept.defects),
          "an unrecognised upstream defect code is carried through, never dropped")
    open_div = build_pack([{"section_number": "74", "section_id": "49099", "title": "x",
                            "defects": ()}]).provisions[0]
    check(any(dd.code == SD_002_OPEN for dd in open_div.defects) and not open_div.usable_for_answering,
          "an uninspected cross-render divergence is flagged and withheld")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
