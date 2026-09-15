# R-UX1 — Harvey Assistant: what the prompt surface publicly looks like

Written 2026-09-15 for PLAN_13 Phase R. Extends [HARVEY_DOCUMENT_INTAKE.md](../HARVEY_DOCUMENT_INTAKE.md)
(cited below as **HDI** + row id); nothing sourced there is re-fetched or repeated here except where a
row is needed to reason about the UI. All pages fetched 2026-09-15.

Markers: **SOURCED** (URL opened this session; quote is from the page) · **INFERRED** (my reasoning) ·
**UNVERIFIED** (search snippet, login-walled page, or no page found). A UI detail with no URL is never
better than INFERRED.

Reading discipline: a Harvey blog post is the vendor describing its product. It says what exists, not
how it looks in pixels, and **nothing below was observed in the running product** — `app.harvey.ai`
needs a login and was not touched. Screenshots and GIFs on the pages were not readable by the fetch
tool; only their alt text / captions were.

---

## Question

What does Harvey's Assistant look like and do at the prompt surface — page layout (sidebar, thread,
panels), composer (source selectors, attach, modes), answer rendering, citation display, history and
threads, sharing, the Word add-in pane, and visual language — and which of those patterns survive
PLAN_13 constraints C1–C10?

## Sources checked

| Source | Type / date | Accessed? |
|---|---|---|
| https://www.harvey.ai/platform/assistant | product page | yes — serves the **Agents** page ("Harvey Agents \| Delegate the Work. Own the Judgment."); no Assistant UI detail (same as HDI) |
| https://www.harvey.ai/blog/introducing-the-next-version-of-assistant | vendor blog, 20 Aug 2024 | yes |
| https://www.harvey.ai/blog/integrating-deep-research-into-harvey | engineering blog, 3 Jul 2025 | yes |
| https://www.harvey.ai/blog/introducing-harvey-deep-research | vendor blog, 4 Nov 2025 | yes (demo video not transcribed) |
| https://www.harvey.ai/blog/the-brief-november-2025 | release summary, 6 Nov 2025 | yes |
| https://www.harvey.ai/blog/how-we-approach-design-at-harvey | design blog, 14 Nov 2025 | yes |
| https://www.harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence | engineering blog, 10 Dec 2025 | yes |
| https://www.harvey.ai/blog/raising-the-bar-with-harvey | release summary, 11 Dec 2025 | yes |
| https://www.harvey.ai/blog/top-5-product-releases-of-2025 | vendor blog, 30 Dec 2025 | yes |
| https://www.harvey.ai/blog/rebuilding-harveys-design-system-from-the-ground-up | design blog, 16 Jan 2026 | yes |
| https://www.harvey.ai/blog/the-brief-march-2026 · -april-2026 · -june-2026 · -july-2026 | release summaries, 10 Mar / 9 Apr / 11 Jun / 17 Jul 2026 | yes (re-read for UI items only) |
| https://www.harvey.ai/blog/shared-spaces-analytics-and-management | vendor blog, 3 Jun 2026 | yes |
| https://www.harvey.ai/blog/how-harvey-integrates-with-microsoft-365-applications | vendor blog, 22 Oct 2025 | yes (re-read for pane UI) |
| https://www.harvey.ai/blog/announcing-harvey-integrations-with-microsoft | vendor blog, 5 Dec 2024 | yes — one sentence, no UI |
| https://www.harvey.ai/platform/word-add-in | product page | yes |
| https://www.harvey.ai/press | press kit | yes — guidelines only in a download zip; not downloaded |
| https://www.harvey.ai/design-system | — | **404** (URL came from a search result; a 404 on it is evidence of nothing) |
| https://www.harvey.ai/ + its `/_next/static/immutable/chunks/*.css` | marketing site CSS | yes (curl, browser UA) |
| help.harvey.ai: `/articles/getting-started-with-assist-and-draft-modes`, `/release-notes/harvey-for-microsoft-word-now-available` (and others surfaced by search: `in-document-citations`, `ask-lexisnexis`, `shared-spaces`, `flexible-query-organization`, `improved-magic-prompt`, `editing-files-in-assistant`) | help centre | **Not accessed** — curl returns `307 → /auth/login?returnTo=…`. Anything from these appears only as UNVERIFIED |
| academy.harvey.ai demo pages (`/demo-shared-spaces`, `/how-to-use-shared-spaces-april-1/482691`) | training videos | **403** to curl. Not bypassed. UNVERIFIED |
| `app.harvey.ai/wordaddin/` | the add-in app itself | not opened (product app, auth) |

