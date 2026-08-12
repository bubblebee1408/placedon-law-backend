# Build context

Constraints an agent must load before touching this repository. Each one exists because
following the obvious alternative produced a specific, traced failure.

## Where the work happens

`placedon-law-backend`. Not `~/placedon`, which does not exist. The frontend is a separate
repository (`placedon-law-frontend`); plans and research are in `placedon-law-research`.

## Never chunk a legal section

The corpus stores **whole sections** plus six separately addressable sub-sections. Fixed-size
chunking — "500 characters with 50 overlap" — splits a section mid-sentence and destroys verbatim
quotability, which is the property `checker/verifier.py` depends on to reject a fabricated figure.
If text must be split, split at section boundaries and nowhere else.

## No self-verification

Chain-of-thought self-checking by the same model is weak: a model that fabricated a claim will
usually endorse it on re-reading. Use **external** verifiers — `verifier.py` against retrieved
source text, provenance recorded alongside every claim, and a golden set a lawyer has scored.

## No vector search yet

`checker/retrieval.py` documents the arithmetic: 30 sections, ~2 GB of torch to beat a 0.05 ms
scan. Revisit at roughly 500 sections, i.e. when the labour codes land. Not before.

## The register rule

A date exists in `corpus/reference/notified_dates.json` only alongside the reply it came from.
Enforced in three places: `scripts/build_register.py` refuses `--record` without `--reply`,
`checker/register.py` raises rather than describe a date with no source, and
`scripts/verify.py::_register_dates_have_sources` refuses the state in the file.

**An empty register is correct.** "Asked, no reply" is a publishable finding, not a gap to fill.
`asked_on` means a letter was actually sent — a rendered letter in `outbox/` is not an ask.

## Research priority

Magesh et al., *Hallucination-Free?* (Stanford RegLab, JELS 2025) is Tier 1: Lexis+ AI hallucinates
>17% and Westlaw ~33% on exactly the retrieve-then-generate architecture, which is why ours does
not generate the decision. LoRA and any other fine-tuning are **NEVER** at present — no labelled
data, no training set, and the corpus solves the problem for nothing. See `docs/TECHNICAL_PLAN.md`.

## Failure is loud

No silent fallbacks. An unknown jurisdiction code raises; a missing input fails a check rather than
skipping it. Two index checks once printed PASS while asserting nothing because their input was
absent — that is the bug class this rule exists to prevent.

## The ratchet

Every check in `scripts/verify.py` carries `because=`, naming the incident that bought it. When a
bug escapes, add a check with its story. Do not delete one because it has never fired; a check that
never fires is a bug that never came back.
