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

## A claim is recordable only with its source

This was "the register rule", stated over `corpus/reference/notified_dates.json` and enforced by
`scripts/build_register.py`, `checker/register.py` and `scripts/verify.py`. **All of those are now
gone.** POSH is a retired product direction — `checker/scope.py` returns OUT_OF_SCOPE for it by
name, with a test on the refusal text, and `docs/RETIRED_POSH.md` is the record.

Until 27-09-2026 this section told an agent the rule was "enforced in three places", two of which
had not existed for weeks. A constraints file that describes absent machinery is worse than a
silent one: it reads as a guarantee. That is why it is corrected here rather than deleted.

**The rule outlived the machinery, because it was never about POSH.** A date, a threshold or a
prior wording is recordable only alongside the evidence it came from. `verified_by` enforces it on
the corpus, `checker/observation_store.py` enforces it by being append-only, and
`checker/provenance.py` enforces it on a source. **An empty register is correct** — "asked, no
reply" is a publishable finding, not a gap to fill, and UNVERIFIED and OPEN carry the same meaning
today.

## Research priority

Magesh et al., *Hallucination-Free?* (Stanford RegLab, JELS 2025) is Tier 1: Lexis+ AI hallucinates
>17% and Westlaw ~33% on exactly the retrieve-then-generate architecture, which is why ours does
not generate the decision. LoRA and any other fine-tuning are **NEVER** at present — no labelled
data, no training set, and the corpus solves the problem for nothing. See `docs/PLAN_01_ARCHITECTURE.md`.

## Failure is loud

No silent fallbacks. An unknown jurisdiction code raises; a missing input fails a check rather than
skipping it. Two index checks once printed PASS while asserting nothing because their input was
absent — that is the bug class this rule exists to prevent.

## The ratchet

Every check in `scripts/verify.py` carries `because=`, naming the incident that bought it. When a
bug escapes, add a check with its story. Do not delete one because it has never fired; a check that
never fires is a bug that never came back.
