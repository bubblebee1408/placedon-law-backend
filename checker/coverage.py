"""What was checked, what was not, and why — attached to every answer.

Two personas in different registers converged on the same defect
(`objection_sim` O-02, O-03), and neither was told about the other:

    the practising CS   "Kavitha will run your panel, it will say nothing, and
                        she will tell me 'ma'am, checked'. She will not know the
                        difference between 'the law has not changed' and 'we do
                        not hold that Rule'."

    the in-house GC     "My paralegal sees thirteen green ticks, assumes the
                        document is clean, and stops thinking. Partial coverage
                        that LOOKS like full coverage is more dangerous than no
                        tool at all."

One fears the silence, the other the ticks. The defect underneath is the same:
**an answer that does not carry its own scope.** The engine has always known the
difference internally — `staleness` has six acquisition states and refusals name
their missing instrument — but a reader sees an output, not a data structure, and
a quiet output reads as a clean one.

## The two rules

1. **A `Report` cannot be constructed without its unchecked list.** Not a flag, not
   a default, not an optional field: `unchecked` is a required argument and the
   constructor refuses a claim of full coverage that does not prove it. A caller
   who has not thought about scope cannot accidentally omit it.

2. **Nothing may say the document is compliant.** `mca_strip` already forbids a
   green all-clear headline; this generalises it. `sentence()` states what was
   examined and against what, never a verdict on the document — and
   `FORBIDDEN` blocks the words at the boundary rather than in review.

## Why a count is not a coverage report

"13 of 15" is the number the GC objected to. It reads as 87%, which reads as
nearly-done. What he asked for was the **names** of the two, every time, so that
a reader who is not a lawyer cannot mistake the ratio for a result. So `Unchecked`
carries the obligation, the instrument that would settle it, and its acquisition
state — and `sentence()` prints them in full, with no truncation and no "and 3
others".

Run: python3 checker/coverage.py
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field

# Words no coverage report may contain. A scope statement that says "compliant"
# has stopped being a scope statement and become an opinion about the document.
FORBIDDEN = ("compliant", "complies", "in compliance", "all clear", "clean",
             "no issues", "nothing to report", "fully checked", "verified as")


class ScopeOverclaim(ValueError):
    """Raised when a coverage report states a verdict instead of a scope."""


@dataclass(frozen=True)
class Unchecked:
    """One thing we did not check, and what it would take to check it."""
    what: str                 # the obligation or field, in the reader's words
    why: str                  # why not, in one clause
    acquire: str = ""         # the instrument that would settle it
    state: str = ""           # its acquisition state, e.g. NOT_HELD, STAGED

    def __post_init__(self) -> None:
        if not self.what or not self.why:
            raise ValueError(
                "an unchecked item must say WHAT was not checked and WHY. "
                "An unnamed gap is indistinguishable from no gap.")

    def line(self) -> str:
        bits = [f"{self.what} — {self.why}"]
        if self.acquire:
            bits.append(f"needs: {self.acquire}")
        if self.state:
            bits.append(f"({self.state})")
        return "  · " + "; ".join(bits)


@dataclass(frozen=True)
class Report:
    """The scope frame that travels with every answer."""
    checked: tuple[str, ...]
    unchecked: tuple[Unchecked, ...]
    corpus: str = ""              # what body of law was searched
    as_of: str = ""

    def __post_init__(self) -> None:
        # The constructor is the enforcement point. A caller that has not thought
        # about what it failed to check cannot omit the question by forgetting it.
        if not isinstance(self.unchecked, tuple):
            raise TypeError("unchecked must be a tuple, given explicitly")
        blob = " ".join([*self.checked, *(u.what + " " + u.why
                                          for u in self.unchecked)]).lower()
        for word in FORBIDDEN:
            if word in blob:
                raise ScopeOverclaim(
                    f"a coverage report may not contain {word!r}. It states what "
                    f"was examined and against what law. Whether the document is "
                    f"compliant is a conclusion, and not one this system reaches.")

    @property
    def complete(self) -> bool:
        return not self.unchecked

    def sentence(self) -> str:
        """The frame, in full. Never truncated, never summarised to a ratio."""
        head = (f"Checked {len(self.checked)} of {len(self.checked) + len(self.unchecked)}"
                + (f" against {self.corpus}" if self.corpus else "")
                + (f", as at {self.as_of}" if self.as_of else "") + ".")
        if not self.unchecked:
            return (head + " Nothing was withheld. This states what was examined, "
                            "not a conclusion about the document.")
        return "\n".join([
            head,
            f"NOT checked ({len(self.unchecked)}) — these were not examined at all, "
            f"and silence about them is not a finding:",
            *[u.line() for u in self.unchecked],
        ])

    def to_json(self) -> dict:
        return {
            "checked": list(self.checked),
            "checked_count": len(self.checked),
            "unchecked": [{"what": u.what, "why": u.why, "acquire": u.acquire,
                           "state": u.state} for u in self.unchecked],
            "unchecked_count": len(self.unchecked),
            "corpus": self.corpus,
            "as_of": self.as_of,
            "sentence": self.sentence(),
            "establishes_compliance": False,
            "dismissable": False,
        }


def from_rows(rows, *, corpus: str = "", as_of: str = "") -> Report:
    """Build a report from obligation rows, using the row's own blocked_by.

    A row that names what blocks it is a row that can explain itself; a row that
    merely refuses cannot. This reads `blocked_by` rather than re-deriving the
    reason, so the coverage frame cannot drift from what the engine actually did.
    """
    checked, unchecked = [], []
    for r in rows:
        blocked = getattr(r, "blocked_by", None)
        if blocked:
            unchecked.append(Unchecked(
                getattr(r, "duty", None) or getattr(r, "obligation_id", "?"),
                "its governing instrument is not held", acquire=str(blocked),
                state=getattr(r, "state", "")))
        else:
            checked.append(getattr(r, "duty", None)
                           or getattr(r, "obligation_id", "?"))
    return Report(tuple(checked), tuple(unchecked), corpus=corpus, as_of=as_of)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("coverage")

    # ── O-02: the gap is named, never merely absent ──────────────────────────
    r = Report(
        checked=("board meeting intervals", "small company status"),
        unchecked=(Unchecked("audit committee constitution",
                             "Rule 6 is held but no reviewer has read it",
                             "Rule 6, Meetings of Board Rules 2014",
                             "HELD_UNREVIEWED"),
                   Unchecked("related-party thresholds",
                             "Rule 15's 2019 limbs are unreviewed",
                             "Rule 15, Meetings of Board Rules 2014", "STAGED")),
        corpus="Companies Act 2013", as_of="2026-09-13")

    s = r.sentence()
    check("NOT checked (2)" in s, "the unchecked count is stated, not implied")
    check("audit committee constitution" in s and "related-party thresholds" in s,
          "...and every unchecked item is NAMED -- the GC asked for names, not a "
          "ratio, because 13-of-15 reads as 87% and 87% reads as nearly-done")
    check("silence about them is not a finding" in s,
          "...and the report says outright what silence does not mean, which is "
          "the sentence the CS asked for")
    check("Rule 6" in s and "HELD_UNREVIEWED" in s,
          "...with the instrument and its acquisition state, so a reader can see "
          "the difference between unheld and unread")

    # ── O-03: it cannot say the document is fine ─────────────────────────────
    for bad in ("the document is compliant", "all clear on capital",
                "nothing to report", "verified as current"):
        try:
            Report(checked=(bad,), unchecked=())
            check(False, f"a report may not say {bad!r}")
        except ScopeOverclaim as e:
            check("not one this system reaches" in str(e),
                  f"a report is refused for saying {bad!r}")
    try:
        Report(checked=("x",), unchecked=(Unchecked("y", "the company complies"),))
        check(False, "the guard covers the unchecked reasons too")
    except ScopeOverclaim:
        check(True, "the guard covers the WHY text, not just the checked list")

    # ── a full-coverage report still states that it is a scope ───────────────
    full = Report(checked=("a", "b"), unchecked=(), corpus="Companies Act 2013")
    check(full.complete and "Nothing was withheld" in full.sentence(),
          "complete coverage says so plainly")
    check("not a conclusion about the document" in full.sentence(),
          "...and STILL refuses to be read as a verdict -- the dangerous case is "
          "the clean run, not the messy one")

    # ── the report cannot be forgotten ───────────────────────────────────────
    try:
        Report(checked=("a",))                      # type: ignore[call-arg]
        check(False, "unchecked is required")
    except TypeError:
        check(True, "unchecked is a REQUIRED argument -- a caller who has not "
                    "thought about scope cannot omit it by forgetting")
    try:
        Unchecked("something", "")
        check(False, "an unchecked item must say why")
    except ValueError as e:
        check("indistinguishable from no gap" in str(e),
              "an unnamed gap is refused: it is indistinguishable from no gap")

    # ── the JSON carries the frame, and says it is not dismissable ───────────
    j = r.to_json()
    check(j["establishes_compliance"] is False and j["dismissable"] is False,
          "the payload states that it establishes no compliance and may not be "
          "dismissed -- so a UI cannot collapse it and claim it was optional")
    check(len(j["unchecked"]) == 2 and all(u["acquire"] for u in j["unchecked"]),
          "every unchecked item crosses the wire with what would settle it")
    check(j["sentence"] == s, "the rendered sentence travels with the data")

    # ── from_rows reads the engine rather than re-deriving it ────────────────
    class _Row:
        def __init__(self, oid, duty, blocked=None, state="VERIFIED"):
            self.obligation_id, self.duty = oid, duty
            self.blocked_by, self.state = blocked, state

    rep = from_rows([_Row("A", "keep a register"),
                     _Row("B", "constitute an audit committee", "Rule 6", "UNVERIFIED")],
                    corpus="Companies Act 2013")
    check(rep.checked == ("keep a register",) and len(rep.unchecked) == 1,
          "from_rows splits on the row's own blocked_by")
    check(rep.unchecked[0].acquire == "Rule 6",
          "...and carries the blocker the engine named, rather than re-deriving a "
          "reason that could drift from what actually happened")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
