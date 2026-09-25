#!/usr/bin/env python3
"""The dev/test split, frozen by a committed seed.

    python3 eval/goldset/split.py            # self-test
    python3 eval/goldset/split.py --write    # regenerate split.json + questions.jsonl

## Why a split at all

On 2026-09-25 a retrieval fix moved the gold set 12/19 -> 15/19 and was reverted:
`checker/text_search.py`'s own suite caught it breaking precision, because "capital"
is a Companies Act word and *"what is the capital of France"* had started retrieving.
The gold set could not see that. It held fourteen refusal entries and every one was
about a different body of INDIAN LAW; nothing in it was not law at all. So a change
that broke the product looked like an improvement.

Fourteen OFF_TOPIC entries were added the same day, and fourteen entries were moved
to a held-out side **by hand**. A hand split is not a split: it was six rows, all of
them OFF_TOPIC, so the held-out side contained no held-law question and no
unheld-body question and could not have caught a regression in either. This module
replaces it with a seeded, stratified, reproducible one.

## What is stratified, and why each stratum is load-bearing

The stratum is the pair **(provenance, body class)**, because both decide what a row
can be used for:

    MECHANICAL/HELD_LAW      a question about law we hold; answering is correct.
    MECHANICAL/UNHELD_BODY   a question about another Indian body of law that
                             `checker/scope.py` declares and we have not acquired;
                             refusing, NAMING the body, is correct.
    MECHANICAL/OFF_TOPIC     not a question about Indian corporate law at all.
                             This is the stratum whose ABSENCE let the bad fix pass.

Provenance is part of the key rather than assumed, so that the first HUMAN-labelled
rows form their own strata the moment they land, instead of being averaged into the
mechanical ones. Today only MECHANICAL rows exist, so there are three strata.

## SYNTHETIC entries get no split, and that is the point

`Entry.__post_init__` refuses an expected answer on a SYNTHETIC row, and `score()`
skips it, so a SYNTHETIC entry can never reach a numerator or a denominator. Putting
one on the test side would therefore be decoration: it would make the test side look
like 57 rows when 17 of them can judge nothing. They stay on `dev` (where their value
is -- candidate questions to READ while developing) and are listed in split.json
under `synthetic_unsplit_ids`, explicitly outside both sides.

## Groups, not rows, are shuffled

`held_s173_count` and `held_s173_gap` are two questions about ONE provision. If one
is tuned against and the other judges the tuning, the test side is measuring the dev
side. So the unit that moves is the GROUP:

    HELD_LAW      the provision (`expected_refs[0]`, e.g. ACT:COMPANIES_ACT_2013:S173)
    UNHELD_BODY   the body (`FEMA1999`), keeping the statute-naming question and its
                  practitioner-phrased twin on the SAME side. G0.3 builds a lexicon
                  per body; a body seen on dev cannot then test whether the lexicon
                  generalises to a body it was not written against.
    OFF_TOPIC     the row itself -- these share nothing to leak.

## Reproducibility

`SEED` is committed here. Each stratum is shuffled by its OWN `random.Random` seeded
with `f"{SEED}:{stratum}"`, so adding a stratum later (the first HUMAN rows) does not
reshuffle the existing ones and silently move rows across the boundary. Ids are
sorted before the shuffle, so the result does not depend on line order in
questions.jsonl.

## Naming

`Entry.split` has carried the values `dev` / `heldout` since it was added. PLAN_19
G0.2 calls the two sides `dev` and `test`. They are the same two sides: `test` ==
`heldout` == the string `"heldout"` on disk. No second vocabulary is introduced.

## Ring

Ring 2. It reads `checker/scope.py` to learn which bodies are declared-not-held, and
decides nothing about law.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

from eval.goldset import (DEV, HELDOUT, MECHANICAL, SHOULD_ANSWER, SHOULD_REFUSE,
                          GOLDSET_PATH, Entry, load, save)

__all__ = ["SEED", "TEST_FRACTION", "MIN_PER_STRATUM_PER_SIDE", "SPLIT_PATH",
           "HELD_LAW", "UNHELD_BODY", "OFF_TOPIC", "BODY_CLASSES", "SYNTHETIC_UNSPLIT",
           "Unclassified", "body_class_of", "stratum_of", "group_of",
           "make_split", "load_split", "write_split", "apply_split", "ids_sha256",
           "ids_for"]

# Committed, so the split reproduces from this repository alone. The date the gold
# set's OFF_TOPIC stratum was added -- the day the split became necessary.
SEED = 20260925

# One third to the test side. Not tuned: with 47 scorable rows NO fraction yields a
# test side above MIN_N_FOR_A_RATE=30, so the test side's job is not to state a rate.
# It is to hold at least three independent groups of every stratum that a fix could
# be tuned against, which a third does and a tenth does not.
TEST_FRACTION = 1.0 / 3.0

# Below this, a side of a stratum is decoration. Three groups is the smallest number
# where "all of them went the same way" is not the single most likely outcome.
MIN_PER_STRATUM_PER_SIDE = 3

SPLIT_PATH = GOLDSET_PATH.parent / "split.json"

HELD_LAW = "HELD_LAW"
UNHELD_BODY = "UNHELD_BODY"
OFF_TOPIC = "OFF_TOPIC"
BODY_CLASSES = (HELD_LAW, UNHELD_BODY, OFF_TOPIC)

# Not a stratum: a label for the rows that are on neither side.
SYNTHETIC_UNSPLIT = "SYNTHETIC_UNSPLIT"

# The sentence every OFF_TOPIC rule opens with. Matched rather than guessed from the
# question_id prefix, because an id is a convention and a rule is the entry's own
# statement of what it checks. An entry that matches nothing raises: a stratifier
# with a default bucket silently mis-stratifies the first row that does not fit.
_OFF_TOPIC_MARKER = "Not a question about Indian corporate law at all"


class Unclassified(ValueError):
    """An entry no stratum rule matches. Never silently bucketed."""


def _declared_unheld_keys() -> tuple[str, ...]:
    """The bodies scope.py declares and has not acquired: LLP2008, FEMA1999, ..."""
    from checker import scope
    return tuple(b.key for b in scope.declared_unheld())


def body_class_of(entry: Entry) -> str:
    """HELD_LAW / UNHELD_BODY / OFF_TOPIC, from the entry's own fields."""
    if entry.expected == SHOULD_ANSWER:
        # Answering is the correct behaviour, so by construction we hold the law.
        return HELD_LAW
    if entry.expected == SHOULD_REFUSE:
        if _OFF_TOPIC_MARKER in entry.rule or _OFF_TOPIC_MARKER in entry.note:
            return OFF_TOPIC
        if any(k in entry.rule for k in _declared_unheld_keys()):
            return UNHELD_BODY
        raise Unclassified(
            f"entry {entry.question_id!r} expects a refusal but its rule names neither a "
            f"body checker/scope.py declares nor {_OFF_TOPIC_MARKER!r}. A stratified split "
            "cannot place it, and placing it by default would put an unknown kind of row "
            "on one side without anyone deciding to. State the rule, or add a stratum.")
    raise Unclassified(f"entry {entry.question_id!r} has expected={entry.expected!r}")


