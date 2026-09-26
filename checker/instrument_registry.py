"""Which instruments are on record at all, and which of them a person has read.

Ring 0. PLAN_19 G0.1, built to the decision in
`docs/plan19/decisions/G0_1_INSTRUMENT_REGISTRY.md`.

## The question this answers, and the one it refuses to answer

`checker/currency.acquisition_for` could distinguish only two states: an instrument
whose prescribed threshold is servable, and `None`. `None` was returned for both
"we have never heard of this instrument" and "it is downloaded, hashed, and waiting
for a reviewer". Those are different facts and collapsing them told a caller the
second was the first -- so an operation raised a BLOCKING requirement to go and
*acquire* a file already sitting in `corpus/sources/`.

This module supplies the missing middle: **registered, not attested.**

## Why it holds pointers and not facts

The obvious registry lists the instruments and their status. That is a second notion
of truth, and this repository has a name for what happens next: a constant saying
CORROBORATED outliving the artifact it was asserting
(`prescribed_thresholds.py`), and `staleness.py`'s rule -- *"derived from disk,
never a hand-edited constant"*.

So `_POINTERS` below declares only **where to look**: the module, the name of its
record accessor, and the name of its attestation predicate. All three are facts
about a Python API, none about the law. Title, status and dates are read from the
record the module returns, at call time.

**"Registered" therefore means "the accessor returned a dict."** It is not a list
this module keeps, so this module cannot assert a registration that does not exist.

## Why the accessor is named per entry rather than assumed

Because the six modules do not agree, and assuming they did would have been a
silent failure:

    register_gsr700e     registration()   is_attested
    register_gsr880e     registration()   is_attested
    register_kmp_rules   registration()   is_servable   <- attested != servable here,
                                                           deliberately, see that file
    register_pas_rules   registration()   is_attested
    register_sebi_lodr   registration()   is_attested
    register_s188_rule15 review_record()  is_attested   <- different accessor, and its
                                                           record keys the name as
                                                           `instrument`, not `title`

`is_servable` for KMP is not a preference. That module draws a distinction between
attested and servable on purpose, and asking it `is_attested` would report a rule as
usable that its own author says is not.

## The two guards on the one duplicated thing

The module list is the only duplication left, and two things stop it drifting:

1. `_test()` compares `_POINTERS` against `sorted(scripts/register_*.py)` on disk.
   The same technique `rings.py` uses so that a feed cannot escape classification by
   being forgotten. (`Path.glob` is not a dynamic import, so it does not trip RT-01.)
2. Failure direction. A wrong accessor name raises `AttributeError` on first call. A
   forgotten module degrades that instrument to today's behaviour -- `None` -- and
   turns the glob test red. **Neither path can make an unattested instrument read as
   attested,** because `attested` is only ever the value the register module's own
   predicate returned.

## Static imports, and why there is no choice

`rings.violations()` bans `__import__`, `eval`, `exec`, `importlib.import_module` and
`sys.modules[...]` in any registered Ring 0 or Ring 1 module outside its own
`_test()`. So the tempting implementation -- glob the directory and import what is
found -- is structurally forbidden the moment this module is registered, which is the
point of registering it. Six `import` statements it is.

`checker/matrix_view.py:460` and `scripts/slice_s173.py:157` do use
`import_module("scripts.register_gsr700e")`, unflagged only because those modules are
unregistered. That is not a precedent to copy.

## What this module does not do

It does not poll, fetch, or decide. It does not know what an instrument *governs* --
`staleness.py` owns that, is keyed by an internal `rule_id` no caller here holds, and
must not be imported from here (it imports `currency`, which imports this; the cycle
is deliberately left open, lazily, in `currency`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Static, because rings.py bans the dynamic alternative. See the docstring.
import scripts.register_gsr700e as _gsr700e
import scripts.register_gsr880e as _gsr880e
import scripts.register_kmp_rules as _kmp
import scripts.register_pas_rules as _pas
import scripts.register_s188_rule15 as _s188
import scripts.register_sebi_lodr as _lodr

__all__ = ["Registered", "records", "declared_modules", "ROOT"]

ROOT = Path(__file__).resolve().parent.parent

# (module object, module name, record-accessor name, attestation-predicate name).
# Nothing about the law appears here. See the docstring on why the last two are
# named per entry instead of assumed.
_POINTERS: tuple[tuple[object, str, str, str], ...] = (
    (_gsr700e, "scripts.register_gsr700e", "registration", "is_attested"),
    (_gsr880e, "scripts.register_gsr880e", "registration", "is_attested"),
    (_kmp, "scripts.register_kmp_rules", "registration", "is_servable"),
    (_pas, "scripts.register_pas_rules", "registration", "is_attested"),
    (_lodr, "scripts.register_sebi_lodr", "registration", "is_attested"),
    (_s188, "scripts.register_s188_rule15", "review_record", "is_attested"),
)


@dataclass(frozen=True)
class Registered:
    """One instrument that is on record, as its own register module describes it.

    Every field is read from that module or its record. Nothing here is restated
    from a list, which is what stops this type becoming a second opinion.
    """

    module: str                 # "scripts.register_kmp_rules" -- the witness
    title: str                  # the record's own `title`, or `instrument` for s188
    attested: bool              # the module's OWN predicate, verbatim
    state: str                  # the record's own `status` word, verbatim
    source_url: str             # "" when the record names none -- never invented
    predicate: str              # which predicate answered: is_attested | is_servable


def records() -> tuple[Registered, ...]:
    """Every instrument with a registration record on disk, read fresh.

    Not cached: a record is a file a person edits by running a register script, and
    a cache would serve a status the artifact no longer carries. The whole set costs
    six small JSON reads.

    A module whose accessor returns `None` is simply absent from the result -- it has
    no record, so there is nothing to report about it.
    """
    out: list[Registered] = []
    for mod, name, accessor, predicate in _POINTERS:
        rec = getattr(mod, accessor)()
        if rec is None:
            continue
        # s188's record keys the name as `instrument`; the others use `title`.
        # Read both rather than assume, and never fall back to the module name --
        # a filename is not an instrument's title.
        title = rec.get("title") or rec.get("instrument") or ""
        out.append(Registered(
            module=name,
            title=title,
            attested=bool(getattr(mod, predicate)(rec)),
            state=str(rec.get("status") or ""),
            source_url=str(rec.get("source_url") or ""),
            predicate=predicate))
    return tuple(out)


def declared_modules() -> tuple[str, ...]:
    """The module basenames `_POINTERS` declares. Exists for the completeness test."""
    return tuple(sorted(name.rsplit(".", 1)[-1] for _m, name, _a, _p in _POINTERS))


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("instrument_registry")

    # ---- THE guard: the declared set equals what is on disk ----------------------
    # A seventh register script added without a pointer here would silently be
    # invisible to acquisition_for, which is the failure this whole module fixes.
    on_disk = tuple(sorted(p.stem for p in (ROOT / "scripts").glob("register_*.py")))
    check(declared_modules() == on_disk,
          f"every scripts/register_*.py is declared ({len(on_disk)} on disk)")
    check(len(on_disk) == 6, f"...and there are six of them, not five ({len(on_disk)})")

    recs = records()
    check(len(recs) == 6, f"all six have a record on disk right now ({len(recs)})")
    check(all(r.title.strip() for r in recs),
          "every record names its instrument -- no blank titles, no filenames")
    check(all(r.module.startswith("scripts.register_") for r in recs),
          "every answer carries the module that produced it, as a witness")

    # ---- the middle state this module exists for --------------------------------
    by_mod = {r.module.rsplit(".", 1)[-1]: r for r in recs}
    attested = [m for m, r in by_mod.items() if r.attested]
    pending = [m for m, r in by_mod.items() if not r.attested]
    check("register_gsr880e" in attested,
          f"880(E) reads as attested -- a person checked it on 2026-09-10 ({attested})")
    check("register_gsr700e" in attested, "...and so does 700(E)")
    check(set(pending) >= {"register_kmp_rules", "register_pas_rules",
                           "register_sebi_lodr"},
          f"KMP, PAS and SEBI LODR are on record and NOT attested ({sorted(pending)})")

    # ---- the per-entry accessor and predicate are not decoration ----------------
    check(by_mod["register_s188_rule15"].title.strip(),
          "s188's record is reached through review_record(), not registration()")
    check(by_mod["register_kmp_rules"].predicate == "is_servable",
          "KMP is asked is_servable, because that module says attested != servable")
    check(all(r.predicate in ("is_attested", "is_servable") for r in recs),
          "no third predicate crept in")

    # ---- it restates nothing ------------------------------------------------------
    src = Path(__file__).read_text(encoding="utf-8")
    # PRODUCTION region only: after the module docstring, before `def _test`. A first
    # attempt scanned to end-of-file and failed on the test's own search strings --
    # the check was testing itself, which is the shape of a check that cannot fail
    # for the right reason.
    body = src.split('"""', 2)[-1].split("def _test", 1)[0]
    for word in ("CORROBORATED", "PENDING_HUMAN_REVIEW", "VERIFIED_INSTRUMENT"):
        if word in body:
            check(False, f"the code restates a status word ({word}) instead of reading it")
            break
    else:
        check(True, "no status word is hard-coded below the docstring -- statuses are read")

    # ---- no dynamic import, which rings.py will also enforce ---------------------
    for banned in ("import_module", "__import__", "eval(", "exec("):
        if banned in body:
            check(False, f"{banned} appears -- rings.py bans it in a registered Ring 0 module")
            break
    else:
        check(True, "no dynamic import: six static imports, as rings.py requires")

    from checker import rings
    check(rings.ring_of("checker.instrument_registry") == rings.RING_0,
          "this module is Ring 0")
    check(not [v for v in rings.violations() if "instrument_registry" in v],
          "...and introduces no ring violation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
