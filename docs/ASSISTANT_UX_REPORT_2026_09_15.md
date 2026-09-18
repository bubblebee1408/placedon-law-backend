# The Ask section — loop report (15–17 Sep 2026)

Runbook: `.claude/plans/loop-assistant-ux-2026-09-15.md` · Plan: `docs/PLAN_13_ASSISTANT_UX_PLAN.md` ·
Spec: `docs/PLAN_13_ASSISTANT_UX.md` · Prototype: `web/assistant/` · Branch: `loop/bookmark-godseye-v0`
(pushed; nothing deployed; no model called; the public business-plan repo untouched).

## Read this first — decisions only you can make

| # | Decision | Why it matters | Where |
|---|---|---|---|
| **1** | **G.S.R. 880(E) is served as CORROBORATED on an attestation that does not hold.** `corpus/sources/gsr880e_registration.json` attests "the URL and date this artifact was downloaded from are recorded, and the host was the Gazette or India Code" — but `downloaded_from` and `downloaded_at` are `null`, and `source_url` is an mca.gov.in e-books page. `scripts/register_gsr880e.py:236` `is_attested()` checks only the two human sign-offs and the status, never the source. Every ₹10 crore / ₹100 crore small-company answer rests on it. | Integrity, top priority. Options: tighten `is_attested()` to require a recorded download from a permitted host and re-attest from the Gazette copy, or downgrade the figure until then. | red team L6; spec §26 |
| 2 | **Is `placedon-claude-legal-3300` the design system of record?** The prototype now follows it (the live site uses it). Its own `AGENTS.md:3` still says Next 15 + shadcn; neither is true. | Everything visual in §27 rests on it. | spec §27 |
| 3 | **Where the web Ask lives**: a fifth product surface at `/product/ask` in the site's `SurfaceShell`, concept-only until `/v1/ask` exists. The site's docs forbid a client method for `/v1/ask` and "a working chatbot" (`types.ts:5`, `RAG-INTEGRATION.md:60`). | The prototype respects that: it sends nothing and says so. | spec §27 |
| 4 | **State words**: a `partial` turn now reads "Abstained in part", and "Abstained" when nothing was confirmed (was "Partly answered"). Reversible copy. | "Partly answered" over a turn that answered nothing was an overclaim; the site's promise is "Or abstain." | spec §13, §27 |
| 5 | **Currency at a past date** (red team L2): `checker/currency.currency_of()` reports Act-only obligations CURRENT at any date, because the Act text is the current consolidation. The document turn now says "It is not the law as it stood on 01-Jun-2024", but the engine semantics are unchanged. | A 2024 document is checked against 2026 text. | `ea627b7` |
| 6 | **The pane gets Harvey's structure or not** (F22): a docked source sheet and turn switcher at 320–400px is a redesign, not an edit. | The pane is where the product lives (C7). | spec §25 F22 |
| 7 | Dates (`DD-Mon-YYYY` in the Ask vs ISO / "11 Sept 2026" on the site); motion ceiling (200ms vs the site's 250ms). | One convention each. | spec §27 |
| 8 | The site's home page promises MCA21 connection, drafting in Word, MCP, email and AOC-4/MGT-7 plugins that the backend does not implement; its FAQ says securities law is "not covered" while `checker/scope.py` declares SEBI in scope. The live site is also reported six commits behind that repo's `main`. **These come from the analysis agent and were not re-checked in the main session.** | Unsupported product claims (CLAUDE.md). | research report §E |

Earlier decisions still open: D-002 (PDF reader), L-007 (company-class mapping), S-002 (G.S.R. 700(E)
download), MCP registration, Sarvam, the 20-document test.

## What was built

| Commit | What |
|---|---|
| `fe9b3a5` | PLAN_13: constraints C1–C10, nine harsh questions, phases, six acceptance checks |
| `6c6e848` | Research: Harvey's assistant UI, Claude.ai's chat UI, legal-AI chat patterns, internal audit, design brief |
| `7d1fb4e` `b7ebc25` `992874b` | `placedon.ask/0` contract, validator and fixtures built by calling the engine (no hand-typed law) |
| `b83e734` `6c4e756` | The design spec (Harvey-leaning base, three judges) and 43 critic findings dispositioned |
| `7f5255d` `1e4c401` | Static prototype + acceptance runner (Playwright kept outside the repo) |
| `ea627b7` | A document turn must say what law it was checked against (validator + builder); a nothing-confirmed fixture |
| `2c21e09` | Rebuild after the red team (52 findings): 233/396 → **403/403** |
| `bda494a` | Red-team dispositions (§26); two spec rules proved wrong and corrected |
| `5202f85` | Re-based onto the finalized frontend's design system |
| `bb6effb` | Alignment report + spec §27 + contract §9 |

**How it works.** The page renders one saved `placedon.ask/0` response per `?fixture=`; with none, it shows
the empty state. The server decides one of three states; the client never infers one. Every string is
either the response's own (marked `data-f` with its JSON path) or fixed chrome (`data-chrome`), and the
runner fails the page if a digit appears that the fixture did not supply. A figure always carries its
instrument and in-force date under a solid rule; section text always carries "Text as ingested … not a
point-in-time version" under a double rule. Abstention looks like the site's abstention. Ask sends
nothing.

## Code task record (CLAUDE.md)

- **Files changed:** `web/assistant/{index.html, app.js, assistant.css, README.md, contract.md, tools/accept.mjs}`,
  `scripts/assistant_contract.py`, `web/assistant/fixtures/*`, `docs/PLAN_13_ASSISTANT_UX.md`,
  `docs/research/ux/FRONTEND_ALIGNMENT_2026_09_17.md`, `research/TASKS.md`.
- **Tests added or updated:** `assistant_contract.py --test` 37/37 (law_version on legal content;
  nothing-confirmed fixture); `accept.mjs` gained the red-team assertions (confirmed/superseded rendered,
  "Confirmed: none", model line, parent line, no overclaiming copy, no duplicate duty, 3:1 input border,
  Ask does not navigate, markers → records → back, aria-expanded, one h1, heading groups, empty state).
- **Commands run:** `bash scripts/run_tests.sh` → `HARNESS_RESULT suites=163 failed=0 status=GREEN` before
  every commit; `FONTS_DIR=… PLAYWRIGHT=… node web/assistant/tools/accept.mjs web/assistant/index.html
  web/assistant/fixtures --shots=~/.cache/placedon-ux-tools/shots` → `ACCEPTANCE 403/403`.
- **Results:** all red-team findings closed except L6 (decision 1); DQ4 built differently (composer stays
  first, so focus order is visual order).
- **Known limitations:** DOM assertions, not a screen-reader run; the verbatim text keeps the source PDF's
  line breaks and literal `<sup>` markup (faithful, ragged); waiting, cancel and service-error states are
  specified but not built; "Copy with sources" copies rendered text only; screenshots live outside the repo
  (`~/.cache/placedon-ux-tools/shots`); the Word add-in still has the retired tokens.
- **Process facts:** usage and session limits killed agents repeatedly (design judges, the first red team, research
  agents, the frontend analysis), and one fix agent stalled six times on an 86KB payload; each was
  resumed from its cache or finished in the main session, and partial outputs were checked on disk first.

## Next command

Open the prototype: `open web/assistant/index.html` (empty state) or append
`?fixture=document_context_2024`. Re-run the checks with the command above.
