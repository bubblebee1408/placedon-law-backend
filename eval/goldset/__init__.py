"""The gold set: the first thing in this repository that could tell us we are wrong.

Themis has 196 green suites and **no accuracy number**. Not a bad one -- none. Every
one of those suites is a test written by the author, about code written by the
author, asserting behaviour the author chose. `CLAUDE.md` already says this of the
one number that exists: *"Test A 31/32 is an internal consistency measure, not
production accuracy."* That sentence applies to the whole harness.

This module is the instrument that makes "accuracy" a quantity at all. It is
expected to REFUSE to report a rate for a long time. A refusal here is the module
working.

## The mistake this module is built to make impossible

The obvious way to build a gold set quickly is to have a model generate questions,
have a model answer them, and have a model judge the answers. That produces a
confident percentage within a day. It measures nothing about whether a lawyer was
helped, and it is exactly the failure L-15 records -- *"I fixed the arithmetic and
kept the fabrication."*

So every label carries **where it came from**, and the provenance decides what it
may be used for:

    HUMAN       a named person, qualified to say, signed it with a date.
                The only provenance that can settle a question of judgement.
    MECHANICAL  checkable against text this system already holds, by a rule stated
                in the entry, with no opinion involved -- "does s.173(1) say four
                meetings" is a string in the corpus, not an opinion about it.
    SYNTHETIC   proposed by a model. NEVER an answer. A SYNTHETIC entry is a
                QUESTION someone should look at, carrying `expected=None`, and it
                cannot be scored. Its whole value is finding questions a human
                would not have thought to ask.

`score()` computes over HUMAN and MECHANICAL only. A SYNTHETIC entry cannot reach
the numerator or the denominator, because `Entry` refuses to hold an expected
answer alongside SYNTHETIC provenance -- enforced in `__post_init__`, not by
convention.

## Two denominators, never one

"Accuracy" on a system whose product is abstention is a trap. A system that refuses
everything scores 100% on "never wrong" and is worthless; one that answers
everything scores well on coverage and fabricates. Conflating them is how a
flattering number gets built by accident, so this module will not compute a single
figure:

    ANSWERED   of the questions it answered, how many were right?
    REFUSED    of the questions it refused, how many SHOULD it have refused?

The second is the one that matters here and the one nobody reports, because it is
the only measure of whether the abstention this product sells is honest or merely
cautious. An over-refusing system is `PLAN_00` falsifier 1; an under-refusing one
is the thing the repository exists to prevent. One number cannot see both.

## No rate is rendered that the arithmetic will not support

Every rate goes through `checker.calibration_contract.render_number`, which refuses
a number whose observable lattice is coarser than the claim it would make. At n=12
the finest observable difference is 1/12 = 0.083, so "we are at 91%" is not a
statement the data can carry -- and this module will say so rather than print it.
`PLAN_16` C1 sets the first honest measurement at n >= 59.

## Where the questions come from

- **Scraped question PATTERNS** (Reddit, forums, CS/CA groups): what practitioners
  actually ask, in their own words. These are QUESTIONS ONLY. An answer found on a
  forum is not a label and may never become one -- and Reddit's own Responsible
  Builder Policy forbids using its content for model training or commercial
  redistribution, which this module's SYNTHETIC/HUMAN split already enforces.
- **Adversarial agents** playing a practitioner: good at finding questions that
  SHOULD be refused and are not. Their output is SYNTHETIC: candidate questions.
- **The statute itself**: MECHANICAL entries, derived from held text.
- **A practising Company Secretary or advocate**: the only source of HUMAN labels,
  and therefore the only route to a reported rate. No amount of code substitutes.

## Ring

Ring 2 -- it reads the engine and writes local evaluation state. It decides nothing
about law, and nothing in `checker/` may import it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path

__all__ = ["Entry", "Outcome", "Scored", "Report",
           "HUMAN", "MECHANICAL", "SYNTHETIC", "PROVENANCE",
           "ANSWERED", "REFUSED", "SHOULD_ANSWER", "SHOULD_REFUSE",
           "load", "save", "score", "GOLDSET_PATH", "MIN_N_FOR_A_RATE"]

HUMAN = "HUMAN"
MECHANICAL = "MECHANICAL"
SYNTHETIC = "SYNTHETIC"
PROVENANCE = (HUMAN, MECHANICAL, SYNTHETIC)

# What the gold set says the RIGHT behaviour is for a question.
SHOULD_ANSWER = "SHOULD_ANSWER"   # the system holds enough; answering is correct
SHOULD_REFUSE = "SHOULD_REFUSE"   # out of scope, or not enough held; refusing is correct
EXPECTATIONS = (SHOULD_ANSWER, SHOULD_REFUSE)

# DEV is what a fix may be developed against. HELDOUT is never looked at while
# choosing a fix, and is the only honest report of whether one generalised.
#
# Added 2026-09-25, the same day a retrieval fix scored 12/19 -> 15/19 on this gold
# set and was reverted because checker/text_search.py's OWN suite caught it breaking
# precision ("what is the capital of France" started retrieving, because "capital" is
# a Companies Act word). The gold set had FOURTEEN refusal entries and every one was
# about a different body of INDIAN LAW. It contained nothing that was not law at all,
# so it could not see the failure, and a change that broke the product looked like an
# improvement. A split does not fix that on its own -- the OFF_TOPIC entries below
# do -- but without it the next fix gets tuned against the very rows that judge it.
DEV = "dev"
HELDOUT = "heldout"
SPLITS = (DEV, HELDOUT)

# What the system actually did.
ANSWERED = "ANSWERED"
REFUSED = "REFUSED"
BEHAVIOURS = (ANSWERED, REFUSED)

_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDSET_PATH = _ROOT / "eval/goldset/questions.jsonl"

# Below this n, only the count is printed. 30 is not a magic threshold for truth --
# it is the point where the lattice spacing (1/n = 0.033) is finer than the
# differences anyone would act on. PLAN_16 C1 sets the first HUMAN-labelled
# measurement at n>=59; this is the floor for showing any fraction at all.
MIN_N_FOR_A_RATE = 30


@dataclass(frozen=True)
class Entry:
    """One question, and what the right behaviour on it is -- if anyone knows yet.

    `expected` is None for a SYNTHETIC entry and that is not an oversight: a model
    may propose a question, never its own answer key. `__post_init__` refuses the
    combination rather than trusting a caller to remember.
    """

    question_id: str
    question: str
    provenance: str
    expected: str | None = None          # SHOULD_ANSWER / SHOULD_REFUSE, or None
    expected_substrings: tuple[str, ...] = ()   # must appear in a correct answer's prose
    # The corpus refs that must reach the evidence pack, e.g.
    # "ACT:COMPANIES_ACT_2013:S173". Added 2026-09-25 because `expected_substrings`
    # was the wrong instrument for what this engine actually produces. It returns an
    # evidence PACK, not prose -- `answer` is empty and the content lives in
    # `confirmed` -- so a substring test would have been matching against a JSON dump
    # of the whole response. That passes whenever the phrase appears ANYWHERE,
    # including inside a provision retrieved for an unrelated reason, and would have
    # scored retrieval noise as correctness. Asking "did the right provision reach
    # the pack" is a question this system can actually be wrong about.
    expected_refs: tuple[str, ...] = ()
    rule: str = ""                       # MECHANICAL: the check, stated
    labelled_by: str = ""                # HUMAN: who, by name
    labelled_on: str = ""                # HUMAN: when, ISO date
    source: str = ""                     # where the QUESTION came from
    split: str = DEV                     # DEV to develop against; HELDOUT judges
    note: str = ""

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(f"{self.provenance!r} is not a provenance; one of {PROVENANCE}")
        if self.split not in SPLITS:
            raise ValueError(f"{self.split!r} is not a split; one of {SPLITS}")
        if not self.question.strip():
            raise ValueError("a gold-set entry with no question is not an entry")
        if self.expected is not None and self.expected not in EXPECTATIONS:
            raise ValueError(f"{self.expected!r} is not an expectation; one of {EXPECTATIONS}")
        # The rule this whole module exists for.
        if self.provenance == SYNTHETIC and self.expected is not None:
            raise ValueError(
                f"entry {self.question_id!r} is SYNTHETIC and carries an expected answer. "
                "A model may propose a QUESTION; it may never supply its own answer key. "
                "Scoring against model-written labels produces a confident percentage that "
                "measures nothing (L-15). Have a person label it and set provenance=HUMAN, "
                "or state a mechanical rule against held text and set provenance=MECHANICAL.")
        if self.provenance == HUMAN and not (self.labelled_by.strip() and self.labelled_on.strip()):
            raise ValueError(
                f"entry {self.question_id!r} claims a HUMAN label with no named labeller or "
                "date. An unattributable label cannot be audited, and an unauditable label is "
                "indistinguishable from an invented one.")
        if self.provenance == MECHANICAL and not self.rule.strip():
            raise ValueError(
                f"entry {self.question_id!r} is MECHANICAL but states no rule. 'Checkable' "
                "means a reader can run the check; a rule nobody wrote down is an opinion.")
        if self.provenance in (HUMAN, MECHANICAL) and self.expected is None:
            raise ValueError(
                f"entry {self.question_id!r} is {self.provenance} but says nothing about what "
                "the right behaviour is, so it cannot be scored either way")

    @property
    def scorable(self) -> bool:
        return self.provenance in (HUMAN, MECHANICAL)


@dataclass(frozen=True)
class Outcome:
    """What the system actually did on one entry."""

    question_id: str
    behaviour: str                        # ANSWERED / REFUSED
    text: str = ""
    refs: tuple[str, ...] = ()            # refs that reached the evidence pack

    def __post_init__(self) -> None:
        if self.behaviour not in BEHAVIOURS:
            raise ValueError(f"{self.behaviour!r} is not a behaviour; one of {BEHAVIOURS}")


@dataclass(frozen=True)
class Scored:
    entry: Entry
    outcome: Outcome
    correct: bool
    why: str


@dataclass(frozen=True)
class Report:
    """Two denominators and, usually, a refusal to state a rate.

    `sentence()` never prints a percentage the observable lattice cannot carry.
    """

    scored: tuple[Scored, ...]
    skipped_synthetic: int
    unanswered: tuple[str, ...] = ()      # entries with no outcome supplied

    def _split(self, expectation: str, split: str | None = None) -> tuple[int, int]:
        rows = [s for s in self.scored if s.entry.expected == expectation
                and (split is None or s.entry.split == split)]
        return sum(1 for s in rows if s.correct), len(rows)

    @property
    def answered(self) -> tuple[int, int]:
        """(right, total) over questions the system SHOULD have answered."""
        return self._split(SHOULD_ANSWER)

    @property
    def refused(self) -> tuple[int, int]:
        """(right, total) over questions the system SHOULD have refused."""
        return self._split(SHOULD_REFUSE)

    def _rate(self, label: str, right: int, total: int) -> str:
        """k/n with its interval, and never a bare percentage.

        `calibration_contract.TrackRecord` is deliberately NOT used here, and the
        reason is worth stating because reaching for it is the obvious move. That
        type describes a FORECASTER -- it wants a mean forecast, a Brier score and
        a naive baseline to beat. A gold-set pass rate is none of those things, and
        manufacturing a `mean_forecast` to satisfy the dataclass would be inventing
        inputs to make an instrument answer a question it was not built for. That
        is the failure this whole module exists to prevent, committed against the
        very module written to prevent it.

        What DOES transfer is the second argument in that module's docstring: with
        n outcomes the observable frequency lattice is {0, 1/n, ..., 1}, spacing
        1/n. At n=12 the finest distinction the data can express is 0.083, so
        "91%" is not a statement it can carry. So the interval is printed always,
        the point estimate never appears alone, and below MIN_N_FOR_A_RATE only the
        raw count is shown -- a fraction there is arithmetic pretending to be a
        measurement.
        """
        if total == 0:
            return f"  {label}: no entries. Nothing is measured, so nothing is claimed."
        from checker.interval import wilson
        lo, hi = wilson(right, total)
        if total < MIN_N_FOR_A_RATE:
            return (f"  {label}: {right}/{total} correct. NO RATE STATED -- at n={total} "
                    f"the observable lattice is 1/{total}={1/total:.3f} wide, coarser than "
                    f"any claim a rate would make. 95% CI [{lo:.2f}, {hi:.2f}] spans "
                    f"{hi - lo:.2f}, which is the honest width of what we know.")
        return (f"  {label}: {right}/{total} = {right / total:.2f} "
                f"(95% CI [{lo:.2f}, {hi:.2f}], n={total})")

    def sentence(self) -> str:
        ar, at = self.answered
        rr, rt = self.refused
        lines = [
            "GOLD SET -- two denominators, because one would flatter.",
            self._rate("answered-correctly (of those it SHOULD answer)", ar, at),
            self._rate("refused-rightly   (of those it SHOULD refuse)", rr, rt),
        ]
        # The held-out split, printed separately and always. A fix tuned on DEV that
        # does not move HELDOUT has been fitted to the rows that judge it.
        hr, ht = self._split(SHOULD_REFUSE, HELDOUT)
        ha, hta = self._split(SHOULD_ANSWER, HELDOUT)
        if ht or hta:
            lines += ["  --- HELD OUT (never to be tuned against) ---",
                      self._rate("  answered-correctly", ha, hta),
                      self._rate("  refused-rightly   ", hr, ht)]
        lines += [
            f"  not scored: {self.skipped_synthetic} SYNTHETIC entr"
            f"{'y' if self.skipped_synthetic == 1 else 'ies'} "
            "(candidate questions; a model may not supply its own answer key)",
        ]
        if self.unanswered:
            lines.append(f"  no outcome supplied for {len(self.unanswered)} scorable entr"
                         f"{'y' if len(self.unanswered) == 1 else 'ies'}: "
                         f"{', '.join(self.unanswered[:5])}"
                         f"{' ...' if len(self.unanswered) > 5 else ''}")
        human = sum(1 for s in self.scored if s.entry.provenance == HUMAN)
        if human == 0:
            lines.append("  NO HUMAN LABELS. Every scored row is mechanical -- checkable "
                         "against text we hold. That measures self-consistency, not whether "
                         "a lawyer was helped. PLAN_16 C1 needs n>=59 human labels before "
                         "any claim about accuracy is meaningful.")
        return "\n".join(lines)


def score(entries, outcomes) -> Report:
    """Score outcomes against the gold set. SYNTHETIC entries are counted, never scored."""
    by_id = {o.question_id: o for o in outcomes}
    scored: list[Scored] = []
    synthetic = 0
    missing: list[str] = []
    for e in entries:
        if not e.scorable:
            synthetic += 1
            continue
        got = by_id.get(e.question_id)
        if got is None:
            missing.append(e.question_id)
            continue
        if e.expected == SHOULD_REFUSE:
            ok = got.behaviour == REFUSED
            why = ("refused, as it should" if ok else
                   "ANSWERED a question it does not hold enough to answer")
        else:
            if got.behaviour == REFUSED:
                ok, why = False, "refused a question it should have been able to answer"
            else:
                miss_refs = [r for r in e.expected_refs if r not in got.refs]
                miss_sub = [s for s in e.expected_substrings
                            if s.lower() not in got.text.lower()]
                ok = not miss_refs and not miss_sub
                if miss_refs:
                    why = (f"answered, but the governing provision never reached the pack: "
                           f"{', '.join(miss_refs)}")
                elif miss_sub:
                    why = f"answered, but omitted: {', '.join(miss_sub)}"
                else:
                    why = "answered, and the governing provision is in the pack"
        scored.append(Scored(e, got, ok, why))
    return Report(tuple(scored), synthetic, tuple(missing))


def load(path: Path | None = None) -> tuple[Entry, ...]:
    """Read the gold set. A malformed line is an error, never a skipped row."""
    p = path or GOLDSET_PATH
    if not p.exists():
        return ()
    out: list[Entry] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            d = json.loads(line)
            d["expected_substrings"] = tuple(d.get("expected_substrings") or ())
            d["expected_refs"] = tuple(d.get("expected_refs") or ())
            out.append(Entry(**d))
        except Exception as exc:                          # noqa: BLE001
            raise ValueError(f"{p}:{i}: {type(exc).__name__}: {exc}") from exc
    return tuple(out)


def save(entries, path: Path | None = None) -> Path:
    p = path or GOLDSET_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for e in entries:
        d = asdict(e)
        d["expected_substrings"] = list(d["expected_substrings"])
        d["expected_refs"] = list(d["expected_refs"])
        rows.append(json.dumps(d, ensure_ascii=False, sort_keys=True))
    p.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return p


def _test() -> None:
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("goldset")

    # ---- THE rule: a model may not supply its own answer key --------------------
    # If this check ever passes silently, the gold set has become a machine for
    # producing a confident number about nothing (L-15).
    for exp in (SHOULD_ANSWER, SHOULD_REFUSE):
        try:
            Entry(question_id="q", question="does s.173 require four meetings?",
                  provenance=SYNTHETIC, expected=exp)
            check(False, f"a SYNTHETIC entry was allowed to carry expected={exp}")
            break
        except ValueError as exc:
            if "may never supply its own answer key" not in str(exc):
                check(False, f"refused, but not for the stated reason: {exc}")
                break
    else:
        check(True, "a SYNTHETIC entry may not carry an expected answer, either way")

    syn = Entry(question_id="s1", question="What if the company is a Section 8 company?",
                provenance=SYNTHETIC, source="agent:adversarial-lawyer")
    check(syn.expected is None and not syn.scorable,
          "...and a SYNTHETIC entry is a candidate QUESTION, never scorable")

    # ---- a HUMAN label must be attributable -------------------------------------
    try:
        Entry(question_id="h0", question="q", provenance=HUMAN, expected=SHOULD_ANSWER)
        check(False, "an unattributable HUMAN label was accepted")
    except ValueError as exc:
        check("cannot be audited" in str(exc),
              "a HUMAN label with no named labeller and date is refused")

    # ---- a MECHANICAL label must state its rule ---------------------------------
    try:
        Entry(question_id="m0", question="q", provenance=MECHANICAL, expected=SHOULD_ANSWER)
        check(False, "a MECHANICAL label with no rule was accepted")
    except ValueError as exc:
        check("a rule nobody wrote down is an opinion" in str(exc),
              "a MECHANICAL label must state the check a reader can run")

    # ---- and a scorable entry must say what right looks like ---------------------
    try:
        Entry(question_id="m1", question="q", provenance=MECHANICAL, rule="r")
        check(False, "a scorable entry with no expectation was accepted")
    except ValueError as exc:
        check("cannot be scored either way" in str(exc),
              "a scorable entry with no expected behaviour is refused")

    # ---- two denominators, and neither can hide in the other ---------------------
    mech = [
        Entry(question_id="a1", question="Board meetings required per year under s.173(1)?",
              provenance=MECHANICAL, expected=SHOULD_ANSWER, rule="corpus s.173(1) text",
              expected_substrings=("four",)),
        Entry(question_id="a2", question="Small company paid-up capital ceiling?",
              provenance=MECHANICAL, expected=SHOULD_ANSWER, rule="prescribed_thresholds",
              expected_substrings=("crore",)),
        Entry(question_id="r1", question="What are the FEMA rules for FDI in e-commerce?",
              provenance=MECHANICAL, expected=SHOULD_REFUSE, rule="scope.py: FEMA not held"),
        Entry(question_id="r2", question="Is my PoSH internal committee validly formed?",
              provenance=MECHANICAL, expected=SHOULD_REFUSE, rule="scope.py: PoSH retired"),
    ]
    outs = [
        Outcome("a1", ANSWERED, "Section 173(1) requires four meetings each year."),
        Outcome("a2", ANSWERED, "The ceiling is stated in rupees."),      # omits 'crore'
        Outcome("r1", REFUSED),
        Outcome("r2", ANSWERED, "Your IC looks fine."),                   # fabrication
    ]
    rep = score(mech + [syn], outs)
    check(rep.answered == (1, 2), f"answered-correctly is 1 of 2 ({rep.answered})")
    check(rep.refused == (1, 2), f"refused-rightly is 1 of 2 ({rep.refused})")
    check(rep.skipped_synthetic == 1, "the SYNTHETIC entry is counted, not scored")

    # A system that refuses everything must NOT look good.
    all_refuse = score(mech, [Outcome(e.question_id, REFUSED) for e in mech])
    check(all_refuse.refused == (2, 2) and all_refuse.answered == (0, 2),
          "a system that refuses everything scores 2/2 on refusal and 0/2 on answering "
          "-- which is why one number would have flattered it")
    all_answer = score(mech, [Outcome(e.question_id, ANSWERED, "four crore") for e in mech])
    check(all_answer.answered == (2, 2) and all_answer.refused == (0, 2),
          "...and a system that answers everything is caught by the other denominator")

    # ---- no rate is printed that the data cannot carry ---------------------------
    s = rep.sentence()
    # The property is "no POINT ESTIMATE of the rate", not "the digits 0.50 are
    # absent" -- the lattice width legitimately prints 1/2=0.500. A sloppier
    # assertion here failed on the module's own correct output, which is the cheap
    # version of the mistake this file is about.
    check("NO RATE STATED" in s and " = 0." not in s,
          "at n=2 the sentence refuses to state a rate and says why")
    check("observable lattice" in s, "...naming the reason, not merely withholding")
    check("NO HUMAN LABELS" in s,
          "...and it says out loud that nothing here was labelled by a person")
    big = [Entry(question_id=f"m{i}", question=f"q{i}", provenance=MECHANICAL,
                 expected=SHOULD_REFUSE, rule="r") for i in range(40)]
    rep2 = score(big, [Outcome(f"m{i}", REFUSED if i % 4 else ANSWERED) for i in range(40)])
    check("95% CI" in rep2.sentence() and "0.75" in rep2.sentence(),
          f"at n=40 a rate IS stated, with its interval")

    # ---- a missing outcome is reported, never silently dropped -------------------
    partial = score(mech, [Outcome("a1", ANSWERED, "four")])
    check(len(partial.unanswered) == 3 and "no outcome supplied" in partial.sentence(),
          "entries with no outcome are named, not quietly excluded from the denominator")

    # ---- round-trip, and a malformed line is an error ----------------------------
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "g.jsonl"
        save(mech + [syn], p)
        back = load(p)
        check(len(back) == 5 and {e.question_id for e in back} == {"a1", "a2", "r1", "r2", "s1"},
              "the gold set round-trips through disk")
        check(any(e.provenance == SYNTHETIC and e.expected is None for e in back),
              "...and a SYNTHETIC entry survives without acquiring an answer key")
        p.write_text(p.read_text() + '{"question_id": "bad"\n')
        try:
            load(p)
            check(False, "a malformed line was skipped rather than raised")
        except ValueError:
            check(True, "a malformed line raises -- a skipped row is a silently smaller "
                        "denominator, which flatters every rate above it")

    # ---- the live gold set on disk parses, whatever is in it ---------------------
    live = load()
    check(isinstance(live, tuple), f"the committed gold set loads ({len(live)} entries)")
    human = [e for e in live if e.provenance == HUMAN]
    print(f"\n  gold set today: {len(live)} entries, {len(human)} human-labelled. "
          f"PLAN_16 C1 needs 59.")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
