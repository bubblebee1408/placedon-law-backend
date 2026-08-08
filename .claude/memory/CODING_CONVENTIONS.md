# Coding conventions

Rules with a reason. A convention nobody can justify gets ignored the first time it is
inconvenient, so each one below names what it prevents.

## The one that matters

**Code decides. The LLM explains. A lawyer verifies.**

`applicability.py` and `jurisdiction.py` decide whether a law applies, deterministically, and
never call a model. The LLM is only ever asked to phrase an answer whose substance is already
fixed, and `verifier.py` rejects its output if it contains a number absent from the source.

Consequence: **a wrong model cannot make the product wrong.** That is why model choice is a cost
decision. Never move an applicability decision into a prompt.

## Python

- Type annotations on every signature. `from __future__ import annotations` at the top.
- `@dataclass(frozen=True)` for anything crossing a boundary. Return new objects; never mutate.
- **Tests live in `if __name__ == "__main__":` in the module they test.** Unusual, deliberate:
  one file to open, no fixture indirection, and `python3 checker/ic_order.py` is the whole
  contract. `scripts/verify.py` runs them all.
- Assert against **the ingested corpus**, not against constants. `ic_order.py`'s tests read
  `posh_act_2013.json` — so if the corpus changes, the tests notice.
- Never `except: pass`. Every error is handled, logged, or raised.
- No magic numbers. `MAX_TERM_YEARS = 3` with the citation beside it.

## TypeScript / React

- `strict` on. No `any` — `unknown` and narrow.
- Server Component by default; `"use client"` only for state, effects, or handlers.
- Named `type Props = {…}`, destructured in the signature.
- **Never unmount a form to show its result.** Hide it with `hidden`. Unmounting discards user
  input, and the moment they need to go back is the moment they have most to lose.
- Semantic HTML. `<fieldset>`/`<legend>` for groups, `role="alert"` for errors, real `<label>`s.

## Money

- Every cost is derived from a constant, never asserted. Multiply it out before believing it.
- `can_make_call()` before the request, not after.
- New paid dependency → escalate to the human. No exceptions.

## Legal claims

- Quote **verbatim** from `text_display`. Never paraphrase statute — "not exceeding three years"
  is not "up to three years".
- Every claim carries its citation, and the citation must actually support it. `checker/rules.py`
  documents the case where ours did not.
- **Abstention is a feature.** If the corpus does not hold it, say so and say why.
- Never assert verification that has not happened. `scripts/verify.py` enforces this.

## Before saying anything is done

```
python3 scripts/verify.py          # GO / NO-GO, 19 checks
```

And if it touches a UI flow, drive it in a browser. Three bugs shipped past a green suite;
see `LESSONS.md` L-2.