WebSearch queries run (all `site:harvey.ai`): Assistant redesign citations side panel; Deep Research
launch; design system / brand / typography; Word add-in assistant pane; share thread history Shared
Spaces; the exact phrase "clearer distinction between content and sidebar panels"; citation hover
preview / document viewer; "Magic Prompt". No third-party review site used.

**Could not find (what was searched):** any public Harvey page describing (a) the page grid of Assistant
(left rail widths, panel order), (b) the visual form of an inline citation marker in the UI, (c) how a
Deep Analysis report's headings are structured, (d) the Word pane's tab layout, (e) any "I could not
find this" / refusal state in Assistant. Searched via the queries above and the pages listed. Not
finding them is not evidence they don't exist; most of it is plausibly in the login-walled help centre
or in the untranscribed videos.

---

## Evidence found

### E. Layout — sidebar, thread, panels

| id | Claim | Marker | URL |
|---|---|---|---|
| E1 | Dec 2025: "refreshed Harvey's design to create a clearer distinction between content and sidebar panels like Assistant threads and drafts, added new icons, and updated panel headers" | SOURCED | https://www.harvey.ai/blog/raising-the-bar-with-harvey |
| E2 | So the Assistant screen has at least: a content area, and **sidebar panels** that hold "Assistant threads" and "drafts", each with a panel header | INFERRED from E1 (the wording names the panels, not their position) | — |
| E3 | A separate **sources panel** exists: "A redesigned sources panel makes it easier to navigate, search, and interpret citations — with clearer icons, a new search bar, and auto-updating sources that stay aligned with your current thread view" | SOURCED (6 Nov 2025) | https://www.harvey.ai/blog/the-brief-november-2025 |
| E4 | "auto-updating sources that stay aligned with your current thread view" means the sources panel follows scroll/position in the thread, i.e. it shows the sources of the turn in view, not of the whole thread | INFERRED from E3's wording; not shown on any page read | — |
| E5 | Draft Mode revises long-form output with "Show Edits" to "track changes between revisions" and "highlight specific text for focused revisions" | SOURCED (Aug 2024) | https://www.harvey.ai/blog/introducing-the-next-version-of-assistant |
| E6 | Apr 2026: "Edit contracts, memos, and transaction documents in Microsoft Word format directly in Assistant, preserving original formatting" | SOURCED | https://www.harvey.ai/blog/the-brief-april-2026 |
| E7 | A "side-by-side document viewer" for generated files | UNVERIFIED — search snippet of a help-centre page only | (help.harvey.ai, not opened) |
| E8 | Harvey right-rail = sources, left-rail = history (the layout PLAN_13 §4 assumes) | **UNVERIFIED as to side.** E1/E3 prove the panels exist; no public page read says which side each sits on | — |

### F. Composer — sources, attach, modes

