# Design brief: the Ask section (critic's synthesis of Phase R)

Written 2026-09-15 for PLAN_13 Phase D. The three design agents (*Harvey-leaning*, *Claude-leaning*,
*evidence-first native*) work from this file.

Markers: **SOURCED** means a URL opened, or a file:line read, by a researcher or by me; the row names who.
**INFERRED** means reasoning. **UNVERIFIED** means a snippet, a login-walled page, or a downgraded row.
Row ids refer to the four research files: **H** = [HARVEY_ASSISTANT_UI.md](HARVEY_ASSISTANT_UI.md),
**C** = [CLAUDE_CHAT_UI.md](CLAUDE_CHAT_UI.md), **L** = [LEGAL_AI_CHAT_PATTERNS.md](LEGAL_AI_CHAT_PATTERNS.md),
**I** = [INTERNAL_ASK_AUDIT.md](INTERNAL_ASK_AUDIT.md). So `H-E3` is row E3 of the Harvey file.
Every verdict in this brief is INFERRED design reasoning resting on the rows it cites.

---

## Question

What does Phase R actually establish, and not establish, for the three design directions? That covers:
(1) a verdict on every Harvey and Claude.ai pattern against C1–C10;
(2) the evidence on each harsh question in PLAN_13 §2, with what stays open;
(3) the non-negotiables and the draft `/v1/ask` fields a design may rely on;
(4) the strongest case for and against the founder's "Harvey + Claude look";
(5) the gaps.

## Sources checked

- The five input files: PLAN_13 and the four research files above.
- The four adversarial source-check reports, dated 2026-09-15:
  - H: 7 claims checked, 0 refuted.
  - C: 6 checked, 0 refuted.
  - L: 7 checked, 1 downgraded (A2).
  - I: 10 checked, 1 downgraded (E13).
- `checker/evidence_pack.py:432-457, 491-504`, which I re-read to settle the contract defects the I-check raised.
- Not re-fetched: no competitor URL. I rely on the checks above, and nothing here adds a new external claim.

---

## Evidence found

These rows are the critic's findings. Each is a correction or a conflict between files that changes how the
research may be used.

| id | claim | marker | URL / location |
|---|---|---|---|
| K1 | Harvey rows E1, E3, F1, F3, F9, G9 and T2 say what the file claims, word for word. The check also notes that E3's page goes on to say "…in both the source picklist and filter chips", which the file omits | SOURCED (H-check) | https://www.harvey.ai/blog/raising-the-bar-with-harvey · https://www.harvey.ai/blog/the-brief-november-2025 · https://www.harvey.ai/blog/integrating-deep-research-into-harvey · https://www.harvey.ai/blog/introducing-the-next-version-of-assistant · https://www.harvey.ai/blog/rebuilding-harveys-design-system-from-the-ground-up |
| K2 | Vendor pages show that a feature **exists**. None shows what Harvey's running product looks like or how it behaves | INFERRED (H file, and the H-check agrees) | — |
| K3 | C-E7 puts a paraphrase in quotation marks. The page's words are: 'A "Thinking" indicator with a timer…' and 'An expandable "Thinking" section above Claude's response'. The substance holds. The page also says thinking cannot be turned off on Opus 5 | SOURCED (C-check) | https://support.claude.com/en/articles/8664678-change-the-model-effort-and-thinking-settings |
| K4 | C-E13 (Projects RAG) and C-E17 (the voice-mode Stop button) are marked SOURCED but rest on search snippets from pages nobody opened. **This brief treats both as UNVERIFIED.** No verdict below depends on either one alone | UNVERIFIED | https://support.claude.com/en/articles/11473015-retrieval-augmented-generation-rag-for-projects · https://support.claude.com/en/articles/11101966-use-voice-mode |
| K5 | L-A2 is downgraded. In Westlaw AI-AR, a bracketed number opens a side panel that lists "all relevant resources and snippets". It does not open the resource itself in a panel. L verdict #4 and L Result 2 still cite A2. The inline-marker-plus-side-list layout still has **one** SOURCED legal precedent: vLex Vincent (L-A16) | UNVERIFIED (A2) · SOURCED (A16) | https://www.thomsonreuters.com/en-ca/help/cocounsel/legal/skills/understanding-cocounsel-skills/ai-assisted-research · https://support.vlex.com/vincent-by-vlex/vincent/getting-started-with-vincent/your-first-analysis-asking-a-research-question |
| K6 | L's evidence-quality note calls Sun et al. a "CHI extended abstract". The arXiv page gives no venue | UNVERIFIED (venue) | https://arxiv.org/abs/2606.25489 |
| K7 | I-E13 is downgraded. `checker/retrieval_eval.py` does not import the cascade. The other importer is `checker/metric_policy.py:189,255`, in gate/test code. The conclusion that matters still holds: no answer path (claim_verifier, model_adapter, reasoning, orchestrator) uses the cascade | SOURCED (I-check) | `checker/ground_span.py:27`; `checker/metric_policy.py:189,255` |
| K8 | Contract defect 1: the `partial` draft has a top-level `coverage` key (the coverage frame), yet I's recommended action 1 has the validator reject any `coverage` field. As drafted, the contract fails its own validator | SOURCED (I-check; I §R2 and its recommended action 1) | `docs/research/ux/INTERNAL_ASK_AUDIT.md` R2 |
| K9 | Contract defect 2: the envelope puts `stages` (orchestrator steps) in every state. But only the document path runs the orchestrator (I-E5), so a general-context turn has **no** stages | SOURCED (I-check) | `checker/orchestrator.py:200-204` |
| K10 | Contract defect 3: the pack's `query` is at `evidence_pack.py:494`, not 497. A provision's `to_dict` has **no** `corpus_fetched`. The date sits in `sources[].retrieved_on`, and at pack level in `as_of`. The same `to_dict` also exposes `evidence_state_servable`, `evidence_statement` and `sources[].human_reviewed` | SOURCED (re-read by me) | `checker/evidence_pack.py:432-457, 491-504` |
| K11 | The comment at `prescribed_thresholds.py:243-245` still says "CLAIM PENDING ATTESTATION … unservable". The state is computed at runtime, and it measured servable on 2026-09-15 (I-E23). The comment is stale, and fixtures must not rely on it or on today's value (I-U7) | SOURCED (I-check) | `checker/prescribed_thresholds.py:180-209, 230, 243-245` |
| K12 | **Conflict between files.** H recommends a history rail on the web and a History list in the pane (H verdict table). I rejects follow-up threads for now, because no conversation state exists (I-E34) and the session release guard is verbatim-only (I-E32). C rejects memory and chat search. The research files do not agree on history | INFERRED from SOURCED rows | H, I, C verdict tables |
| K13 | **Conflict between files.** L verdict #3 adapts a "This document / General" switch, but I finds that "general" has no driver: the orchestrator needs a document date (I-E5), and only `retrieve()` runs without one (I-E18). A General mode today can return source lookups, not decisions | SOURCED (I-E5, I-E18) + INFERRED | `checker/orchestrator.py:200-204`; `checker/retrieve.py:42-44` |
| K14 | **Conflict between documents.** The UX spec's out_of_scope heading "Outside what Placedon covers" is false for DECLARED bodies. For those bodies, `refusal_for()` says the body "is within scope" (I-U3, I-E29) | SOURCED (I) | `checker/scope.py:202-205` |
| K15 | None of the four files contains user research with Indian practitioners (Company Secretaries, firm lawyers). Every user-need claim below is INFERRED | INFERRED (absence across files) | — |

