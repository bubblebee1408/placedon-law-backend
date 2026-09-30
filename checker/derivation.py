"""Every conclusion stores its witnesses, so revocation is re-evaluation not re-query.

Ring 1, pure. PLAN_19 G2.1, built to `docs/plan19/decisions/M13_DERIVATION.md`.

## What this buys

A conclusion that remembers *which* facts it rested on can answer "if this source is
withdrawn, what stops being true?" by re-evaluating what it already has. Without the
witnesses you have to ask every source again, and sources go away — which is the whole
reason `docs/research/` records withdrawn and inaccessible ones.

## Evidence states form a semiring, and half of it already existed

`checker/lattice.py` already had ⊗:

    worst_of   weakest link       a conclusion is only as good as its weakest support
    best_of    strongest route    an alternative support can be stronger   (added with this)

`worst_of` was NOT reimplemented here. It carries the witness and a documented tie rule,
and a second notion of composition would drift from the first. `best_of` went into
`lattice.py` beside it rather than into this module, so a reader cannot find one half of a
dual without the other.

## The order is a PARAMETER, and that is deliberate

`provenance.STATES` is *"a vocabulary, not an order"* — PLAN_19 04 §1's own words, and
`RETRACTED` sits last in the tuple while being the weakest thing in it. The order the
algebra needs is `provenance.EVIDENCE_ORDER`, which **does not exist**: it is G0.5, and
G0.5 is a legal decision about whether an inaccessible source *reported to agree*
(`UNFETCHED_CORROBORATION`) outranks our own inference (`INFERRED`). A model deciding that
would be a model setting an evidence rule.

So nothing here declares an order. `evaluate` takes a `Lattice`, and `_test` generates
**random total orders** and asserts the axioms against each. The algebra is therefore
proved for *any* order rather than for one guess, and whatever G0.5 decides cannot
invalidate it. PLAN_19 04 §1 says exactly this: *"The algebra works for any total order.
The legal meaning depends on which one is chosen."*

## Why OR over conflicting VALUES raises instead of choosing

`⊕` combines alternative supports **for the same claim**. Two sources that disagree about
the *value* are not alternatives, they are a contradiction, and returning the
better-evidenced one would launder it into an answer. CLAUDE.md: *"Never repair a
defective government source. Flag it, preserve it verbatim."*

## Presence is not content

Four defects in two days came from guards that tested presence
(`docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md`,
`RED_TEAM_INSTRUMENT_REGISTRY_2026_09_26.md`). Here:

- `Lattice.rank` raises on an unknown state and **this module does not catch it**. An
  unrecognised evidence word stops the rollup; it does not quietly become the weakest one.
- A derivation with **no** witnesses is not one whose witnesses are all `UNRESOLVED`. The
  first has nothing to say (`⊕` identity = `worst`, witness `None`); the second says
  something weak and names what. They must not render alike, and a test pins it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from checker.lattice import Lattice, Verdict

__all__ = ["Fact", "Derivation", "SourceConflict", "evaluate", "dependents",
           "reevaluate", "minimal_witnesses"]


class SourceConflict(ValueError):
    """Alternatives disagree about the VALUE, not merely about how well it is known.

    Raised rather than resolved. Choosing the better-evidenced of two contradictory
    values would present a contradiction as a finding.
    """


@dataclass(frozen=True)
class Fact:
    """One thing believed, with how well it is known. `state` must be in the lattice."""

    fact_id: str
    value: object
    state: str

    def __post_init__(self) -> None:
        if not self.fact_id.strip():
            raise ValueError("a fact with no id cannot be a witness to anything")


@dataclass(frozen=True)
class Derivation:
    """A conclusion in disjunctive normal form: alternative routes, each a conjunction.

    `routes` is OR-of-ANDs -- `((a, b), (c,))` means "a AND b, or else c". That shape is
    not decoration: it is what makes `minimal_witnesses` meaningful, and what lets
    `reevaluate` answer a revocation without re-querying anything.
    """

    conclusion_id: str
    routes: tuple[tuple[str, ...], ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.conclusion_id.strip():
            raise ValueError("a derivation with no conclusion id cannot be depended on")
        if any(not r for r in self.routes):
            raise ValueError(f"{self.conclusion_id}: an EMPTY route means 'supported by "
                             "nothing', which is not the same as having no routes at all. "
                             "Drop it or name its facts")


def _route_verdict(route: tuple[str, ...], facts: dict[str, Fact],
                   lat: Lattice) -> Verdict:
    """⊗ over one route. A named fact that is absent is an error, never a default."""
    missing = [f for f in route if f not in facts]
    if missing:
        raise KeyError(f"route names fact(s) not supplied: {missing}. A missing witness "
                       "is not a weak witness -- substituting a default here is how a "
                       "gap becomes a plausible value")
    return lat.worst_of([facts[f] for f in route], lambda x: x.state)


def evaluate(d: Derivation, facts: dict[str, Fact], lat: Lattice) -> Verdict:
    """The conclusion's state and the witness responsible, over `lat`.

    ⊕ of (⊗ of each route). No routes at all -> the ⊕ identity, `lat.worst`, with witness
    `None`: nothing supports this, and that is different from a weak support.

    Raises `SourceConflict` if the surviving routes disagree about the VALUE.
    """
    if not d.routes:
        return Verdict(lat.worst, None)
    per_route = [(r, _route_verdict(r, facts, lat)) for r in d.routes]

    # Alternatives must be alternatives FOR THE SAME CLAIM. Different values are a
    # contradiction, and the strongest of two contradictions is still a contradiction.
    values = {}
    for route, _v in per_route:
        for fid in route:
            values.setdefault(facts[fid].value, []).append(fid)
    if len(values) > 1:
        shown = {str(k)[:40]: v for k, v in values.items()}
        raise SourceConflict(
            f"{d.conclusion_id}: witnesses disagree about the value, not merely about how "
            f"well it is known: {shown}. Returning the better-evidenced one would present "
            "a contradiction as a finding")

    best = lat.best_of([v for _r, v in per_route], lambda v: v.state)
    # Carry the FACT that produced the winning route, not the route's Verdict wrapper --
    # a witness a reader cannot follow to a source is not a witness.
    return Verdict(best.state, best.witness.witness if best.witness else None)


def minimal_witnesses(d: Derivation, facts: dict[str, Fact],
                      lat: Lattice) -> tuple[str, ...]:
    """The facts of the single best route -- the smallest set that yields the result.

    Lemma 2: evaluating these gives the same state as evaluating the full DNF. That is
    what makes revocation cheap: only these need re-checking.
    """
    if not d.routes:
        return ()
    ranked = sorted(d.routes, key=lambda r: lat.rank(_route_verdict(r, facts, lat).state))
    return tuple(ranked[0])


def dependents(fact_id: str, ds: list[Derivation]) -> tuple[str, ...]:
    """Every conclusion naming `fact_id` in any route. The revocation question's first half."""
    return tuple(d.conclusion_id for d in ds
                 if any(fact_id in r for r in d.routes))