| id | Claim | Marker | URL |
|---|---|---|---|
| F1 | Composer contents named by Harvey: "the full power of Harvey's Assistant composer, including magic prompt, deep research, prompt library, and voice-to-prompt"; plus "@mention … to directly tag the file or source in Assistant" | SOURCED (Dec 2025) | https://www.harvey.ai/blog/raising-the-bar-with-harvey |
| F2 | Two modes at launch: "Assist Mode is optimized for summaries, analyses, and searches"; "Draft Mode is purpose-built for generating and revising detailed long-form content". The GIF is captioned "assistant toggle" | SOURCED (Aug 2024). Whether Assist/Draft still exist as a toggle in 2026 is UNVERIFIED | https://www.harvey.ai/blog/introducing-the-next-version-of-assistant |
| F3 | Knowledge sources are selected in the composer: "Select and refine knowledge sources in Assistant with greater clarity. Source details now highlight descriptions and data source information"; "Query across two sources at once" | SOURCED (Nov 2025) | https://www.harvey.ai/blog/the-brief-november-2025 |
| F4 | SCC Online is one such selectable source for Indian research (Jun 2026) | SOURCED (HDI B12; re-read) | https://www.harvey.ai/blog/the-brief-june-2026 |
| F5 | **Model Selector** in Assistant, Vault, Agent Builder, and in Harvey for Word | SOURCED | https://www.harvey.ai/blog/the-brief-march-2026 · https://www.harvey.ai/blog/the-brief-june-2026 |
| F6 | Magic Prompt ("Improve"): rewrites the user's prompt before submit; "Quickly improve your prompts with smarter, more targeted suggestions" (Apr 2026); on mobile Jun/Jul 2026 | SOURCED for existence and the quoted text. That the button is labelled "Improve" is UNVERIFIED (help-centre snippet) | https://www.harvey.ai/blog/the-brief-april-2026 · https://www.harvey.ai/blog/the-brief-july-2026 |
| F7 | Suggestions inside the thread: "Workflow agent suggestions, file upload prompts, and deep analysis options surfaced directly in your Assistant thread when they're relevant" | SOURCED (Mar 2026) | https://www.harvey.ai/blog/the-brief-march-2026 |
| F8 | Deep analysis is "Harvey's most advanced mode for complex, multi-source legal analysis and reports"; it "plans a research strategy … and resurfaces in minutes with a citation-backed report". How it is invoked (toggle vs button) is not stated in text | SOURCED for the quotes; invocation form UNVERIFIED (only in the untranscribed video) | https://www.harvey.ai/blog/introducing-harvey-deep-research |
| F9 | "Thinking states": "we provide users with visibility into an agent's plan and how decisions are made with the user in the loop"; users can "intervene at any step" | SOURCED (Jul 2025, engineering framing) | https://www.harvey.ai/blog/integrating-deep-research-into-harvey |
| F10 | Agents: "Preview the plan, adjust the scope, and approve work before Harvey begins" | SOURCED (HDI C7) | https://www.harvey.ai/platform/workflow-agents |
| F11 | Custom Writing Styles applied to outputs | SOURCED (Apr 2026) | https://www.harvey.ai/blog/the-brief-april-2026 |
| F12 | Prompt limits (4,000 chars with a file / 20,000 without) and file caps | Already in HDI A11/A12 — not repeated | — |

### G. Answer rendering and citations