def stratum_of(entry: Entry) -> str:
    """`PROVENANCE/BODY_CLASS`, or SYNTHETIC_UNSPLIT for a row that cannot be scored."""
    if not entry.scorable:
        return SYNTHETIC_UNSPLIT
    return f"{entry.provenance}/{body_class_of(entry)}"


def group_of(entry: Entry) -> str:
    """The unit that moves between sides. Rows sharing a group share a side."""
    cls = SYNTHETIC_UNSPLIT if not entry.scorable else body_class_of(entry)
    if cls == HELD_LAW and entry.expected_refs:
        return entry.expected_refs[0]            # the provision, not the question
    if cls == UNHELD_BODY:
        for k in sorted(_declared_unheld_keys(), key=len, reverse=True):
            if k in entry.rule:
                return k                          # the body, keeping both phrasings together
    return entry.question_id


def ids_sha256(ids) -> str:
    """sha256 over the SORTED ids, one per line, each line newline-terminated."""
    body = "".join(f"{i}\n" for i in sorted(ids))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _target_test_size(n: int) -> int:
    return max(MIN_PER_STRATUM_PER_SIDE, int(n * TEST_FRACTION + 0.5))


def _split_one_stratum(stratum: str, groups: dict) -> tuple[list, list]:
    """(dev_ids, test_ids) for one stratum. Groups move whole, in seeded order."""
    n = sum(len(v) for v in groups.values())
    order = sorted(groups)                                   # file order cannot matter
    random.Random(f"{SEED}:{stratum}").shuffle(order)        # own RNG per stratum
    target = _target_test_size(n)
    test: list[str] = []
    taken = 0
    for g in order:
        if len(test) >= target:
            break
        test.extend(groups[g])
        taken += 1
    dev = [i for g in order[taken:] for i in groups[g]]
    if len(dev) < MIN_PER_STRATUM_PER_SIDE or len(test) < MIN_PER_STRATUM_PER_SIDE:
        raise ValueError(
            f"stratum {stratum!r} has {n} rows in {len(groups)} groups and cannot put "
            f"{MIN_PER_STRATUM_PER_SIDE} on each side (dev={len(dev)}, test={len(test)}). "
            "A stratum that appears on only one side is the defect this split exists to "
            "prevent -- add rows to it rather than lowering the floor.")
    return sorted(dev), sorted(test)


