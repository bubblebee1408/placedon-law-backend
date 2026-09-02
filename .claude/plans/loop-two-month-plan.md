# Loop runbook — the two-month technical and feature plan

    pattern : sequential (draft -> adversarial critique -> synthesis)
    mode    : safe
    started : 2026-09-02

## Why a loop rather than one pass

Six planning documents already exist and none of them changed what got built,
because each was written in one pass by an agent that could not be argued with.
This loop drafts, then attacks the draft, then synthesises. The critique stage
is the point.

## Evidence status of the market research this rests on

The research supplied cites a Manupatra 2025 survey for nearly every market
number (227 respondents; 87.63% experienced or heard of AI errors; 4.07% fully
trust AI output; 51.16% hallucinated content; 42.44% inadequate Indian-law
support; 47.67% data-security concern; 66.52% want freemium; 67.40% want
training; 43.61% want case-management integration).

**These could not be verified.** The published PDF is a Canva design export
whose text layer carries glyph codes with no ToUnicode CMap, so neither WebFetch
nor `checker/pdf_text.extract_text` can read it. Web search budget is exhausted,
so no secondary source could be checked either.

Consequences, which the plan must carry rather than bury:

- Every percentage from that survey is UNVERIFIED and must be labelled so.
- The survey's own stated limits still apply even if verified: 227 respondents
  including students is directional, not a census.
- The NJDG pendency figures are separately sourced to Department of Justice
  material and are more reliable, but they measure court backlog, not lawyer
  demand for software.

The plan may use these as HYPOTHESES to test. It may not use them as evidence.

## Stop condition

1. A two-month plan exists with dated milestones tied to the code that exists.
2. Every market claim carries VERIFIED / UNVERIFIED / ASSUMED.
3. A named risk register with a mitigation per risk.
4. An adversarial critique has been run against the draft and its surviving
   objections are answered in the text, not deleted.
5. Kill criteria: what evidence would say the plan is wrong.

## Out of scope

- Any accuracy claim. B-001 and H-001 remain open.
- Model training. Settled and not reopened.
- Litigation features. The wedge is corporate compliance.
