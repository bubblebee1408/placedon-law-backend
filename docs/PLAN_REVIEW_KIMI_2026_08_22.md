# Review — "Complete Development Plan" (Kimi, 22 Aug 2026)

Source: `~/Downloads/Complete_Development_Plan.pdf`, 29,844 chars, 10 sections.
Extraction note: 9 subset fonts, 51 character codes with conflicting ToUnicode
meanings. Naive extraction yields 42 chars. Per-font CMap tracking required.

## BLOCKED — conflicts with a binding rule

| Plan item | Rule it breaks |
|---|---|
| Risk mitigation: "user-agent rotation" to defeat India Code blocking | CLAUDE.md: "Do not bypass the MCA WAF, robots restrictions, access controls, or source terms." NOT IMPLEMENTED. |
| SCC Online / Taxmann as P1 daily API feeds | Paid subscription, no public API, terms prohibit systematic download. Not in permitted-source list. Substitute: Indian Kanoon under attribution. |
| Features 1 & 5: date-versioned statute browser with side-by-side diff | s.52(1)(q)(ii) — Act text servable only together with original matter. Never a clean-statute browser. Buildable only with commentary attached. |

## UNSUPPORTED CLAIMS — do not repeat

- "<2% hallucination" measured by "manual audit of 100 outputs". n=100 cannot
  resolve 2%: expected 2 errors, 95% CI ~0.2%-7%. Needs ~750+ for +/-1%.
- "17-33% raw LLM, 8-12% RAG-only" baselines: no citation in document.
- "+14% retrieval relevance" for GraphRAG: no citation in document.
- "Companies Act 100%" as a coverage metric: our actual state is 464/474
  mapped (97.9%), corpus NOT_FULLY_VERIFIED, 2 confirmed source defects.

## MISDIAGNOSIS

Plan's headline differentiator is point-in-time retrieval, modelled as a
storage problem (Neo4j valid_from/valid_until edges). It is not a storage
problem. We already emit text for past dates. Nothing independent confirms it
is correct. See docs/RETRACTIONS.md — this exact claim was made and retracted
when the "reference" proved to be the current consolidation.

## ADOPT

- 5-step verification pipeline. Converges with our independently-built
  retrieval -> admission -> as_of -> grounding -> attribution ladder.
  Independent convergence on the same architecture is corroborating.
- Section-aware chunking over fixed-token chunking.
- Regulatory alerts as the wedge.
- DPDP-compliant India hosting.
- Court hierarchy for precedential value.

## DEFER

Neo4j, Pinecone, Elasticsearch, Celery, Datadog. Loop runbook lists these as
out of scope. Repo currently has zero third-party dependencies, 13,499 lines.
At 5 users these add five failure modes and no measurable latency win.

## BUDGET

Infra arithmetic is correct (45+25+20+30+15+3 = INR 1,38,000/month) but omits
3.5 salaries, which dominate it by roughly 10x. Not usable as a budget.
