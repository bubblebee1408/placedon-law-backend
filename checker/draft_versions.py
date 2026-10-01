#!/usr/bin/env python3
"""Every save is a version, and any two versions diff exactly.

H3 of `.claude/loops/DECISION_harvey_parity.md`. The approval rule it asks for already
exists and is not re-implemented here: `checker/provenance_slots.py` types every value and
makes `MODEL_SUGGESTION` and `UNKNOWN` block approval, and `checker/drafting.py` assembles
one draft from those slots. **This module adds the history**: versions, the diff between
any two, and the exports.

## Why this is not `checker/drafts.py`, which H3 names

`checker/drafting.py` already exists, and `drafts.py` beside it is a trap: two files one
character apart, one assembling a draft and one storing its history, and a reader reaching
for the wrong one every time. The same confusion H4 created with `review_grid` /
`review_table`, which is now a paragraph in `docs/START_HERE.md` §5. This is
`draft_versions.py` because that is what it holds.

## A version is immutable, and that is the whole feature

`save()` appends. It never edits a version in place, because the point of a version is that
someone can go back to exactly what was approved — or exactly what was NOT approved and
why. A "current draft" that is mutated in place has no history, only a present tense.

## The diff that matters is not the text diff

A unified diff over the body shows which words changed. It does **not** show that a
sentence stopped being a `SOURCE_QUOTE` and became a `MODEL_SUGGESTION` — the words can be
identical and the support gone, which is the one change a lawyer must see. So `diff()`
returns both, and names `newly_blocking` separately: slots that now block approval and did
not before.

The reverse matters too. A slot that was `MODEL_SUGGESTION` and is now a verified
`SOURCE_QUOTE` is the revision working, and `newly_supported` says so.

## No new dependency for .docx, and that is the reason

A `.docx` is a ZIP of XML. `zipfile` and `xml` are in the standard library, so
`to_docx()` writes the three parts the format requires and nothing else. A writer was
considered and refused:

- `python-docx` is neither installed nor declared here, and README's claim that the SERVED
  path has no dependency outside the standard library would become false the day a draft
  export shipped through it. `checker/pdf_pages.py` holds that boundary for reading, with
  its own test; this keeps it for writing.
- A document WRITER is a format emitter, not a parser. The failure mode of a hand-written
  one is "Word will not open it", which a test can check by reading the archive back. The
  failure mode of a hand-written PDF *reader* is silently wrong text, which is why
  `pdf_pages` uses a library and this does not.

**The ceiling, stated:** plain paragraphs, no styling, no tables, no tracked changes. The
day a lawyer needs real formatting, `python-docx` is the right answer and gets declared in
`requirements.txt` with that as the reason.

Run: PYTHONPATH=. python3 checker/draft_versions.py --test
"""
from __future__ import annotations

import difflib
import io
import re
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime

from checker.provenance_slots import (BLOCKING_TYPES, MODEL_SUGGESTION, Slot,
                                      blocking_slots, provenance_panel,
                                      ready_for_approval)

__all__ = ["Version", "VersionError", "History", "save", "diff", "to_docx",
           "to_text", "docx_text"]


class VersionError(ValueError):
    """A version or a diff that cannot be described. Never a warning."""


@dataclass(frozen=True)
class Version:
    draft_id: str
    version: int
    title: str
    body: str
    slots: tuple = ()
    citations: tuple = ()
    created_at: str = ""
    approved_by: str = ""
    approved_at: str = ""

    def __post_init__(self) -> None:
        if self.version < 1:
            raise VersionError(f"a version is 1-based, got {self.version}")
        if not self.draft_id.strip():
            raise VersionError("a version belongs to a draft")
        if not self.title.strip():
            raise VersionError("a draft version needs a title")
        if not self.created_at.strip():
            raise VersionError(
                "a version with no timestamp cannot be ordered against another, and the "
                "whole point of a version is which one came first")
        try:
            when = datetime.fromisoformat(self.created_at)
        except ValueError:
            raise VersionError(f"created_at {self.created_at!r} is not ISO 8601") from None
        if when.tzinfo is None:
            raise VersionError(
                f"created_at {self.created_at!r} has no timezone. Two drafts saved either "
                f"side of midnight IST would order wrongly read as UTC")
        if bool(self.approved_by) != bool(self.approved_at):
            raise VersionError("an approval carries both a reviewer and a time, or neither")
        if self.approved_by and blocking_slots(tuple(self.slots)):
            raise VersionError(
                f"version {self.version} is recorded as approved by "
                f"{self.approved_by!r} while {len(blocking_slots(tuple(self.slots)))} "
                f"slot(s) still block approval. That combination cannot exist: it is the "
                f"record of a gate that did not hold")

    @property
    def ready(self) -> bool:
        return ready_for_approval(tuple(self.slots))

    def blockers(self) -> tuple:
        return blocking_slots(tuple(self.slots))

    @property
    def approved(self) -> bool:
        return bool(self.approved_by)

    def approve(self, reviewer: str, at: str) -> "Version":
        """A NEW version carrying the approval. Raises while anything is unsupported."""
        if not reviewer.strip():
            raise VersionError("approval requires a named reviewer -- an unattributed "
                               "approval is not an approval")
        if not self.ready:
            names = ", ".join(f"{s.name} ({s.slot_type})" for s in self.blockers())
            raise VersionError(
                f"cannot approve: {len(self.blockers())} slot(s) are unsupported -- "
                f"{names}. Accept or source them first, or the document states things "
                f"nobody stands behind.")
        return replace(self, approved_by=reviewer, approved_at=at)

    def to_dict(self) -> dict:
        return {"draft_id": self.draft_id, "version": self.version, "title": self.title,
                "body": self.body, "created_at": self.created_at,
                "slots": [s.to_dict() for s in self.slots],
                "citations": list(self.citations),
                "ready": self.ready, "approved": self.approved,
                "approved_by": self.approved_by or None,
                "approved_at": self.approved_at or None,
                "blocking": [s.name for s in self.blockers()]}