def make_split(entries=None) -> dict:
    """Derive the split from the entries and the committed seed. Pure: no I/O."""
    entries = tuple(entries if entries is not None else load())
    by_stratum: dict[str, dict[str, list[str]]] = {}
    for e in entries:
        by_stratum.setdefault(stratum_of(e), {}).setdefault(group_of(e), []).append(
            e.question_id)

    synthetic = sorted(i for g in by_stratum.pop(SYNTHETIC_UNSPLIT, {}).values() for i in g)

    dev: list[str] = []
    test: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    for stratum in sorted(by_stratum):
        d, t = _split_one_stratum(stratum, {k: sorted(v)
                                            for k, v in by_stratum[stratum].items()})
        dev += d
        test += t
        counts[stratum] = {"dev": len(d), "test": len(t),
                           "groups": len(by_stratum[stratum])}
    return {
        "seed": SEED,
        "test_fraction": TEST_FRACTION,
        "min_per_stratum_per_side": MIN_PER_STRATUM_PER_SIDE,
        "generated_by": "eval/goldset/split.py --write",
        "note": ("`test` and `heldout` are the same side: Entry.split carries the string "
                 "'heldout'. SYNTHETIC rows are on NEITHER side -- score() cannot score "
                 "them, so a test side containing them would overstate what it judges. "
                 "test_ids_sha256 = sha256 of the sorted test ids, one per line, each "
                 "newline-terminated."),
        "strata": counts,
        "dev_ids": sorted(dev),
        "test_ids": sorted(test),
        "test_ids_sha256": ids_sha256(test),
        "synthetic_unsplit_ids": synthetic,
    }


def load_split(path: Path | None = None) -> dict:
    p = path or SPLIT_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"{p} does not exist. The split must be committed BEFORE any fix is developed "
            "against the gold set (PLAN_19 G0.2); without it every row is a dev row and "
            "nothing judges the fix.")
    d = json.loads(p.read_text(encoding="utf-8"))
    got = ids_sha256(d["test_ids"])
    if got != d["test_ids_sha256"]:
        raise ValueError(
            f"{p}: test_ids_sha256 says {d['test_ids_sha256']} but the ids hash to {got}. "
            "The test side has been edited. Any number measured against it is void.")
    return d