## Evidence quality

- **Competitor look:** weak. Harvey's help centre, Academy videos and app are all closed (H Sources). Claude's citation form is undocumented (C-E2). The layout details a "look" depends on are UNVERIFIED or INFERRED: panel sides (H-E8), the citation glyph (H-G2), hover preview (H-G4), Claude's centred empty state (C-E24) and streaming (C-E23).
- **Competitor existence of features:** moderate to strong. The rows are dated, first-party and checked (K1, C-check).
- **Trust/HCI:** moderate. The studies are peer-reviewed lab work, but none uses legal practitioners (L Evidence quality). Streaming has no evidence at all (L-C12).
- **Internal audit:** strong, as file:line reads and measured runs, with three contract defects (K8–K10) and one downgraded row (K7). Measured values can change as instruments are attested (I-U7).
- **Users:** none (K15). This is the weakest link. PLAN_13 §7's falsifiers need real conversations.

---

## Result

### 1. Pattern table: every Harvey and Claude.ai pattern found

Verdicts are INFERRED. Where this brief changes a researcher's verdict, the Note column says so.

#### Harvey

| # | Pattern | Evidence | Verdict | Reason (C1–C10) | Note |
|---|---|---|---|---|---|
| H1 | Separate **sources panel**, searchable | H-E3 SOURCED | **ADAPT** | It inspects verbatim text and the currency strip. It can never be the only place instrument and as-of appear (C2). At 320px it becomes an in-flow section (C7) | "Tracks the turn in view" is H-E4, INFERRED. Adopt it on its merits, not as a Harvey fact |
| H2 | Numbered inline markers → page + quote | H-G1 SOURCED via HDI; glyph H-G2 INFERRED | **ADAPT** | A bare `[N]` fails C2. The figure itself carries instrument + as-of, and the marker only points into the panel | The H researcher said KEEP; I downgrade to ADAPT to match L #4 |
| H3 | Hover preview of a citation | H-G4 UNVERIFIED | **REJECT** as a path to provenance | Hover-only fails C2 and fails touch at 320px (C7). It must not be cited as Harvey precedent | — |
| H4 | Knowledge-source selector with descriptions; two sources at once | H-F3 SOURCED | **ADAPT → read-only scope line** | One body held (I-E27). A picker would imply we hold DECLARED bodies, the C10 DPDP-chip failure (C1, C3) | — |
| H5 | @mention a file or source | H-F1 SOURCED | **ADAPT → one explicit context control** (this document / general) | Makes §2 Q7 unmissable in the pane (C7). Free @-tagging is rejected | Agrees with L #16 (reject @ syntax) |
| H6 | Model selector | H-F5 SOURCED | **REJECT** | Implies answers vary by model. That contradicts server-decided state (C3), and the model is not wired (C8) | — |
| H7 | Magic Prompt rewrite | H-F6 SOURCED | **REJECT the rewrite; ADAPT → capability suggestions** | A rewrite changes what was asked (C1). Suggestions come from `bundles.py` (I-R4) | — |
| H8 | Prompt library | H-F1, H-W2 SOURCED | **REJECT user-authored library; ADAPT → server-supplied capability list** | Free prompts invite out-of-scope questions (C1). A list generated from bundles is truthful (I-R4, §6.4) | Not ruled on by H; added here |
| H9 | Voice-to-prompt, dictation | H-F1, H-W4 SOURCED | **REJECT** | No named need (§2 Q8). Not a v1 surface (C7) | — |
| H10 | Deep research / deep analysis report | H-F8, H-G7 SOURCED | **REJECT** | Open-ended multi-source reports are the C1 non-goal. There is one held body | — |
| H11 | Thinking states; plan preview and approve | H-F9 SOURCED; H-F10 SOURCED via HDI | **ADAPT → stage captions; REJECT an editable plan** | C4: a caption, never a plan the user edits. The server decides (C3) | See §2 Q3: captions must be server-supplied |
| H12 | Streamed prose ("time to first word") | H-G9 SOURCED (vendor metric); streaming H-G10 INFERRED | **REJECT** | Prose before the state is decided breaks C3, C4 and §2 Q3 | — |
| H13 | No visible abstention state | H-G11 not found (not evidence of absence) | **DIFFERENTIATE** | Ours is a first-class state, worded in the heading and never red (C3, C5) | — |
| H14 | In-thread suggestions (workflows, uploads, deep analysis) | H-F7 SOURCED | **REJECT**; one exception: inside `out_of_scope`, state what *is* held | Widens scope (C1) and adds chrome to the pane (C7) | — |
| H15 | Threads/drafts sidebar; History (web and Word) | H-E1, H-H4 SOURCED | **OPEN**, leaning ADAPT to a session-only list of past turns, each with its original as-of | No conversation state (I-E34). Persisting questions that quote client text collides with `session.py` (I-E32). See K12 | The H researcher said ADAPT; I mark OPEN |
| H16 | Thread search | H-H5 not found | **REJECT** (v1) | §2 Q8: no named need | — |
| H17 | Share Modal with permissions, activity log | H-H2 SOURCED | **REJECT** (v1) | §2 Q8. A shared answer would first need an immutable pack id and as-of in the contract (C8) | — |
| H18 | Draft mode, Show Edits, editing Word in Assistant | H-E5, H-E6, H-W3 SOURCED | **REJECT** | Generation is outside the wedge (CLAUDE.md "audit layer, not generator"; C1) | — |
| H19 | Side-by-side document viewer | H-E7 UNVERIFIED | **REJECT** | Generation (C1). Not usable as precedent anyway | — |
| H20 | Writing styles | H-F11 SOURCED | **REJECT** | Server-authored wording (e.g. `refusal_for` verbatim, I-E29) must not be restyled (C3) | Added here |
| H21 | Pane extras: web search, fill/edit tables, translate, redact | H-W2 SOURCED | **REJECT** | Web search is outside the held corpus (C1). The rest are generation | Added here |
| H22 | Pane verbs Ask / Edit / Playbook | H-W1 SOURCED as words; tabs INFERRED | **ADAPT** → an Ask tab beside *Currency check* and *Register strip* (§4). No Edit | C7; C1 | — |
| H23 | Full Assistant inside the pane | H-W8 INFERRED from H-W2/H-W4 | **ADAPT by subtraction** | The pane must be complete for *our* job: scope line, as-of, context, composer, answer, source section. Rejecting H6–H10 and H14–H21 is what makes 320px feasible (C7) | — |
| H24 | Principle: "backtrack … verify the sources … confirm that citations are accurate" | H-G6 SOURCED | **KEEP** (principle) | Matches C2 and L-C3 (checking cost) | — |
| H25 | Role-based tokens, warm neutral near hue 90°, contrast in light and dark | H-T2 SOURCED | **KEEP the method** | Fits C6. Harvey's values are unpublished, so nothing is copied | — |
| H26 | Serif + sans pairing (site CSS) | H-T3 SOURCED (marketing site only; the app is H-T5 UNVERIFIED) | **ADAPT** | A document serif for statute text and answer prose, a sans for chrome (C6). Use our faces, not Harvey's. Whether a serif survives at 320px is open (I-R3: the pane uses system sans) | — |
| H27 | Radius / shadow / motion values | H-T6 not published | **No input** | C6 decides | — |
| H28 | Vendor accuracy metrics (60% / 23% / 80%) | H-G9 SOURCED, method unstated | **No design input** | — | — |