| id | Claim | Marker | URL |
|---|---|---|---|
| G1 | API shape: answers carry `[N]` markers resolving to `sources[]` with document name, page, quoted text | SOURCED in HDI C1/C4 — not repeated | https://developers.harvey.ai/api-reference/completion/completion.md |
| G2 | The UI renders `[N]` as numbered inline markers / footnotes | INFERRED from G1 + the "footnotes" snippet in G4. No public screenshot read confirms the glyph | — |
| G3 | Citations are navigated and searched in a **panel**, not only inline (E3) | SOURCED | https://www.harvey.ai/blog/the-brief-november-2025 |
| G4 | "hover over a citation to preview the data source … click View Reference to open the full context"; on the LexisNexis path "hover over footnotes … to preview source content" | UNVERIFIED — help-centre snippets (`ask-lexisnexis`, general Assistant help) behind login | (help.harvey.ai, not opened) |
| G5 | Apr 2026 (review tables): "transparent reasoning, sentence-level citations, stronger formatting adherence (e.g. bold text, bulleted lists)" | SOURCED — scoped to **review table cells**, not stated for Assistant answers | https://www.harvey.ai/blog/the-brief-april-2026 |
| G6 | Design principle on trust: "Users can backtrack through the logic the AI applied, verify the sources and data used, and confirm that citations are accurate" | SOURCED (Nov 2025) — a principle, not a UI spec | https://www.harvey.ai/blog/how-we-approach-design-at-harvey |
| G7 | Deep analysis output: "a citation-backed report detailing key context, timelines, stakeholders, and next steps" | SOURCED — the only public hint at report structure | https://www.harvey.ai/blog/introducing-harvey-deep-research |
| G8 | Agentic search yields "responses based on verified, current data from multiple sources that can be traced back to specific documents or database entries". The page says nothing about how "not found" is displayed | SOURCED (quote); no refusal UI found | https://www.harvey.ai/blog/how-agentic-search-unlocks-legal-research-intelligence |
| G9 | Aug 2024 vendor metrics: "reduced hallucinations by 60%", "improved the accuracy of cited sources by 23%", "improved time to first word by 80%" | SOURCED as vendor-reported; method not stated | https://www.harvey.ai/blog/introducing-the-next-version-of-assistant |
| G10 | "time to first word" as a headline metric implies Assistant **streams** prose as it is generated | INFERRED from G9 | — |
| G11 | An answer state distinct from an answer (e.g. abstained / out of scope / partial) in Assistant | **Not found** on any page listed. Not evidence of absence | INFERRED from pages read |

### H. History, threads, sharing

| id | Claim | Marker | URL |
|---|---|---|---|
| H1 | Threads can be moved "in and out of vaults", with "more granular sharing controls" | SOURCED (Dec 2025) | https://www.harvey.ai/blog/raising-the-bar-with-harvey |
| H2 | One "redesigned Share Modal" across "vaults, threads, workflow agents, playbooks, and review tables" with "clearer recipient search, explicit internal and external labeling, and transparent, consistent permission controls"; admins see "a full activity log" | SOURCED (Jun 2026) | https://www.harvey.ai/blog/shared-spaces-analytics-and-management |
| H3 | Moving a thread into a project makes it visible to project members, "available both in History and in Vault" | UNVERIFIED — help-centre snippet (`flexible-query-organization`) | (help.harvey.ai, not opened) |
| H4 | Word add-in "History": "Access important context in the form of previous Ask, Edit, and Playbook interactions directly from Word documents" | SOURCED (Oct 2025) | https://www.harvey.ai/blog/how-harvey-integrates-with-microsoft-365-applications |
| H5 | Search over thread history in Assistant | Not found on any page read | INFERRED from pages read |

### W. Word add-in assistant pane

| id | Claim | Marker | URL |
|---|---|---|---|
| W1 | Interaction verbs in the pane: **Ask, Edit, Playbook** (from the History description, H4) | SOURCED as words; that they are **tabs** is INFERRED | https://www.harvey.ai/blog/how-harvey-integrates-with-microsoft-365-applications |
| W2 | Pane features: Magic Prompt, Prompt Library, History, Web Search, Fill and Edit Tables, Translate, Redact ("coming soon" at the time) | SOURCED (Oct 2025) | https://www.harvey.ai/blog/how-harvey-integrates-with-microsoft-365-applications |
| W3 | "Draft and edit documents using natural language prompts and proven precedents, drawing from Vault, your DMS, and other knowledge sources"; playbooks "with complete visibility into rule updates, redlines, and version history" | SOURCED (product page) | https://www.harvey.ai/platform/word-add-in |
| W4 | Writing Styles and Model Selector inside Harvey for Word (Jun 2026); dictation in Word/Outlook add-ins (Jul 2026) | SOURCED | https://www.harvey.ai/blog/the-brief-june-2026 · https://www.harvey.ai/blog/the-brief-july-2026 |
| W5 | "you'll see your draft alongside the Assist panel, where you can make direct edits, highlight text for specific changes"; redline over "specific text or over the full document" | UNVERIFIED — help-centre snippets | (help.harvey.ai, not opened) |
| W6 | The pane shows citations, and in what form | **Not found** on any public page read | — |
| W7 | Add-in components are adapted "in ways that feel native to each platform" | SOURCED (Jan 2026) | https://www.harvey.ai/blog/rebuilding-harveys-design-system-from-the-ground-up |
| W8 | Harvey ships the pane with composer + model selector + prompt library + history in a task-pane width, i.e. it treats the pane as a full Assistant, not a reduced one | INFERRED from W2/W4 | — |

