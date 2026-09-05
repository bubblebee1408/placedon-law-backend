# Retractions

Claims this project made and later found to be wrong. Kept permanently so they are not repeated,
and so anyone reading older commits or notes knows what not to trust.

## R-1. Reconstruction was validated against the as-enacted 2013 print
**Claimed:** 19 Aug 2026, commits `3641a7e` / `9589adb`.
**Retracted:** 20 Aug 2026, commit `28e7b41`.

India Code's full-Act PDF was treated as the as-enacted 2013 print. It is the **current
consolidation with its footnote apparatus included** — its arrangement-of-sections lists 3A and 10A
(inserted 2018/2019) and `11. [Omitted.]`, and it carries 562 occurrences of `w.e.f.`

Two dependent claims fall with it:
- **"43 of 43 prior wordings found, zero misses"** was CIRCULAR. Those wordings appear because the
  footnotes quoting them are in the same file, not because the body is pre-amendment.
- **"119/119 EXACT match"** compared a 2014 reconstruction against 2026 text. Meaningless.

**Current status: point-in-time reconstruction is UNVERIFIED against any external source.**
Obtaining a genuine as-enacted or dated as-amended edition is an open task (R-004 in the ledger).

## R-2. The SS defect scanner was validated
**Claimed:** implicitly, 19 Aug 2026, commit `8252fc3` — "20/20 tests pass".
**Retracted:** 20 Aug 2026.

The regexes and the test fixtures were written by the same author. Circular. Against 30 real and
specimen documents the scanner fired DEFECT on **18 of 18** for the serial-number check alone,
including all five of ICSI's own specimen minutes — a 100% false-positive rate. Three further checks
false-PASSED or over-fired.

The root cause was deeper than regex tuning: **minutes checks were being run against notices**, a
category error, since a notice is issued before the meeting and cannot record its conclusion.

**Current status: partially fixed** (document-type gating added). Still over-fires. False negatives
have never been measured at all — every real document in the corpus is compliant.

## R-3. ComplyRelax is coasting / abandoned
**Claimed:** 19 Aug 2026, commit `ebd7afc`.
**Corrected:** 20 Aug 2026, commit `5b42b6a`.

Two supporting facts were wrong:
- The "43 help videos from 2021" are a stale embedded playlist. The channel publishes actively.
- "50,000+ MCA V3 forms filed" is **static marketing text, not a counter** — byte-identical across
  Wayback snapshots from 10 Sep 2025 to today, frozen ~11 months across two filing seasons.

ComplyRelax has **201 unbroken updates from Oct 2020 to Aug 2026**. It is a small, actively-shipping
product with almost no market presence. Treat it as an active competitor.

The strategic conclusion (build the audit layer, not a generator) survives — on different reasoning.
See `docs/PRODUCT_DIRECTION_V2.md` §2.4.

## R-4. High India Code section IDs indicate inserted sections
**Claimed:** 19 Aug 2026.
**Corrected:** 20 Aug 2026, commit `3641a7e`.

352 of 527 IDs exceed 40000. The ID space is simply non-contiguous. s.3A (48973) and s.10A (49492)
are insertions; the converse does not hold. Generalised from two examples.

## R-5. The COP figure was ~12,000
**Superseded:** 19 Aug 2026, commit `ad4daaa`.

Press figure. ICSI's own Annual Report 2023-24 gives **11,460** as on 31.05.2024 — and the pool is
**contracting ~3% a year** while membership grows. That is a materially worse fact than an unverified
number would have been.
