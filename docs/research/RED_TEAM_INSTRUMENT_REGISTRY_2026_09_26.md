# Red team — the instrument registry, hours after it was written

Run 2026-09-26 against `ac14767`, by the session that wrote the code the same morning.
Move 9 of `.claude/plans/loop-twenty-moves-2026-09-26.md` (PLAN_19 G0 red-team pass).

**The claim under attack**, from `checker/instrument_registry.py`'s own docstring:

> *"Neither path can make an unattested instrument read as attested, because `attested`
> is only ever the value the register module's own predicate returned."*

That claim held. One other thing did not.

## Result

| id | Vector | Outcome |
|---|---|---|
| A1 | Can any fragment of an **unattested** title make it read as attested? | **HELD** — 0 of every word of every unattested title |
| A2 | Punctuation-only fragments | **DEFECT** — `"."`, `"-"`, `"("` each answered `AMBIGUOUS` |
| A3 | Case sensitivity | HELD — `SEBI`/`sebi`/`Sebi` all `PENDING`, consistently |
| A4 | Does `AMBIGUOUS` ever carry `read=True`? | HELD — never, across six ambiguous fragments |
| A5 | Could a blank record title become a catch-all? | HELD, and my worry was unfounded |
| A6 | Does the glob guard actually bind? | HELD — declared 6, on disk 6 |

## A2 — the one real finding

```
acquisition_for(".")  -> AMBIGUOUS
acquisition_for("-")  -> AMBIGUOUS
acquisition_for("(")  -> AMBIGUOUS
acquisition_for("")   -> None      (already correct)
acquisition_for("()") -> None      (correct by accident: "()" is in no title)
```

A single punctuation character is a substring of several instrument titles, so
`AMBIGUOUS` was *literally true* — the fragment does match several instruments. It is
still wrong, because **a caller passing `"."` asked no question**, and an answer of the
form "this names several instruments" implies it named something.

`_matches` refused an EMPTY fragment and stopped there. **"Non-empty" is not "means
something"** — which is exactly `RT-12` from yesterday's operation-store red team, where
`source.strip()` let a requirement be closed citing one full stop. Same mistake, one
layer up, in code written the following morning by the same session that had just fixed
it.

**Fix:** `_matches` now requires at least one alphanumeric character. `"."`, `"-"`,
`"("`, `"--"`, `" . "` all return `None`; `"880"` and `"SEBI"` unaffected. Pinned by a
test that loops over the junk fragments, so re-adding the hole fails the suite.

## A5 — a worry that was wrong, recorded because being wrong is also a finding

I expected a blank record title to become a catch-all: if `title == ""`, would every
fragment match it? No. `_matches(frag, "")` evaluates `frag in ""`, which is False for
any non-empty fragment — and an empty fragment is already refused. There are also zero
blank titles on disk today. The concern was unfounded in both directions.

## What held, and why it is worth stating

**A1 is the load-bearing one.** Every word of length ≥ 3 in every unattested instrument
title was tried as a fragment. None produced `read=True`. That is a structural
consequence rather than luck: `read` is only ever the value the register module's own
predicate returned, and the worst record governs when several match. The design claim
survived the attempt to break it.

**A4 matters for the callers.** `operations.py` and `mcp/tools.py` both branch on
`acq.read`, and an `AMBIGUOUS` that carried `read=True` would have served an answer
about an instrument the caller never named. It never does.

## Method note

This is the fourth defect of the same family in two days: `hasattr` swallowing a
missing API, `.get(default)` turning missing into plausible, a `source` check that
tested non-emptiness instead of meaning, and now a fragment check that did the same.
Every one accepted something unverified and rendered it as established.

The pattern is specific enough to write down as a rule: **a guard that tests for
presence is not a guard that tests for content**, and in this repository the second is
almost always what was wanted.
