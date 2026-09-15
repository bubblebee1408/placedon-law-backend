# PLAN_13 — the Ask section (grounded assistant): research, design, prototype

Written 2026-09-15, before an unattended loop. Runbook: `.claude/plans/loop-assistant-ux-2026-09-15.md`.
Markers as in [PLAN_00](PLAN_00_INDEX.md): BUILT · MEASURED · SOURCED · INFERRED · UNVERIFIED · BLOCKED.

**The ask:** design the chat/prompt section — how it looks (a mix of Harvey's product and Claude.ai),
where it sits, how it is used, how it works — research it, question it hard, then build it.

---

## 1. The constraints that bind the design (decided before any pixel)

| # | Constraint | Source | Consequence |
|---|---|---|---|
| C1 | A *general* legal chatbot is a non-goal | `NON_GOALS.md`; FEATURES F9 | It is a **grounded assistant**: cited answer or honest refusal. It borrows Harvey/Claude's *form*, never open-ended *behaviour* |
| C2 | The product's job is currency, not answering | `Placedon-law-business-plan/docs/UX_INTERACTION_SPEC.md` §1 | Every figure carries its instrument and as-of date **next to the number** |
| C3 | Exactly three answer states, **server-decided** | UX spec §3, §6.3 | `answered` · `partial` · `out_of_scope`. The UI renders; it never infers a state |
| C4 | No confidence percentages; no loading skeletons | UX spec §3.1, §6.2 | Progress is a stage caption ("checking the source…"), never a fake answer shape |
| C5 | Abstention is never red, never styled as error | `DESIGN_SYSTEM.md` §1 | Caution `#8B4513`, and the heading word carries the state without colour |
| C6 | Quiet authority: ≤ 4px radius, no shadows, ≤ 200ms motion, one accent per view | `DESIGN_SYSTEM.md` §1, §5 | The Harvey/Claude mix is expressed through layout, type and restraint — not effects |
| C7 | The v1 surface is the Word add-in | PLAN_05 Phase 1 | The section must work in a ~320–400px task pane **before** a full web layout |
| C8 | `/v1/ask` does not exist; the model is not wired | FEATURES F9 | Prototype against **fixtures that follow a written contract**; the contract is a deliverable |
| C9 | The business-plan repo is PUBLIC | its `CLAUDE.md` | All new design and prototype work lands in the **private** backend repo |
| C10 | The existing `ask.html` violates C2–C4 | read 2026-09-15 | Shows superseded ₹50L as "verified", an invented reviewer, an out-of-scope DPDP chip. Evidence of failure, not a base |

## 2. Harsh questions the design must answer — each gets a written verdict, not a vibe

1. **Is chat even the right primitive?** Users will type questions the engine cannot answer. What does
   the composer do *before* submit so out-of-scope is rare, and what does `out_of_scope` look like so
   it reads as competence, not failure?
2. **Harvey's look is marketing polish.** Which Harvey/Claude patterns survive C1–C7, and which are
   rejected — with the reason stated per pattern?
3. **Streaming vs server-decided state.** Token streaming shows prose before verification. Decide:
   what may appear before the state is decided? (Default: stage captions only.)
4. **Follow-ups.** A thread invites context drift. Does each turn re-ground against its own evidence
   pack and as-of date, and how is that shown per turn?
5. **Citations.** Inline chips (Claude), a source side panel (Harvey), or both — measured against
   C2: can a reader see instrument + as-of for every figure without a click?
6. **Task pane first.** Does the design degrade to 320px without hiding the evidence?
7. **Document context.** When a Word document is open, is the question about *that* document or the
   law in general — and how does the UI make the difference unmissable?
8. **What we refuse to build**: history search, sharing, voice, file drop into chat — each either
   earns its place against a named user need or is cut.
9. **What would falsify the design** (§7).

## 3. Phases

| Phase | Work | Method | Output |
|---|---|---|---|
| **R** Research | Harvey Assistant UI; Claude.ai chat UI; legal-AI chat patterns + trust/HCI evidence; internal audit of what the engine can truthfully show | Workflow: 4 researchers, each adversarially source-checked; then a brief critic. Public sources only, every claim SOURCED (URL) / INFERRED / UNVERIFIED | `docs/research/ux/*.md` |
| **C** Contract | `/v1/ask` response schema for the three states, citations, as-of, refusals, stages; JSON fixtures for every state | TDD: a validator with tests that fail first | `web/assistant/contract.md`, `web/assistant/fixtures/*.json`, `scripts/assistant_contract.py --test` |
| **D** Design | Three independent directions — *Harvey-leaning*, *Claude-leaning*, *evidence-first native* — scored by judges against C1–C10 and §2; synthesis; harsh critique round | Workflow; design agents use the repo's design skills (impeccable, emil-design-eng, ui-ux-pro-max) and the research | `docs/PLAN_13_ASSISTANT_UX.md` (the design spec) |
| **B** Build | Static prototype: web layout + task-pane layout, rendering every fixture; no framework, no CDN, CSP-safe (no inline script) | TDD for the contract; Playwright screenshots at 320/768/1024/1440; grayscale check; keyboard pass | `web/assistant/` |
| **V** Verify | Red team: legal accuracy & abstention · accessibility · design quality (anti-template) · NON_GOAL guard | Workflow, findings → fixes → dispositions | Dispositions section in the spec; fixes committed |
| **M** Report | What was built, what was decided, what is open | — | `docs/ASSISTANT_UX_REPORT_2026_09_15.md` |

## 4. How it will be used, placed, and work (the working hypothesis Phase D must confirm or overturn)

- **Placement.** (a) Word add-in: an **Ask** tab beside *Currency check* and *Register strip*, scoped to
  the open document by default. (b) Web: the Ask screen, composer centred in an empty state (Claude
  pattern), thread + a right **Source** panel once an answer exists (Harvey pattern), history in a
  collapsible left rail.
- **Composer.** One text field. Above it, always visible: **scope** (the bodies of law held — today,
  Companies Act 2013), **as-of date** (default today; editable), **context** (this document / general).
  Suggested questions come from the capabilities the engine actually has (`checker/bundles.py`), never
  invented.
- **Work.** Submit → stage captions (retrieving → checking the source → verifying dates) → the server
  returns one state → the answer renders with figures carrying instrument + as-of inline → the Source
  panel shows verbatim text and the currency strip. Nothing narrative appears before the state is decided.
- **Follow-up.** Each turn is re-grounded and carries its own as-of stamp.

## 5. What the loop may not do

Deploy anything; edit the public repo; call a model (fixtures only); add a runtime dependency; invent a
competitor UI detail without a URL; claim a design choice is "proven" without a source or a check.

## 6. Acceptance checks for the prototype

1. Every fixture renders, and **with colour removed** the three states differ by heading word.
2. At 320px nothing horizontal-scrolls, and every figure still shows instrument + as-of.
3. Full keyboard path: focus composer → submit → reach every citation → open Source → back.
4. No text on screen that the fixture did not supply (no invented figures, reviewers, or scope).
5. Contract validator rejects: a state the client inferred; a figure without an as-of; a citation
   outside the evidence pack.
6. `prefers-reduced-motion` removes all motion; no animation exceeds 200ms.

## 7. What would falsify the design

- A practitioner, shown `partial`, says "just answer" — the thesis fails, not just the layout.
- In the task pane, users miss that an answer is about the open document versus the law generally.
- The as-of date next to each figure reads as hedging rather than rigour (UX spec §9).