@dataclass(frozen=True)
class History:
    draft_id: str
    versions: tuple = ()

    def __post_init__(self) -> None:
        nums = [v.version for v in self.versions]
        if nums != list(range(1, len(nums) + 1)):
            raise VersionError(
                f"versions must be 1..N with no gaps, got {nums}. A gap means a save was "
                f"lost, and a history with a hole in it cannot answer 'what did we send'")
        if any(v.draft_id != self.draft_id for v in self.versions):
            raise VersionError("every version in a history belongs to the same draft")

    @property
    def latest(self):
        return self.versions[-1] if self.versions else None

    def at(self, version: int) -> Version:
        for v in self.versions:
            if v.version == version:
                return v
        raise VersionError(f"this draft has no version {version} "
                           f"(it has {len(self.versions)})")


def save(history: History, *, title: str, body: str, slots=(), citations=(),
         created_at: str) -> History:
    """Append a new version. Never edits an existing one."""
    n = len(history.versions) + 1
    v = Version(history.draft_id, n, title, body, tuple(slots), tuple(citations),
                created_at)
    return History(history.draft_id, history.versions + (v,))


# ── the diff ─────────────────────────────────────────────────────────────────

def _slot_map(v: Version) -> dict:
    return {s.name: s for s in v.slots}


def diff(a: Version, b: Version) -> dict:
    """An exact diff between two versions: the text, and the provenance.

    `text` is a unified diff, so it can be rendered or applied. `slots` is per name, and it
    is the half that catches what the text cannot: identical words whose support changed.
    """
    if a.draft_id != b.draft_id:
        raise VersionError(
            f"cannot diff across drafts ({a.draft_id[:8]} vs {b.draft_id[:8]}) -- the "
            f"result would read as a revision of something that was never revised")
    text = list(difflib.unified_diff(
        a.body.splitlines(), b.body.splitlines(),
        fromfile=f"v{a.version}", tofile=f"v{b.version}", lineterm=""))
    am, bm = _slot_map(a), _slot_map(b)
    added = sorted(set(bm) - set(am))
    removed = sorted(set(am) - set(bm))
    retyped, revalued = [], []
    for name in sorted(set(am) & set(bm)):
        if am[name].slot_type != bm[name].slot_type:
            retyped.append({"name": name, "from": am[name].slot_type,
                            "to": bm[name].slot_type})
        elif am[name].value != bm[name].value:
            revalued.append({"name": name, "from": am[name].value,
                             "to": bm[name].value})
    # The two that matter legally, named rather than left for a reader to derive.
    newly_blocking = sorted(n for n in set(bm)
                            if bm[n].blocks_approval
                            and not (am.get(n) and am[n].blocks_approval))
    newly_supported = sorted(n for n in set(am) & set(bm)
                             if am[n].blocks_approval and not bm[n].blocks_approval)
    return {"draft_id": a.draft_id, "from_version": a.version, "to_version": b.version,
            "text": text, "text_changed": bool(text),
            "slots": {"added": added, "removed": removed, "retyped": retyped,
                      "revalued": revalued},
            "newly_blocking": newly_blocking, "newly_supported": newly_supported,
            "ready_changed": a.ready != b.ready,
            "note": ("`newly_blocking` is the change a text diff cannot show: a sentence "
                     "whose words are identical and whose support is gone. A slot retyped "
                     "to MODEL_SUGGESTION reads the same on the page and may no longer be "
                     "relied on.")}