### T. Typography and visual language

| id | Claim | Marker | URL |
|---|---|---|---|
| T1 | Principles: "Design With Domain Awareness … deeply familiar, yet unmistakably modern"; "Make the Complex Feel Effortless"; "Design With Intention: Every visual and structural choice is deliberate, from the hierarchy of text to the rhythm of motion" | SOURCED | https://www.harvey.ai/blog/how-we-approach-design-at-harvey |
| T2 | Token system: role-based tokens (e.g. `foreground-base`) prefixed `hy-`, used via Tailwind (`bg-hy-bg-base`, `text-hy-fg-subtle`); neutrals with "hue around 90° for a consistent warm-neutral feel", "higher chroma in light tones for cleaner whites, lower chroma in dark tones to avoid brown shifts"; WCAG contrast "across both light and dark modes"; prior codebase mixed "legacy components, Shadcn components, and custom one-off implementations" | SOURCED | https://www.harvey.ai/blog/rebuilding-harveys-design-system-from-the-ground-up |
| T3 | Marketing-site CSS declares two families: `HarveySansFont` (file `HarveySansDiatypeVariable…woff2`) and `HarveySerifFont` (Regular + Italic, `subset_HarveySerif_…woff2`), both `font-display:swap`, Arial metric-adjusted fallbacks | SOURCED (fetched CSS, www.harvey.ai) | https://www.harvey.ai/ |
| T4 | The sans is a custom cut of Dinamo's ABC Diatype | INFERRED from the filename only | — |
| T5 | The product app uses the same serif + sans pairing | **UNVERIFIED** — T3 is the marketing site; the app is login-walled | — |
| T6 | Radius, shadow, spacing and motion values | Not published on any page read (the design-system post names none; `/design-system` 404) | — |

---

## Evidence quality

- **Best available:** dated release summaries ("The Brief", "Raising the Bar") and the two design posts.
  They name surfaces and controls precisely (E1, E3, F1, F3, H2, T2) but describe *existence*, not
  *appearance*. They are marketing, written to announce, and never show a failure state.
- **Hard evidence of shape, not look:** the API citation schema (HDI C1/C4) and the site CSS (T3).
- **The layer that would answer "what does it look like" is closed to us:** help centre (307 → login),
  Academy videos (403), the app itself. Every detail sourced only there (E7, G4, H3, W5) is UNVERIFIED.
- **Dating:** Assist/Draft (F2) is Aug 2024 and may be superseded by the Dec 2025 composer (F1). Treat
  the Dec 2025 – Jul 2026 posts as current.
- **No independent look at the UI** (press screenshots, conference talk transcripts) was found in the
  searches run; none was sought beyond harvey.ai, which is a limit of this pass.

## Result

1. **Layout.** Harvey's Assistant is a thread in a content area, with **named side panels** — threads,
   drafts (E1) and a **sources panel** that is searchable and tracks the turn in view (E3). Draft work
   opens as an editable document with tracked "Show Edits" (E5, E6). Which side each panel sits on is
   not publicly documented (E8).