def ids_for(which: str, split: dict | None = None) -> frozenset:
    """Ids on one side. `which` is 'dev', 'test'/'heldout', or 'all'."""
    d = split if split is not None else load_split()
    if which == DEV:
        return frozenset(d["dev_ids"]) | frozenset(d["synthetic_unsplit_ids"])
    if which in (HELDOUT, "test"):
        return frozenset(d["test_ids"])
    if which == "all":
        return frozenset(d["dev_ids"]) | frozenset(d["test_ids"]) | frozenset(
            d["synthetic_unsplit_ids"])
    raise ValueError(f"{which!r} is not a side; one of dev, test, all")


def apply_split(entries, split: dict) -> tuple[Entry, ...]:
    """Stamp Entry.split from the split. Every entry must be named exactly once."""
    test = frozenset(split["test_ids"])
    known = test | frozenset(split["dev_ids"]) | frozenset(split["synthetic_unsplit_ids"])
    missing = [e.question_id for e in entries if e.question_id not in known]
    if missing:
        raise ValueError(f"split.json does not name {len(missing)} entr(ies): "
                         f"{', '.join(missing[:5])}. Regenerate it with --write.")
    return tuple(replace(e, split=HELDOUT if e.question_id in test else DEV)
                 for e in entries)


def write_split(entries=None) -> Path:
    """Regenerate split.json AND stamp questions.jsonl to agree with it."""
    entries = tuple(entries if entries is not None else load())
    d = make_split(entries)
    SPLIT_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    save(apply_split(entries, d))
    return SPLIT_PATH


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("goldset/split")
    live = load()

    # ---- the stratifier reads the entry, not the id ------------------------------
    strata = {}
    for e in live:
        strata.setdefault(stratum_of(e), []).append(e.question_id)
    check(set(strata) == {f"{MECHANICAL}/{HELD_LAW}", f"{MECHANICAL}/{UNHELD_BODY}",
                          f"{MECHANICAL}/{OFF_TOPIC}", SYNTHETIC_UNSPLIT},
          f"every live entry lands in a named stratum ({sorted(strata)})")
    check(len(strata.get(f"{MECHANICAL}/{OFF_TOPIC}", [])) == 14,
          "the OFF_TOPIC stratum -- whose absence let a bad fix pass -- is found: "
          f"{len(strata.get(f'{MECHANICAL}/{OFF_TOPIC}', []))} rows")
    check(all(i.startswith("off_") for i in strata[f"{MECHANICAL}/{OFF_TOPIC}"])
          and all(i.startswith("ref_") for i in strata[f"{MECHANICAL}/{UNHELD_BODY}"])
          and all(i.startswith("held_") for i in strata[f"{MECHANICAL}/{HELD_LAW}"]),
          "...and the classification derived from rule/expected agrees with the ids, "
          "which were never consulted")

    # An entry that fits no rule is refused, never defaulted into a bucket.
    try:
        body_class_of(Entry(question_id="x", question="q", provenance=MECHANICAL,
                            expected=SHOULD_REFUSE, rule="because I said so"))
        check(False, "an unclassifiable refusal entry was silently bucketed")
    except Unclassified as exc:
        check("add a stratum" in str(exc),
              "an entry no stratum rule matches raises rather than defaulting")

    # ---- groups keep the rows that would leak together ---------------------------
    s173 = [e for e in live if e.question_id.startswith("held_s173")]
    check(len({group_of(e) for e in s173}) == 1 and len(s173) == 4,
          "four questions about s.173 share one group, so they cannot judge each other")
    fema = [e for e in live if e.question_id.startswith("ref_fema1999")]
    check(len({group_of(e) for e in fema}) == 1 and len(fema) == 2
          and {group_of(e) for e in fema} == {"FEMA1999"},
          "a body's statute-naming question and its practitioner twin share one group")

    # ---- the split reproduces from the seed --------------------------------------
    a, b = make_split(live), make_split(live)
    check(a == b, "make_split is deterministic: two derivations are identical")
    shuffled = tuple(reversed(live))
    check(make_split(shuffled)["test_ids"] == a["test_ids"],
          "...and independent of the order of questions.jsonl")

    # ---- every stratum appears on BOTH sides -------------------------------------
    dev_ids, test_ids = frozenset(a["dev_ids"]), frozenset(a["test_ids"])
    both = True
    for stratum, ids in strata.items():
        if stratum == SYNTHETIC_UNSPLIT:
            continue
        d = sum(1 for i in ids if i in dev_ids)
        t = sum(1 for i in ids if i in test_ids)
        if d < MIN_PER_STRATUM_PER_SIDE or t < MIN_PER_STRATUM_PER_SIDE:
            both = False
            print(f"         {stratum}: dev={d} test={t}")
    check(both, f"every stratum has >= {MIN_PER_STRATUM_PER_SIDE} rows on BOTH sides "
                f"({', '.join(f'{k}={v[chr(100)+chr(101)+chr(118)]}/{v[chr(116)+chr(101)+chr(115)+chr(116)]}' for k, v in sorted(a['strata'].items()))})")

    # ---- SYNTHETIC rows are on neither side --------------------------------------
    syn = {e.question_id for e in live if not e.scorable}
    check(syn and not (syn & (dev_ids | test_ids))
          and set(a["synthetic_unsplit_ids"]) == syn,
          f"{len(syn)} SYNTHETIC rows are on neither side, and are listed as unsplit "
          "-- they cannot reach a numerator, so a test side holding them would lie "
          "about how much it judges")
    check(not (dev_ids & test_ids) and len(dev_ids | test_ids | syn) == len(live),
          "the sides are disjoint and together with the unsplit rows cover the gold set")

    # ---- the sha is of the sorted test ids, and it moves when they do ------------
    check(a["test_ids_sha256"] == ids_sha256(a["test_ids"])
          == ids_sha256(list(reversed(a["test_ids"]))),
          "test_ids_sha256 is over the SORTED ids, so it does not depend on order")
    check(ids_sha256(a["test_ids"][:-1]) != a["test_ids_sha256"],
          "...and dropping one id changes it, so the test side cannot be quietly trimmed")

    # ---- THE gate: what is committed IS what the seed produces -------------------
    try:
        on_disk = load_split()
    except FileNotFoundError as exc:
        check(False, f"eval/goldset/split.json is not committed: {exc}")
        on_disk = None
    if on_disk is not None:
        check(on_disk["dev_ids"] == a["dev_ids"] and on_disk["test_ids"] == a["test_ids"],
              "the committed split.json is exactly what SEED produces from the "
              "committed questions.jsonl")
        check(on_disk["seed"] == SEED and on_disk["test_ids_sha256"] == a["test_ids_sha256"],
              "...carrying the seed and the sha256 of the test ids")
        stamped = {e.question_id for e in live if e.split == HELDOUT}
        check(stamped == frozenset(on_disk["test_ids"]),
              f"questions.jsonl agrees with split.json about the test side "
              f"({len(stamped)} stamped heldout vs {len(on_disk['test_ids'])} listed)")
        check(ids_for(DEV, on_disk) >= syn and not (ids_for("test", on_disk) & syn),
              "ids_for('dev') includes the unsplit SYNTHETIC rows; ids_for('test') never does")

        # A tampered test side is refused, not read.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "split.json"
            bad = dict(on_disk)
            bad["test_ids"] = on_disk["test_ids"][:-1]
            p.write_text(json.dumps(bad), encoding="utf-8")
            try:
                load_split(p)
                check(False, "a split.json whose sha does not match its ids was loaded")
            except ValueError as exc:
                check("void" in str(exc),
                      "a split.json whose test ids no longer hash to its sha is refused")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--write" in sys.argv:
        print(f"wrote {write_split()}")
    else:
        _test()