#### Claude.ai

| # | Pattern | Evidence | Verdict | Reason (C1–C10) | Note |
|---|---|---|---|---|---|
| C1 | "+" menu in the lower left hiding files, web search, Research | C-E1, C-E4, C-E8, C-E9 SOURCED | **REJECT the hidden menu; ADAPT the slot** for the context control | Scope, as-of and context must stay visible (§4, §2 Q1) | — |
| C2 | "/" commands | C-E9 SOURCED | **REJECT** | A hidden affordance, rejected for the same reason as C1. Nothing to command | Added here |
| C3 | Attachments (upload, drag, paste) | C-E8 SOURCED | **REJECT** | The open Word document is the context. The UX spec cut upload (I-R5 A9); §2 Q8 | Added here |
| C4 | Model / effort / thinking picker next to send | C-E6 SOURCED | **REJECT; the slot takes the as-of date** | C3, C1. As-of is the one parameter the user legitimately sets (C2) | — |
| C5 | Web search toggle | C-E1 SOURCED | **REJECT** | Outside the held corpus (C1) | — |
| C6 | Research mode, blue indicator, "minutes" | C-E4, C-E5 SOURCED | **REJECT** | A long agentic run does not fit the pane (C7) or C1 | — |
| C7 | Thinking timer + expandable Thinking section | C-E7 SOURCED (quote paraphrased; K3) | **ADAPT → one-line stage caption; REJECT expandable reasoning** | Narrative before the state breaks C4 and §2 Q3 | — |
| C8 | Inline citations, "easy to check" | C-E2, C-E5 SOURCED as existing; form undocumented | **KEEP the principle, ADAPT the form** | C2 is stricter than anything Claude documents | — |
| C9 | API citations with guaranteed-valid pointers (`cited_text`, `char_location`) | C-E20 SOURCED | **KEEP** (backend and contract) | Matches §6.5 "reject a citation outside the evidence pack" | — |
| C10 | Response labelled with the model that answered + switch notice | C-E15 SOURCED | **ADAPT → per-turn provenance stamp** (context, as-of, pack) | Answers §2 Q4. The model name is irrelevant (C1) | — |
| C11 | Artifacts window to the right of chat | C-E11 SOURCED | **ADAPT → Source panel on web; in-flow section in pane** | Contents are verbatim source only, never generated (C1, C7) | — |
| C12 | Projects + knowledge base | C-E12 SOURCED; C-E13 UNVERIFIED (K4) | **REJECT** | The corpus is ours (C1). The document is the context (§2 Q7). The verdict rests on C-E12 + C1, not C-E13 | — |
| C13 | Plain-language error copy with the recovery step | C-E16 SOURCED | **KEEP** | The model for `out_of_scope` and service-error copy (C5; L-C2) | — |
| C14 | Share; incognito; chat search; memory | C-E14, C-E18 SOURCED | **REJECT** (v1) | §2 Q8. Memory invites context drift (§2 Q4) | — |
| C15 | Edit message and retry | C-E15 SOURCED as actions; controls undocumented | **ADAPT: edit-and-resubmit (a new grounded turn); REJECT retry** | Retry implies a different answer might come back (C3) | — |
| C16 | Per-message copy / retry / edit icons | C-E25 INFERRED | **ADAPT copy only if it carries state + instrument + as-of** | Copying bare prose strips the provenance C2 requires | Added here |
| C17 | Stop button | C-E17 UNVERIFIED (K4); chat stop C-E23 INFERRED | **ADAPT → Cancel during stage captions** | Grounded on the keyboard path (§6.3), not on precedent | — |
| C18 | Centred composer empty state; left rail | C-E24 INFERRED | **ADAPT** | Centred, but filled with the scope line and a capability list (L #8, I-R4), **not a greeting**. The rail disappears in the pane (C7) | The C researcher said KEEP; see §4 on why the empty "ask anything" state is the riskiest Claude element |
| C19 | Token streaming | C-E23 INFERRED | **REJECT** | C3, C4; L-C12 (no evidence it helps) | — |
| C20 | Styles presets | C-E10 UNVERIFIED | **REJECT** | Same as H20 | Added here |
| C21 | Keyboard shortcuts | C-E21 UNVERIFIED (third-party) | **No precedent**; §6.3 keyboard path required anyway | — | — |
| C22 | Accessibility statement / VPAT | C-E22 UNVERIFIED | **No input** | — | — |

### 2. The harsh questions (PLAN_13 §2)

"Open" means the design must answer it in writing. Where evidence is thin, this brief does not settle the question.

**Q1 — Is chat the right primitive? What does the composer do before submit, and how does `out_of_scope` read as competence?**

| Plausible answer | For | Against |
|---|---|---|
| (a) Free-text chat, as Harvey and Claude do | Every legal vendor ships a composer (L-A1, L-A11, L-A13, L-A16 SOURCED). Harvey puts one in the Word pane (H-W2). Familiarity is INFERRED | No module maps free text to a body of law (I-R1 item 3), so `out_of_scope` **cannot be decided from a question today**. `answered` is truthful only for deterministic results (I-R1 item 2). A narrow corpus yields many non-answers (L-B2: 62% incomplete for the narrow-corpus tool). An undeclared body such as Income-tax has no refusal text (I-E28) |
| (b) Free text, constrained by an always-visible scope line + capability suggestions | Scoping before the question is the industry pattern (L Result 1). Magesh counts an out-of-jurisdiction source as a hallucination (L-C1). Suggestions can be generated from `bundles.py` (I-R4) | Suggestions only help if users read them (no evidence, K15). Detection is still missing |
| (c) Structured capability picker (choose a question type, fill inputs) | Matches what the engine actually does: 5 bundles, 15 obligations, all `uses_model=False` (I-E30, I-E31). No detection needed | No competitor precedent found. It is not "Harvey + Claude". It may read as a form, not an assistant (INFERRED) |

Out-of-scope as competence, SOURCED support:
- Magesh codes a refusal as correct only when it says what was searched and not found (L-C2).
- PAIR: "explain why … provide alternative paths forward" (L-B6).
- Claude's recovery-step copy (C-E16).
- `refusal_for()` separates "not held" from "no obligation" (I-E29).

**Open:**
- Is the primitive (a), (b) or (c), or a hybrid (b + c)? The evidence leans away from (a) (INFERRED). It cannot choose between (b) and (c) without users.
- What heading word is true for DECLARED bodies (K14)? "Outside what Placedon covers" is ruled out.
- What does the UI show when detection itself fails or returns an undeclared body?

**Q2 — Which Harvey/Claude patterns survive?** Answered in §1. What remains open is H15 (history) and whether the H26 serif holds at 320px.

**Q3 — What may appear before the state is decided?**

| Plausible answer | For | Against |
|---|---|---|
| Stage captions only (PLAN default) | No evidence that streaming helps trust (L-C12). Timing of reasoning matters less than correctness (L-C9). No module decides a state before review completes (I verdict table; `orchestrator.py:215-259`) | Today stages are a **post-hoc trace**, not a stream (I-E4, I-R1 item 9), and general-context turns have none (K9). A client that animates "retrieving → checking → verifying" on a timer is showing text the server never supplied, which breaks §6.4 |
| A single neutral caption ("Checking…") until the response arrives | Truthful with today's backend. No invented stages | Less informative. Latency is unknown because `/v1/ask` does not exist (I-E1) |
| Streamed prose | Presumed product convention (H-G10, C-E23, both INFERRED) | C3, C4 |

**Open:**
- Are stage captions server-sent events (a NEW contract field and transport), or one generic caption?
- Whatever the design shows must come from the fixture or contract.
- No latency figure exists to judge whether a wait is acceptable.

**Q4 — Follow-ups: per-turn re-grounding, and how it is shown**

| Plausible answer | For | Against |
|---|---|---|
| Thread; each turn has its own pack, as-of and context stamp | Per-response provenance labelling exists (C-E15). Harvey's sources align with the thread view (H-E3 SOURCED; per-turn alignment H-E4 INFERRED). Westlaw bounds follow-ups (L-A3) | No conversation state (I-E34). No pack id (I-R1, NEW). The context carried between turns is undefined |
| Independent turns, with no inherited context; a list of past turns | Honest with today's backend (C8). Removes context drift by construction | Users may expect "and what about…" to inherit the document or as-of (INFERRED, no user data) |
| No follow-ups in v1 | I verdict: reject for now | ask.html's "Ask Follow-up" was a failure (I-R5 A13), but that is evidence against faking it, not against the need |

**Open:**
- Does a second question inherit context and as-of? If so, the inherited values must be visible *on that turn*.
- Is past-turn history stored at all (K12)? The design must at least specify the per-turn stamp, whichever answer wins.

**Q5 — Citations: inline chips, side panel, or both, measured against C2**

| Plausible answer | For | Against |
|---|---|---|
| Inline marker only | Harvey API `[N]` (H-G1). Claude "inline" (C-E5) | A marker without the instrument and as-of text fails C2. Citations raise trust even when random (L-C5), and 25% of citations don't support their sentence (L-C4) |
| Side panel / list only | Harvey sources panel (H-E3). Vincent authorities on the right (L-A16). Protégé list below (L-A8) | Needs a click, so it fails C2 on its own. Whether practitioners open panels is unknown (L rec 3) |
| Both: inline instrument + as-of text, with a marker into a panel of verbatim text | The only option that satisfies C2. No competitor page shows dates beside figures (L Result 2, INFERRED from absence), so this is unoccupied ground | Length at 320px (Q6). **For section text there is no in-force date.** Only "current consolidation, ingested 2026-08-18, not point-in-time" can truthfully appear (I-E16, I-U6), and that string risks reading as hedging (§7 falsifier 3) |

**Open:**
- The wording and form of as-of for (i) a dated Threshold figure (instrument + effective_from, I-E22) versus (ii) quoted section text (ingestion basis only).
- These are different truths and must not look the same.
- The design must never present `retrieved_on` or `corpus_fetched` as an in-force date.

**Q6 — Does it degrade to 320px without hiding the evidence?**
- **For:** Spellbook splits single-document work into the Word add-in and multi-document work onto the web (L-A10). A list below the answer works narrow (L-A8). Claude's right window can become an in-flow section (C-E11 ADAPT).
- **Against / unknown:**
  - No competitor's pane citation display is public (H-W6).
  - The real instrument string is long: "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025" (I-R2).
  - Today's pane breaks the design system: 11px text, 3px radius, no focus ring, Caution used for errors (I-R3).
- **Open:**
  - A short form versus the full instrument string inline. If short, what minimum still satisfies C2?
  - Which pane tokens are corrected first.

**Q7 — Document context versus the law in general**
- **For a visible switch:**
  - Spellbook's "Legal Sources" toggle in a Word add-in (L-A11 SOURCED).
  - Protégé's separate Documents mode (L-A8, secondary).
  - Harvey's @mention (H-F1).
- **Engine facts:**
  - The document path needs document_date, company_class and incorporation_date (I-R4).
  - The orchestrator refuses without a date (I-E5).
  - "General" can only do source lookups today (K13).
- **Risk:** §7 falsifier 2 (users miss the difference). No evidence yet on which form prevents it.
- **Open:**
  - The default context when a document is open.
  - What "general" promises. I recommends it say "source lookups, not decisions".
  - How the per-turn stamp names the document without leaking client text into stored history (I-E32).

**Q8 — What we refuse to build**

| Feature | Precedent | Named user need found? | Brief position |
|---|---|---|---|
| History search | Claude chat search (C-E18); Harvey not found (H-H5) | None (K15) | Cut |
| Sharing | Harvey Share Modal (H-H2); Claude share (C-E14) | None | Cut. It would first need an immutable pack id (C8) |
| Voice | Harvey (H-F1, H-W4); Legora (L-A13) | None | Cut |
| File drop into chat | Claude (C-E8); Legora @ (L-A13) | None; UX spec cut upload (I-R5 A9) | Cut |
| History *list* (not search) | Harvey (H-H4) | None, but plausibly implied by Q4 | **Open** (K12) |

"None" means no research file names one. It does not mean users have none.

**Q9 — What would falsify the design.** PLAN_13 §7 lists three falsifiers. Add, from the evidence:
- (i) Practitioners do not open the Source panel (L rec 3; L-C5). Then the chips are decoration and the inline text must carry everything.
- (ii) In early use, most questions end `partial`/`out_of_scope` and users stop asking (L-B2 suggests a narrow corpus produces this; INFERRED).
- (iii) Users ignore the scope line and still ask about DECLARED bodies at the same rate.
- (iv) The two as-of forms (Q5 i and ii) are read as the same claim.

None of these is measurable with fixtures. All need the ten practitioner conversations.

### 3. Non-negotiables for every design

Taken from C1–C10, PLAN_13 §6 and the audit. A design that breaks any of these is disqualified, not scored down.

1. **Three states, server-decided** (C3). The client never infers or relabels a state. With colour removed, the states differ by heading word (§6.1). The DECLARED heading must be a word that is true (K14).
2. **Instrument + as-of next to every figure, no click** (C2). Figures come only from `Threshold`: amount, instrument, effective_from, effective_to, state (I-E22).
3. **Two kinds of as-of, never conflated.**
   - A figure's in-force date (effective_from).
   - Section text's ingestion basis (`CURRENT_CONSOLIDATION_AS_INGESTED`, `point_in_time_verified: false`).
   - `retrieved_on` and `corpus_fetched` are fetch dates, not in-force dates (I-E16, K10).
4. **No confidence numbers, no skeletons** (C4). `claim.confidence` and the `ClaimVerification.coverage` float are never rendered (I-E10, I-E12).
5. **Abstention is never red** (C5), and a **service failure is not abstention**. `BUDGET_EXHAUSTED` and backend errors get a neutral Ink treatment that is distinct from Caution `#8B4513` (I-R3 `.err`, I verdict table).
6. **No "Verified" badge and no reviewer name.** The corpus ceiling is CORROBORATED (I-E17), and the verifier never returns SUPPORTED (I-E11). `sources[].human_reviewed` is a boolean on a source. It is never turned into a person or an answer-level seal (K10; C10's invented reviewer).
7. **`answered` only for deterministic results** (bundle row or servable Threshold). Model-composed prose never sits under `answered` until I-U1 is decided.
8. **Nothing narrative before the state** (§2 Q3). Any pre-state text is supplied by the fixture or contract, never timed or invented by the client (§6.4, K9).
9. **Suggestions only from real capabilities** (I-R4):
   - Never a DECLARED, CURRENT_ONLY or OUT_OF_SCOPE body.
   - Never SD-002 / SD-002-OPEN sections (s.16, 124, 76A, 329, 236, 465, 247, 74, 78).
   - Never a Rules citation.
   - The 15-obligation list must say it is not the whole Act.
10. **Scope visible above the composer as a statement of fact**, not a picker (C1, C10). Held today: Companies Act 2013. DPDP is DECLARED in `scope.py`, so no DPDP chip.
11. **Out-of-scope copy is `refusal_for()` text, verbatim**, server-supplied (I-E29). An undeclared body needs NEW server copy, never client copy (I-E28).
12. **Coverage frame and `what_it_is_not` are shown and cannot be dismissed** when present (I-E25, I-E26).
13. **C6:** ≤ 4px radius, no shadows, ≤ 200ms motion, one accent per view, `prefers-reduced-motion` removes all motion, 12px minimum, 2px Slate focus ring (I-R3).
14. **320px first** (C7). No horizontal scroll, and evidence is never hidden behind hover. Full keyboard path (§6.3).
15. **`ask.html` is not a base** (C10, I-R5 A1–A18). All work lands in this private repo (C9).

#### Draft `/v1/ask` fields a design may rely on

Status: **BUILT** means a module produces it today (I-R1/R2). **NEW** means the design may use it, but it is a contract proposal and must render gracefully if Phase C changes it.

| Field | Status | Note for designers |
|---|---|---|
| `state` ∈ answered / partial / out_of_scope | NEW (mapping) | The only state signal. Never derive one |
| `question` | BUILT (`evidence_pack.query`, `:494`; K10) | — |
| `as_of` (read date) | BUILT pattern (`api.py`) | The date the user asked "as of" |
| `generated_at` | BUILT pattern | — |
| `context.kind` document / general | NEW | Must drive the per-turn stamp |
| `context.document_date` | BUILT | Null in general context |
| `uses_model` | BUILT | Disclose; do not style as quality |
| `scope.held[]`, `scope.sentence` | BUILT (`scope.py`) | Render verbatim |
| `stages[]` `{n, what, detail}` | BUILT but post-hoc, **document path only** (K9) | Design for absent or empty. `what` values are internal names, so the captions need NEW server copy |
| `turn_id` | NEW | — |
| `headline` | NEW | Server-composed |
| `figures[]` `{label NEW, amount, instrument, effective_from, effective_to, evidence_state, source_url}` | BUILT except label | The C2 carrier |
| `rows[]` `{obligation_id, provision, state, basis}` | BUILT | States: APPLIES_SATISFIED, APPLIES_NOT_SATISFIED, APPLIES_UNDETERMINED, DOES_NOT_APPLY, CANNOT_DETERMINE (I-E31) |
| `citations[]` `{ref, cite, title, evidence_state, evidence_state_servable, defects[], usable_for_answering, subsection}` | BUILT (section level; subsection recorded, not resolved, I-E19) | Show defects, never hide them |
| `citations[].sources[]` `{source_title, source_url, official, retrieved_on, human_reviewed}` | BUILT (K10) | `retrieved_on` is a fetch date |
| `law_version` `{basis, point_in_time_verified, corpus_fetched[]}` | BUILT (pack `as_of`) | The only truthful "as-of" for section text |
| `evidence_pack.usable_keys / unusable_keys / missing[]` | BUILT; `evidence_pack.id` NEW | — |
| `what_it_is_not[]` | BUILT pattern | — |
| partial: `confirmed[]`, `not_confirmed[]` groupings | NEW groupings over BUILT items | Items: `pack_missing`, `unusable` (+ reason, defects), `refusal` (code, detail, offending), `model_decision` |
| partial: `verbatim[]` `{ref, reading_text, corpus_content_sha256}` | BUILT (drop the per-provision `corpus_fetched`; K10) | — |
| partial: coverage frame | BUILT (`coverage.py`) but **key name must change** (K8); document context only | Do not bind a design to the key `coverage` |
| partial: `route` exact / search / abstain | BUILT | — |
| partial: `demand_signal` | NEW | "Tell us this is blocking you" |
| out_of_scope: `body {key, name, regulator, scope_status}`, `reason`, `held[]` | BUILT except detection (NEW) | `reason` = `refusal_for()` verbatim |
| **Forbidden:** `confidence`, a coverage *float*, any reviewer name, any client-inferred state | — | Validator rejects (§6.5) |
| **No slot yet:** a refusal inside the held Act (route `abstain` / `ABSTAINED`) | OPEN (I-U2) | Each design must propose how this looks without faking `out_of_scope` or a blank `partial` |

### 4. Is "Harvey + Claude" the right look?

**The strongest case that it is WRONG.**

1. **The form promises the non-goal.** Both products signal "ask anything":
   - streaming (H-G10, C-E23, both INFERRED);
   - model pickers (H-F5, C-E6);
   - deep research (H-F8, C-E4);
   - a centred empty composer (C-E24).

   C1 forbids that behaviour. The engine holds one Act, 15 obligations and 5 no-model bundles (I-E27, I-E30, I-E31), and it cannot yet even detect which body a question is about (I-R1 item 3). A chat frame invites exactly the questions that end in `partial`/`out_of_scope`. A narrow corpus drives non-answers up (L-B2). The first falsifier is a practitioner saying "just answer" (§7). A look that sets a chatbot expectation makes that outcome more likely (INFERRED).
2. **Almost every signature element is already rejected.** §1 rejects H6–H10, H12, H14, H16–H21, C1–C7 (as behaviour), C12, C14, C19 and C20. What survives (a side panel, a rail, a centred composer, warm neutrals, a serif) is generic. "Harvey + Claude" then means "a chat app with a right panel", which is borrowed and not distinctive (INFERRED).
3. **The look cannot be sourced.** The details that make it Harvey or Claude are UNVERIFIED or INFERRED: panel sides (H-E8), citation glyph (H-G2), hover (H-G4), Claude's citation form (C-E2), empty state (C-E24). §5 bans inventing a competitor detail without a URL. A faithful "Harvey + Claude look" can only be built from impressions (K2).
4. **The v1 surface is neither product's web layout.** C7 puts v1 in a 320–400px Word pane, where Harvey's pane appearance is not public (H-W6). The existing pane is already structured as a document check with a coverage frame (I verdict table), which is not chat.
5. **A confident frame inflates trust regardless of correctness.** Citations raise trust even when random (L-C5), and certainty cues sway trust independent of correctness (L-C9). For an audit layer, a polished assistant look may make "Partial" read as the tool failing rather than the law being unsettled (INFERRED from L-C5 and L-C9, untested with practitioners).

**The strongest case that it is RIGHT.**

1. **It is the market's convention.** Legal AI has converged on composer + visible scope + citations beside the answer: Westlaw (L-A1), Spellbook (L-A11), Legora (L-A13), Vincent (L-A16), Harvey (H-F3). Harvey now offers SCC Online for Indian research (H-F4), so Indian firm users can plausibly meet this vocabulary (INFERRED; no Indian user data, K15). Fighting a learned convention has an adoption cost.
2. **The patterns that survive are the useful ones, and they have sources:**
   - a sources panel for inspection (H-E3, L-A16);
   - per-turn provenance labels (C-E15);
   - plain recovery copy (C-E16);
   - visible work (H-F9 → captions);
   - role-token warm neutrals and a serif/sans pairing (H-T2, H-T3), which suit C6's quiet authority better than a dashboard look.
3. **Contrast makes the differentiator legible.** No competitor page shows as-of dates beside figures (L Result 2), and none documents a designed abstention state (L-A19, H-G11). Inside a familiar frame, "it looks like the tool you know, but every figure carries its instrument and date, and it says *Not held* instead of guessing" is instantly readable. In an unfamiliar frame the difference has no baseline (INFERRED).
4. **Harvey's own stated principle is ours.** "Verify the sources … confirm that citations are accurate" (H-G6) and "deeply familiar, yet unmistakably modern" (H-T1). Borrowing the restraint of the frame is not borrowing the behaviour.

**Critic's reading (INFERRED, not a verdict).** The evidence supports borrowing Harvey and Claude's **structure and restraint**: layout zones, type pairing, warm neutrals, panel-for-inspection, per-turn stamps. It gives no support for borrowing their **interaction model**: an open empty composer, streaming, modes and pickers. Whether the primitive is free text at all is Q1, and it is open. The *evidence-first native* direction should be allowed to win on merit, not treated as the control.

### 5. Gaps: what research could not establish

1. **Any competitor's non-answer screen.** Harvey (H-G11), Westlaw's "unable to answer" (L-A6 UNVERIFIED), and none of the five legal products (L-A19). Searched: harvey.ai, support.claude.com and the vendor help pages listed in H/C/L. Vendor webinar videos were not searched.
2. **Harvey's panel positions, citation glyph, hover, pane citation display, and product fonts** (H-E8, H-G2, H-G4, H-W6, H-T5). The help centre, Academy and app are login-walled or 403.
3. **Claude.ai citation rendering, streaming/stop, message actions, shortcuts, accessibility statement** (C-E2, C-E21–E25). Undocumented in public help pages, and claude.ai/accessibility returned 403.
4. **Any evidence that token streaming changes trust or verification** (L-C12). Two searches found none.
5. **Practitioner evidence of any kind** (K15): whether CSs want follow-ups, history, a free-text box or a picker; whether they open source panels; how an as-of stamp reads. All HCI studies used non-legal tasks (L Evidence quality).
6. **Backend capabilities the design presumes:**
   - body detection (I-R1 item 3);
   - an `answered` path for model text (I-U1);
   - a slot for refusal inside the held Act (I-U2);
   - conversation state (I-E34);
   - streamed stages (I-R1 item 9);
   - a pack id;
   - an in-force date on section text (I-U6);
   - a correct Rules resolver (I-E20, I-U5).
7. **Latency of `/v1/ask`.** It does not exist (I-E1), so the cost of refusing to stream cannot be estimated.
8. **DPDP status conflict** between the public BP specs (OUT_OF_SCOPE) and `scope.py` (DECLARED) (I-U4). `scope.py` governs, but the BP docs are unreconciled.
9. **Harvey's press-kit brand guidelines** (a zip, not downloaded) and Passi & Vorvoreanu 2022 (found, not opened).

---

## Unresolved issues

- The contract defects K8 (the `coverage` key), K9 (stages only on the document path) and K10 (line refs, `corpus_fetched`) need fixing in Phase C before fixtures are written.
- The files conflict on history (K12) and on General mode (K13). This brief marks both OPEN rather than picking a side.
- L verdict #4 and L Result 2 still cite downgraded L-A2 (K5). C-E13 and C-E17 are over-marked (K4). This brief does not edit those files; designers should cite the rows as corrected here.
- The heading word for DECLARED `out_of_scope` (K14), the refusal slot inside the held Act (I-U2), and whether model-path text can ever be `answered` (I-U1) are policy decisions, not design choices.

## Recommended next action

1. **Design agents:** each direction states, in writing, its answer to the "Open" item in every §2 question, and marks which non-negotiable (§3) each screen element satisfies.
2. **Phase C:**
   - rename the coverage-frame key;
   - make `stages` optional, with server-supplied caption text;
   - drop per-provision `corpus_fetched`;
   - add `evidence_pack.id` and `turn_id`;
   - add a fixture for refusal inside CA2013 (I-U2) and one for an undeclared body (I-E28).
3. **Judges:** score against §3 first, as pass/fail, then against §2. Penalise any competitor detail used as precedent that §1 marks INFERRED or UNVERIFIED.
4. **Before any design is "chosen":** run the Q9 falsifiers in the ten practitioner conversations. The Q1 primitive, (b) or (c), should be decided there, not in the design round.
5. **Research follow-up (human, legitimate channel):** capture one non-answer screen from a legal-AI vendor webinar or demo video, with a timestamped URL.

---

## What this means for the Ask section design

- **Keep:**
  - Instrument + as-of inline on every figure (C2).
  - Three heading-worded states (C3, C5).
  - `refusal_for()` verbatim (C3).
  - Coverage frame and `what_it_is_not` (C1).
  - Role-based warm-neutral tokens and C6 restraint (H-T2).
  - Plain recovery copy (C-E16).
  - Valid-pointer citations in the contract (C-E20; §6.5).
- **Adapt:**
  - A source panel for verbatim text: side on the web, in-flow in the pane (H-E3, C-E11; C2, C7).
  - Markers as pointers, not provenance (H-G1; C2).
  - Scope as a read-only line (H-F3, L-A16; C1, C10).
  - One explicit context control, stamped per turn (H-F1, L-A11; C7, §2 Q7).
  - Stage captions from the server (H-F9, C-E7; C4, §6.4).
  - Per-turn provenance stamp (C-E15; §2 Q4).
  - Edit-and-resubmit (C-E15; C3).
  - Cancel during captions (§6.3).
  - A centred empty state filled with scope and real capabilities (C-E24, I-R4; C1).
  - A serif for statute text, if it survives 320px (H-T3; C6, C7).
- **Reject:**
  - Model/effort pickers (C3, C8).
  - Streaming prose (C3, C4).
  - Deep research / Research modes, web search, Magic Prompt rewrite, styles (C1).
  - Hidden "+" and "/" menus (§2 Q1).
  - Hover-only citations (C2, C7).
  - Attachments, voice, share, chat search, memory (§2 Q8).
  - Draft/edit/generation features (C1).
  - Any "Verified" seal or reviewer name (C5, C10).
  - `ask.html` as a base (C10).
- **Open, and each design must answer:**
  - the primitive (Q1);
  - pre-state text source (Q3);
  - follow-up inheritance and history (Q4, K12);
  - the two as-of forms (Q5);
  - the inline instrument's short form at 320px (Q6);
  - what General promises (Q7, K13);
  - the DECLARED heading word (K14);
  - refusal inside the held Act (I-U2).