def reevaluate(fact_id: str, new_state: str, ds: list[Derivation],
               facts: dict[str, Fact], lat: Lattice) -> dict[str, tuple[Verdict, Verdict]]:
    """`{conclusion_id: (before, after)}` if `fact_id` moved to `new_state`.

    Nothing is mutated -- `facts` is copied. This answers "what stops being true if this
    source is withdrawn?" from what is already held, which is the point of storing
    witnesses at all.
    """
    if fact_id not in facts:
        raise KeyError(f"{fact_id} is not a known fact")
    lat.rank(new_state)                       # raises on an unknown state, deliberately
    after_facts = dict(facts)
    old = after_facts[fact_id]
    after_facts[fact_id] = Fact(old.fact_id, old.value, new_state)
    out = {}
    for d in ds:
        if not any(fact_id in r for r in d.routes):
            continue
        out[d.conclusion_id] = (evaluate(d, facts, lat),
                                evaluate(d, after_facts, lat))
    return out


def _test() -> None:
    import itertools
    import random

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("derivation")

    from checker.provenance import STATES

    def random_order(rng) -> Lattice:
        """A RANDOM total order over the real provenance vocabulary.

        The axioms must hold for ANY order, because the real one (G0.5) is an undecided
        LEGAL question -- is an inaccessible source reported to agree stronger than our
        own inference? Testing one guessed order would prove nothing about the algebra
        and would quietly bless the guess.
        """
        st = list(STATES)
        rng.shuffle(st)
        return Lattice("random", tuple(st))

    rng = random.Random(20260926)
    N = 500

    # ---- semiring axioms, over 500 random orders --------------------------------------
    bad = []
    for i in range(N):
        lat = random_order(rng)
        a, b, c = (Fact(f"f{n}", 1, rng.choice(STATES)) for n in range(3))
        facts = {f.fact_id: f for f in (a, b, c)}
        g = lambda x: x.state                                        # noqa: E731

        # ⊗ and ⊕ commutative
        if lat.worst_of([a, b], g).state != lat.worst_of([b, a], g).state:
            bad.append(("⊗ commutative", i)); continue
        if lat.best_of([a, b], g).state != lat.best_of([b, a], g).state:
            bad.append(("⊕ commutative", i)); continue
        # associative
        ab = lat.worst_of([a, b], g).state
        if lat.worst_of([Fact("x", 1, ab), c], g).state != \
           lat.worst_of([a, Fact("y", 1, lat.worst_of([b, c], g).state)], g).state:
            bad.append(("⊗ associative", i)); continue
        # identities: best is ⊗'s, worst is ⊕'s
        if lat.worst_of([a, Fact("id", 1, lat.best)], g).state != a.state:
            bad.append(("⊗ identity", i)); continue
        if lat.best_of([a, Fact("id", 1, lat.worst)], g).state != a.state:
            bad.append(("⊕ identity", i)); continue
        # worst annihilates ⊗
        if lat.worst_of([a, Fact("z", 1, lat.worst)], g).state != lat.worst:
            bad.append(("⊗ annihilator", i)); continue
        # ⊗ distributes over ⊕:  a ⊗ (b ⊕ c) == (a ⊗ b) ⊕ (a ⊗ c)
        lhs = lat.worst_of([a, Fact("bc", 1, lat.best_of([b, c], g).state)], g).state
        rhs = lat.best_of([Fact("ab", 1, lat.worst_of([a, b], g).state),
                           Fact("ac", 1, lat.worst_of([a, c], g).state)], g).state
        if lhs != rhs:
            bad.append(("distributivity", i)); continue
    check(not bad, f"semiring axioms hold over {N} RANDOM total orders: commutative, "
                   f"associative, identities, annihilator, distributive"
                   + (f" -- FAILURES {bad[:3]}" if bad else ""))

    # ---- Lemma 2: the minimal witness set gives the full DNF's answer -----------------
    bad2 = []
    for i in range(N):
        lat = random_order(rng)
        pool = {f"f{n}": Fact(f"f{n}", 7, rng.choice(STATES)) for n in range(6)}
        ids = list(pool)
        routes = tuple(tuple(rng.sample(ids, rng.randint(1, 3)))
                       for _ in range(rng.randint(1, 4)))
        d = Derivation("c", routes)
        full = evaluate(d, pool, lat)
        mins = minimal_witnesses(d, pool, lat)
        viaMin = evaluate(Derivation("c", (mins,)), pool, lat)
        if full.state != viaMin.state:
            bad2.append((i, full.state, viaMin.state, routes))
    check(not bad2,
          f"LEMMA 2: the minimal witness set yields the same state as the full DNF, "
          f"{N} random cases ({bad2[:1]})")

    # ---- Corollary 3: monotonicity ----------------------------------------------------
    bad3 = []
    for i in range(N):
        lat = random_order(rng)
        pool = {f"f{n}": Fact(f"f{n}", 7, rng.choice(STATES)) for n in range(4)}
        d = Derivation("c", (("f0", "f1"), ("f2", "f3")))
        before = evaluate(d, pool, lat)
        target = rng.choice(list(pool))
        improved = dict(pool)
        # move one fact to the BEST state: the result must not get worse
        improved[target] = Fact(target, 7, lat.best)
        after = evaluate(d, improved, lat)
        if lat.rank(after.state) > lat.rank(before.state):
            bad3.append((i, before.state, after.state))
    check(not bad3,
          f"COROLLARY 3: improving any input never worsens the result, {N} random cases "
          f"({bad3[:1]})")

    # ---- the same-value guard ----------------------------------------------------------
    lat = Lattice("t", ("VERIFIED", "CORROBORATED", "INFERRED", "UNRESOLVED"))
    conflict = {"a": Fact("a", 4_00_00_000, "VERIFIED"),
                "b": Fact("b", 2_00_00_000, "INFERRED")}
    try:
        evaluate(Derivation("small_company_ceiling", (("a",), ("b",))), conflict, lat)
        check(False, "conflicting VALUES were composed instead of refused")
    except SourceConflict as e:
        check("disagree about the value" in str(e),
              "alternatives disagreeing about the VALUE raise, rather than the "
              "better-evidenced contradiction being served as a finding")
    same = {"a": Fact("a", 4_00_00_000, "UNRESOLVED"),
            "b": Fact("b", 4_00_00_000, "VERIFIED")}
    v = evaluate(Derivation("c", (("a",), ("b",))), same, lat)
    check(v.state == "VERIFIED" and v.witness.fact_id == "b",
          "...while agreeing on the value, the STRONGER route wins and names its fact")

    # ---- no witnesses is not weak witnesses -------------------------------------------
    empty = evaluate(Derivation("c", ()), {}, lat)
    weak = evaluate(Derivation("c", (("a",),)),
                    {"a": Fact("a", 1, "UNRESOLVED")}, lat)
    check(empty.state == lat.worst and empty.witness is None,
          "no routes at all -> the OR identity (worst) with NO witness: nothing supports it")
    check(weak.state == "UNRESOLVED" and weak.witness is not None,
          "...whereas an UNRESOLVED witness says something weak AND names what -- the two "
          "must not render alike")

    # ---- presence is not content --------------------------------------------------------
    try:
        evaluate(Derivation("c", (("missing",),)), {}, lat)
        check(False, "a route naming an absent fact was evaluated")
    except KeyError as e:
        check("not a weak witness" in str(e),
              "a route naming a fact that was not supplied RAISES -- a missing witness is "
              "not a weak one, and defaulting is how a gap becomes a plausible value")
    try:
        evaluate(Derivation("c", (("a",),)), {"a": Fact("a", 1, "PROBABLY")}, lat)
        check(False, "an unknown evidence state was accepted")
    except Exception as e:
        check(type(e).__name__ == "LatticeError",
              f"an unknown evidence state raises LatticeError from rank(), uncaught "
              f"({type(e).__name__})")
    try:
        Derivation("c", ((),))
        check(False, "an empty route was accepted")
    except ValueError as e:
        check("supported by nothing" in str(e),
              "an EMPTY route is refused: it is not the same as having no routes")

    # ---- revocation: the question the witnesses exist to answer -------------------------
    ds = [Derivation("small_company", (("gsr880", "s2_85"),)),
          Derivation("unrelated", (("other",),))]
    facts = {"gsr880": Fact("gsr880", 4_00_00_000, "CORROBORATED"),
             "s2_85": Fact("s2_85", 4_00_00_000, "VERIFIED"),
             "other": Fact("other", 1, "VERIFIED")}
    check(dependents("gsr880", ds) == ("small_company",),
          "dependents names every conclusion resting on a fact, and only those")
    moved = reevaluate("gsr880", "RETRACTED", ds, facts, lat_ := Lattice(
        "t2", ("VERIFIED", "CORROBORATED", "INFERRED", "UNRESOLVED", "RETRACTED")))
    before, after = moved["small_company"]
    check(before.state == "CORROBORATED" and after.state == "RETRACTED",
          f"retracting a witness re-evaluates the conclusion from what is already held "
          f"({before.state} -> {after.state}) -- no source is queried again")
    check("unrelated" not in moved,
          "...and a conclusion not resting on it is untouched, not recomputed")
    check(facts["gsr880"].state == "CORROBORATED",
          "reevaluate mutates nothing: the caller's facts are unchanged")

    from checker import rings
    check(rings.ring_of("checker.derivation") == rings.RING_1, "this module is Ring 1")
    check(not [v for v in rings.violations() if "derivation" in v],
          "...and introduces no ring violation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