2. **Composer.** A dense, capability-rich composer: knowledge-source selection with descriptions,
   up to two sources at once (F3), model selector (F5), Magic Prompt rewrite (F6), @mention of files or
   sources (F1), prompt library, voice (F1), deep research/analysis (F1, F8), and in-thread suggestions
   of workflows, uploads and deep analysis (F7). SOURCED.
3. **Answers and citations.** Numbered source references backed by page + quote (HDI), surfaced in a
   panel (E3); hover preview is UNVERIFIED (G4). Sentence-level citations are sourced only for review
   table cells (G5). Streaming is INFERRED from the "time to first word" metric (G10). **No public page
   read shows an abstention, partial, or out-of-scope answer state** (G11).
4. **Deep analysis.** Plan → agentic search → "citation-backed report" (F8, G7), with "thinking states"
   exposing the plan and allowing intervention (F9). Report heading structure is not published.
5. **Threads and sharing.** Threads live in History, move into vaults/projects, and share through one
   Share Modal with internal/external labels and permissions (H1, H2). Thread search: not found (H5).
6. **Word pane.** A near-full Assistant in the task pane: Ask / Edit / Playbook history, prompt library,
   Magic Prompt, model selector, writing styles, dictation, web search, table fill, translate (W1–W4).
   How citations appear in the pane is not publicly documented (W6).
7. **Visual language.** Warm-neutral palette at hue ~90°, role tokens, light + dark (T2); a custom
   serif + custom sans (likely Diatype) pairing on the public site (T3, T4). Harvey's stated aim —
   "deeply familiar, yet unmistakably modern" — maps onto a legal-document serif paired with a
   technical sans (INFERRED).

## Unresolved issues

- Panel positions, widths and collapse behaviour (E8); the inline citation glyph (G2); hover preview (G4).
- Whether Assist/Draft is still a mode toggle (F2), and how deep analysis is switched on (F8).
- Whether Assistant ever returns a *non-answer* state, and how it looks (G11) — the single most
  relevant gap for PlacedOn, and unanswerable from public pages.
- Citation display in the Word pane (W6).
- Whether the product app uses the site's serif/sans pairing (T5); radius/shadow/motion (T6).
- The press-kit zip (brand guidelines) was not downloaded or opened.

## Recommended next action

1. Treat E8/G2/G4/W6 as open and **do not write them into PLAN_13 as Harvey facts**.
2. If a Harvey demo or trial becomes available through a legitimate channel, capture: panel layout at
   1440 and the Word pane at ~350px; one answer with citations hovered; one question Harvey cannot
   answer; one deep-analysis run from start to report.
3. Search for public conference talks and press screenshots (Legalweek, Microsoft Build, YouTube demos
   published by Harvey) — not done in this pass.
4. Cross-read with the Claude.ai UI research for the composer and empty-state patterns.

---

## What this means for the Ask section design

Each verdict is INFERRED design reasoning resting on the rows cited.