# ── exports ──────────────────────────────────────────────────────────────────

def to_text(v: Version) -> str:
    """The document as a reader sees it, with the provenance panel beneath."""
    out = [v.title, "=" * len(v.title), "", v.body, ""]
    if v.citations:
        out += ["LEGAL BASIS", *[f"  - {c}" for c in v.citations], ""]
    out.append(provenance_panel(tuple(v.slots)))
    if not v.ready:
        out += ["", f"NOT APPROVABLE: {len(v.blockers())} slot(s) are unsupported -- "
                    + ", ".join(f"{s.name} ({s.slot_type})" for s in v.blockers())]
    return "\n".join(out)


_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _paragraph(text: str) -> str:
    # xml:space="preserve" so an indented or blank line survives. Without it Word
    # collapses leading spaces, and a numbered clause loses its indentation.
    return (f'<w:p><w:r><w:t xml:space="preserve">{_xml_escape(text)}</w:t></w:r></w:p>')


def to_docx(v: Version) -> bytes:
    """The version as a .docx, written with the standard library only.

    Plain paragraphs. See the module docstring for why there is no `python-docx` here and
    what the ceiling is.
    """
    lines = to_text(v).split("\n")
    body = "".join(_paragraph(line) for line in lines)
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{_W}"><w:body>{body}'
                f'<w:sectPr/></w:body></w:document>')
    buf = io.BytesIO()
    # Deterministic: a fixed date_time on every entry, so the same version exports to the
    # same bytes. An export whose sha256 changes every call cannot be compared or cached.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (("[Content_Types].xml", _CT), ("_rels/.rels", _RELS),
                           ("word/document.xml", document)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue()


