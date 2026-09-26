"""Ordinal state algebra — one implementation of "the worst thing wins".

Three modules had independently grown the same shape: an ordered tuple of states,
a private `_SEVERITY` dict mapping each to a rank, and a `max(..., key=...)` to
roll several findings up into one. `currency.py`, `staleness.py` and
`corpus_currency.py` all did it, slightly differently.

## Why an ordinal lattice and not a probability

This is the structure `.claude/memory/LESSONS.md` L-15 prescribes after a Bayesian
belief engine was built here and deleted: "Where the inputs are categorical facts,
the honest structure is an ordinal lattice with weakest-link composition, not a
probability: it composes, it orders, it explains, and it cannot be misread as a
measurement."

The composition argument is the load-bearing one. `max` needs no joint
distribution. Multiplying probabilities across a section, the rule that qualifies
it, and the reviewer who attested that rule would assert independence between
three maximally dependent things — and would produce a number that looks like a
measurement of the world when it is an artefact of an assumption nobody checked.

## The witness is not optional

A rollup that returns only a state is unusable: "UNACQUIRED" tells a person
nothing about which of five dependencies to go and fix. Every verdict here names
the input that produced it. That is why `worst_of` returns a `Verdict` and not a
string, and why the empty case returns the best state with `witness=None` rather
than raising — an obligation resting on nothing is genuinely fine, and saying so
without a witness is honest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


class LatticeError(ValueError):
    """A state outside the declared vocabulary. Never downgraded to a warning."""


@dataclass(frozen=True)
class Verdict:
    """The composed state, and the input responsible for it."""
    state: str
    witness: object | None      # the item that produced `state`, or None if empty


@dataclass(frozen=True)
class Lattice:
    """A totally ordered vocabulary, declared best -> worst."""
    name: str
    states: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.states:
            raise LatticeError(f"{self.name}: a lattice needs at least one state")
        if len(set(self.states)) != len(self.states):
            dupes = sorted({s for s in self.states if self.states.count(s) > 1})
            raise LatticeError(f"{self.name}: duplicate state(s) {dupes} — rank would be ambiguous")

    @property
    def best(self) -> str:
        return self.states[0]

    @property
    def worst(self) -> str:
        return self.states[-1]

    def rank(self, state: str) -> int:
        """Position in the order. Worse = higher, matching the private _SEVERITY
        dicts this replaces, so extraction cannot silently reorder a verdict."""
        try:
            return self.states.index(state)
        except ValueError:
            raise LatticeError(
                f"{self.name}: unknown state {state!r}; declared states are "
                f"{list(self.states)}") from None

    def worst_of(self, items: Iterable[T], status_of: Callable[[T], str]) -> Verdict:
        """Weakest-link composition: the worst state present, and what caused it.

        Empty is the identity, not an error — a thing resting on no dependencies
        is genuinely at the best state, and returning `witness=None` says exactly
        that rather than inventing a cause.

        Ties resolve to the FIRST item at the worst rank, so a rollup over the
        same inputs in the same order always names the same witness.
        """
        found: tuple[int, T] | None = None
        for item in items:
            r = self.rank(status_of(item))     # raises on an unknown state
            if found is None or r > found[0]:
                found = (r, item)
        if found is None:
            return Verdict(self.best, None)
        return Verdict(self.states[found[0]], found[1])

    def best_of(self, items: Iterable[T], status_of: Callable[[T], str]) -> Verdict:
        """Strongest-alternative composition: the best state present, and what gave it.

        The dual of `worst_of`, and it lives here rather than in a caller so that a
        reader cannot find one half of the pair without the other.

        Added 2026-09-26 for `checker/derivation.py` (PLAN_19 G2.1), where the two are
        the semiring's operations: `worst_of` is ⊗ (a conclusion is only as good as its
        weakest support) and this is ⊕ (an alternative route can be stronger).

        **Empty returns `worst`, not `best`** -- the mirror of `worst_of`'s argument and
        not a copy of it. `worst_of` returns `best` on empty because resting on no
        dependencies IS unconstrained. Here, having no alternative means nothing supports
        the claim at all, which is the weakest thing that can be said. Returning `best`
        would make "no support" indistinguishable from "verified", which is the identity
        this whole module exists to keep straight.

        Ties resolve to the FIRST item at the best rank, the same rule as `worst_of`, so
        a rollup over the same inputs in the same order always names the same witness.
        """
        found: tuple[int, T] | None = None
        for item in items:
            r = self.rank(status_of(item))     # raises on an unknown state
            if found is None or r < found[0]:
                found = (r, item)
        if found is None:
            return Verdict(self.worst, None)
        return Verdict(self.states[found[0]], found[1])


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("lattice")

    # The real currency vocabulary, in its real order.
    from checker.currency import (CURRENT, NOT_YET_IN_FORCE, SUPERSEDED,
                                  UNACQUIRED, UNDECLARED, _SEVERITY)
    cur = Lattice("currency",
                  (CURRENT, NOT_YET_IN_FORCE, SUPERSEDED, UNACQUIRED, UNDECLARED))

    # ── the runbook's check: compose three states, get the worst AND its source
    items = [("a", CURRENT), ("b", UNACQUIRED), ("c", SUPERSEDED)]
    v = cur.worst_of(items, lambda t: t[1])
    check(v.state == UNACQUIRED,
          f"composing (CURRENT, UNACQUIRED, SUPERSEDED) yields UNACQUIRED ({v.state})")
    check(v.witness is not None and v.witness[0] == "b",
          f"...and names the input that produced it ({v.witness and v.witness[0]})")

    # ── it must agree with the ranks currency.py already uses, or extracting it
    # silently changes a legal verdict somewhere.
    check(all(cur.rank(s) == _SEVERITY[s] for s in _SEVERITY),
          "the extracted ranks match currency._SEVERITY exactly")

    # ── the same algebra over a DIFFERENT vocabulary
    from checker.staleness import (OK, REFUSED_DISCLOSED, CLAIMED_CURRENT_UNHELD,
                                   SERVED_UNWATCHED, _SEVERITY as _ST)
    stale = Lattice("staleness",
                    (OK, REFUSED_DISCLOSED, CLAIMED_CURRENT_UNHELD, SERVED_UNWATCHED))
    check(all(stale.rank(s) == _ST[s] for s in _ST),
          "...and staleness._SEVERITY exactly")

    # ── empty composition is the identity, and says so without a witness
    e = cur.worst_of([], lambda t: t[1])
    check(e.state == CURRENT and e.witness is None,
          f"an empty rollup is the BEST state with no witness ({e.state}, {e.witness})")

    # ── an unknown state must raise, not sort to the end
    try:
        cur.worst_of([("x", "NONSENSE")], lambda t: t[1])
        check(False, "an unknown state raises LatticeError")
    except LatticeError as err:
        check("NONSENSE" in str(err), f"an unknown state raises, naming it ({err})")

    # ── a duplicate or empty vocabulary is a construction error
    for bad, why in (((CURRENT, CURRENT), "duplicate"), ((), "empty")):
        try:
            Lattice("bad", bad)
            check(False, f"a {why} vocabulary is refused at construction")
        except LatticeError:
            check(True, f"a {why} vocabulary is refused at construction")

    # ── ties: the FIRST worst wins, so composition is deterministic
    tie = cur.worst_of([("p", UNACQUIRED), ("q", UNACQUIRED)], lambda t: t[1])
    check(tie.witness[0] == "p",
          f"on a tie the first worst wins, so the verdict is deterministic ({tie.witness[0]})")


    # ---- best_of: the dual, added 2026-09-26 for checker/derivation.py --------------
    L = Lattice("dual", ("VERIFIED", "CORROBORATED", "INFERRED", "UNRESOLVED"))
    rows = [{"s": "INFERRED", "n": "a"}, {"s": "CORROBORATED", "n": "b"},
            {"s": "UNRESOLVED", "n": "c"}]
    g = lambda r: r["s"]                                          # noqa: E731
    check(L.best_of(rows, g).state == "CORROBORATED"
          and L.best_of(rows, g).witness["n"] == "b",
          "best_of returns the STRONGEST state present and names what gave it")
    check(L.worst_of(rows, g).state == "UNRESOLVED",
          "...and worst_of still returns the weakest, unchanged")
    # The empty cases are OPPOSITE, and that is the point rather than an oversight.
    check(L.worst_of([], g).state == L.best and L.best_of([], g).state == L.worst,
          "empty: worst_of -> best (resting on nothing is unconstrained); best_of -> worst "
          "(no alternative means NOTHING supports the claim). Returning best from an empty "
          "best_of would make 'no support' indistinguishable from 'verified'")
    check(L.best_of([], g).witness is None and L.worst_of([], g).witness is None,
          "...and neither invents a witness for an empty input")
    ties = [{"s": "INFERRED", "n": "first"}, {"s": "INFERRED", "n": "second"}]
    check(L.best_of(ties, g).witness["n"] == "first"
          and L.worst_of(ties, g).witness["n"] == "first",
          "both resolve ties to the FIRST item, so the same inputs always name the same "
          "witness")
    try:
        L.best_of([{"s": "MADE_UP", "n": "x"}], g)
        check(False, "best_of accepted a state outside the lattice")
    except LatticeError:
        check(True, "best_of raises on an unknown state, like worst_of -- it does not "
                    "treat an unrecognised word as the weakest one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
