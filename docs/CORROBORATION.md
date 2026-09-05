# Independent corroboration of prior wording

**Run:** 22 Aug 2026 · `checker/corroborate.py` · results in
`corpus/corroboration/results.json`

## Why this exists

Two earlier accuracy claims were retracted (`docs/RETRACTIONS.md`):

- "119/119 EXACT vs as-enacted print" — the reference was the *current*
  consolidation, so the test could not fail.
- "43/43 prior wordings found in the PDF" — circular: the footnotes quoting
  those wordings are in that same PDF.

Every prior wording we hold comes from one publisher's footnote. A defect in
India Code's own footnote was, until now, invisible to us.

## The witness

The **amending Act** names the words it replaces:

> in clause (p), for the words "annual evaluation has been made by the Board of
> its own performance and that of its committees and individual directors", the
> words "..." shall be substituted
> — Companies (Amendment) Act 2017, s.36(b)(ii)

That is a different document by a different publisher. Agreement between it and
India Code's footnote is genuine corroboration; disagreement locates a defect.

## Result

| | |
|---|---|
| Testable claims | 40 |
| Corroborated (EXACT) | **24** |
| Conflicts | **0** |
| No witness available | 16 |
| **Where the instrument is held** | **21/24** |

By instrument:

| Instrument | Corroborated | No witness | Witness held |
|---|---|---|---|
| Act 1 of 2018 (Amdt. Act 2017) | 12 | 1 | yes |
| Act 29 of 2020 | 7 | 2 | yes |
| Act 21 of 2015 | 2 | 0 | yes |
| Act 22 of 2019 | 2 | 9 | **no** |
| Act 31 of 2016 | 0 | 2 | no |
| Act 7 of 2017 | 0 | 1 | no |

**Indian Kanoon does not appear to host The Companies (Amendment) Act, 2019.**
That is a gap in the witness, not a defect in the claim. Those claims are
reported NO_WITNESS and are not counted as either pass or fail.

## What this establishes — and what it does not

**Does:** for 24 amended spans, the prior wording we extracted matches the
instrument that made the change, confirmed against a second publisher.

**Does not:** establish that any whole section reconstructs correctly. A section
may carry spans we never parsed, un-footnoted editorial changes, or a
commencement date differing from the recorded w.e.f.

**Section-level point-in-time reconstruction remains UNVERIFIED.** The scope
distinction is exactly what the retracted claims got wrong.

## Method notes

- Fetches go through `checker/robots.py`, which enforces Indian Kanoon's
  ~9,300-document denylist and fails closed on an unreadable robots.txt or a
  missing CA bundle. No user-agent rotation; the 403 from India Code and MCA
  was respected, not worked around.
- Phrase search alone reached 16/40. Reading each instrument end to end took it
  to 24/40 — the earlier shortfall was Indian Kanoon's search index, not our data.
- Cached source HTML is gitignored. Attribution is not redistribution.

Source: Indian Kanoon (indiankanoon.org), retrieved under its terms of use.
