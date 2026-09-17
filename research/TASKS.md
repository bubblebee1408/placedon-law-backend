# Placedon Task Ledger

Single source of truth for what is open. Agents update only their own row, or return a report for
the main session to record. Status: open / ready / in-progress / blocked / complete.

| ID | Task | Owner | Status | Evidence | Commit | Blocker |
|---|---|---|---|---|---|---|
| R-001 | Diagnose six rollback failures | benchmark-engineer | **complete** | 4 engine defects found; undated amendments 13→3 | `28e7b41` | — |
| R-002 | Real document corpus for scanner | document-classifier | **complete** | 30 docs, 18 real from 5 listed issuers + 11 ICSI specimens | — | — |
| R-003 | Scope rules by document type | scanner-engineer | **in-progress** | gating added; T1.4a/T1.6a/b/c/T1.7 still over-fire | — | needs rule-by-rule rework |
| R-011 | Rebuild market model for the LAWYER segment | main | **open** | current model is CS-based, now secondary | — | scope change 20 Aug |
| R-004 | Non-circular reconstruction benchmark | benchmark-engineer | **open** | prior benchmark retracted (R-1) | — | need independent as-amended source |
| R-005 | Stale-claim study, 42 comments | product-evidence-auditor | **in-progress** | 1 confirmed SUPERSEDED (DIR-3 KYC) | `9285108` | agent mid-run |
| R-006 | Verify G.S.R. 943(E) primary text | legal-source-researcher | **in-progress** | secondary only (TaxGuru x4) | — | MCA WAF; try eGazette |
| R-007 | Current ICSI CoP figure (AR 2024-25) | legal-source-researcher | **open** | AR 2023-24 gives 11,460, contracting 3%/yr | `ad4daaa` | — |
| R-008 | Measure scanner FALSE NEGATIVES | scanner-engineer | **open** | never measured — all corpus docs are compliant | — | need known-defective docs |
| R-009 | RBI e-mandate: does annual auto-renewal work? | legal-source-researcher | **open** | UNVERIFIED | — | — |
| R-010 | Retire HR-era agents and docs | main | **complete** | `hr-ops-researcher`, `trust-boundary-reviewer`, PoSH corpus | — | — |
| B-001 | Corporate-law task benchmark, 30-50 docs incl. **defective** ones | benchmark-engineer | **open** | none | — | CRITICAL PATH |
| B-002 | Accessible legal testers (students, junior associates) | founder | **open** | none | — | after B-001 |
| H-001 | Expert review by 1 practising Company Secretary of the matrix | **founder** | **ready** | outreach + capture built: docs/H001_OUTREACH.md, validation_kit.html, record_interview.py with per-row fields | — | gates CLAIMS not development |
| H-002 | Apply: Indian Kanoon free non-commercial tier | **founder** | **open** | ₹10,000/mo, exceeds whole budget | — | human-only |
| H-003 | ICSI CoP query | **founder** | **deprioritised** | CS is now a secondary segment | — | — |
| H-004 | Reddit OAuth credentials | **founder** | **open** | only route to live practitioner voice | — | human-only |
| L-007 | Map document wording to `CompanyClass` ("Private Limited" → private, "(OPC) Private Limited" → opc), or keep extracted class display-only | **founder** | **blocked** | gemma3 proposed `company_class='Company'` ×4; downstream is guarded (`api._profile`, `checker/api.py:86-87`, BadRequest on any other value) | — | interpretive mapping; see docs/OVERNIGHT_REPORT_2026_09_14.md §8 |
| L-008 | Integer value-support: number words ("seven") and first-number ambiguity ("4 of 7") | main | **complete** | Rows now store raw proposals (`e1d95fc`); re-run showed gpt-5-mini proposing the wrong count (4) from a two-number span. Rule: digits or words, one distinct number only. Replay: Llama-70B R03 → CORRECT, 0 leaks, 0 text-probe changes | `9920e41`, `94c5514` | open choice for founder: a correct count in a two-number span is now refused |
| D-002 | Page-anchored spans for multi-page PDFs | **founder** | **blocked** | `checker/pdf_text.extract_pages` agrees with pdfplumber on 0 of 14 corpus PDFs (object streams) | `9010605` | reader decision: fix stdlib parser, or adopt a PDF library (new runtime dependency) |
| C-001 | Scanner fixture `board_outcomes/routemobile_outcome_board_meeting_2025-01-28.txt` is an OCR layer over a scan with errors in its figures | main | **open** | 14 of 14 source pages text-over-page-image; T1.6b/c times clean | `583d11e` | never repair; decide whether annexure figures may be used by any check |
| S-001 | Resolve SD-004 s.174(1) transcription defect ("of a company **hall** be one-third") | legal-source-researcher | **open** | defect logged, text preserved verbatim; blocks `v2-174-1-rule-pos` promotion | — | needs an independent authoritative witness for s.174(1); India Code is the only rendering held |
| S-002 | Acquire G.S.R. 700(E) (Specification of Definition Details Amendment Rules 2022) verbatim | **founder** | **blocked** | instrument located: India Code handle 123456789/508916, text bitstream uuid 6d5e9902-44a7-4ee5-975a-1fd7fc5d51a5 (5153 bytes); attempt chain in corpus/sources/acquisition_gsr700e.json | — | BOTH official routes blocked: indiacode robots.txt HTTP 502 (fail-closed per RFC 9309); egazette sends no intermediate cert and chains to ISRG Root YR, absent from this machine's trust store. Human download + `python3 scripts/register_gsr700e.py <file>` |
| A-001 | G.S.R. 880(E) attestation: `is_attested()` ignored the source (and the classification); the record had no `downloaded_from`/`downloaded_at` yet attested they were recorded from the Gazette/India Code | main | **complete** (founder step optional) | eGazette serves the held file byte for byte (https://egazette.gov.in/WriteReadData/2025/268124.pdf, sha256 44faa58c…a031), recorded as automated `corroborating_copy`, not a human check. Guard now requires classification VERIFIED_INSTRUMENT + a Gazette/India Code source (recorded or corroborated); served `source_url` is that URL. Checked 3×: implementer tests, independent verifier (PASS ×2, 30+ break attempts), main-session hand checks | `86941c5`, `dc2c399`, `0fae26c` | founder may record their own download: `python3 scripts/register_gsr880e.py --source --from <https URL> --at <YYYY-MM-DD>` |
| A-002 | Currency at a past date: `currency_of()` reports Act-only obligations CURRENT at any date | **founder** | **open** | red team L2; the Ask now states the text is not the law as it stood on the document date (`ea627b7`) | `ea627b7` | engine semantics decision |
| A-003 | Ask: confirm `placedon-claude-legal-3300` as design system of record; web Ask at `/product/ask`, concept-only | **founder** | **open** | docs/research/ux/FRONTEND_ALIGNMENT_2026_09_17.md; PLAN_13 §27 | `5202f85` | — |
| A-004 | Ask: bring a docked source sheet and turn switcher to the 320–400px pane (F22) | **founder** | **open** | PLAN_13 §25 F22 | — | redesign of §7/§10 |
| A-005 | Re-base the Word add-in (`addin/taskpane.html`) onto the finalized tokens | main | **open** | still Parchment/Slate/Caution + green `.row.ok` (`taskpane.html:9,27`) | — | after A-003 |
| A-006 | `placedon.ask/0` questions from the frontend before `/v1/ask` is built (provenance stamp, `no_model`, class mapping, `not_confirmed` refs) | main | **open** | web/assistant/contract.md §9 | `bb6effb` | build of `/v1/ask` (F9) |
| A-007 | Site copy promises unbuilt features (MCA21, Word drafting, MCP, email, AOC-4/MGT-7); FAQ says securities law "not covered" vs `scope.py` | **founder** | **open** | FRONTEND_ALIGNMENT §E | — | lives in the 3300 repo |

