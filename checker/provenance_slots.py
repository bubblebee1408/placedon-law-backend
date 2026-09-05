"""
Typed provenance for every value that reaches a document.

A draft that reads well is not the same as a draft that is supported, and the difference is
invisible on the page. "The AGM must be held by 30 September 2026" looks identical whether the date
was computed from a statutory interval, typed by the user, or invented by a model. This module makes
that difference structural: every value carries where it came from, and the document cannot be
assembled from values that do not.

    SOURCE_QUOTE      text lifted verbatim from an admitted provision
    USER_FACT         supplied by the person; true only if they are right
    DERIVED_FACT      computed from user facts and a quoted interval, with its working
    TEMPLATE_TEXT     fixed drafting language a human approved in advance
    MODEL_SUGGESTION  produced by a language model -- NEVER legally supported on its own
    UNKNOWN           a slot the document needs and nobody has filled

The rule the module enforces: **a MODEL_SUGGESTION or UNKNOWN slot blocks approval.** Not a warning
in a panel a reviewer may scroll past -- `ready_for_approval()` is False and `approve()` raises. A
model may draft prose; it may not be the reason a legal statement appears in a document a company
files.

`SOURCE_QUOTE` is verified, not asserted: the text must actually occur in the cited provision, or
construction fails. A quote nobody checked is a paraphrase with quotation marks around it.

Run: python3 checker/provenance_slots.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Slot", "SlotError", "SLOT_TYPES", "BLOCKING_TYPES", "SOURCE_QUOTE", "USER_FACT",
           "DERIVED_FACT", "TEMPLATE_TEXT", "MODEL_SUGGESTION", "UNKNOWN",
           "ready_for_approval", "blocking_slots", "provenance_panel"]

SOURCE_QUOTE = "SOURCE_QUOTE"
USER_FACT = "USER_FACT"
DERIVED_FACT = "DERIVED_FACT"
TEMPLATE_TEXT = "TEMPLATE_TEXT"
MODEL_SUGGESTION = "MODEL_SUGGESTION"
UNKNOWN = "UNKNOWN"

SLOT_TYPES = (SOURCE_QUOTE, USER_FACT, DERIVED_FACT, TEMPLATE_TEXT, MODEL_SUGGESTION, UNKNOWN)

# Types that stop a document being approved. MODEL_SUGGESTION is here because a fluent sentence is
# not evidence of anything, and UNKNOWN because a blank in a legal document is not a small problem.
BLOCKING_TYPES = (MODEL_SUGGESTION, UNKNOWN)

# Types that must say where they came from. A quote with no citation cannot be checked, and a
# derived value with no working cannot be re-computed by the person relying on it.
NEEDS_SOURCE = (SOURCE_QUOTE,)
NEEDS_WORKING = (DERIVED_FACT,)


class SlotError(ValueError):
    """A slot that cannot be audited. Never downgraded to a warning."""


@dataclass(frozen=True)
class Slot:
    name: str
    value: str
    slot_type: str
    source: str = ""                       # citation, for SOURCE_QUOTE and DERIVED_FACT
    working: str = ""                      # the derivation, for DERIVED_FACT
    inputs: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def __post_init__(self) -> None:
        if self.slot_type not in SLOT_TYPES:
            raise SlotError(f"{self.name}: {self.slot_type!r} is not a slot type; one of {SLOT_TYPES}")
        if self.slot_type != UNKNOWN and not str(self.value).strip():
            raise SlotError(f"{self.name}: a {self.slot_type} slot with no value is UNKNOWN, "
                            "and should say so rather than looking filled")
        if self.slot_type in NEEDS_SOURCE and not self.source.strip():
            raise SlotError(f"{self.name}: a SOURCE_QUOTE must cite the provision it came from. "
                            "A quote nobody can check is a paraphrase in quotation marks.")
        if self.slot_type in NEEDS_WORKING and not self.working.strip():
            raise SlotError(f"{self.name}: a DERIVED_FACT must carry its working. A number whose "
                            "derivation is not shown cannot be re-checked by the person relying "
                            "on it.")

    @property
    def blocks_approval(self) -> bool:
        return self.slot_type in BLOCKING_TYPES

    def verify_quote(self, provision_text: str) -> None:
        """For SOURCE_QUOTE: the text must actually occur in the provision. Raises if it does not."""
        if self.slot_type != SOURCE_QUOTE:
            return
        flat = " ".join(provision_text.split()).lower()
        if " ".join(str(self.value).split()).lower() not in flat:
            raise SlotError(
                f"{self.name}: the quoted text is NOT in {self.source}. Either the provision was "
                "amended, the wrong provision was cited, or the text was paraphrased -- all three "
                "are reasons to stop, not to soften the quote.")

    def to_dict(self) -> dict:
        return dict(name=self.name, value=self.value, type=self.slot_type, source=self.source,
                    working=self.working, inputs=list(self.inputs), note=self.note,
                    blocks_approval=self.blocks_approval)


def blocking_slots(slots: tuple[Slot, ...]) -> tuple[Slot, ...]:
    return tuple(s for s in slots if s.blocks_approval)


def ready_for_approval(slots: tuple[Slot, ...]) -> bool:
    """Whether a human may be asked to approve this. False while anything is unsupported."""
    return not blocking_slots(slots)


def provenance_panel(slots: tuple[Slot, ...]) -> str:
    """The panel a reviewer reads. Shown even when the exported document is clean."""
    width = max((len(s.name) for s in slots), default=4)
    out = ["PROVENANCE", ""]
    for s in slots:
        mark = "  <= BLOCKS APPROVAL" if s.blocks_approval else ""
        out.append(f"  {s.name:<{width}}  {s.slot_type:<16} {str(s.value)[:46]}{mark}")
        if s.source:
            out.append(f"  {'':<{width}}  {'':<16} source: {s.source}")
        if s.working:
            for line in s.working.splitlines():
                out.append(f"  {'':<{width}}  {'':<16} {line}")
        if s.note:
            out.append(f"  {'':<{width}}  {'':<16} note: {s.note}")
    blocked = blocking_slots(slots)
    out += ["", f"APPROVAL: {'available' if not blocked else 'BLOCKED'}"]
    if blocked:
        out.append("  blocked by: " + ", ".join(f"{s.name} ({s.slot_type})" for s in blocked))
    return "\n".join(out)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    q = Slot("interval", "six months", SOURCE_QUOTE, source="Companies Act 2013, s.96(1)")
    u = Slot("fy_end", "31 March 2026", USER_FACT)
    d = Slot("deadline", "30 September 2026", DERIVED_FACT, source="s.96(1)",
             working="2026-03-31 + six months = 2026-09-30")
    t = Slot("heading", "NOTICE OF ANNUAL GENERAL MEETING", TEMPLATE_TEXT)
    check(all(not s.blocks_approval for s in (q, u, d, t)),
          "quote, user fact, derived fact and template do not block approval")
    check(ready_for_approval((q, u, d, t)), "a fully supported draft is ready for approval")

    m = Slot("blurb", "The company is in good standing.", MODEL_SUGGESTION)
    check(m.blocks_approval, "a MODEL_SUGGESTION blocks approval")
    check(not ready_for_approval((q, u, d, t, m)),
          "...and one of them blocks the whole document")
    check(blocking_slots((q, u, d, t, m)) == (m,), "...and is named as the blocker")

    unk = Slot("registered_office", "", UNKNOWN)
    check(unk.blocks_approval, "an UNKNOWN slot blocks approval")
    check("BLOCKS APPROVAL" in provenance_panel((q, unk)),
          "...and the panel says so where a reviewer will see it")

    # A quote must be checkable.
    try:
        Slot("interval", "six months", SOURCE_QUOTE)
        check(False, "an uncited SOURCE_QUOTE must raise")
    except SlotError as e:
        check("must cite the provision" in str(e), "an uncited SOURCE_QUOTE is refused")
    try:
        Slot("deadline", "30 September 2026", DERIVED_FACT, source="s.96")
        check(False, "a DERIVED_FACT without working must raise")
    except SlotError as e:
        check("carry its working" in str(e), "a DERIVED_FACT without working is refused")
    try:
        Slot("x", "  ", USER_FACT)
        check(False, "an empty non-UNKNOWN slot must raise")
    except SlotError:
        check(True, "an empty slot must declare itself UNKNOWN rather than looking filled")

    # verify_quote against real provision text.
    from checker.retrieve import MODE_MODEL, retrieve
    pack, _ = retrieve("s.96", mode=MODE_MODEL)
    src = pack.usable[0].reading_text or pack.usable[0].raw_text
    q.verify_quote(src)
    check(True, "a genuine quote from s.96 verifies against the provision")
    bogus = Slot("interval", "ninety-nine months", SOURCE_QUOTE, source="s.96(1)")
    try:
        bogus.verify_quote(src)
        check(False, "a quote absent from the provision must raise")
    except SlotError as e:
        check("NOT in" in str(e), "a quote absent from the provision is refused, not softened")

    check(Slot("x", "y", UNKNOWN).slot_type == UNKNOWN, "UNKNOWN may carry an empty value")
    try:
        Slot("x", "y", "INVENTED")
        check(False, "an invented slot type must raise")
    except SlotError:
        check(True, "an invented slot type is rejected")

    panel = provenance_panel((q, u, d, t))
    check("source: Companies Act 2013, s.96(1)" in panel, "the panel shows the citation")
    check("2026-03-31 + six months" in panel, "the panel shows the derivation")
    check("APPROVAL: available" in panel, "...and states approval is available")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
