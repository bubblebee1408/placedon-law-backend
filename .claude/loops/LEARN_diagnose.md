# Learn: diagnose API and result page

2026-08-08 · Phase 5 of 5

## Summary

The Research phase did the job the loop exists for: **the feature was already built and live.**
Executing the spec as written would have duplicated a working stack at new paths and shipped two
claims that fail our own build.

Net change: **one file**, plus a real fix to the verifier.

## Per phase

| Phase | Output | Finding |
|---|---|---|
| Research | `RESEARCH_diagnose.md` | Feature exists; 4 improvements worth taking, 5 claims to reject, 2 of them proven to fail the build |
| Decision | `DECISION_diagnose.md` | Option B. One file. 6 test cases written first. |
| Build | `frontend/app/result/page.tsx` | 3 of 4 improvements already existed; only the key fix was real work |
| Verify | `VERIFY_diagnose.md` | GO. Found a gap in `verify.py` and closed it. |
| Learn | this file | — |

## Budget

**₹0.00.** No LLM call on the diagnose path; total project spend still ₹0.00. The spec's own
estimate for this feature was ₹0 and that is the one number in it that was right.

## What worked

Research-before-build paid for the whole loop in one pass. Adversarial verification found what
self-verification could not — twice in one session.

## What was harder than expected

The verifier's blind spot. A check written against *one phrasing* of a fabrication does not catch
the fabrication. The spec's wording avoided the single word my check keyed on, and it passed. The
lesson generalises: match the claim, not the sentence.

## Tomorrow

Not the RAG Q&A engine. It is **built and unreachable** — `verifier.should_abstain` rejects every
packet because 0 of 30 sections carry `verified_by`. Building more of it produces code nobody can
run, and the spec's ₹300 budget for it would buy nothing, because the call is gated pre-flight
and costs ₹0 to refuse.

The two things that unblock everything are unchanged and neither is code:

1. **H-2** — a lawyer, 12 sections, one evening. Rehearsed end to end: all 12 core questions go
   from abstaining to answering.
2. **H-1** — ten calls. *"Your Board's Report this year needs three numbers about sexual
   harassment complaints — do you know which three?"*

T-8 closed today: private remote at `bubblebee1408/placedon-hr`, all commits pushed.