| Harvey pattern (row) | Verdict | Reason, tied to C1–C10 |
|---|---|---|
| **Separate sources panel** tied to the turn in view (E3, E4) | **Adapt** | Keep the panel for verbatim text and the currency strip, and make it follow the turn in view — that answers §2 Q4 (each turn has its own evidence). But C2 requires instrument + as-of **next to the figure**, so the panel can never be the only place those appear. Harvey's panel is where citations are *interpreted*; ours is where they are *inspected* |
| **Knowledge-source selector** with descriptions (F3) | **Adapt → scope line** | Harvey lets the user pick sources; our scope is fixed by `checker/scope.py` and only one body is held. A picker would invite choosing a DECLARED body and imply we hold it (C1, C3). Show scope as an always-visible, read-only statement ("Companies Act 2013 — held") with the declared bodies discoverable, per §4 |
| **@mention a file/source** (F1) | **Adapt, narrowly** | Maps to §2 Q7: the context toggle "this document / law in general". One explicit control, not free @-tagging, so the difference is unmissable in the task pane (C7) |
| **Model selector** (F5) | **Reject** | Model choice is not a user decision in a grounded system; it implies answers vary by model, which undercuts server-decided state (C3), and C8 says the model is not wired |
| **Magic Prompt rewrite** (F6) | **Reject as a rewrite; adapt as scope feedback** | Rewriting a question before submit changes what was asked and hides it (C1). The useful kernel is pre-submit help: suggested questions from `checker/bundles.py` (§4) and, later, a pre-submit hint when the question names an undeclared body — which answers §2 Q1 |
| **Deep research / deep analysis mode** (F8, G7) | **Reject for v1** | An open-ended multi-source report is the general-chatbot behaviour C1 rules out, and there is one held body to research. Nothing for a mode to switch |
| **Thinking states / visible plan** (F9, F10) | **Adapt → stage captions** | Harvey's instinct (show the work before the result) is right. C4 constrains the form: stage captions ("retrieving → checking the source → verifying dates"), never partial prose or a plan the user edits |
| **Streamed prose, "time to first word"** (G9, G10) | **Reject** | Streaming shows text before the state is decided. §2 Q3 and C3: nothing narrative before `answered`/`partial`/`out_of_scope` arrives. We trade time-to-first-word for time-to-verified-state, and should say so in the design spec |
| **Numbered inline markers → page + quote** (G1, G2) | **Keep, and add as-of** | The page+quote pair is the user expectation Harvey set (HDI item 2). Keep the marker; the figure it attaches to also carries instrument + as-of inline (C2). The marker opens the source panel |
| **No visible abstention state** (G11) | **Differentiate** | Publicly, Harvey shows no `partial`/`out_of_scope` equivalent. Ours is a first-class, non-red, heading-worded state (C3, C5) and is where the product earns trust — §2 Q1 |
| **In-thread suggestions** of workflows, uploads, deep analysis (F7) | **Reject for v1** | Upselling capabilities mid-thread widens scope (C1) and adds chrome to a 320px pane (C7). Revisit only for "this question is out of scope; here is what we hold" |
| **Threads/drafts sidebar, History** (E1, H4) | **Adapt → collapsible history rail on web; History list in pane** | Harvey uses history on web and in the Word pane. A plain list of past questions, each re-opened with its original as-of stamp, earns its place (§2 Q4). History *search* (H5) is cut for v1, per §2 Q8 — no named need |
| **Share Modal with permissions** (H2) | **Reject for v1** | No named user need yet (§2 Q8); sharing a grounded answer later would need to carry its as-of and evidence pack immutably, which is a contract question (C8) before it is a UI one |
| **Draft mode / Show Edits / edit Word in Assistant** (E5, E6, W3) | **Reject** | Generation is commoditised and out of the wedge (CLAUDE.md "audit layer, not generator"; C1) |
| **Full Assistant inside the Word pane** (W2, W4, W8) | **Adapt, subtract** | Harvey's pane carries composer, model selector, library, history. C7 makes the pane the v1 surface, so it must be complete for *our* job: scope line, as-of, context toggle, composer, answer with inline as-of, source drawer. Every Harvey extra listed above is rejected, which is what makes 320px feasible |
| **Warm-neutral palette, role tokens, light+dark** (T2) | **Keep the method** | Role-based tokens and a warm neutral fit C6's quiet authority; our semantic tokens (caution `#8B4513`, one accent) slot into the same pattern. Harvey's palette values are not published, so nothing is copied |
| **Serif + sans pairing** (T3, T4) | **Adapt** | A document serif for answer prose and quoted statute text, a sans for chrome, reads as legal without effects (C6). Use our own faces from `DESIGN_SYSTEM.md`; do not imitate Harvey's custom fonts |
| **Radius, shadow, motion** (T6) | **No input** | Not published; C6 already decides it (≤ 4px, no shadows, ≤ 200ms) |
