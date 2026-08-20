# Placedon Task Ledger

Single source of truth for what is open. Agents update only their own row, or return a report for
the main session to record. Status: open / ready / in-progress / blocked / complete.

| ID | Task | Owner | Status | Evidence | Commit | Blocker |
|---|---|---|---|---|---|---|
| R-001 | Diagnose six rollback failures | benchmark-engineer | **complete** | 4 engine defects found; undated amendments 13→3 | `28e7b41` | — |
| R-002 | Real document corpus for scanner | document-classifier | **complete** | 30 docs, 18 real from 5 listed issuers + 11 ICSI specimens | — | — |
| R-003 | Scope rules by document type | scanner-engineer | **in-progress** | gating added; T1.4a/T1.6a/b/c/T1.7 still over-fire | — | needs rule-by-rule rework |
| R-004 | Non-circular reconstruction benchmark | benchmark-engineer | **open** | prior benchmark retracted (R-1) | — | need independent as-amended source |
| R-005 | Stale-claim study, 42 comments | product-evidence-auditor | **in-progress** | 1 confirmed SUPERSEDED (DIR-3 KYC) | `9285108` | agent mid-run |
| R-006 | Verify G.S.R. 943(E) primary text | legal-source-researcher | **in-progress** | secondary only (TaxGuru x4) | — | MCA WAF; try eGazette |
| R-007 | Current ICSI CoP figure (AR 2024-25) | legal-source-researcher | **open** | AR 2023-24 gives 11,460, contracting 3%/yr | `ad4daaa` | — |
| R-008 | Measure scanner FALSE NEGATIVES | scanner-engineer | **open** | never measured — all corpus docs are compliant | — | need known-defective docs |
| R-009 | RBI e-mandate: does annual auto-renewal work? | legal-source-researcher | **open** | UNVERIFIED | — | — |
| R-010 | Retire HR-era agents and docs | main | **open** | `hr-ops-researcher`, `trust-boundary-reviewer`, PoSH corpus | — | — |
| H-001 | 30 practitioner interviews (10 CS / 10 CA / 10 corp lawyer) | **founder** | **open** | zero to date | — | human-only |
| H-002 | Apply: Indian Kanoon free non-commercial tier | **founder** | **open** | ₹10,000/mo, exceeds whole budget | — | human-only |
| H-003 | Written query to ICSI for current CoP count | **founder** | **open** | load-bearing for SAM | — | human-only |
| H-004 | Reddit OAuth credentials | **founder** | **open** | only route to live practitioner voice | — | human-only |
