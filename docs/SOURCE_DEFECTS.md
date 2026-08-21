# Known defects in the source, preserved not repaired

`CLAUDE.md`: *never repair a defective government source. Flag it, preserve it verbatim.* Silent
correction destroys the ability to say what the source actually said, which is the whole product.

## SD-001 — editorial instruction inside the text of s.1

**Found:** 2026-08-21, by cross-validating the JSON corpus against the full-Act PDF.
**Where:** `corpus/companies_act/184.json`, `content`, at the end of the record. Companies Act 2013
**section 1** — "Short title, extent, commencement and application".

The record ends:

> "...subject to such exceptions, modifications or adaptation, as may be specified in the
> notification. **To be deleted**"

"To be deleted" is an editorial instruction that has been left in India Code's JSON rendering. It
is **not statutory text**. It does not appear in the full-Act PDF of the same section, which is how
it was found: two renderings of the same law from the same publisher disagree, and the disagreement
is an artefact of their editing process.

**Handling.** Preserved verbatim in the corpus. Not deleted, not cleaned. Any pipeline that serves
or quotes s.1 must be aware the record's tail is not law. This is the only record of 526 carrying
it — checked exhaustively, not sampled.

**Status:** `SOURCE_DEFECT_CONFIRMED`. Present in the source; not caused by our ingestion.
**Bearing on the MVP:** s.1 is not among the 17 MVP sections, so nothing currently shipping quotes
it. It matters because it demonstrates the corpus contains non-statutory editorial matter, which
was not previously known and is not detectable by any test that only reads one rendering.

## What the cross-validation does and does not establish

`scripts/cross_validate_corpus.py`, report at `reports/corpus_cross_validation.json`.

**Establishes:** the JSON corpus and the PDF agree on the text of the Act. Median coverage of a
corpus record by the PDF is **1.0000**; 456 of 464 sections are at or above 0.99; the lowest is
0.873. 518,409 characters were compared that the section index had never touched.

**Does not establish:** that either rendering is *correct*. Both come from India Code. A defect
present in their own source appears identically in both and is invisible to this check. Genuine
independence still needs a different publisher — see `docs/NEXT_PHASE_PLAN.md` P0.

**Residual:** 57 sections carry differences not explained by heading, page number, or footnote.
Sampling their character: mostly word fragments from PDF hyphenation and line breaks, short runs,
and statute cross-references the classifier does not recognise. **Six carry long unexplained runs
and have not been individually inspected** — s.16, s.124 and s.378ZR are the largest. These are
open, not cleared.
