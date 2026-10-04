# Product Scope — locked 20 Aug 2026

## What Placedon is

> **An evidence-grounded AI assistant for corporate lawyers.** It helps lawyers research Indian
> company law, review corporate documents, identify potentially applicable requirements, and trace
> every answer to its legal source and effective date.

It assists legal judgment. It does not replace it, and it does not give legal advice.

## What Placedon is NOT

- Not a general legal chatbot
- Not a tool for every legal field
- Not an autonomous compliance scanner that decides whether a document is compliant
- Not a product aimed primarily at Company Secretaries
- Not trained on Reddit or unvetted web content
- Not a foundation-model project

## The one workflow — MVP scope

> Given a corporate document and a relevant date:
> 1. classify the document
> 2. extract facts, dates, entities, actions
> 3. identify candidate provisions
> 4. determine the law applicable **on that date**
> 5. retrieve supporting primary sources
> 6. explain why each provision may or may not apply
> 7. flag possible defects
> 8. **abstain** where information is insufficient
> 9. produce a lawyer-reviewable report

Example the product must handle: *"Review this board resolution dated 15 March 2024. Identify
provisions that may apply, show the source and effective date, and list issues requiring a lawyer's
confirmation."*

Note the framing: **"provisions that may apply"**, not "this document is compliant". The second is a
legal conclusion and we do not make it.

## Success criteria

The MVP is not successful because it produces fluent answers. It succeeds if it can:
- find relevant provisions
- **avoid citing irrelevant ones**
- handle historical amendments correctly
- show evidence for every conclusion
- distinguish APPLICABLE from POSSIBLY_APPLICABLE
- know when it lacks enough information
- outperform a general-purpose AI on the same controlled tasks

## Scope-change record — 20 Aug 2026

The primary customer changed from **practising Company Secretary** to **corporate lawyer**.

Evidence that pointed toward CS, now demoted rather than deleted, because it may matter again:
- ICSI's member directory is public with CoP and city filters; ICAI's Trace-a-Member requires the
  searcher's own membership number, so the lawyer/CA population is far harder to reach directly.
- The 68 ROC adjudication orders in `checker/ss/RULES.md` penalise the **certifying** professional.
  MGT-8 certification is a CS function specifically.
- The ICSI software-empanelment channel grew 4 → 8 vendors in two years. No lawyer-side equivalent
  was found.

Evidence supporting the change:
- All four real interviews conducted to date are with **lawyers**, none with a CS.
- Higher willingness to pay on the lawyer side.
- The practising-CS pool is **11,460 and contracting ~3%/yr** (ICSI AR 2023-24).
- "AI for lawyers" is the larger and growing category.

**Consequence, recorded honestly:** the market model in
`Placedon-law-business-plan/model/market_model.py` is built on CoP counts and CS pricing anchors.
It is now **scoped to a secondary segment** and must be rebuilt for the lawyer market before any
figure in it is used externally. Same for the ICSI-channel GTM analysis.
