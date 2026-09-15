# Claude.ai chat interface: what Anthropic has publicly documented

Written 2026-09-15 for PLAN_13 Phase R. Markers: **SOURCED** (URL opened this session), **INFERRED**
(my reasoning, not a source), **UNVERIFIED** (claim exists but I could not confirm it from a primary public source).
No logged-in access was used. Anything about claude.ai's *look* that has no URL below is INFERRED at best.

---

## Question

What does Anthropic publicly document about Claude.ai's chat interface? That covers layout, composer
affordances, how sources and citations are displayed, Projects, Artifacts, streaming and stop, message
actions, keyboard shortcuts and accessibility. And which of those patterns survive PLAN_13's constraints C1–C10?

## Sources checked

| Source | Result |
|---|---|
| support.claude.com: web search, artifacts, projects, upload files, research, model/effort/thinking, share chats, get started, error messages, usage-limit best practices, Opus 5 model switch, personalization, Conversation-management collection, release notes | Opened. Main evidence base |
| claude.com/blog/web-search (redirected from anthropic.com/news/web-search) | Opened |
| claude.com/blog/research (redirected from anthropic.com/news/research) | Opened |
| platform.claude.com/docs/en/build-with-claude/citations | Opened (API, not UI; relevant to the backend's span grounding) |
| support.anthropic.com/en/articles/10181068-configuring-and-using-styles | **404** |
| claude.com/blog/styles (redirected from anthropic.com/news/styles) | **404** |
| Accessibility: anthropic.com/accessibility (404), anthropic.com/legal/accessibility (404), claude.com/accessibility → 301 → claude.ai/accessibility (**403**, Cloudflare JS challenge via curl with browser UA) | No public statement read |
| Web searches: `site:support.claude.com keyboard shortcuts`; `…shortcut claude.ai web new chat sidebar`; `…stop generating response`; `…edit previous message branch conversation`; `…edit message retry`; `…accessibility screen reader`; `Anthropic accessibility statement claude.ai WCAG` | See "could not find" in Result |

## Evidence found

| id | claim | marker | URL |
|---|---|---|---|
| E1 | Web search is enabled from "the '+' button in the lower left corner of the chat window", then "Web search" in the dropdown; "A checkmark will appear next to 'Web search' when it's enabled." Team/Enterprise owners must first enable it under Organization settings > Capabilities | SOURCED | https://support.claude.com/en/articles/10684626-enable-and-use-web-search |
| E2 | Web-search answers include "Direct citations to sources", "Source links for further reading" and "Relevant quotes when appropriate". The article **does not say** whether citations render inline, on hover, or as a list | SOURCED (the gap too) | https://support.claude.com/en/articles/10684626-enable-and-use-web-search |
| E3 | Launch post (20 Mar 2025): Claude "provides direct citations so you can easily fact check sources". At launch search was toggled "in their profile settings", which has since moved to the composer "+" menu (E1) | SOURCED | https://claude.com/blog/web-search |
| E4 | Research is enabled via "the '+' button on the bottom left of your chat interface, then 'Research'". "A blue indicator will appear on the bottom of the chat window." It requires web search and a paid plan, and delivers answers "in minutes, complete with easy-to-check citations". Progress display, report layout and citation format are **not described** (updated 2 Jun 2026) | SOURCED | https://support.claude.com/en/articles/11088861-use-research-on-claude |
| E5 | Research launch post (15 Apr 2025): "toggle on the Research setting in chat". It "will provide inline citations that you can use to verify the source" and works "agentically, conducting multiple searches that build on each other" | SOURCED | https://claude.com/blog/research |
| E6 | Model and effort "appear next to the send button". Click the model name to switch, or "More models". Effort levels: Low, Medium, High, Extra high, Max. The Thinking toggle is under Effort | SOURCED | https://support.claude.com/en/articles/8664678-change-the-model-effort-and-thinking-settings |
| E7 | With thinking on, "you'll see a timer showing processing time and an expandable 'Thinking' section above the response" | SOURCED | https://support.claude.com/en/articles/8664678-change-the-model-effort-and-thinking-settings |
| E8 | Attachments: "Click the '+' button in the lower left corner of the chat box", then "Add files or photos". Drag-and-drop and clipboard paste also work. Limits: 500MB per file, up to 20 files per chat, images up to 8000×8000px, PDFs limited to 1000 pages. How attachments render is **not described** (updated 23 Jul 2026) | SOURCED | https://support.claude.com/en/articles/8241126-upload-files-to-claude |
| E9 | "click the '+' button in the lower left or type '/' to view additional options and commands". The current model is shown "below your text input (on web and desktop) or at the top of your screen (on mobile)" (updated 2 Jun 2026) | SOURCED | https://support.claude.com/en/articles/8114491-get-started-with-claude |
| E10 | Styles: presets Normal / Concise / Formal / Explanatory, selected via "Search and tools" menu → "Use style". The current style applies to "new messages, message edits, and retries". This is from a search-result snippet only; both primary pages returned 404. The menu name conflicts with the current "+" menu (E1, E4, E9), so it is likely stale | UNVERIFIED | https://support.anthropic.com/en/articles/10181068-configuring-and-using-styles (404); https://www.anthropic.com/news/styles → https://claude.com/blog/styles (404) |
| E11 | Artifacts: content is "displayed in a dedicated window to the right of the main chat". The window has a version selector. Its lower-right corner lets you view code, copy and download. "Publish" adds an artifact to the sidebar's Artifacts section. With several artifacts in one chat, "Use the chat controls (slider icon in upper right) to switch between them" | SOURCED | https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them |
| E12 | Projects: reached by hovering "over the left side of your account and click 'Projects'" or at claude.ai/projects. "You'll find the project knowledge base on the right side of your project's main page." There is a "Set project instructions" action. The Projects page has tabs "Your projects", "Organization", "Shared with you" | SOURCED | https://support.claude.com/en/articles/9519177-how-can-i-create-and-manage-projects |
| E13 | Projects with RAG use "a project knowledge search tool to retrieve relevant information from your uploaded documents", and switch on automatically as knowledge nears the context limit | SOURCED | https://support.claude.com/en/articles/11473015-retrieval-augmented-generation-rag-for-projects (search-result snippet; page not opened) |
| E14 | Share is "in the upper right corner of your chat". A shared chat shows messages sent before sharing, including artifacts; files and MCP tool-call data stay private (updated 15 Jun 2026) | SOURCED | https://support.claude.com/en/articles/10593882-share-and-unshare-chats |
| E15 | When a flagged request falls back to another model: "You'll see a notice explaining that the model switched, and the response will be labeled with the model that answered". Guidance tells the user to "edit your message and retry". This confirms edit and retry exist as user actions; it does **not** describe the controls | SOURCED | https://support.claude.com/en/articles/16049681-why-claude-switched-models-in-your-conversation-with-opus-5 |
| E16 | Error copy is written in plain language with the recovery step included, e.g. "Your message will exceed the length limit for this chat. Try attaching fewer or smaller files or starting a new conversation." No retry button, stop control or streaming behaviour is described | SOURCED | https://support.claude.com/en/articles/12466728-troubleshoot-claude-error-messages |
| E17 | A "Stop" button "in the lower right corner of the chat window" is documented **for voice mode only** | SOURCED | https://support.claude.com/en/articles/11101966-use-voice-mode (search-result snippet) |
| E18 | Conversation management is documented as delete/rename, share (link or specific people), incognito chats, chat search and memory | SOURCED | https://support.claude.com/en/collections/18031977-conversation-management |
| E19 | Release notes contain no entries on keyboard shortcuts, edit/retry, stop/streaming, sidebar redesign, citation display, accessibility or composer changes (fetch-tool summary of the page) | SOURCED (absence within one page) | https://support.claude.com/en/articles/12138966-release-notes |
| E20 | API citations: `cited_text` is extracted by the API, and "citations are guaranteed to contain valid pointers to the provided documents". Location types are `char_location`, `page_location`, `content_block_location`. `cited_text` does not count toward output tokens | SOURCED | https://platform.claude.com/docs/en/build-with-claude/citations |
| E21 | Web keyboard shortcuts: Cmd/Ctrl+Shift+O for new chat, Cmd/Ctrl+Shift+S for sidebar, Cmd/Ctrl+/ for a shortcuts panel. Third-party pages only | UNVERIFIED | https://fastshortcuts.com/shortcuts/claude/ ; https://aigeniuslab.substack.com/p/how-to-see-the-secret-claude-shortcuts |
| E22 | A claude.ai VPAT exists but reportedly requires an NDA. Single LinkedIn post, not opened | UNVERIFIED | https://www.linkedin.com/posts/sloandr_anthropic-now-has-a-vpat-for-the-claudeai-activity-7362147596133363712-6vMI |
| E23 | Answers stream token-by-token and a stop control replaces send while generating | INFERRED (common knowledge of the product; no Anthropic document found) | — |
| E24 | The empty state is a centred composer with a greeting; after the first turn the thread scrolls above a bottom-docked composer; the left rail holds new chat, projects, artifacts and recents | INFERRED (E11, E12, E18 confirm a sidebar exists; the centred empty state is undocumented) | — |
| E25 | Copy / retry / edit appear as per-message icon actions | INFERRED (E15 confirms edit and retry as actions; placement undocumented) | — |

## Evidence quality

- **Strong** for the *composer*: E1, E4, E6, E8 and E9 all agree on one "+" menu in the lower left for files, web search and Research, plus a model/effort picker next to send. They are recent (Jun–Sep 2026) and mutually consistent.
- **Strong** for *Artifacts* (right-hand window, versions, copy/download) and *Projects* (knowledge base on the right of the project page).
- **Weak** for *how citations look*. Anthropic repeatedly says citations exist and are "easy to check" and "inline" (E5), but no public page describes the visual form (chip, superscript, hover card, sources list). Anything more specific is INFERRED.
- **Absent** for streaming, the chat stop button, copy/retry/edit placement, keyboard shortcuts and an accessibility statement. The evidence is either third-party or blocked.
- **Drift noted:** the help centre's own instructions moved (web search: profile settings → "+" menu; styles: "Search and tools" → presumably "+"). Documentation dates matter; one-off screenshots in older posts are not reliable.

## Result

1. **Documented layout:** a left sidebar with Projects and Artifacts sections (E11, E12); a composer with a "+" menu lower-left and the model picker by send (E1, E6, E9); Share upper-right (E14); artifacts in a window to the right of the chat (E11). **Not documented:** the centred empty state and exact thread layout (E24, INFERRED).
2. **Composer affordances:** attachments, web search, Research, "/" commands, and model + effort + thinking. All are SOURCED. Styles are UNVERIFIED (E10).
3. **Citations:** documented as existing, verifiable, "inline" for Research, with quotes and links for web search. The rendering form is **not publicly documented**. For API use, citations are machine-extracted spans with guaranteed-valid pointers (E20).
4. **Visible reasoning and provenance:** the thinking timer + expandable section (E7) and the "labeled with the model that answered" notice (E15) are the documented ways Claude.ai shows *how* an answer was produced.
5. **Could not find (not "does not exist"):** a Claude.ai web keyboard-shortcut article, a chat stop/streaming description, a message-action (copy/retry/edit) description, or a public accessibility statement. Searches and URLs are listed above. claude.ai/accessibility exists as a route but returned 403 to non-browser access.

## Unresolved issues

- Citation rendering in Claude.ai (chip vs superscript vs sources list): only observable in-product; no public doc found.
- Whether claude.ai/accessibility holds a statement: blocked by a Cloudflare challenge (403).
- Official web keyboard shortcuts (E21): third-party only.
- Current location of styles (E10): primary pages 404.

## Recommended next action

- Accept INFERRED for undocumented visual details and do not cite them as Claude precedent in PLAN_13_ASSISTANT_UX.md.
- If citation-display precedent is needed, the founder (a logged-in human) could capture one screenshot of a web-search answer and file it with a date. That is first-hand observation, and should be labelled as such, not SOURCED.
- Re-open claude.ai/accessibility in a normal browser (human) to settle E22.

## What this means for the Ask section design

| Claude.ai pattern | Verdict | Reason (constraint) |
|---|---|---|
| Composer "+" menu hiding capabilities (files, web search, Research) (E1, E4, E8) | **Reject** as a hidden menu; **adapt** the *location* | PLAN_13 §4 requires scope, as-of and context to be *always visible above* the composer. Hiding scope behind "+" would make out-of-scope questions more likely (C1, §2 Q1). Keep one lower-left slot for the context control (this document / general) |
| Model / effort picker next to send (E6) | **Reject** | The user must not tune answering behaviour. State is server-decided (C3), and a model/effort control implies open-ended generation (C1). Replace that slot with the **as-of date** chip, the one parameter the user legitimately controls (C2) |
| Web search toggle (E1) | **Reject** | A web-grounded answer is outside the held corpus (C1). Declared-not-held bodies must refuse, not search |
| Research mode, multi-search "in minutes" (E4, E5) | **Reject** the mode; **adapt** the idea of visible work | A long agentic run does not fit a 320px Word task pane (C7). Stage captions (C4) are our visible work |
| Thinking timer + expandable "Thinking" section (E7) | **Adapt** as stage captions only; **reject** the expandable reasoning | Showing prose before the state is decided violates §2 Q3 and C4. A single-line stage caption ("checking the source…") conveys the same "work is happening" without narrative |
| Citations that are "easy to check", inline (E2, E5) | **Keep** the principle; **adapt** the form | C2 demands instrument + as-of *next to the figure without a click*. That is stricter than any documented Claude pattern. Hover-only or collapsed source lists fail C2 and the 320px check (C7) |
| API citations with guaranteed-valid pointers (E20) | **Keep** (backend, contract) | Matches the contract rule "reject a citation outside the evidence pack" (PLAN_13 §6.5). The UI can trust span offsets; the backend already depends on `char_location` (CLAUDE.md) |
| "Response labeled with the model that answered" + switch notice (E15) | **Adapt** | Per-turn provenance is the right pattern for §2 Q4: label each turn with its evidence pack and as-of stamp, not with a model name (C1 makes the model irrelevant to the user) |
| Artifacts window to the right of chat, with versions and copy (E11) | **Adapt** as the **Source panel** (web only) | The right panel is a documented Claude pattern and the Harvey-style Source panel of §4. Its content is verbatim source text and the currency strip, never generated content. In the task pane (C7) it becomes an in-flow expand, not a side window |
| Projects with a knowledge base on the right (E12, E13) | **Reject** for v1 | Users do not upload a knowledge base; the corpus is ours and scope is declared in `checker/scope.py` (C1). The Word document *is* the context (§2 Q7) |
| Plain-language error copy with the recovery step (E16) | **Keep** | Model for `out_of_scope` copy: say what we hold, what we don't, what to do next. It reads as competence, not failure (§2 Q1, C5) |
| Share, incognito, chat search, memory (E14, E18) | **Reject** for v1 | §2 Q8: no named user need yet; memory specifically invites context drift across turns (§2 Q4) |
| Edit message and retry (E15) | **Adapt**: edit-and-resubmit only; no "retry" | Retry implies a different answer might come back, which contradicts server-decided state (C3). Editing the question is legitimate and produces a new grounded turn |
| Voice-mode Stop button (E17) / stop while streaming (E23, INFERRED) | **Adapt** as "Cancel" during stage captions | No tokens stream (C4, §2 Q3), so there is nothing to "stop mid-answer". A cancel control during retrieval is still needed for keyboard users (PLAN_13 §6.3) |
| Centred composer empty state, left rail (E24, INFERRED) | **Keep** for web, marked as INFERRED precedent | Already the §4 hypothesis. Cite it as observed convention, not documented fact. The rail collapses entirely in the task pane (C7) |
| Streaming token-by-token (E23, INFERRED) | **Reject** | Prose before verification (C3, C4, §2 Q3) |
| Visual effects (none documented) | n/a | C6 already binds: the mix comes from layout and type, not effects. Nothing sourced here argues otherwise |
