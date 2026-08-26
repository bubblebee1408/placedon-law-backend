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

## SD-002 — the JSON corpus is pre-amendment for a small set of sections

**Found:** 2026-08-21, inspecting the sections flagged by the cross-render check.
**Status:** `CONFIRMED — RENDERING VINTAGE MISMATCH`. Not our ingestion; not a defect in either
rendering taken alone.

India Code's JSON endpoint and its full-Act PDF are **not at the same amendment vintage** for some
sections. The PDF carries current consolidated text; the JSON carries the earlier wording.

| Section | JSON (older) | PDF (current) |
|---|---|---|
| s.16(3) | "punishable with **fine** of one thousand rupees for every day" | "the Central Government shall allot a new name to the company…" |
| s.124(7) | "punishable with **fine** … not less than five lakh rupees" | "liable to a **penalty** of one lakh rupees … continuing failure" |
| s.76A | "punishable with **fine** … one crore rupees or twice…" | superseded wording |
| s.329 | retains "passing of a resolution for voluntary winding up of the company" | text removed |

`fine` → `penalty` is the signature of the Companies (Amendment) Act 2020 decriminalisation;
s.329's removal is consistent with the Insolvency and Bankruptcy Code 2016.

**Why this matters more than SD-001.** The product's claimed differentiator is statutory currency.
A corpus that silently serves pre-amendment text is that claim failing in exactly the place it is
sold. Nothing in the test suite detected this, because a single-rendering test cannot.

**Scope — tested, not assumed.** The hypothesis that the whole JSON corpus is a stale snapshot was
tested and **is not supported**: 31 records say "punishable with fine" and 29 of those wordings
appear verbatim in the current PDF, i.e. those sections genuinely were never decriminalised. The
divergence is localised. **21 of 464 sections** carry JSON text absent from the PDF; most are
hyphenation fragments, and roughly four are genuine vintage divergence.

**MVP impact: none confirmed.** All 17 MVP sections were checked individually. Sixteen are at
1.0000 or above 0.999. s.117 was inspected directly and is clean — its 0.22% shortfall is
line-break fragments, with no JSON-only run longer than 12 characters.

**Handling.** Nothing repaired. Both renderings preserved. Until an independent source resolves
which is authoritative for a given date, **no section in the table above may be served**.

## Open, not cleared

Eight sections had long unexplained runs and were inspected. Classification:

| Section | Class |
|---|---|
| s.67, s.378ZR | PDF section heading; the classifier missed it because the arrangement says "Restrictions" where the body says "Restriction" |
| s.22 | PDF chapter heading injected between sections |
| s.139, s.186 | PDF-side proviso/explanation text, structural |
| s.1 | SD-001 (editorial tail) plus a JSON-only application clause |
| s.16, s.124 | SD-002 — genuine vintage divergence |

s.329, s.236, s.465, s.247, s.74 and s.78 remain **uninspected** and are open.

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

---

## SD-003 — CORRECTED. Mostly not a source defect.

**Filed:** 26 Aug 2026 as "120 unbalanced spans".
**Corrected:** same day, before any of it was acted on.

The original entry claimed India Code emitted 120 amendment spans with an
opening `<sup>N</sup>[` and no closing bracket. That was wrong, and the error was
mine. Classifying the 121 cases by actual cause:

| Cause | n | Whose defect |
|---|---|---|
| Bracket present, after a formatting tag | **42** | **ours** — the regex |
| No bracket at all (mostly omissions) | 69 | neither: correct source behaviour |
| Opens but never closes | 5 | India Code |
| Marker absent from content | 5 | India Code |

India Code writes `<sup>2</sup><b>[` and `<sup>2</sup><i>[Explanation.</i>` as
freely as `<sup>1</sup>[`. Our `_SPAN_OPEN` allowed only whitespace between the
marker and the bracket, so 42 well-formed spans read as broken markup.

Fixing the pattern to permit short intervening tags recovered **41 spans** and
moved **38 sections** from PARTIAL to EXACT on both sides of their first
amendment (45 -> 83).

**The 69 without a bracket are not defects.** 61 of them are omissions. When
text is omitted the marker points at where it used to be and there is nothing to
bracket, because the text is gone from the current consolidation entirely. Its
prior wording cannot come from India Code at any price; it can only come from
the amending Act.

**What remains a genuine India Code defect: 10 spans.** Five open and never
close (s.96 among them, blocking reconstruction before 13-6-2018), and five
name a marker in the footnote that appears nowhere in the content.

**Lesson recorded rather than quietly fixed.** A source-defect claim is an
accusation against a government publisher, and this one survived a commit, a
docs entry and a CLAUDE.md status line before anybody classified the failures by
cause. Counting instances is not diagnosis.

---

## SD-003 (original entry, retained for the record)

## SD-003 — Unbalanced amendment-span markup (120 spans)

**Found:** 26 Aug 2026, while proving the temporal engine.
**Source:** India Code section content (`SectionPageContent`).
**Severity:** blocks exact point-in-time reconstruction for the affected spans.

India Code marks amended spans inline as `<sup>N</sup>[ ... ]`. In **120 spans
across the corpus** the opening bracket has no matching close.

s.96 is one of them. Its content contains exactly one `[` after the marker at
offset 1823 and **zero** `]` characters thereafter:

    <sup>1</sup>[Provided that annual general meeting of an unlisted company
    may be held at any place in India if consent is given ...

The section's footnote *does* quote the prior wording
(`Subs. by Act 1 of 2018, s. 26, for "Provided that"`), so the change is known —
but the extent of the replaced span is not, so the substitution cannot be
reversed. `checker/as_of.py` reports PARTIAL and names marker 1.

**Not repaired.** Guessing the span end would mean choosing where the amendment
stops, which is a legal judgement disguised as a parsing decision. `_find_span`
already carries a comment recording an earlier attempt to swallow to
end-of-document: it captured 8,777 characters in s.1323 and destroyed a later
marker in the same section.

**Consequence.** Across amended sections, reconstruction before the first
amendment date is:

| | count |
|---|---|
| PARTIAL before, EXACT on/after | 118 |
| EXACT both sides | 45 |
| PARTIAL both sides | 41 |
| ABSTAIN | 2 |

Roughly two thirds of amended sections cannot be reconstructed exactly from this
source alone. The remedy is the amending Act itself — the same independent
witness used in `docs/CORROBORATION.md` — not a repair to India Code's markup.