def docx_text(data: bytes) -> str:
    """Read a .docx back and return its text. Used by the tests, and by nothing else.

    A writer with no reader is a writer nobody has checked, and "Word will not open it" is
    not a failure a unit test can see directly -- but a malformed archive or a lost
    paragraph is.
    """
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(xml)
    return "\n".join(t.text or "" for t in root.iter(f"{{{_W}}}t"))


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("draft_versions")
    from checker.provenance_slots import (DERIVED_FACT, SOURCE_QUOTE, TEMPLATE_TEXT,
                                          UNKNOWN, USER_FACT)
    T0, T1, T2 = ("2026-10-01T10:00:00+05:30", "2026-10-01T11:00:00+05:30",
                  "2026-10-01T12:00:00+05:30")
    PROV = ("Every company shall in each year hold a general meeting as its annual "
            "general meeting.")
    QUOTE = Slot("duty", "hold a general meeting as its annual general meeting",
                 SOURCE_QUOTE, source="Companies Act 2013, s.96(1)")
    NAME = Slot("company", "Acme Private Limited", USER_FACT)
    GUESS = Slot("venue", "the registered office, probably", MODEL_SUGGESTION)
    BLANK = Slot("meeting_time", "", UNKNOWN)

    # ── every save is a version, and a version is immutable ─────────────────
    h = History("d1")
    check(h.latest is None, "a new history has no latest version")
    h = save(h, title="AGM Notice", body="Notice is hereby given.", created_at=T0,
             slots=(NAME, QUOTE))
    h = save(h, title="AGM Notice", body="Notice is hereby given to the members.",
             created_at=T1, slots=(NAME, QUOTE))
    check([v.version for v in h.versions] == [1, 2], "each save appends a version")
    check(h.at(1).body == "Notice is hereby given.",
          "...and version 1 is UNCHANGED by the second save -- a version someone can go "
          "back to is the whole feature")
    check(h.latest.version == 2, "latest is the newest")
    try:
        h.at(9)
        check(False, "an absent version raises")
    except VersionError as e:
        check("no version 9" in str(e), "an absent version raises, naming what exists")
    try:
        History("d1", (h.at(2),))
        check(False, "a history starting at version 2 is refused")
    except VersionError as e:
        check("no gaps" in str(e),
              "a history with a GAP is refused: a hole means a save was lost, and it "
              "cannot answer 'what did we send'")
    try:
        History("d1", (h.at(1), replace(h.at(2), draft_id="d2")))
        check(False, "a version from another draft is refused")
    except VersionError:
        check(True, "a version belonging to another draft is refused")

    # ── the version record refuses to be built wrong ────────────────────────
    for kw, why in [
        (dict(draft_id="d", version=0, title="t", body="b", created_at=T0), "version 0"),
        (dict(draft_id="", version=1, title="t", body="b", created_at=T0), "no draft id"),
        (dict(draft_id="d", version=1, title="", body="b", created_at=T0), "no title"),
        (dict(draft_id="d", version=1, title="t", body="b", created_at=""), "no timestamp"),
        (dict(draft_id="d", version=1, title="t", body="b",
              created_at="2026-10-01T10:00:00"), "a timestamp with no timezone"),
        (dict(draft_id="d", version=1, title="t", body="b", created_at=T0,
              approved_by="A"), "an approval with no time"),
    ]:
        try:
            Version(**kw)
            check(False, f"a version with {why} is refused")
        except VersionError:
            check(True, f"a version with {why} is refused")

    # ── approval is BLOCKED while anything is unsupported ───────────────────
    blocked = save(History("d2"), title="AGM Notice", body="Notice.", created_at=T0,
                   slots=(NAME, QUOTE, GUESS)).latest
    check(not blocked.ready and [s.name for s in blocked.blockers()] == ["venue"],
          f"a MODEL_SUGGESTION blocks approval ({[s.name for s in blocked.blockers()]})")
    try:
        blocked.approve("A. Reviewer", T1)
        check(False, "approving a blocked version raises")
    except VersionError as e:
        check("cannot approve" in str(e) and "venue (MODEL_SUGGESTION)" in str(e),
              f"approving while a suggestion is unaccepted RAISES and names it "
              f"({e!s:.56})")
    unknown = save(History("d3"), title="T", body="b", created_at=T0,
                   slots=(NAME, BLANK)).latest
    check(not unknown.ready, "an UNKNOWN slot blocks approval too -- a blank in a legal "
                             "document is not a small problem")
    good = save(History("d4"), title="T", body="b", created_at=T0,
                slots=(NAME, QUOTE)).latest
    appr = good.approve("A. Reviewer", T1)
    check(appr.approved and appr.approved_by == "A. Reviewer",
          "a fully supported version can be approved")
    check(appr.version == good.version and good.approved is False,
          "...and approval returns a NEW version record; the unapproved one is untouched")
    try:
        good.approve("", T1)
        check(False, "an unattributed approval is refused")
    except VersionError as e:
        check("unattributed" in str(e), "an unattributed approval is refused")
    try:
        Version("d", 1, "t", "b", (NAME, GUESS), (), T0, "A. Reviewer", T1)
        check(False, "an approved-yet-blocked version cannot be constructed")
    except VersionError as e:
        check("gate that did not hold" in str(e),
              "a version recorded as APPROVED while still blocked cannot exist at all -- "
              "that combination is the record of a gate that did not hold")

    # ── the diff: text, and the provenance the text cannot show ─────────────
    d12 = diff(h.at(1), h.at(2))
    check(d12["text_changed"] and any(l.startswith("+") for l in d12["text"]),
          "a changed body produces a unified diff")
    check(d12["slots"] == {"added": [], "removed": [], "retyped": [], "revalued": []},
          f"...and no slot changed ({d12['slots']})")

    # The case the whole design is for: identical words, support removed.
    v1 = save(History("d5"), title="T", body="The AGM must be held by 30 September.",
              created_at=T0, slots=(NAME, QUOTE)).latest
    swapped = Slot(QUOTE.name, QUOTE.value, MODEL_SUGGESTION)
    v2 = save(History("d5"), title="T", body="The AGM must be held by 30 September.",
              created_at=T1, slots=(NAME, swapped)).latest
    dd = diff(v1, replace(v2, version=2))
    check(not dd["text_changed"],
          "two versions with IDENTICAL words produce no text diff")
    check(dd["slots"]["retyped"] == [{"name": "duty", "from": SOURCE_QUOTE,
                                      "to": MODEL_SUGGESTION}],
          f"...while the slot diff shows the retype ({dd['slots']['retyped']})")
    check(dd["newly_blocking"] == ["duty"],
          f"**and `newly_blocking` names it**: the words are the same and the support is "
          f"gone, which is the one change a text diff cannot show ({dd['newly_blocking']})")
    check(dd["ready_changed"], "...and the version stopped being approvable")

    # The reverse: a suggestion that became a verified quote.
    back = diff(replace(v2, version=1), replace(v1, version=2))
    check(back["newly_supported"] == ["duty"] and not back["newly_blocking"],
          f"a suggestion replaced by a verified quote is `newly_supported` -- the revision "
          f"working ({back['newly_supported']})")

    v3 = save(History("d5"), title="T", body="b", created_at=T2,
              slots=(NAME, QUOTE, GUESS)).latest
    d13 = diff(v1, replace(v3, version=3))
    check(d13["slots"]["added"] == ["venue"] and d13["newly_blocking"] == ["venue"],
          f"an ADDED suggestion is both added and newly blocking ({d13['newly_blocking']})")
    renamed = Slot(NAME.name, "Acme Limited", USER_FACT)
    d_rev = diff(v1, replace(save(History("d5"), title="T", body="b", created_at=T2,
                                  slots=(renamed, QUOTE)).latest, version=2))
    check(d_rev["slots"]["revalued"] == [{"name": "company",
                                          "from": "Acme Private Limited",
                                          "to": "Acme Limited"}],
          f"a changed VALUE at the same type is revalued ({d_rev['slots']['revalued']})")
    try:
        diff(v1, h.at(1))
        check(False, "diffing across drafts raises")
    except VersionError as e:
        check("across drafts" in str(e),
              "diffing two different drafts RAISES -- the result would read as a revision "
              "of something that was never revised")
    check("cannot show" in d12["note"], "the diff carries the note about what it is for")

    # ── a SOURCE_QUOTE is verified against the provision, not asserted ──────
    QUOTE.verify_quote(PROV)
    check(True, "a quote that IS in the provision verifies")
    try:
        Slot("duty", "hold a meeting within ninety days", SOURCE_QUOTE,
             source="s.96(1)").verify_quote(PROV)
        check(False, "a quote not in the provision raises")
    except Exception as e:
        check("NOT in" in str(e),
              "a quote that is NOT in the cited provision raises -- amended, wrong "
              "provision, or paraphrased, and all three are reasons to stop")

    # ── exports ─────────────────────────────────────────────────────────────
    txt = to_text(blocked)
    check("NOT APPROVABLE" in txt and "venue (MODEL_SUGGESTION)" in txt,
          "the text export says it is not approvable and names the slot")
    check("Acme Private Limited" in txt, "...and renders the document")
    data = to_docx(blocked)
    check(data[:2] == b"PK", "a .docx is a ZIP (PK magic bytes)")
    import zipfile as _z
    parts = sorted(_z.ZipFile(io.BytesIO(data)).namelist())
    check(parts == ["[Content_Types].xml", "_rels/.rels", "word/document.xml"],
          f"...with exactly the three parts the format requires ({parts})")
    back_text = docx_text(data)
    check("Notice." in back_text and "venue" in back_text,
          "the document text round-trips when the archive is read back")
    check("NOT APPROVABLE" in back_text,
          "...including the not-approvable warning: an exported blocked draft says so on "
          "its own face, because the file travels away from this system")
    check(to_docx(blocked) == data,
          "the export is DETERMINISTIC -- the same version gives the same bytes, so it "
          "can be hashed, compared and cached")
    evil = save(History("d6"), title="T & <Co>", body='A clause with <tags> & "quotes".',
                created_at=T0, slots=(NAME, QUOTE)).latest
    ev = docx_text(to_docx(evil))
    check("<tags>" in ev and "&" in ev and '"quotes"' in ev,
          "XML special characters survive escaping and come back verbatim")
    import xml.etree.ElementTree as _ET
    with _z.ZipFile(io.BytesIO(to_docx(evil))) as z:
        _ET.fromstring(z.read("word/document.xml"))
    check(True, "...and the document XML still parses, so the archive is well-formed")
    indented = save(History("d7"), title="T", body="  (1) an indented clause",
                    created_at=T0, slots=(NAME, QUOTE)).latest
    check("  (1) an indented clause" in docx_text(to_docx(indented)),
          "leading spaces survive: without xml:space=preserve a numbered clause loses its "
          "indentation")

    # ── no new dependency ───────────────────────────────────────────────────
    import importlib.util as _u
    check(_u.find_spec("docx") is None,
          "python-docx is NOT installed, and the export does not need it -- see the module "
          "docstring for why a format WRITER is safe to hand-write where a PDF reader is "
          "not")
    # Parsed, not grepped: the first version searched this file's TEXT for "import docx"
    # and matched its own assertion. Same self-referential trap as the "there is no
    # --lower flag" check that had to scan for the flag it said did not exist.
    import ast as _ast
    mods = set()
    for node in _ast.walk(_ast.parse(
            (__import__("pathlib").Path(__file__)).read_text(encoding="utf-8"))):
        if isinstance(node, _ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, _ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    check("docx" not in mods,
          f"...and this module IMPORTS no document library -- read from its import "
          f"statements, not its text ({sorted(m for m in mods if m not in __builtins__.__dict__)[:8]})")
    check({"zipfile", "difflib", "io"} <= mods,
          "...it uses zipfile and difflib from the standard library instead")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
