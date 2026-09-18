# PLAN_13 — the Ask section: design spec

Written 2026-09-15 (Phase D output). This is the spec `web/assistant/` is built from in Phase B.
Plan: [PLAN_13_ASSISTANT_UX_PLAN.md](PLAN_13_ASSISTANT_UX_PLAN.md) (constraints C1–C10, the nine harsh
questions, acceptance checks). Brief: [research/ux/DESIGN_BRIEF.md](research/ux/DESIGN_BRIEF.md).
Contract: [`web/assistant/contract.md`](../web/assistant/contract.md) + `web/assistant/fixtures/*.json`.

**Base direction:** *Harvey-leaning* (`direction_harvey.md`), which all three judges scored first
(40/50, 41/50, 43/50). Grafted: the evidence-first state word, its no-amount-in-headline rule, its
change badge, its placeholder marking and its pane-beside-canvas frame; Claude's disabled web document
context, "Copy with sources" and the notes on what a turn carried. Every fatal flaw the judges named is
removed in §2.

**Markers used below.** **S** = a string the response supplies, rendered verbatim. **UI** = fixed
client chrome. **†** = copy written for a fixture or wireframe that no engine produces — it may never be
quoted as engine behaviour. **⟨field⟩** = a value the contract does not supply today.
Research row ids: **H** = HARVEY_ASSISTANT_UI, **C** = CLAUDE_CHAT_UI, **L** = LEGAL_AI_CHAT_PATTERNS,
**I** = INTERNAL_ASK_AUDIT, **K** = DESIGN_BRIEF critic rows, **J1/J2/J3** = the three Phase D judges.
Every design verdict here is INFERRED reasoning resting on the rows it cites. Dates the client formats
are **DD-Mon-YYYY**; dates inside server strings are never reformatted.

---

## 1. Summary

The Ask section is Harvey's floor plan running PlacedOn's behaviour: a session rail, a content column of
turn cards, and a sources surface that follows the turn in view (H-E1, H-E3, H-E4) at 1440px, collapsing
to one column of the same turn cards, each with its own in-flow Sources section, in a 320–400px Word task
pane (C7). Everything in Harvey and Claude that promises "ask anything" is subtracted — model picker,
Magic Prompt, prompt library, deep research, streaming, hidden "+" and "/" menus, retry, persistence
(H-F5, H-F6, H-F8, H-G10, C-E1, C-E6, C-E9, C-E15, C-E18) — and the freed slots carry the three things
C2 and C3 need instead: a read-only statement of what is held, the as-of date where Claude's model picker
sat (C-E6), and a two-option **About** control where Claude's "+" sat (C-E1). Each turn opens with a
full-width context band ("About the Act" / "About the open document · dated 01-Jun-2024") so a turn's
context can never be signalled by something *missing*, then the question, a provenance stamp, and one
server-decided state word — **Answered** / **Partly answered** / **Not held** — which differ in their
first word and carry a shape glyph, so they survive grayscale (PLAN §6.1). Every amount lives in a figure
block under a **solid** rule with `In force from <date>` and the full instrument string, with no click
(C2); quoted section text lives under a **dashed** rule with "Text as ingested 18-Aug-2026. Current
consolidation, not a point-in-time version." and never carries an in-force date — the two as-of truths
differ by word, position, rule style and typeface, and the request date appears only in the stamp as
"Asked as of". Nothing narrative appears before the state: one static line and Cancel. Nothing is
rendered that the response did not supply, and a `?fields=1` overlay in the prototype proves it element
by element.

---

## 2. What changed from direction H (fatal flaws removed, grafts taken)

| # | Change | Why |
|---|---|---|
| 1 | State word **"Partly answered"** replaces "Answered in part", in Playfair 22/24 as the card's largest element | J1: "Answered in part" shares its first word with "Answered"; a skimming CS can read partial as answered (evidence direction's wording, praised by all three judges) |
| 2 | In `partial`, **NOT CONFIRMED renders before CONFIRMED** | J1: "put the Not confirmed reason before the confirmed figure". The reason the turn is partial leads the result |
| 3 | **The context band carries no glyph.** Square glyphs are reserved for the three state words, and nothing else on the page uses one | J1: the document band's hollow rectangle read as the Not-held hollow square in grayscale |
| 4 | **No client-composed headline, and no amount in any headline.** `headline` is NEW and absent from every fixture, so nothing renders in its slot today; a validator rule refuses a headline containing an amount. Because that slot is empty, the **finding line** — `rows[].basis`, a server string — is promoted to H2 18 directly under the duty, and the row's state word drops to a caption beside the provision (§7.4). The largest words on an `answered` card are never the bare word "Answered" over a state word that reads as its opposite (D10) | J1/J2/J3: all three flagged direction H's fixture headline as invented copy presented as server text, and the ₹ amount appearing in both headline and figure block (evidence direction's rule). Critique F3(2): with `headline` empty the only text carrying the answer was a 12px caption |
| 5 | **Web "This document" is disabled**, with the reason beside it, and there is no web document-context wireframe. The document frame is drawn as Word desktop: document canvas + 400px pane | J1/J2/J3: the web document turn showed a flow no hand-off can reach (direction H risk 9). Claude's disabled segment + the evidence direction's pane-beside-canvas |
| 6 | **"Covers the document's date…", "as served on…" and every other client-worded date sentence is gone.** Six date wordings are named in §9, each with exactly one position and one source field | J1: a fourth and fifth date wording read as client-computed |
| 7 | **"Checked on its own" is removed from the stamp.** Each turn instead shows, from the response, what it looked up (`evidence_pack.retrieval_query`) and, when `parent_turn_id` is set, which turn it follows | The Phase C fixture `followup_turnover` resolves "And the turnover limit?" against `s.2(85)` and carries `parent_turn_id`. A fixed claim that nothing is inherited would now be false (I-E34 says no conversation state exists — so what a turn used must be shown, not asserted) |
| 8 | **Collapsed earlier turns show no amount** — state word, question, asked-as-of and a count of figures, never a number and never a truncated instrument | Evidence direction (J1 best idea). It also avoids the client slicing a server instrument string into "G.S.R. 880(E)" |
| 9 | **Change badge** "About changed from the previous turn" / "Date changed from the previous turn", computed only by comparing two server-echoed stamps | Evidence direction (J1, J2, J3 all listed it) |
| 10 | **"Copy with sources"** on every turn; plain copy is not offered | Claude direction (J1, J2, J3). Provenance must survive outside the tool (C-E25 → brief C16) |
| 11 | **Pane composer docks sticky and compact** after the first turn; a new turn's heading is scrolled to and focused, never the page bottom. **Built differently (2026-09-17):** the composer compacts to one summary line plus the field but stays *first*, above the turns, so focus order equals visual order (WCAG 2.4.3) and the acceptance check "composer within six tab stops" holds; a foot-docked composer would put the field last in DOM order or break that order | J2: a docked composer plus a 1,500px partial turn made the pane a scroll hunt |
| 12 | **The whole spec is re-bound to the Phase C contract** (`placedon.ask/0`), not to audit §R2's draft. Field names, shapes and the five fixtures now decide what every component may render (§18) | The contract and fixtures landed after the directions were written. Nine defects this surfaced are listed in §18.3 |

---

## 3. Placement, and how a user reaches it

| Surface | Where | How reached | Default context |
|---|---|---|---|
| **Word task pane (v1, C7)** | Third tab of the existing pane: `Currency check · Register strip · Ask` (H-W1 verbs, adapted per brief H22; the pane today stacks the two as sections, `addin/taskpane.html:58,68`) | Ribbon → PlacedOn → pane → **Ask**. First open of a session lands on *Currency check*, the wedge; after that the pane reopens on the last tab used (a per-device convenience in `localStorage`, nothing else stored) | **This document**, when `readDocument()` returns a document date (`addin/taskpane.js:34-52`). Otherwise **The Act**, with the reason stated |
| **Word desktop, any window width** | The same 320–400px pane beside the document canvas | as above | as above |
| **Web (secondary)** | `/ask`, one screen. No dashboard, client picker, deadlines or search (UX §5; I-R5 A10–A12) | Direct link. Sign-in is out of this spec | **The Act**, fixed. "This document" is rendered disabled with "Document checks run in the Word add-in." The web has no document: upload is cut (I-R5 A9), and no Word→web hand-off exists |

**The pane is the deliverable; the 1440 frames are illustrative of the same system.** C7 puts v1 in the
Word pane, so the Harvey structure is spent there first, not on a screen that cannot check documents:
the pane carries a **turn-scoped source sheet with a header naming the turn it belongs to** (§10) and a
**compact turn switcher** standing in for the rail (§12). The rail, the three-zone frame and the 384px
panel at ≥1100px are the same two structures at a width that has room for them — not a richer product.

Nothing about the Ask tab changes the add-in's standing rule: it reads the document and annotates via
comments; it never edits text or formatting (`addin/taskpane.js:1-15`). Every document turn ends with
"Nothing was changed in your document." (kept from `taskpane.js:71-72`).

---

## 4. How it works, end to end

### 4.1 Requests (both NEW — the contract documents the response only)

**`GET /v1/scope` — the bootstrap this design depends on.** Everything the composer states before the
first turn (§7.1, §7.2, §11) is server text, and every field it needs lives today only inside an
`/v1/ask` *response* envelope. Without this request the empty state has no scope claim, no not-held
register and no capability list — see §19 Q1, which no longer argues from a fence that does not render.
It is a **blocking Phase C deliverable**, not a NEW field the client waits for:

```jsonc
GET /v1/scope
{ "scope": { "held": ["Companies Act, 2013"],
             "sentence": "1 of 9 in-scope bodies of law are held",
             "bodies": [ {"name": …, "regulator": …, "scope_status": …} ] },   // scope.py is the authority
  "capabilities": [ {"group", "question", "provision", "requires[]", "inputs[]", "needs_document"} ],
  "capabilities_note": "15 obligations are checked. That is not the whole Act." }
```

The client enumerates no body and no capability of its own (§11 item 1). Until the route exists, Phase B
renders §7.1's **unfenced fallback**: title, About, question field, As of, Ask — and *no* scope
sentence, *no* register and *no* capability list, because a hard-coded "1 of 9" would recreate the C10
DPDP-chip failure the moment `scope.py` changes.

```jsonc
POST /v1/ask
{ "question": "Is this company a small company?",     // the user's words, never rewritten
  "as_of": "2026-09-15",                              // today, and only today in v1 (§9)
  "context": { "kind": "general" },                   // the About control
  "document": { "date": "2024-06-01", "text": "…" },  // document context only; pane only; as taskpane.js sends today
  "capability": "company.compliance_matrix",          // set only when a capability row was chosen
  "facts": { "company_class": "private",              // only the fields that capability declares
             "paid_up_capital_rupees": 120000000 },
  "parent_turn_id": "t_20ccadb72b4b" }                // present from the second turn of a session on
```

Document text is sent, the file is not; the backend holds it in an ephemeral session
(`checker/session.py`; `taskpane.js:11-14`). Nothing is stored client-side except the last tab.

### 4.2 Server → state

The server maps its own vocabularies (orchestrator verdict, adapter decision, retrieval route) onto one
of three states (contract §6). The client never infers, upgrades or relabels a state (C3, PLAN §6.5).
`BUDGET_EXHAUSTED`, a 5xx, a timeout and an abort are **not** states; they render as §7.11, which uses none
of the state words, glyphs or rules.

### 4.3 Render

```
render(response, requestValues):
  1. transport failed, empty body, or validate_hard(response) non-empty → ServiceError (§7.11)
  2. state ∉ {answered, partial, out_of_scope}                          → ServiceError
  3. out_of_scope without `reason`                                      → ServiceError  (client never writes refusal prose, I-E28)
  4. drop = validate_soft(response)        // a set of FIELD names, never a whole-response refusal
  5. TurnCard (skipping every element named in `drop`):
       ContextBand(context.kind, context.document_date)
       ParentLine(parent_turn_id)            if present
       Question(question)
       Stamp(as_of, uses_model, evidence_pack.retrieval_query?)
       ChangeBadge(both sides, from echoed values)                   if different
       StateHeading(state)                   word + glyph + rule
       Headline(headline)                    if present  (NEW; absent in all five fixtures)
       body by state (§8)
       WhatItIsNot(what_it_is_not[])         if present AND not dropped — heading and list render together or not at all
       Actions(copy, edit, demand_signal?)
       Sources(citations[], figures[], law_version, evidence_pack, stages[]?)   sheet in the pane, panel on web
  6. for EVERY terminal card — answered, partial, out_of_scope, cancelled, ServiceError:
       the card is an `article` with an `h2`; focus → its first element (the question, or the
       error heading where there is none); the live region announces the state word (or
       "No result" / "Cancelled") and the question
```

**Hard vs soft validation (this is what keeps §24 check 1 true).** A *hard* rule means the response
cannot be read as an answer at all — a missing or unknown `state`, an `out_of_scope` with no `reason`, a
citation outside the evidence pack, a figure with no `instrument` or no `effective_from`, an inferred
state, a `confidence` field. A *soft* rule means one **element** is defective — a malformed
`what_it_is_not`, a `source_url` that is not a URL or is on a dead host, a `not_confirmed[].detail`
written for a model. A soft failure suppresses that element **and its heading**, and the rest of a
legally correct turn still renders. §18.2 classifies every proposed rule. Nothing about this lets the
client relabel a state (C3); it only decides whether an element is drawn.

Every element names the field it renders in a `data-f` attribute. `?fields=1` outlines each element and
prints that name, which is how PLAN §6.4 ("no text on screen the fixture did not supply") is checked by
eye rather than by assertion (J3 named this direction H's strongest buildability feature).

### 4.4 Waiting, and cancelling

Submit disables the composer, appends a card carrying **only the request values the user set**, one
static line — "Checking the Companies Act, 2013." — and **Cancel**. No spinner, no timer, no stage
names, no skeleton (C4, PLAN §2 Q3). The line names the corpus, not a machine deciding a legal question.
`stages[]` appear only after the state, only when present, and only on the document path (K9). Cancel
aborts the fetch and rewrites the card to "Cancelled. Nothing was returned." keeping its stamp.

The waiting card, the cancelled card and the service-error card are `article`s with their own `h2`, and
each is focused and announced on arrival by pipeline step 6 — so a cancel or a 502 is never a silent
replacement that leaves focus on a destroyed button (the failure §15's Cancel focus would otherwise
cause).

---

## 5. Layout zones

| Width | Zones |
|---|---|
| **≥1100px (web)** | **Rail** 232px (Parchment, 1px Ink-10 right border, 48px header): wordmark, *New question*, this session's turns, the not-saved note. **Content**: turn cards on Parchment, text measure 680px, composer docked at the foot. **Sources** `min(384px, 32vw)` (1px Ink-10 left border, 48px header naming the turn it shows) |
| **820–1099px** | Rail folds away (the browser's own back/scroll replaces it). Content + Sources, the panel fluid, the content column never below 400px — 820px is the width at which a 384px panel would push it there |
| **<820px, and the Word pane at 320–400px** | One column: pane tab bar, the **turn switcher** (§12) once there are two turns, turn cards, the docked **source sheet** (§10), sticky compact composer at the foot. No rail, no side panel |

In the empty state the order is title → sub-line → Holds → About → **capability list → question field →
As of → Ask** (§7.1): the list that says what can be asked precedes the control that asks, in DOM, tab
and visual order alike (§15). The composer does not move to the top. On the web the Sources column is **reserved in the empty state** — its 48px header
renders with "Nothing to inspect yet." and the gutter holds — so the first answer changes content
without sliding the whole reading column sideways (no motion is needed, and none is added, C6).

Separation is by border and panel header, never by fill or shadow (C6, H-E1). Nothing has a fixed width
above 320px; long keys and instrument strings wrap (`overflow-wrap:anywhere` on mono keys), and no block
relies on two aligned columns (§7.4's supplied facts stack label-over-value).

---

## 6. Component inventory

| Component | States | Notes |
|---|---|---|
| `TabBar` (pane) | current / other / focus | Native `role=tablist`, arrow keys, 44px |
| `PaneHeader` (pane) | document date read / no date read | Client-read, pre-request: "Open document dated 01-Jun-2024" or "No document date found" |
| `HoldsLine` | **absent (no `/v1/scope`)** / full (empty state) / compact (after first turn) | `scope.held[]` + `scope.sentence`, verbatim, read-only (H-F3 adapted). Renders nothing at all until `GET /v1/scope` exists — never a hard-coded count (§4.1) |
| `ScopeRegister` | **absent** / closed / open | Disclosure over `scope.bodies[]` (NEW, §4.1). The client enumerates no body |
| `AboutControl` | this-document selected / act selected / **document option disabled + reason** (web, or no document date) / focus | Native radios in a fieldset, arrow keys free. The *reason* line is Ink-80, not disabled-grey (§14) |
| `AsOfField` | **today, read-only (v1)** | Displays today in DD-Mon-YYYY with the reason inline: "Answers are given as the law stands today. Placedon holds a current consolidation, not point-in-time law." No past date can be entered, so no card can be stamped with an as-of the engine cannot honour (§9, I-U6, CLAUDE.md). It has **no invalid state in v1**, because there is nothing to parse. If Phase C ever makes it editable it must accept `DD-MM-YYYY`, `DD/MM/YYYY` and ISO on input and normalise to DD-Mon-YYYY on blur, carry `aria-invalid` + `aria-describedby` to a named error line, and state what **Ask** does while the value is invalid — none of which exists or is needed while the field is read-only |
| `QuestionField` | empty / typing / disabled while waiting | 3 rows, grows to 8 |
| `FactsFields` | hidden / shown when a capability declares inputs / invalid | Labels are the capability's own `evidence_needed` strings |
| `AskButton` | idle / disabled while waiting / hover / focus | Slate on the web; **Ink in the pane**, where the docked composer shares the screen with Caution (§14) |
| `CapabilityList` | **absent (no `/v1/scope`)** / shown before the first turn only | Rows fill the field; they never submit. Precedes the question field in DOM and tab order (§15). While it is absent, **no control may point at it** — `[See what can be checked]` is not rendered on an `out_of_scope` card (§7.7), because a recovery action that opens an empty region is worse than none |
| `SessionRail` (web) | empty / rows / current row | Row: **state word first**, then glyph, then question (2 lines), then asked-as-of |
| `TurnSwitcher` (pane) | absent (one turn) / rows | Harvey's threads list at 320px: one 44px row per turn, state word + glyph + the question clipped to one line. Activating it scrolls to that turn and focuses it. Replaces the rail; it is not a history store (§12) |
| `TurnCard` | waiting / cancelled / answered / partly answered / not held / service error / collapsed | `article`, `h2` = the state word, `aria-label` = `"{question} — {state word}"`, both server-supplied |
| `ContextBand` | act / document | Full-width Ink-10 strip, no glyph, no radius |
| `Stamp` | with pack / without pack | `generated_at` is the element's `title` only |
| `ParentLine` | present / absent | "Follow-up to turn 1" |
| `ChangeBadge` | about changed / date changed / both / absent | Compares echoed values only |
| `StateHeading` | answered ■ / partly answered ◧ / not held □ | Word first; the glyph is redundant, never alone |
| `Headline` | present / absent | NEW; no amount permitted |
| `FigureBlock` | with end date / no end date recorded / link / no link | Solid 2px Ink left rule. **Every element of `figures[]` renders through this one block** — key, amount, `In force from`, end state, full instrument, evidence state — at every width, including the second and third figure of a turn. No compressed "same form" variant exists: that phrase would be a client comparison of two server strings (C2, PLAN §6.2) |
| `SuppliedFacts` | present / absent | Label over value, never two aligned columns. The **value is rendered exactly as `facts.*.value` arrives** (`120000000`, not `₹12,00,00,000`): no grouping, no ₹ the server did not write, and **not mono** — body sans at Caption 12, so a number the user typed can never be mistaken for a dated figure |
| `FindingLine` | present (`answered` with rows) / absent | `rows[].basis` at H2 18, directly under the duty — the largest body text on the card while `headline` renders nothing (§2 change 4). **Never clipped, never ellipsized** at any width (§16) |
| `RowItem` | five obligation states | Order is **duty (Body 14) → `FindingLine` (H2 18) → provision (mono Caption) · state word (Caption, beside it)**. The finding is the largest text in the row and the state word is the smallest, because `rows[].basis` carries the answer while `rows[].state` renders as "Does not apply" — which reads as the inverse of the truth (D10). A state word may never be rendered without the row's **full** `basis` in the same block (§18.2 rule 9) |
| `NotConfirmedItem` | pack_missing / unusable / cannot_verify / ⟨refusal⟩ / ⟨model_decision⟩ | Caution left rule and Caution label — the only hue on the page. Two suppressions: (a) a `detail` addressed to a model is dropped by the soft validator (§4.3, §18.2 rule 6) and the kind word plus `ref` render alone — never a `pack_missing` detail saying a provision is "not admitted for model use" on a card stamped "No model used"; (b) on a document turn, an item whose `duty` already appears in `scope_frame.unchecked[]` is **not repeated** as its own item — its `detail` hangs off the scope frame's "Why each was not checked" disclosure instead, so nothing server-supplied is dropped and no duty is counted twice (§7.8) |
| `SupersededItem` | present / absent / **withheld** | Governed then / governs now; instruments only, no in-force date; each status word beside its instrument and `detail` verbatim (red team L9). ~~Withheld when both statuses match~~ — withdrawn, see §18.2 rule 7 |
| `ConfirmedItem` | citation (has `ref`) / obligation row (has `obligation_id`) / **none** | "Confirmed: none" is a label for an empty list, never a claim. The **group heading follows the shape**: citations group under CONFIRMED; obligation rows group under **CHECKED AGAINST THE ACT** with "None of these is a finding of compliance.", because every such row in `document_context_2024` is `APPLIES_UNDETERMINED` or `CANNOT_DETERMINE` (D11). The count is `len(confirmed[])` and never `scope_frame.checked_count` (§13) |
| `LocatedItem` | present / absent | The empty-`confirmed` `partial` (I-U2): one server string naming what was searched, in what corpus, and that nothing usable was found. ⟨NEW⟩ — until Phase C supplies it the client writes no refusal prose and the card shows `not_confirmed[]` and "Confirmed: none" alone (§7.12) |
| `VerbatimBlock` | open / clipped with "Show the full text" | Text serif; the basis line is never clipped. A clip **may not end inside a numbered sub-section**: the cut falls at the last sub-section boundary that fits, and the clipped state carries a count derived from the text — "sub-sections (2)–(5) not shown" — never a summary of what they say. Footnote markup inside `verbatim` (`<sup>1</sup>[Provided further …]`) is rendered **literally**, as a visible marker, with "Bracketed spans marked ¹ are amendments recorded in the source." Stripping it would be repairing a source (CLAUDE.md) |
| `TextBasisLine` | always under verbatim or a citation record | Dashed 2px Ink-80 left rule |
| `ScopeFrame` | present (document turns) | Never collapsible, no close control (I-E25) |
| `NotHeldBlock` | DECLARED / CURRENT_ONLY / OUT_OF_SCOPE | Neutral Ink-80 rule. Never Caution, never red (C5) |
| `Marker [n]` | idle / focus / target-of | Button, 44px hit area. `aria-describedby` names **what it points at**: a citation marker names the cite ("Source 1: Companies Act 2013, s.2"); a figure marker names `figures[].key` + the instrument. A figure record with no addressable content gets **no marker**. Activating a marker **expands the pane's source sheet first**, then moves focus — focus is never sent into a hidden subtree (§15) |
| `Sources` | sheet (pane) / panel (web) · collapsed / open · empty | Collapsed summary names **counts only** — "1 citation · 2 dated figures" — never a date. The two as-of truths are never set in one line in one typeface; each keeps its own rule, position and words inside the open state (§9, §10) |
| `Actions` | copy / edit / demand signal (if supplied) | Secondary buttons, never the accent |
| `ServiceError` | transport / invalid / missing reason | **Dashed Ink-80 border** (Ink-40 is 1.7:1 and would leave the failure card with no visible boundary), Ink text, no glyph |
| `LiveRegion` | polite | Announces state word + question; "Copied with instruments and dates." |

---

## 7. Wireframes

Legend: `■` Answered, `◧` Partly answered, `□` Not held · `┃` solid rule = a figure (in-force date) ·
`┊` dashed rule = section text (ingestion basis) · `▌` Caution rule = not confirmed · `[n]` marker into
Sources. Questions are illustrative (contract §8); every legal string shown is engine output unless
marked **†** or ⟨⟩.

### 7.1 Empty state — pane, 360px

```
┌──────────────────────────────────────┐
│ Placedon      Open document dated    │
│               01-Jun-2024            │
│ Currency check  Register strip  Ask  │
│                                 ━━━  │
├──────────────────────────────────────┤
│ Ask about the Companies Act, 2013    │ Playfair 24
│ Every figure shows the instrument    │
│ that set it and the date it came     │
│ into force. What we do not hold, we  │
│ say we do not hold.                  │
│ ┌──────────────────────────────────┐ │
│ │ Holds  Companies Act, 2013       │ │ S: scope.held[]
│ │ 1 of 9 in-scope bodies of law    │ │ S: scope.sentence
│ │ are held      ▸ What is not held │ │
│ │ About                            │ │
│ │ (•) This document   ( ) The Act  │ │ native radios
│ │ Checks the open document, dated  │ │
│ │ 01-Jun-2024, against the         │ │
│ │ Companies Act, 2013.             │ │
│ │ WHAT CAN BE CHECKED              │ │ the list precedes the question field
│ │ This document                    │ │ in DOM, tab and visual order (§15)
│ │  Has the law this document rests │ │ S: bundles answers
│ │  on moved since it was made?     │ │
│ │ Companies Act obligations        │ │
│ │  Establish whether the company   │ │ S: obligations duty
│ │  is a small company      s.2(85) │ │
│ │  Hold an annual general meeting, │ │
│ │  and within the statutory gap    │ │
│ │                          s.96(1) │ │
│ │  Hold the minimum number of      │ │
│ │  board meetings, correctly       │ │
│ │  spaced                 s.173(1) │ │
│ │  Constitute a CSR committee, if  │ │
│ │  the company crosses a CSR       │ │
│ │  threshold              s.135(1) │ │
│ │ Law changes                      │ │
│ │  What changed in the law, dated  │ │ S: bundles answers
│ │  and sourced?                    │ │
│ │ Source lookup                    │ │
│ │  Show a section, for example     │ │
│ │  s.173                         † │ │
│ │ 15 obligations are checked. That │ │ † (⟨capabilities.note⟩ NEW)
│ │ is not the whole Act.            │ │
│ │ ┌──────────────────────────────┐ │ │
│ │ │ Ask about the Companies Act… │ │ │
│ │ └──────────────────────────────┘ │ │
│ │ As of 15-Sep-2026        [ Ask ] │ │ read-only; today only in v1 (§9)
│ │ Answers are given as the law     │ │
│ │ stands today.                    │ │
│ │ Enter asks · Shift+Enter new line│ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

**Why the list sits above the field.** It is the fence that makes a free-text box safe (§19 Q1), and a
keyboard user reaches DOM order, not visual proximity: drawn below the composer it could only be found
*after* Ask, i.e. after committing (§15). The cost is that the question field starts about two-thirds of
the way down a 360px pane in the empty state, so the pane opens scrolled to the top of the list rather
than to the field. The list renders **before the first turn only** (§6 `CapabilityList`), so from turn 2
the docked compact composer is the whole of the composer and nothing sits above the field.

**This frame requires `GET /v1/scope` (§4.1).** The Holds line, *What is not held* and the whole
*What can be checked* block are server text. Until that route exists, Phase B renders the **unfenced
fallback** — title, sub-line, About, question field, As of, Ask, and nothing else. No count, no register,
no capability list, and (per §6 `CapabilityList`) no control anywhere that points at the missing list. A
hard-coded "1 of 9" would recreate the C10 DPDP-chip failure the first time `scope.py` changes. §19 Q1
records what that fallback does to the answer on C1.

Choosing a row fills the question field; it never submits. A row whose capability declares inputs also
reveals `FactsFields` under the field, labelled with that obligation's own `evidence_needed` strings
("paid-up share capital", "turnover for the immediately preceding financial year", "holding or subsidiary
status" — `checker/obligations.py:714`). Free text alone sends no facts: there is no extractor, and
guessing facts from prose is exactly the misgrounding the product exists to refuse.

### 7.2 Empty state — web, 1440px

```
┌─ rail 232 ──────┬─ content ────────────────────────────────────────────────────────────┐
│ Placedon        │            Ask about the Companies Act, 2013                         │
│ [+ New question]│            Every figure shows the instrument that set it and the     │
├─────────────────┤            date it came into force. What we do not hold, we say we   │
│ THIS SESSION    │            do not hold.                                              │
│ No questions    │  ┌────────────────────────────────────────────────────────────────┐  │
│ yet.            │  │ Holds  Companies Act, 2013 · 1 of 9 in-scope bodies of law are │  │
│                 │  │ held                                        ▸ What is not held │  │
│                 │  │ About  ( ) This document — disabled            (•) The Act     │  │
│                 │  │        Document checks run in the Word add-in.                 │  │
│                 │  │ Section text and dated figures from the Act. A company is      │  │
│                 │  │ checked only on facts you enter.                               │  │
│                 │  │ ┌────────────────────────────────────────────────────────────┐ │  │
│                 │  │ │ Ask about the Companies Act, 2013                          │ │  │
│                 │  │ └────────────────────────────────────────────────────────────┘ │  │
│ Not saved.      │  │ As of 15-Sep-2026 (today only) · Enter asks · Shift+Enter [Ask] │ │
│ Closing this    │  └────────────────────────────────────────────────────────────────┘  │
│ window clears   │            What can be checked  (as pane; provision refs mono, right) │
│ the list.       │            15 obligations are checked. That is not the whole Act. †   │
└─────────────────┴───────────────────────────────────────────────┬──────────────────────┘
                                                                  │ SOURCES              │
                                                                  │ Nothing to inspect   │
                                                                  │ yet.                 │
                                                                  └──────────────────────┘
```

The Sources column is **reserved, not omitted**: its 48px header and its gutter render with "Nothing to
inspect yet." So the first answer fills a column that is already there, instead of sliding the whole
reading column a quarter-screen left at the same moment focus moves (§5). No motion is added (C6).
Same `GET /v1/scope` dependency and the same unfenced fallback as §7.1.

### 7.3 Waiting — both widths

```
│ ┌ About the Act ───────────────────┐ │   from the request values the user set
│ Is this company a small company?     │
│ Asked as of 15-Sep-2026              │
│ Checking the Companies Act, 2013.    │   static; no spinner, no timer, no stages.
│ [ Cancel ]                           │   Names the corpus, never a machine deciding
│                                      │   a legal question (§4.4, §13)
│ ┌ composer disabled while waiting ─┐ │
```

After Cancel: "Cancelled before a result arrived. Nothing is shown." The rail row reads "Waiting", then
"Cancelled".

### 7.4 Answered — pane, 360px  (fixture `answered_small_company`)

```
│ ┌ About the Act ───────────────────┐ │
│ Is this company a small company?     │
│ Asked as of 15-Sep-2026 · No model   │
│ used · Looked up s.2(85)             │
│ ■ Answered                           │ Playfair 22 — chrome, not the answer
│ Establish whether the company is a   │ S: rows[].duty, Body 14
│ small company                        │
│ a limb exceeds its limit, so not a   │ S: rows[].basis — **H2 18, the
│ small company                        │ largest body text on the card**
│ Companies Act 2013, s.2(85) ·    [1] │ S: rows[].provision, mono Caption
│ Does not apply                       │ S: rows[].state, Caption beside it
│                                      │ (D10: alone it reads as its inverse)
│ YOU SUPPLIED                         │ S: facts{} · provenance USER_FACT
│ company_class                        │  label over value, never two columns
│   private                            │  (F20: two mono columns overflow 320px)
│ paid_up_capital_rupees               │
│   120000000                          │  value exactly as `facts.*.value` arrives
│ turnover_rupees                      │  (F15b: ₹12,00,00,000 was client-composed)
│   800000000                          │
│ DATED FIGURES                        │
│ ┃ small_company.paid_up_capital.     │ S: figures[].key (⟨label⟩ NEW)
│ ┃ prescribed                         │
│ ┃ ₹10 crore                          │ S: amount, mono 20
│ ┃ In force from 01-Dec-2025          │ S: effective_from
│ ┃ No end date recorded               │ effective_to = null
│ ┃ G.S.R. 880(E), Companies           │ S: instrument, full, wrapped
│ ┃ (Specification of Definition       │
│ ┃ Details) Amendment Rules, 2025,    │
│ ┃ dated 01-12-2025                   │
│ ┃ Corroborated                   [2] │ S: evidence_state
│ ┃ Gazette link: not recorded         │ source_url is not a URL
│ ┃ small_company.turnover.prescribed  │ figures[1] — a SECOND FULL BLOCK,
│ ┃ ₹100 crore                         │ identical in every element. No
│ ┃ In force from 01-Dec-2025          │ compressed variant and no "same
│ ┃ No end date recorded               │ form": that phrase would be the
│ ┃ G.S.R. 880(E), Companies           │ client comparing two server strings,
│ ┃ (Specification of Definition       │ and it would drop the instrument and
│ ┃ Details) Amendment Rules, 2025,    │ the in-force date from the limb that
│ ┃ dated 01-12-2025                   │ decides the answer (C2, PLAN §6 check
│ ┃ Corroborated                   [3] │ 2, §6 `FigureBlock`)
│ ┃ Gazette link: not recorded         │
│ What this does not establish         │ S: what_it_is_not — a **string** in
│ <the paragraph, verbatim>            │ this fixture, a list in
│                                      │ document_context_2024 (D1)
│ [Copy with sources] [Edit question]  │
│ ▸ Sources for this turn (3)          │
│   s.2 Definitions · Text as ingested │ both truths named even when collapsed
│   18-Aug-2026 · 2 figures in force   │
│   from 01-Dec-2025                   │
└──────────────────────────────────────┘
```

### 7.5 Answered — web, 1440px

```
┌ rail ───────────┬ content ─────────────────────────────────┬ SOURCES · Turn 1 · About the Act ──┐
│ THIS SESSION    │ ┌ About the Act ─────────────────────────┐│ [1] Companies Act 2013, s.2        │
│ ■ Is this       │ │ Is this company a small company?       ││     (Definitions)                  │
│   company a     │ │ Asked as of 15-Sep-2026 · No model     ││     Corroborated · No defects      │
│   small         │ │ used · Looked up s.2(85)               ││     recorded                       │
│   company?      │ │ ■ Answered                             ││     Sub-clauses the row named      │
│   Answered ·    │ │ Establish whether the company is a     ││     (resolved to s.2; sub-clause   │
│   15-Sep-2026   │ │ small company                          ││     text not extracted):           │
│                 │ │ a limb exceeds its limit, so not a     ││     2(85)(i)  2(85)(ii)            │
│                 │ │ small company                     [1]  ││     [Show the content hashes]      │
│                 │ │ s.2(85) · Does not apply               ││     Section text is not part of    │
│                 │ │ YOU SUPPLIED  private                  ││     this response.                 │
│                 │ │               120000000  800000000     ││                                    │
│                 │ │ ┃ small_company.paid_up_capital.presc. ││                                    │
│                 │ │ ┃ ₹10 crore   In force from 01-Dec-2025││ ┊ Text as ingested 18-Aug-2026.    │
│                 │ │ ┃ No end date recorded                 ││ ┊ Current consolidation, not a     │
│                 │ │ ┃ G.S.R. 880(E), Companies (Specifica- ││ ┊ point-in-time version.           │
│                 │ │ ┃ tion of Definition Details) Amendment││   ▸ The pack's full statement      │
│                 │ │ ┃ Rules, 2025, dated 01-12-2025        ││   Fetched 18-Aug-2026, 19-Aug-2026 │
│                 │ │ ┃ Corroborated · Gazette link: not [2] ││   (fetch dates, not in-force dates)│
│                 │ │ ┃ recorded                             ││   Source link ⟨dead host, D3⟩      │
│                 │ │ ┃ small_company.turnover.prescribed    ││ [2][3] G.S.R. 880(E) …             │
│                 │ │ ┃ ₹100 crore  In force from 01-Dec-2025││ ┃ In force from 01-Dec-2025        │
│                 │ │ ┃ No end date recorded                 ││ ┃ No end date recorded             │
│                 │ │ ┃ G.S.R. 880(E), Companies (Specifica- ││                                    │
│                 │ │ ┃ tion of Definition Details) Amendment││                                    │
│                 │ │ ┃ Rules, 2025, dated 01-12-2025        ││                                    │
│                 │ │ ┃ Corroborated · Gazette link: not [3] ││                                    │
│                 │ │ ┃ recorded                             ││                                    │
│                 │ │ What this does not establish …         ││                                    │
│                 │ │ [Copy with sources] [Edit question]    ││                                    │
│                 │ └────────────────────────────────────────┘│ Evidence pack · looked up "s.2(85)"│
│                 │ ┌ composer, docked ─────────────────────┐ │ route exact · usable               │
│                 │ └───────────────────────────────────────┘ │ ACT:COMPANIES_ACT_2013:S2          │
└─────────────────┴──────────────────────────────────────────┴────────────────────────────────────┘
```

### 7.6 Partly answered — pane, 360px  (fixture `partial_s173_s16`)

```
│ ┌ About the Act ───────────────────┐ │
│ What does s.173 require, and does    │
│ s.16 apply here?                     │
│ Asked as of 15-Sep-2026 · No model   │
│ used · Looked up s.173 and s.16      │
│ ◧ Partly answered                    │ Playfair 22
│ NOT CONFIRMED                        │ Caution label
│ ▌Not in the evidence pack            │ kind → words
│ ▌ACT:COMPANIES_ACT_2013:S16 exists   │ S: not_confirmed[].detail, verbatim
│ ▌in state SUSPENDED but is not       │
│ ▌admitted for model use              │ (D5: written for a model reader)
│ CONFIRMED                            │
│ │Companies Act 2013, s.173 (Meetings │ S: confirmed[].cite            [1]
│ │of Board)                           │
│ │Corroborated · No defects recorded  │
│ │┊(1) Every company shall hold the   │ S: confirmed[].verbatim, serif
│ │┊first meeting of the Board of      │ open by default (UX §3.2)
│ │┊Directors within thirty days of    │
│ │┊the date of its incorporation and  │
│ │┊thereafter hold a minimum number   │
│ │┊of four meetings of its Board of   │
│ │┊Directors every year …             │ the cut falls at the end of (1),
│ │┊Sub-sections (2)–(5) not shown.    │ never mid-sub-section (§6)
│ │┊[ Show the full text of s.173 ]    │ count derived from the text, never
│ │                                    │ a summary of what (2)–(5) say
│ │┊¹[Provided further that …]         │ footnote markup is rendered
│ │┊Bracketed spans marked ¹ are       │ literally; stripping it would be
│ │┊amendments recorded in the source. │ repairing a source (CLAUDE.md)
│ │┊Text as ingested 18-Aug-2026.      │ S: law_version.corpus_fetched
│ │┊Current consolidation, not a       │ never clipped
│ │┊point-in-time version.             │
│ [Tell us this is blocking you]       │ demand_signal present
│ [Copy with sources] [Edit question]  │
│ ▸ Sources for this turn (1)          │
```

**Why the clip stops at the end of (1) and says so.** s.173(5) deems a One Person Company, small company
or dormant company to comply with one meeting in each half of a calendar year — which changes the answer
for this product's core user class. A clip ending mid-(1) at "four meetings …" states a rule the same
provision later disapplies, with nothing on screen saying more text follows. So the cut falls at the last
sub-section boundary that fits, and the clipped state names what is hidden by number only (§6
`VerbatimBlock`). The eight-line figure in §19 Q6 is a target, not a hard cut: the boundary wins.

**Web:** the same card in the content column; Sources · Turn 2 holds the citation record, the pack
statement, fetch dates, the hash and the pack keys (`usable_keys`, `missing[]`).

### 7.7 Not held — pane and web  (fixture `out_of_scope_fema`)

```
│ ┌ About the Act ───────────────────┐ │
│ What must we report to RBI for this  │
│ share allotment to a foreign         │
│ investor?                            │
│ Asked as of 15-Sep-2026 · No model   │
│ used                                 │
│ □ Not held                           │ Playfair 22
│ ▏Foreign Exchange Management Act,    │ S: body.name · Ink-80 rule, never Caution
│ ▏1999 and the FDI rules              │
│ ▏RBI / DPIIT · In scope, nothing     │ S: body.regulator · DECLARED → words
│ ▏acquired                            │
│ Foreign Exchange Management Act,     │ S: reason, verbatim refusal_for()
│ 1999 and the FDI rules (RBI / DPIIT) │
│ is within scope — it covers foreign  │
│ investment, sectoral caps, reporting │
│ (FC-GPR, FC-TRS), downstream         │
│ investment — but no instrument has   │
│ been acquired, so nothing here can   │
│ be decided. Nothing acquired.        │
│ Sectoral caps change by press note,  │
│ which is a different acquisition     │
│ problem from a Gazette rule. This is │
│ a statement about what we hold, not  │
│ a finding that no obligation applies.│
│ WHAT WE HOLD                         │
│ Companies Act, 2013                  │ S: held[]
│ 1 of 9 in-scope bodies of law held   │ S: scope.sentence
│ [See what can be checked]            │ only with `GET /v1/scope`; absent in
│                                      │ the unfenced fallback (§6, §7.1)
│ Sources for this turn: none. This    │
│ turn has no citations.               │
```

**Web, 1440:** identical in the content column; the Sources panel reads "This turn has no citations."
and shows the scope register (held / current text only / declared, nothing acquired / out of scope).

### 7.8 Document context — pane, 360px  (fixture `document_context_2024`)

```
│ Placedon    Open document dated      │ pane header (client-read, pre-request)
│             01-Jun-2024              │
│ ┌ About the open document ·         ┐│ band, no glyph
│ │ dated 01-Jun-2024                 ││ S: context.document_date
│ Is the law this document relies on   │
│ still current?                       │
│ Asked as of 15-Sep-2026 · No model   │
│ used                                 │
│ ◧ Partly answered                    │
│ SCOPE OF THIS CHECK                  │ not dismissable, no close control
│ Checked 12 of 15 against Companies   │ S: scope_frame.sentence, verbatim,
│ Act 2013, as at 2026-09-15.          │ line breaks preserved (D4: "as at")
│ NOT checked (3) — these were not     │
│ examined at all, and silence about   │
│ them is not a finding:               │
│  · Obtain the required approvals for │
│    related-party transactions — its  │
│    governing instrument is not held  │
│    or not yet reviewed; needs: Rule  │
│    15, Companies (Meetings of Board  │
│    and its Powers) Rules, 2014 …     │
│ NOT CONFIRMED (3)                    │
│ ▌Cannot verify                       │ S: not_confirmed[].kind → words
│ ▌Obtain the required approvals for   │ S: duty · provision
│ ▌related-party transactions          │
│ ▌Companies Act 2013, s.188           │
│ ▌Companies Act 2013 s.188, held      │ S: detail, verbatim
│ ▌verbatim in corpus; the members'-   │
│ ▌approval threshold is a delegated   │
│ ▌rule (S-188-RULES) … is STAGED      │
│ ▌…two more                           │
│ SUPERSEDED (1)                       │
│ │Establish whether the company is a  │ S: superseded[].duty
│ │small company · s.2(85)             │
│ │Governed then  G.S.R. 700(E),       │ S: governed_then, full string
│ │Companies (Specification of         │ no in-force date is claimed:
│ │Definition Details) Amendment       │ a Finding carries none (I-E24)
│ │Rules, 2022, dated 15-09-2022       │
│ │Governs now    G.S.R. 880(E), …     │ S: governs_now
│ CHECKED AGAINST THE ACT (11)         │ count = len(confirmed[]), NEVER
│ │None of these is a finding of       │ scope_frame.checked_count (12).
│ │compliance.                         │ UI sub-line; the group word is not
│ │Hold an annual general meeting, and │ S: confirmed[] obligation rows
│ │within the statutory gap            │
│ │Companies Act 2013, s.96(1)         │
│ │Applies · not determined            │ APPLIES_UNDETERMINED → words
│ │s.96(1) reaches every company other │ S: basis
│ │than an OPC; no AGM dates were      │
│ │supplied                            │
│ │…two more shown  [Show all 11 rows] │ len(confirmed[]) again
│ What this does not establish         │ S: what_it_is_not[], verbatim
│ · that the document is valid,        │
│   correctly drafted, or legally      │
│   effective                          │
│ · that the obligations named here    │
│   are the whole of the Act that      │
│   applies                            │
│ · that a row marked verified is      │
│   compliant -- only that its legal   │
│   basis is current                   │
│ [Copy with sources] [Edit question]  │
│ Sources for this turn: none supplied.│ no citations[], no figures[]
│ Nothing was changed in your document.│
```

**Word desktop, 1440px** — the only 1440 frame in which a document turn exists:

```
┌──────────────── Word document canvas ─────────────────────┬──── Placedon pane, 400px ────┐
│                                                            │ Currency check Register Ask  │
│           [ the practitioner's own document ]              │ ┌ About the open document ·  │
│                                                            │ │ dated 01-Jun-2024          │
│                                                            │ ◧ Partly answered            │
│                                                            │ SCOPE OF THIS CHECK …        │
│                                                            │ (identical to the 360px pane;│
│                                                            │  lines simply wrap less)     │
└────────────────────────────────────────────────────────────┴──────────────────────────────┘
```

**Web, 1440px:** there is no document turn. The composer shows `( ) This document — disabled ·
Document checks run in the Word add-in.`

### 7.9 Follow-up — pane, 360px  (fixture `followup_turnover`)

```
│ ■ Answered · Is this company a small │ turn 1, collapsed: no amount, no
│   company? · Asked as of 15-Sep-2026 │ truncated instrument
│   · 2 dated figures        [Expand]  │
│ ┌ About the Act ───────────────────┐ │
│ Follow-up to turn 1                  │ S: parent_turn_id
│ And the turnover limit?              │
│ Asked as of 15-Sep-2026 · No model   │
│ used · Looked up s.2(85)             │ S: evidence_pack.retrieval_query
│ ■ Answered                           │
│ ┃ small_company.turnover.prescribed  │
│ ┃ ₹100 crore                         │
│ ┃ In force from 01-Dec-2025          │
│ ┃ No end date recorded               │
│ ┃ G.S.R. 880(E), Companies           │
│ ┃ (Specification of Definition       │
│ ┃ Details) Amendment Rules, 2025,    │
│ ┃ dated 01-12-2025                   │
│ ┃ Corroborated · Gazette link: not   │
│ ┃ recorded                       [1] │
│ [Copy with sources] [Edit question]  │
│ ▸ Sources for this turn (2)          │
├──────────────────────────────────────┤ sticky, compact
│ About the Act · As of 15-Sep-2026    │
│                             Change ▾ │
│ ┌──────────────────────────────────┐ │
│ │ Ask another question             │ │
│ └──────────────────────────────────┘ │
│ Each turn shows what it looked   [Ask]│
│ up.                                  │
```

If the About or As-of value differs from the previous turn's, the new card carries a badge:
"About changed from the previous turn" / "Date changed from the previous turn".

### 7.10 Partly answered, then a follow-up — web, 1440px

Turn 1 is collapsed to a line carrying no amount; the panel follows turn 2, the turn in view, and names
it in its own header.

```
┌ rail ───────────┬ content ─────────────────────────────────┬ SOURCES · Turn 2 · About the Act ──┐
│ THIS SESSION    │ ┌ ■ Answered · Is this company a small ──┐│ [1] Companies Act 2013, s.173      │
│ ■ Is this       │ │   company? · 15-Sep-2026 · 2 dated     ││     (Meetings of Board)            │
│   company a     │ │   figures                    [Expand]  ││     Corroborated · No defects      │
│   small         │ └────────────────────────────────────────┘│     recorded                       │
│   company?      │ ┌ About the Act ─────────────────────────┐│ ┊ (1) Every company shall hold the │
│   Answered      │ │ What does s.173 require, and does s.16 ││ ┊ first meeting of the Board of    │
│ ◧ What does     │ │ apply here?                            ││ ┊ Directors within thirty days …   │
│   s.173 require │ │ Asked as of 15-Sep-2026 · No model     ││ ┊ Text as ingested 18-Aug-2026.    │
│   …             │ │ used · Looked up s.173 and s.16        ││ ┊ Current consolidation, not a     │
│   Partly        │ │ ◧ Partly answered                      ││ ┊ point-in-time version.           │
│   answered      │ │ NOT CONFIRMED                          ││ ▸ The pack's full statement        │
│                 │ │ ▌Not in the evidence pack              ││ Fetched 18-Aug-2026, 19-Aug-2026   │
│                 │ │ ▌ACT:COMPANIES_ACT_2013:S16 exists in  ││ (fetch dates, not in-force dates)  │
│                 │ │ ▌state SUSPENDED but is not admitted   ││ Evidence pack · looked up          │
│                 │ │ ▌for model use                         ││ "s.173 and s.16" · route exact     │
│                 │ │ CONFIRMED                              ││ usable ACT:COMPANIES_ACT_2013:S173 │
│                 │ │ │Companies Act 2013, s.173 (Meetings   ││ missing ACT:COMPANIES_ACT_2013:S16 │
│                 │ │ │of Board) · Corroborated          [1] ││                                    │
│                 │ │ │┊ verbatim, open, 16 lines then Show  ││                                    │
│                 │ │ │┊ Text as ingested 18-Aug-2026 …      ││                                    │
│                 │ │ [Tell us this is blocking you]         ││                                    │
│                 │ │ [Copy with sources] [Edit question]    ││                                    │
│ Not saved.      │ └────────────────────────────────────────┘│                                    │
│ Closing this    │ ┌ composer, docked ─────────────────────┐ │                                    │
│ window clears   │ │ About the Act · As of 15-Sep-2026 …   │ │                                    │
│ the list.       │ └───────────────────────────────────────┘ │                                    │
└─────────────────┴──────────────────────────────────────────┴────────────────────────────────────┘
```

A follow-up turn (`followup_turnover`) appends below turn 2 with `Follow-up to turn 1`, its own band,
stamp, figure block and Sources; the rail gains a third row; the panel swaps to `Sources · Turn 3` once
that card is the turn in view.

### 7.11 Service error — not an answer state

```
│ No result                            │ `h2` of an `article`; focused and
│                                      │ announced by pipeline step 6.
│                                      │ Dashed **Ink-80** border (Ink-40 is
│                                      │ 1.7:1, §14), Ink text, no glyph
│ The service did not return a result, │
│ so there is no answer, partial or    │
│ otherwise. Your question is still in │
│ the box.                             │
│ Nothing was changed in your document.│ pane only
│ [ Send again ]                       │
```

Covers `BUDGET_EXHAUSTED`, transport failure, a body that fails `validate_hard()`, a state the client does
not know, and an `out_of_scope` with no `reason`. "Send again" is legitimate because no result was given;
retry on an *answer* is refused (C3, brief C15).

### 7.12 Partly answered with nothing confirmed — the state that will dominate

`answered` is rare (§23 risk 2). Contract §6 routes `ABSTAINED`, `REFUSED_BEFORE_CALL`,
`INSUFFICIENT_EVIDENCE` and retrieval route `abstain` *inside* the Companies Act to `partial` with an
empty `confirmed[]` (I-U2). **No fixture covers it**, and it is the commonest outcome the frame must
carry. It is drawn twice below: as it renders today, and as it should render once Phase C supplies the
`located` string.

**(a) Today — no `located` item exists.** The card is honest but thin, and the client writes no prose:

```
│ ┌ About the Act ───────────────────┐ │
│ What is the stamp duty on this share │
│ transfer?                            │
│ Asked as of 15-Sep-2026 · No model   │
│ used · Looked up "stamp duty share   │ S: evidence_pack.retrieval_query
│ transfer"                            │ — the only record of what was tried
│ ◧ Partly answered                    │
│ NOT CONFIRMED                        │
│ ▌Not in the evidence pack            │ S: not_confirmed[].kind → words
│ ▌<server detail, verbatim>           │ S: detail
│ Confirmed: none                      │ UI label for an empty list,
│                                      │ never a claim (§6 ConfirmedItem)
│ [Tell us this is blocking you]       │ if demand_signal is supplied
│ [Copy with sources] [Edit question]  │
│ Sources for this turn: none supplied.│
```

This is the blank-refusal UX §3.2 warns against, and the design does **not** repair it with client copy:
inventing "we searched the Act and found nothing" would be the client writing refusal prose, which I-E28
forbids. It is an accepted v1 weakness, recorded as such.

**(b) With the `located` item (⟨NEW⟩, §6 `LocatedItem`, §18.2 rule 5).** One server string replaces
"Confirmed: none":

```
│ CONFIRMED                            │
│ │<one server sentence naming (i) the │ ⟨located⟩ NEW — Phase C
│ │corpus searched, (ii) the query or  │ The client supplies none of these
│ │provisions reached, and (iii) that  │ three facts and writes no part of
│ │nothing usable was found there>     │ this sentence
```

**The undeclared body (Income-tax, GST — I-E28) has no screen and cannot have one.** `scope.py` declares
nine bodies; a question about a tenth produces no `body` record and therefore no `refusal_for()` text, so
`out_of_scope` cannot be returned and the turn falls into (a) above. **Blocking Phase C dependency:** body
detection plus refusal copy for an undeclared body — named as ⟨`body.undeclared_reason`⟩ in §18.1. Until
it exists, a question about income tax renders as a `partial` that names the Companies Act corpus and
nothing else, and the reader cannot tell it from a partial where real work was done. §22 gains falsifier
7 for exactly this.

---

## 8. Turn anatomy, in order, per state

Common to all three: context band → parent line → question → stamp → change badge → state heading →
headline (if supplied).

| `answered` | `partial` | `out_of_scope` |
|---|---|---|
| `rows[]` | `scope_frame` (document turns; leads the result, I-E25) | `body.name` + `regulator` + status words |
| `facts` ("You supplied") | **NOT CONFIRMED** — `not_confirmed[]` | `reason`, verbatim |
| `figures[]` | **SUPERSEDED** — `superseded[]` (document turns) | "What we hold": `held[]` + `scope.sentence` |
| `citations[]` markers | **CONFIRMED** (citation items, `verbatim` open) / **CHECKED AGAINST THE ACT** (obligation rows) — `confirmed[]`, counted by `len()` | `See what can be checked` (only when `capabilities[]` exists) |
| `what_it_is_not` **when supplied** | `what_it_is_not` **when supplied** | scope register (Sources) |
| actions | `demand_signal` (if supplied) + actions | actions |
| Sources | Sources | "This turn has no citations." |

**`what_it_is_not` is not guaranteed.** It carries the bound on the claim, but only two of the five
fixtures supply it (`answered_small_company`, a string; `document_context_2024`, a list of three):
`partial_s173_s16` and `followup_turnover` have none, so those cards end at the confirmed text and the
figure block with no closing bound, exactly as §7.6 and §7.9 draw them. The client writes nothing in its
place (I-E28) and the heading never appears alone (§4.3 step 5). §18.2 rule 10 asks Phase C to make the
field mandatory on `answered` and `partial`; until it is, §20's claim that the design bounds every claim
holds only for the turns that carry it.

Never rendered anywhere: a confidence number, a coverage float, a reviewer name, `human_reviewed`, a
"Verified" seal, a model name, or any state the client worked out for itself (brief non-negotiables 4, 6;
I-E10, I-E11, I-E12, I-E17).

---

## 9. The dates: six wordings, one position each

| Truth | Exact words | Only place it appears | Form |
|---|---|---|---|
| The date the user asked about | `Asked as of 15-Sep-2026` | The turn stamp | Caption sans, Ink-80. The bare phrase "as of" appears nowhere else |
| **A figure's in-force date** | `In force from 01-Dec-2025`, then `No end date recorded` or `Until <date>`, then the **full** instrument string | Inside the figure block, directly under the amount (C2) | **Solid** 2px Ink left rule, mono date, label in sans |
| **Section text's basis** | `Text as ingested 18-Aug-2026. Current consolidation, not a point-in-time version.` | Only beneath a verbatim quotation or a citation record | **Dashed** 2px Ink-80 left rule, caption sans under a text-serif quote. Never adjacent to an amount |
| A fetch date | `Fetched 18-Aug-2026, 19-Aug-2026 (fetch dates, not in-force dates)` | Inside a Sources citation record only | Caption, Ink-80 |
| **The read date inside a server sentence** | `as at 2026-09-15`, inside `scope_frame.sentence` | Only inside that sentence, on a document turn | Rendered **verbatim and never restyled**, even though it is a sixth wording for a date this table otherwise calls "Asked as of" (D4; F28) |
| An instrument's own date, inside a server string | e.g. `…Amendment Rules, 2025, dated 01-12-2025` | Wherever that string is rendered | Verbatim, never reformatted, never relabelled "in force from" |

Rules that make the first two impossible to conflate:
- **`as_of` is today, and only today, in v1.** The engine has no point-in-time capability
  (`law_version.point_in_time_verified` is false; the pack statement says "no statement here is a
  statement about the law as it stood on any past date" — I-E16, I-U6). A past `as_of` would put the
  largest date on the card — `Asked as of 01-Jan-2020` — above text and figures that describe 2026 law,
  which is the CLAUDE.md non-negotiable ("never use a current consolidated Act as pre-amendment ground
  truth") committed by the client. So the field is read-only (§6). If Phase C ever makes it editable it
  must also supply the line that fires when `as_of` precedes `law_version` coverage, and §18.2 gains a
  hard rule refusing any figure whose `effective_from` is later than `as_of`.
- `figures[].effective_from` is the only source of "In force from". The validator refuses a citation or a
  confirmed item that carries `effective_from` at all (`scripts/assistant_contract.py:104,121`).
- The text basis comes from `law_version` only — pack level, never per provision (K10).
- `retrieved_on` is never rendered outside a source record and never without its "fetch date" label
  (brief non-negotiable 3).
- `scope_frame.sentence` contains a sixth wording, "as at 2026-09-15", which is the read date in the
  server's own words. It is rendered verbatim and never restyled; Phase C is asked to align that
  vocabulary with this table (D4).
- **No amount may appear in a headline** (proposed validator rule, from the evidence direction). Amounts
  exist in exactly two places: a figure block, which always carries instrument and in-force date, and the
  "You supplied" block, which is labelled as the user's own facts and carries no legal claim.

---

## 10. Sources

Header (web, sticky): `Sources · Turn 2 · About the open document`. Contents, in order:

1. **Each citation** — `[n]`, `cite` (mono) and `title`; `evidence_state` as a word; `defects[]` listed
   plainly or "No defects recorded"; `unusable_reason` when present; `verbatim` when the response
   supplies it, otherwise "Section text is not part of this response."; the spans an obligation row cited
   (`rows[].cited_spans`: path, resolved, first 12 hex of the sha256); the dashed text-basis line; the
   pack statement in a closed disclosure; fetch dates; the source link (only when `source_url` parses as
   an `https://` URL).
2. **Each figure's instrument record** — full instrument string, `In force from` / end state,
   `evidence_state`, and "Gazette link: not recorded" when `source_url` is not a URL. **Since `0fae26c`
   (2026-09-17)** an attested figure serves its recorded or corroborated Gazette URL
   (`https://egazette.gov.in/WriteReadData/2025/268124.pdf` for 880(E)); the "UNRESOLVED" marker remains
   only on rows that are not served.
3. **Evidence pack** — `retrieval_query` ("Looked up …"), `route`, `usable_keys`, `unusable_keys`,
   `missing[]`, all in mono.
4. **Steps the server recorded** — only when `stages[]` is present, i.e. the document path (K9), as a
   closed disclosure using ⟨`stages[].caption`⟩ (NEW). Internal `what` names are never shown. It is a
   record after the fact, never progress.

**Behaviour.** Web: an IntersectionObserver picks the turn with the largest visible share and swaps the
panel; activating a marker also swaps and moves focus into that item, which carries a "Back to answer"
button. The panel never mixes turns. Pane: each turn has its own `Sources for this turn (n)` section —
collapsed by default in every state, with a summary line that still names the cite, the text basis and
the in-force date, so the two truths survive collapse. Partial's verbatim text is *not* inside Sources;
it sits in the CONFIRMED item and is open by default (UX §3.2).

**Cut for v1:** a search bar in the panel (H-E3) — a turn carries one to three citations, so there is
nothing to search (C6). Revisit above eight.
**Deferred:** the currency strip (UX §4). `figures[]` carries the instrument in force, not its lineage;
a strip needs NEW `figures[].lineage[]`. Until then no timeline is drawn, and no node is labelled "now" —
"No end date recorded" is the only truthful claim about the present.

---

## 11. Composer

Top to bottom, nothing behind a "+" or a "/" (C-E1, C-E9 rejected):

1. **Holds line (read-only)** — `Holds` + `scope.held[]` + `scope.sentence` verbatim, then a
   **What is not held** disclosure over ⟨`scope.bodies[]`⟩ grouped by status: held (Companies Act, 2013);
   current text only (SEBI LODR); in scope, nothing acquired (LLP Act 2008, SEBI ICDR/SAST/PIT/Buyback,
   FEMA 1999, IBC 2016, Competition Act 2002, stamp duty, DPDP 2023); outside scope (PoSH, AI
   regulation). Names are facts, not chips — a chip would recreate the C10 DPDP failure.
2. **About** — two native radios: `This document` / `The Act`, each with one hint line
   (§13). On the web the document option is disabled with its reason; in the pane it is disabled when no
   document date could be read.
3. **What can be checked** — before the first turn only, from ⟨`capabilities[]`⟩ (NEW, generated from
   `checker/bundles.py` `answers` and the obligation register, I-R4). **It sits here, above the question
   field**, so a keyboard user meets it before Ask rather than after (§15, §7.1). It never names a
   DECLARED, CURRENT_ONLY or OUT_OF_SCOPE body, an SD-002 section (s.16, 124, 76A, 329, 236, 465, 247,
   74, 78) or a Rules citation (brief non-negotiable 9).
4. **Question field** — placeholder "Ask about the Companies Act, 2013", later "Ask another question".
   Activating a capability row fills it and moves focus to the first revealed facts field, or here when
   the capability declares no inputs (§15).
5. **Facts for this check** — shown only when a chosen capability declares inputs; labels are the
   engine's own `evidence_needed` strings.
6. **Footer** — `As of [15-Sep-2026]` (the slot Claude gives the model picker, C-E6), the key hint, and
   **Ask** (Slate on the web, the one accent; **Ink in the pane**, where the docked composer shares the
   screen with Caution — §14).

After the first turn the composer docks (sticky) and compacts to one line of values plus the field;
**Change** reopens the full control set. The values themselves stay on screen at all times, so what the
next turn will use is never hidden.

---

## 12. History

**Session-only. Nothing persisted, no search, no sharing** (settles K12).

- Web rail: one row per turn — state word + glyph, question (two lines), asked-as-of. Activating a row
  scrolls to the turn and focuses its heading. Footer: "Not saved. Closing this window clears the list."
- Pane: the turns are the history. Earlier turns collapse to one line when a new turn arrives (§7.9).
- Why not persist: no conversation state exists (I-E34); the session release guard catches only verbatim
  fragments of 40+ characters, so a stored question that paraphrases client text is not caught (I-E32);
  persistence would imply sharing and search, which §19 Q8 cuts.

---

## 13. Exact copy

**(S)** = rendered from the response verbatim · **(UI)** = fixed · **†** = proposed, no engine produces it.

| Where | Copy |
|---|---|
| Empty title | Ask about the Companies Act, 2013 (UI) |
| Empty sub | Every figure shows the instrument that set it and the date it came into force. What we do not hold, we say we do not hold. (UI) |
| Holds line | Holds (UI) · `scope.held[]` (S) · `scope.sentence` (S) · What is not held (UI) |
| About | About · This document · The Act (UI) |
| Hint, This document | Checks the open document, dated {context.document_date}, against the Companies Act, 2013. (UI + field) |
| Hint, The Act | Section text and dated figures from the Act. A company is checked only on facts you enter. (UI) |
| Hint, web document option | Document checks run in the Word add-in. (UI) |
| Hint, no document date | No date could be read from this document, so document checks cannot run. (UI; the orchestrator refuses without a date, I-E5) |
| As of | As of {today, DD-Mon-YYYY} (UI, read-only) · Answers are given as the law stands today. Placedon holds a current consolidation, not point-in-time law. (UI) — **no invalid state exists in v1**: the field cannot be edited, so no card can be stamped with an as-of the engine cannot honour (§6, §9, I-U6) |
| Key hint | Enter asks · Shift+Enter for a new line (UI) |
| Submit | Ask (UI) |
| Capability heading / note | What can be checked (UI) · 15 obligations are checked. That is not the whole Act. († ⟨capabilities.note⟩) |
| Facts block (composer) | Facts for this check (UI); field labels = `evidence_needed` strings (S) |
| Waiting | Waiting for the server's decision. (UI) · Cancel (UI) |
| Cancelled | Cancelled before a result arrived. Nothing is shown. (UI) |
| Context band | About the Act (UI) · About the open document · dated {document_date} (UI + field) |
| Stamp | Asked as of {as_of} (UI + field) · No model used / A model was used (`uses_model`) · Looked up {evidence_pack.retrieval_query} (UI + field) |
| Parent line | Follow-up to turn {n} (UI, from `parent_turn_id`) |
| Change badge | About changed from the previous turn. · Date changed from the previous turn. (UI) |
| State words | Answered · ~~Partly answered~~ **Abstained in part** (Abstained, when `confirmed[]` is empty) · Not held (UI, from `state`; changed 2026-09-17, §27) |
| Row states | Applies · met (APPLIES_SATISFIED) · Applies · not met (APPLIES_NOT_SATISFIED) · Applies · not determined (APPLIES_UNDETERMINED) · Does not apply (DOES_NOT_APPLY) · Cannot determine (CANNOT_DETERMINE) |
| Facts block (answer) | You supplied (UI); keys and values (S) |
| Figure block | {figures[].key or ⟨label⟩} (S) · {amount} (S) · In force from {effective_from} (UI + field) · No end date recorded / Until {effective_to} (UI) · {instrument} (S, full, never shortened) · {evidence_state} sentence-cased (S) · Gazette link: not recorded (UI, when `source_url` is not a URL) |
| Verbatim clip | Sub-sections {first}–{last} not shown. (UI + a count derived from the text, never a summary of what they say) · Show the full text of {provision} (UI + field) · Bracketed spans marked ¹ are amendments recorded in the source. (UI, shown whenever `verbatim` contains footnote markup, which is rendered literally) |
| Text basis | Text as ingested {law_version.corpus_fetched}. Current consolidation, not a point-in-time version. (UI + field) · ▸ The pack's full statement (UI) + `law_version.statement` (S) |
| Fetch line | Fetched {retrieved_on, joined} (fetch dates, not in-force dates) (UI + field) |
| Partial groups | NOT CONFIRMED · SUPERSEDED · Confirmed: none (UI) · **CHECKED AGAINST THE ACT ({len(confirmed[])})** + "None of these is a finding of compliance." on document turns, where every `confirmed[]` item is an obligation row (UI) · **CONFIRMED** only where `confirmed[]` holds citation items, which is the thing actually confirmed (UI). The count is always `len(confirmed[])`, **never** `scope_frame.checked_count` — in `document_context_2024` those are 11 and 12, and the twelfth duty is in `superseded[]`. A group heading may never be the only word a skimmer reads about a row whose own state is "Applies · not determined" (C10, I-R5 A3; the `ask.html` "✓ Verified" failure) |
| not_confirmed kinds | Not in the evidence pack (pack_missing) · Held, but its text may not be used (unusable) · Cannot verify (cannot_verify) · Stopped by review: {code} (⟨refusal⟩) · Not decided: {code} (⟨model_decision⟩) — details are server text (S) |
| Superseded | Governed then · Governs now (UI) + instruments (S) |
| Scope frame | Scope of this check (UI) + `scope_frame.sentence` (S, verbatim, line breaks preserved) |
| Not held block | {body.name} (S) · {body.regulator} (S) · In scope, nothing acquired (DECLARED) / Current text only, no history (CURRENT_ONLY) / Outside scope (OUT_OF_SCOPE) (UI) · {reason} (S, verbatim) · What we hold (UI) + {held[]} (S) |
| Located item (empty-`confirmed` partial) | **No UI copy exists and none may be written.** The whole item is ⟨`located`⟩ (S, NEW): one server sentence naming the corpus searched, the query or provisions reached, and that nothing usable was found (§7.12, §18.2 rule 5). Until Phase C supplies it the card shows `not_confirmed[]` and "Confirmed: none" (UI) alone — the client never writes refusal prose (I-E28) |
| What it is not | What this does not establish (UI) + `what_it_is_not` (S) — a **string** renders as one paragraph, a **list** as list items; the field ships in both shapes (D1) |
| Actions | Copy with sources · Edit question · Tell us this is blocking you (only when `demand_signal` is supplied) · See what can be checked (UI) |
| After copy | Copied with instruments and dates. (UI, live region) |
| After demand signal | Recorded. (UI — nothing about what happens next, which the client does not know) |
| Sources | Sources for this turn (n) (UI) · This turn has no citations. (UI, when `citations[]` is empty) · Sources for this turn: none supplied. (UI, when the turn carries no citations and no figures) · Section text is not part of this response. (UI) · Back to answer (UI) · Steps the server recorded (UI) |
| Document turns | Nothing was changed in your document. (UI, kept from `taskpane.js:71-72`) |
| Service error | No result · The service did not return a result, so there is no answer, partial or otherwise. Your question is still in the box. · Send again (UI) |
| Rail | This session · New question · No questions yet. · Not saved. Closing this window clears the list. (UI) |

**Why "Not held" and not the UX spec's "Outside what Placedon covers":** that heading is false for
DECLARED bodies, which *are* in scope and whose own refusal text says so (K14, I-E29). "Not held" is true
for DECLARED, CURRENT_ONLY and OUT_OF_SCOPE alike.

**Copy with sources** puts on the clipboard, as plain text, **the whole card in render order** — every
element §4.3 step 5 drew, with nothing omitted and nothing reordered. In a `partial` that means the
negative half leads, exactly as it does on screen (§2 change 2), because the reason a turn is partial is
the first thing a reader outside the tool needs:

1. the context band, the parent line, the question and the stamp (`Asked as of`, `No model used`,
   `Looked up …`);
2. the state word;
3. `scope_frame.sentence` verbatim, line breaks kept, including its "NOT checked (n)" block;
4. **NOT CONFIRMED** — every `not_confirmed[]` item: kind word, duty, provision and `detail` (or, where
   the soft validator dropped the detail, the kind word and `ref` alone);
5. **SUPERSEDED** — every `superseded[]` item: duty, `governed_then`, `governs_now`;
6. the confirmed group under its own heading (§13), every row (duty, provision, state word, **full**
   basis) and every citation (cite, evidence state, defects, `verbatim` where supplied);
7. every figure through the full block (label/key, amount, `In force from`, end state, full instrument,
   evidence state), one block per element of `figures[]`;
8. `what_it_is_not` verbatim under "What this does not establish";
9. on `out_of_scope`, the body, the regulator, the status words and `reason` verbatim;
10. the text-basis sentence and `scope.sentence`.

Provenance survives the paste, which bare copy would strip (brief C16). **Acceptance:** for every
fixture, the copied text contains every server-supplied string the card rendered — a partial that pastes
as a clean citation with no "not confirmed" line is the worst artefact this product can emit, because
outside the tool the state word is the only survivor and it sits above evidence that reads as complete.

---

## 14. Tokens

> **Superseded 2026-09-17 — see §27.** The tokens below came from the business-plan design system of
> 2026-08-16. The finalized frontend (`placedon-claude-legal-3300`, served at placedon.com) uses a different
> system, and the prototype now follows it. This section is kept as the record of what was designed.

Reused unchanged from DESIGN_SYSTEM §2–§4: Ink `#0A0A0A`, Parchment `#F5F3EF`, Slate `#475569`,
Slate-80 `#334155`, Slate-20 `#E2E8F0`, Ink-80 `#4A4A4A`, Ink-40 `#B5B5B5`, Ink-10 `#E8E6E2`, Caution
`#8B4513`; 4px radius; no shadows; 4px spacing base; type scale Display 32 / H1 24 / H2 18 / H3 14 /
Body 14 / Caption 12 / Mono 13; 2px Slate focus outline; 44px targets.

Harvey's method (H-T2), not Harvey's values (unpublished, H-T6): role aliases over the DS hexes —
`--surface-ground`, `--surface-card`, `--fg-muted`, `--rule-figure`, `--rule-text`, `--rule-caution`.

| New token | Value | Justification |
|---|---|---|
| `--white` | `#FFFFFF` | Card, composer and panel surface. DS §5 says "White bg"; UX §6.4 asks for it to be declared |
| `--font-text` | `"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif` | A **text** serif for 14–15px statute quotations (H-T3's pairing). Playfair is a display face and degrades below 18px, especially in the Windows pane. A system stack: nothing is downloaded or redistributed. Playfair stays for headings and state words (≥22px) |
| `--rule-text-style` | `dashed` | The only new visual primitive. It encodes "section text basis" against the solid figure rule and survives grayscale (§9) |
| `--rail-w` / `--panel-w` / `--measure` | 232 / 384 / 680px | DS §4's sidebar is 240px; 232 = 58×4 keeps the grid and leaves room for the panel at 1440 |

Pane corrections adopted from I-R3 (today's pane breaks the DS): secondary text Slate → Ink-80; border
`#D8D4CC` → Ink-10; radius 3 → 4; 12px minimum; focus ring added; green `#7a9a7a` dropped; `.err` becomes
a neutral dashed Ink treatment distinct from Caution. Mono is `"JetBrains Mono", ui-monospace, Menlo,
Consolas` — the DS names JetBrains, which is not self-hosted in the pane, so it falls back.

**Contrast, measured:** Ink-80 on Parchment 8.0:1 · Ink-80 on White 8.9:1 · Caution on White 7.1:1 ·
Slate on White 7.6:1. **Ink-40 is 1.7:1 against Parchment**, so it is used for **placeholder text and
dividers only** — never for the service-error border (dashed **Ink-80**, §6, §7.11: it is the only
container signal a failure card has, and at 1.7:1 the card would have no visible boundary), and never for
the *reason* line beside a disabled control (also Ink-80, §6 `AboutControl`: the reason is explanatory
text, not the disabled control, so WCAG's disabled exemption does not reach it, and on the web it is the
sole explanation of why document checks cannot run). Every *input* and *control* border is Ink-80 1px, to
clear the 3:1 non-text minimum.

**Colour count, declared, so a review has a number to check against.** DESIGN_SYSTEM §1 sets the golden
rule — one accent-coloured element per screen, max three colours. This design reads it as: **neutrals
(Ink, Ink-80, Ink-10, Ink-40, Parchment, White) are not colours** for that count, and **Caution is a
semantic status hue, not an accent** — it is never decorative, never a brand mark, and appears only as
the rule and label of NOT CONFIRMED, only in `partial`. That leaves **one accent, Slate, on the Ask
button — and the pane never shows even that**: after the first turn the composer docks sticky (§2 change
11), so a Slate Ask button would sit on screen beside a Caution-ruled `partial`. So **the Ask button is
Ink in the pane and Slate on the web** (§6 `AskButton`). Counted this way the pane at `partial` carries
**one hue** (Caution) and the web at `partial` carries **two** (Caution on NOT CONFIRMED, Slate on the
docked Ask button) — against the seven `ask.html` was condemned for in audit R5 A17/A18. If a design
review refuses to treat Caution as outside the accent budget, the resolution is to make the web Ask
button Ink as well, not to recolour NOT CONFIRMED. Selected radios, the current rail row and markers are
Ink.

---

## 15. Interaction and keyboard

- **Tab order, pane:** tab list (arrow keys, Home/End) → What is not held → About radios (arrow keys) →
  **capability rows** → question → facts fields → As of → Ask → turns. The capability list is the fence
  that makes a free-text field safe (§19 Q1), so it precedes the submit control in **DOM order, tab order
  and visual order alike** (§6 `CapabilityList`, §7.1) — a keyboard user must be able to reach it before
  committing, not only after. Activating a row fills the question field and **moves focus to the first
  revealed facts field, or to the question field where the capability declares no inputs**; the live
  region says what landed ("Question set. Three facts needed."), because the ring itself changes when
  `FactsFields` appear.
- **Tab order, web:** "Skip to question" → rail → content → Sources.
- **Submit:** Enter asks, Shift+Enter inserts a new line, Ctrl/Cmd+Enter also asks (no precedent —
  C-E21 is UNVERIFIED — chosen for the PLAN §6.3 path).
- **Waiting:** focus moves to Cancel; Esc cancels; the composer is disabled. **Cancel is a destroyed node
  the moment any terminal card replaces the waiting card**, so focus is never left on it: pipeline step 6
  (§4.3) runs for *every* terminal card — answered, partial, out_of_scope, cancelled and ServiceError
  alike — and moves focus before the waiting card is removed. A 502 or an Esc therefore never resets
  focus to `document.body` in silence.
- **On return:** focus moves to the new turn's **question** (`tabindex="-1"`), not to its state heading,
  so the reading order after focus is question → stamp → state → body rather than a state word the user
  must navigate backwards from (§16). The card's top is scrolled into view (the pane never jumps to the
  page bottom), and a polite live region announces the state word and the question: "Partly answered.
  What does s.173 require, and does s.16 apply here?". On a cancelled or error card, where there is no
  question element, focus goes to that card's own `h2` and the region announces "Cancelled" / "No result"
  with the question.
- **Markers:** every `[n]` is a `<button aria-describedby>` naming the cite ("Source 1: Companies Act
  2013, s.2"). Activating it moves focus into the matching Sources item, which carries **Back to answer**
  returning focus to the marker. Esc from the panel does the same. This is the full PLAN §6.3 path:
  composer → submit → every citation → Source → back.
- **No hover-only anything.** No citation hover preview (H-G4 is UNVERIFIED and fails touch at 320px).
- **Actions:** Copy with sources writes plain text and announces; Edit question refills the composer and
  submits a **new** turn, leaving the old one in place (C-E15; retry is refused, C3).
- **Disabled controls** are `aria-disabled` and described by their reason line, never silently inert.

---

## 16. Accessibility

- Landmarks: `nav[aria-label="This session"]`, `main`, `aside[aria-label="Sources for turn n"]` (web) or
  `section` (pane); a visually hidden `<h1>Ask</h1>`. **Each turn is an `article` labelled
  `"{question} — {state word}"`**, both server-supplied (§6 `TurnCard`) — never by its `h2` alone, which
  would give every article in a session the accessible name "Answered" or "Partly answered" and make the
  rotor list unreadable. Focus on arrival goes to the question, not the state heading, so the reading
  order is question → stamp → state → body and nothing must be navigated backwards to (§15). On the web
  the rail solves this visually; the rail does not exist in the pane, which is the v1 surface.
- **Grayscale (PLAN §6.1):** the three states differ by their first word — Answered / Partly answered /
  Not held — and carry a redundant shape glyph (filled / half / hollow square). Square glyphs are
  reserved for states; the context band has none. CONFIRMED / NOT CONFIRMED / SUPERSEDED are words. A
  figure's rule is solid and its label says "In force from"; section text's rule is dashed and its label
  says "Text as ingested". Colour is never the only signal.
- 12px minimum text; 44×44px targets on buttons, tabs, radio labels and markers; the stamp's
  `generated_at` is a `title`, never the only carrier of anything.
- The scope frame's server sentence keeps its line breaks (`white-space: pre-line`) and is never
  truncated or summarised to a ratio (`checker/coverage.py:108-114` forbids exactly that).
- Statute quotations are marked `lang="en"` per block, ready for Devanagari blocks later.
- The currency strip, when it ships, carries a `<table>` fallback (UX §7).

---

## 17. Motion

| What | Motion | Duration |
|---|---|---|
| Sources panel content swap (web) | opacity 0→1, as a **transition on swap**, never a keyframe that runs on first paint | 120ms ease-out |
| Hover and focus states | none (instant) | — |
| New turn arrives | none. Focus and the live region carry it | — |
| Waiting | none. Static sentence | — |
| Disclosures, radios, rail, dock | none | — |

`@media (prefers-reduced-motion: reduce)` sets `transition: none` and `animation: none` on everything.
Nothing exceeds 200ms; nothing animates a layout property; there are no skeletons (C4, C6). The panel
must render at opacity 1 on load — a mid-animation screenshot cost the Claude direction its evidence
(J1, J3).

---

## 18. Contract

### 18.1 What each component consumes

Status: **C** = in `placedon.ask/0` today and present in a fixture · **C-opt** = in the contract, absent
from some fixtures, so the component must render without it · **NEW** = not in the contract; the design
renders nothing in its place until Phase C adds it.

| Component | Fields | Status |
|---|---|---|
| Context band | `context.kind`, `context.document_date` | C |
| Question, stamp | `question`, `as_of`, `uses_model`, `generated_at`, `evidence_pack.retrieval_query` | C / C-opt (pack) |
| Parent line, change badge | `parent_turn_id`, plus the previous turn's echoed `context` and `as_of` | C-opt |
| State heading | `state` (1:1 enum → word; rendering, not inference) | C |
| Headline | `headline`, with no amount permitted | **NEW** — absent from all five fixtures, so nothing renders |
| Row item | `rows[]` {obligation_id, duty, provision, state, basis, missing_facts, blocked_by, cited_spans} | C |
| You supplied | `facts` {name: {value, provenance}} | C · label: **NEW** (`facts.*.label`), else the key verbatim |
| Figure block | `figures[]` {key, amount, rupees, instrument, effective_from, effective_to, evidence_state, source_url} | C · `label`, `instrument_id`, `lineage[]`: **NEW** |
| Confirmed item | `confirmed[]` — a citation (has `ref`, may carry `verbatim`) **or** an obligation row (has `obligation_id`) | C · a `kind` discriminator: **NEW** (D8) |
| Not confirmed item | `not_confirmed[]` {kind: pack_missing \| unusable \| cannot_verify, detail, ref, reason, defects, duty, provision, instrument} | C · `refusal`, `model_decision` kinds and a reader-facing detail: **NEW** (D5) |
| Superseded | `superseded[]` {duty, provision, governed_then, governs_now, instrument, detail} | C |
| Scope frame | `scope_frame` {sentence, checked_count, unchecked[], establishes_compliance, dismissable} | C — bound to the frame, renamed from `coverage` in Phase C (K8) |
| What it is not | `what_it_is_not[]` | C (broken in one fixture, D1) |
| Not held | `body` {key, name, regulator, covers, scope_status}, `reason`, `held[]`, `scope.sentence` | C (body **detection** is backend-NEW) |
| Located item (§7.12) | ⟨`located`⟩ — one sentence: corpus searched, query or provisions reached, nothing usable found | **NEW** — the empty-`confirmed` partial, the state §23 risk 2 says will dominate, has no server string today |
| Undeclared body (§7.12) | ⟨`body.undeclared_reason`⟩ — refusal copy for a body `scope.py` does not declare (Income-tax, GST; I-E28) | **NEW, blocking** — without it such a question cannot return `out_of_scope` at all and falls into §7.12(a) |
| Demand signal | `demand_signal` | C on `partial`; **NEW** on `out_of_scope` |
| Citations, Sources | `citations[]` {ref, cite, title, evidence_state, usable_for_answering, unusable_reason, defects[], retrieved_on[], source_url}, `law_version` {basis, point_in_time_verified, corpus_fetched, statement}, `evidence_pack` {retrieval_query, route, usable_keys, unusable_keys, missing, insufficient_evidence} | C · `citations[].verbatim` on `answered`, `evidence_pack.id`: **NEW** |
| Steps | `stages[]` + `caption` | C-opt, document path only (K9) · `caption`: **NEW** |
| Holds line, scope register | `scope.held[]`, `scope.sentence` · `scope.bodies[]` {name, regulator, scope_status} | **NEW, blocking** — `scope` is an envelope field on an *ask response*, and the empty state exists before any response. It needs the `GET /v1/scope` bootstrap (§19 Q1), not the ask envelope (F6b) |
| Capability list, facts fields | `capabilities[]` {group, question, provision, requires[], inputs[], needs_document}, `capabilities.note` | **NEW** (from `bundles.registry()` + the obligation register) |
| Request | question, as_of, context.kind, document{date,text}, capability, facts, parent_turn_id | **NEW** — the contract documents the response only |
| Forbidden | `confidence`, any coverage float, any reviewer name, `human_reviewed`, a client-inferred state | never rendered |

### 18.2 Validator rules this design asks Phase C to add

Each rule is **HARD** (`validate_hard` — the response cannot be read as an answer; §4.3 step 1 renders
ServiceError) or **SOFT** (`validate_soft` — one element is defective; §4.3 step 4 names the field, the
element and its heading are suppressed, and the rest of a legally correct turn renders). **A soft rule
may never void a correct legal answer.** Three of the five shipped fixtures trip a soft rule today; if
any of these were hard, §24 check 1 would fail and both `answered` examples would render as "No result".

| # | Rule | Class | Fixtures that trip it today |
|---|---|---|---|
| 1 | A `headline` may not contain an amount (₹, "crore", "lakh", or a digit group followed by a currency word). Amounts live only in figure blocks | **SOFT** (drop the headline; `headline` renders nothing anyway) | none — `headline` is absent from all five |
| 2 | `figures[].source_url` must be `null` when unresolved, never a placeholder sentence (D2) | **SOFT** — render "Gazette link: not recorded" and the figure in full | `answered_small_company`, `followup_turnover` |
| 3 | `what_it_is_not` must be sentences, not a list of single characters, and its shape must be one of string-or-list consistently (D1) | **SOFT** — drop the block **and its heading** together (§4.3) | `answered_small_company` carries a **string**, `document_context_2024` a **list of 3**; neither is malformed since the 2026-09-16 fixture fix, so the rule is currently unfired but the contract still says `what_it_is_not[]` and must be settled |
| 4 | No `source_url` on the dead host `indiacode.nic.in` (CLAUDE.md: the live host is `indiacode.gov.in`) (D3) | **SOFT** — suppress the link only; the citation, its evidence state and its verbatim text still render | every fixture carrying `citations[]` |
| 5 | `partial` with an empty `confirmed[]` carries a `located` item naming what was searched and in what corpus — the I-U2 slot, per Magesh's definition of a correct refusal (L-C2) | **SOFT on the client, HARD on the server**: the server should not emit one without it, but the client never voids the turn and never relabels the state (C3) — it renders `not_confirmed[]` and "Confirmed: none" (§7.12) | none today |
| 6 | `not_confirmed[]` items need a reader-facing `detail`; strings addressed to a model may not be the only text (D5) | **SOFT** — drop the detail, keep the kind word and `ref` | `partial_s173_s16` ("not admitted for model use") |
| 7 | ~~A `superseded[]` item whose `was_at_document_date == is_at_read_date` while `governed_then != governs_now` may not render under SUPERSEDED (D9)~~ **WITHDRAWN 2026-09-17 (red team L11).** A change of governing instrument with both statuses CURRENT is the case the feature exists for: `checker/api.py:314-322` defines "moved" as a change of instrument, precisely because once G.S.R. 880(E) was attested both dates read CURRENT. The item renders under SUPERSEDED with each status beside its instrument | — | — |
| 8 | A confirmed-group heading and its count must derive from `confirmed[]` itself, never from `scope_frame.checked_count` (D11) | **HARD on the client's own copy** — it is a client rule, not a response rule | n/a |
| 9 | A row's state word may not render without that row's full `basis` in the same block | **HARD on the client's own layout** | n/a |
| 10 | Every `answered` and `partial` response carries a `what_it_is_not` — the bound on the claim is the one element the client may not write for itself | **Server-side rule only**; on the client it is **SOFT** (nothing renders, no heading, the turn still renders in full — C3) | `partial_s173_s16`, `followup_turnover` (§8) |

**Hard rules** (already in `scripts/assistant_contract.py:64-133` or asked for there): a missing or
unknown `state`; an `out_of_scope` with no `reason`; a citation outside the evidence pack; a figure with
no `instrument` or no `effective_from`; a `confidence` field; any client-inferred state.

### 18.3 Defects found in the Phase C contract and fixtures (for Phase B/C, not fixed here)

| # | Defect | Location |
|---|---|---|
| D1 | **`what_it_is_not` has two shapes.** The single-character list (the builder wrapping a string in `list()`) was fixed on 2026-09-16, but `answered_small_company` now carries a **string** and `document_context_2024` a **list of three strings**, while the contract names the field `what_it_is_not[]`. The client must accept both (render a string as one paragraph, a list as list items) or Phase C must pick one | `scripts/assistant_contract.py:205`; `fixtures/answered_small_company.json`, `fixtures/document_context_2024.json`; contract §4 |
| D2 | ~~`figures[].source_url` is `"UNRESOLVED — see scripts/register_gsr880e.py"`, a sentence in a URL field~~ **CLOSED 2026-09-17** (`0fae26c`): served figures carry the eGazette URL; the marker stays only on unserved rows | `checker/prescribed_thresholds.py` |
| D3 | `citations[].source_url` points at `indiacode.nic.in`, which 403s; the live host is `indiacode.gov.in` | fixtures; corpus records |
| D4 | `scope_frame.sentence` says "as at 2026-09-15" for the **read** date — a sixth date wording the client may not restyle | `checker/coverage.py:110` |
| D5 | `not_confirmed[].detail` for `pack_missing` is written for a model ("not admitted for model use") | `checker/evidence_pack.py` missing strings |
| D6 | No `headline`, `figures[].label`, fact labels, `capabilities[]`, `scope.bodies[]`, `stages[].caption`, `citations[].verbatim` on `answered`, or `demand_signal` on `out_of_scope` | contract §2–§5 |
| D7 | `followup_turnover` answers "And the turnover limit?" from `s.2(85)` with a `parent_turn_id`, which implies context carried between turns — no conversation state exists (I-E34). Either the server must carry it explicitly, or the fixture's question is illustrative only | `fixtures/followup_turnover.json` |
| D8 | `confirmed[]` holds two different shapes (citation, obligation row) with no discriminator | contract §4 |
| D9 | `document_context_2024.superseded[0]` carries `was_at_document_date: CURRENT` **and** `is_at_read_date: CURRENT` while naming a then/now instrument change — **CLOSED 2026-09-17: not a defect.** Each status describes its own instrument on its own date; `checker/api.py:314-322` detects the move by instrument (red team L11) | fixture |
| D11 | `document_context_2024` puts **11** items in `confirmed[]` while `scope_frame.checked_count` says **12** (the twelfth checked duty is in `superseded[]`), and all 11 are `APPLIES_UNDETERMINED` / `CANNOT_DETERMINE` — i.e. nothing in the group is confirmed of anything. The contract calls these "verified document-check rows" (§4), which they are not. Phase C must either supply a group label the rows can bear or state that `confirmed[]` on a document turn means "checked", not "cleared" | fixture; contract §4 |
| D10 | `rows[].state = DOES_NOT_APPLY` on the classification row "Establish whether the company is a small company" reads as "the test does not apply" rather than "not a small company"; the basis carries the meaning | fixture; `checker/obligations.py:710-718` |

---

## 19. Verdicts on the nine harsh questions (PLAN §2)

**Q1 — Is chat the right primitive?** **Hybrid (b)+(c), and only if `GET /v1/scope` ships.** The designed
answer is free text fenced before submit by four visible things: the read-only Holds line with its scope
sentence and the not-held register; the About control; the As-of date; and, before the first turn, a
server-generated list of what can be checked. **Three of those four do not exist today.** Holds line,
register and capability list all come from `GET /v1/scope`, which the contract does not document (§4.1).
Until that route ships the composer is About + As-of + an open text field — i.e. **the fence is two
controls, not four, and the answer to Q1 in that build is (b) with no scope statement at all**, which is
the "ask anything" frame C1 forbids. That is the reason §4.1 marks the route a *blocking* Phase C
deliverable rather than a NEW field: the design's answer to C1 is false without it, and a hard-coded
"1 of 9" is not an acceptable stand-in (C10). A capability
row fills the field and, where the capability needs facts, reveals fields labelled with the engine's own
`evidence_needed` strings — which is how the `answered` fixture's facts can be supplied at all without an
extractor. `out_of_scope` reads as competence because it says four things in plain recovery style
(C-E16, L-B6, L-C2): which body the question concerns, who regulates it, that it is in scope but not
acquired, and what we do hold — under a neutral rule, never Caution, never red. Two server gaps stay
open: detection failure should return `partial` stating what was searched and not found (L-C2), and an
undeclared body (Income-tax, I-E28) needs NEW server copy — the client never writes refusal prose.
Whether (b) or (c) dominates is for the ten practitioner conversations (K15).

**Q2 — Which Harvey/Claude patterns survive?** §20. The structure survives — panels with headers, a
sources surface that follows the turn, a read-only source line, a session-scoped thread list, role tokens
and the serif/sans pairing. Every behaviour that implies open-ended generation is rejected, with a reason
per pattern. Playfair holds at 320px only at ≥22px (state words, headings); statute text uses a system
text serif.

**Q3 — What may appear before the state is decided?** The question, the request values the user set, one
static sentence, and Cancel. No stage caption is timed or animated by the client. `stages[]` appear after
the state, only when present, only on the document path, as "Steps the server recorded" using server
captions (K9). If Phase C adds server-sent stage events, the same slot may show the latest server caption
verbatim and nothing else.

**Q4 — Follow-ups.** Independent turn cards in one session view; every turn is fully stamped and shows
what it looked up. The composer keeps the last About and As-of values, which are visible text before
submit and are repeated in the turn's band and stamp; a badge fires when either changed. Where the
response carries `parent_turn_id`, the card says "Follow-up to turn 1" and shows
`evidence_pack.retrieval_query`, so anything the server carried across is on the card rather than
implied. We do **not** print a fixed claim that earlier answers are unused: the Phase C follow-up fixture
would make it false (D7). No client-side resolution of elliptical questions exists or is proposed.

**Q5 — Citations.** Both, with provenance inline. Every figure carries amount, in-force date and the full
instrument string in its own block, with no click (C2). `[n]` markers only point into Sources, which holds
verbatim text (where supplied), the text basis, the pack statement, hashes, fetch dates and pack keys.
Section text never shows an in-force date; the validator refuses one. A reader sees instrument + in-force
date for every figure without a click: **yes**.

**Q6 — Task pane first.** It degrades to 320px without hiding evidence: the rail disappears (the turns
are the history), the panel becomes a per-turn in-flow section with a summary line that still names both
truths, the figure block wraps the full instrument string rather than shortening it, verbatim text clips
at the last sub-section boundary within about eight lines — **never mid-sub-section** — behind an explicit
"Show the full text" and a count of the sub-sections hidden (its basis line never clips, §7.6), long rows
collapse behind "Show all {len(confirmed[])} rows", and the composer docks compact so the next question is always one scroll-stop
away. Nothing is hover-only. **Acceptance — the captured widths are 320, 360, 400, 768, 1024 and 1440**
(PLAN §3 Phase B): 320/360/400 are the pane, 768 is one column on a narrow browser, 1024 exercises the
820–1099 band where the panel is fluid and the content column must never fall below 400px (§5), and 1440
is the three-zone frame. No horizontal scroll at any of them.

**Q7 — Document context.** Settled by surface first, control second. The web has no document: the option
is disabled and says why. In the pane, "This document" is the default when a document date can be read,
and the difference is stated four times — the pane header, the About hint, the per-turn band, and the
turn's own content (only document turns carry a scope frame and "Nothing was changed in your document").
Only `context.document_date` identifies the document: no filename, no quoted text (I-E32). "The Act"
promises section text and dated figures, plus checks on facts the user enters — not decisions about a
company from prose (K13, I-E18).

**Q8 — What we refuse to build.** §21.

**Q9 — What would falsify this.** §22.

---

## 20. Harvey + Claude: what we took, what we refused, and why

### Taken (adapted)

| Pattern | Row | How it lands |
|---|---|---|
| Content vs sidebar panels with panel headers | H-E1 | Rail / content / Sources at 1440; 48px headers; borders, no fills |
| Sources panel aligned with the thread view | H-E3 (SOURCED); follow-the-turn H-E4 (INFERRED, adopted on merit) | Panel follows the turn in view; per-turn in-flow section in the pane |
| Knowledge-source selection with descriptions | H-F3 | Read-only Holds line + scope sentence + not-held register |
| @mention a file or source | H-F1, L-A11 | One About control: This document / The Act |
| Threads list; Word pane History | H-E1, H-H4 | Session-only rail on web; the turns themselves in the pane |
| Numbered inline markers → page + quote | H-G1 (glyph H-G2 INFERRED) | `[n]` pointers only; provenance is carried inline |
| Thinking states | H-F9 | Post-hoc "Steps the server recorded", server captions only |
| Pane verbs | H-W1 | Ask tab beside Currency check and Register strip |
| Full Assistant in the pane | H-W8 (INFERRED) | Adapted by subtraction |
| Role tokens, warm neutrals, contrast method | H-T2 | Role aliases over DS hexes |
| Serif + sans pairing | H-T3 (site only; app H-T5 UNVERIFIED) | Playfair ≥22px, system text serif for statute, system sans chrome |
| "Verify the sources … confirm that citations are accurate" | H-G6 | Verbatim text, hashes and pack keys one activation away |
| Model slot beside send | C-E6 | Takes the As-of date |
| "+" slot lower left | C-E1 | Becomes the visible About control |
| Response labelled with what produced it | C-E15 | Per-turn band + stamp |
| Edit message | C-E15 | Edit question → a new grounded turn |
| Per-message actions | C-E25 (INFERRED) | **Copy with sources** only, plus Edit and the demand signal |
| Plain error copy with a recovery step | C-E16 | Not held; service error |
| Right-hand window | C-E11 | The Sources panel |
| Centred empty composer | C-E24 (INFERRED) | Centred, filled with held scope and real capabilities — no greeting |
| Valid-pointer citations | C-E20 | Contract: no citation outside the evidence pack |
| Answer left, authorities right | L-A16 | The 1440 layout |
| List below the answer at narrow width | L-A8 | The pane's per-turn Sources |
| Add-in for one document, web for the rest | L-A10 | Document context lives only where the document is |
| Published list of what it cannot do | L-A4 | Inverted into "What can be checked" + the not-held register |
| A refusal names what was searched | L-C2, L-B6 | Not held copy; the detection-failure partial |

### Refused

| Pattern | Row | Why |
|---|---|---|
| Model selector | H-F5, C-E6 | Implies answers vary by model; contradicts server-decided state (C3); the model is not wired (C8) |
| Magic Prompt rewrite | H-F6 | Changes what was asked (C1). Capability rows fill, never rewrite |
| Prompt library | H-F1, H-W2 | Free prompts invite out-of-scope questions; the server capability list replaces it |
| Voice / dictation | H-F1, H-W4 | No named need; not a v1 surface (C7) |
| Deep research / deep analysis; Research mode | H-F8, H-G7, C-E4, C-E5 | Open-ended multi-source analysis is the C1 non-goal. One body is held |
| Plan preview / adjust scope / approve | H-F10 | An editable plan is narrative before state (C4) |
| Streamed prose, "time to first word" | H-G9, H-G10, C-E23 | Prose before the state is decided (C3, C4); no evidence it helps trust (L-C12) |
| Thinking timer and expandable reasoning | C-E7 (K3) | Frames the wait as model thought; narrative before state |
| In-thread suggestions | H-F7 | Widens scope mid-answer and adds pane chrome. Only "what we hold" survives, inside Not held |
| Draft mode, Show Edits, editing Word in Assistant | H-E5, H-E6, H-W3, H-F2 | Generation (CLAUDE.md: audit layer, not generator) |
| Side-by-side document viewer | H-E7 | Generation, and UNVERIFIED as precedent |
| Writing styles | H-F11, C-E10 | Server wording (`refusal_for`, pack statements) must not be restyled |
| Pane web search, fill/edit tables, translate, redact | H-W2 | Web search is outside the held corpus; the rest is generation |
| Choose knowledge sources; two sources at once | H-F3 | One body is held (I-E27); a picker would recreate the C10 DPDP chip |
| Hover preview of a citation | H-G4 (UNVERIFIED) | Fails C2 and fails touch at 320px |
| Search bar in the sources panel | H-E3 | One to three citations per turn; nothing to search (C6) |
| Persisted threads, vaults, projects | H-H1, H-H3, C-E12 | No conversation state (I-E34); the leak guard is verbatim-only (I-E32) |
| Share modal, permissions, activity log | H-H2, C-E14 | Needs an immutable pack id and as-of first (C8) |
| Chat search, memory, incognito | H-H5, C-E18 | No named need; memory is drift (Q4) |
| Hidden "+" menu and "/" commands | C-E1, C-E9 | Scope, context and date must be visible before submit |
| Attachments, drag-drop, paste files | C-E8 | The open document is the context; upload was cut (I-R5 A9) |
| Retry | C-E15 | Implies a different answer might come back (C3) |
| Artifact versions, publish, download | C-E11 | Sources are not generated; Copy with sources covers the real need |
| Harvey's own type faces | H-T3, H-T4 | Not ours to use |
| Vendor accuracy percentages as UI claims | H-G9 | No independent benchmark (CLAUDE.md) |
| Trust-but-verify boilerplate; long memo answers; confidence % | L-A17, L-A16, L-B7, L-B8 | The dating is done for the user; checking cost rises with length (L-C3); confidence changes no decision |

---

## 21. Out of v1

History search · sharing · persisted threads · voice · attachments · retry · thumbs or ratings ·
a sources-panel search · the currency strip (needs `figures[].lineage[]`) · Hindi statute rendering ·
document context on the web (needs a Word→web hand-off that does not exist) · any `answered` from a
model-composed sentence (I-U1) · streamed stage events · export to PDF · a dark theme (Word's own dark
mode is a known open risk, §23).

---

## 22. What would falsify this design

From PLAN §7: a practitioner shown `partial` says "just answer"; pane users miss that an answer is about
the open document rather than the law generally; the as-of date reads as hedging rather than rigour.
From the brief §2 Q9: nobody opens Sources; most turns end partial or not held and users stop asking;
the scope line is ignored and DECLARED-body questions keep coming at the same rate; the two as-of forms
are read as the same claim. Specific to this direction:

1. **The familiar frame sets an "ask anything" expectation.** Across the ten conversations the share of
   questions about non-held bodies does not fall between a user's first and fifth question. Then the
   chrome is doing harm and the evidence-first ledger should win.
2. **Users go looking for yesterday's question.** A session-only list then reads as data loss, not safety.
3. **One of the two evidence homes is decoration:** at 1440 practitioners read only the panel and skip
   the figure block, or at 360 never open the in-flow Sources.
4. **The dashed/solid distinction goes unnoticed** and users paraphrase "Text as ingested 18-Aug-2026" as
   "the law as of August".
5. **Capability rows go untouched**, which collapses Q1 to option (b) and makes the facts fields dead
   weight.
6. **"Not held" is read as "no obligation applies"** despite the refusal text saying the opposite.
7. **The empty-`confirmed` partial (§7.12a) is indistinguishable from a worked partial.** If practitioners
   read "Partly answered · Confirmed: none" as a considered finding rather than as "nothing was found",
   the `located` item stops being a Phase C nicety and becomes a blocker on shipping the state at all.

---

## 23. Risks and open items

1. **The Harvey frame may itself be the problem** (brief §4, "strongest case it is wrong"). This is the
   direction's bet and it is untested (K15).
2. **`answered` is rare.** Only deterministic results qualify (I-R1 item 2), so most turns will be
   `partial` and the frame spends its best real estate on a state users seldom see. The commonest turn of
   all — `partial` with an empty `confirmed[]` — has no fixture and is drawn in §7.12 from the contract's
   own mapping; today it renders with no server string explaining what was searched.
3. **Figure-block length at 320px:** the full instrument string takes six lines. Shortening would need
   NEW `figures[].instrument_id` and must still satisfy C2.
4. **Six dates on one screen** (asked as of, in force from, text as ingested, fetched, instrument-string
   dates, "as at" inside the scope sentence). Words, position and rule style separate them; falsifier 4
   may still fire.
5. **Dead source links** (D3) and unresolved Gazette links (D2) make Sources look thinner than the work
   behind it.
6. **The threshold state is volatile** (I-U7, K11). "Corroborated" for G.S.R. 880(E) is as measured on
   2026-09-15; a fixture must not treat it as permanent, and if it stops being servable the `answered`
   example becomes `partial`.
7. **Facts entry is a new surface.** It is the smallest thing that makes the `answered` path reachable
   without an extractor, but it moves the primitive toward a form; if practitioners ignore it, Q1's
   answer changes.
8. **Word's dark mode** may recolour the pane under the add-in. Untested; the design commits to the light
   palette and paints its own background explicitly.
9. **Open policy questions, not design ones:** U1 (can model text ever be `answered`), U2 (refusal inside
   the held Act — the `located` item is a proposal), U3/K14 (the DECLARED heading word, answered here as
   "Not held"), body detection and the Rules resolver (I-R1 items 3 and 10).

---

## 24. Acceptance checks (PLAN §6) → where they are met

| Check | Met by |
|---|---|
| 1. Every fixture renders; with colour removed the three states differ by heading word | §7.4–§7.9 render all five fixtures; §16 (word + glyph + rule; Caution only on NOT CONFIRMED) |
| 2. At 320px nothing horizontal-scrolls and every figure still shows instrument + as-of | §5 (no fixed widths above 320, the panel fluid, the content column never below 400px), §7.4 (full instrument wrapped, never shortened), §19 Q6. **Captured widths: 320, 360, 400, 768, 1024, 1440.** Phase B must draw §7.4 (`answered`) and §7.8 (document) at **320** before build sign-off — every frame in §7 is drawn at 360, and 320 is the width PLAN §6 check 2 names |
| 3. Full keyboard path: composer → submit → every citation → Source → back | §15 (markers as buttons, focus into the Sources item, "Back to answer", Esc) |
| 4. No text on screen the fixture did not supply | §4.3 `data-f` on every element + the `?fields=1` overlay; §13 marks every string (S)/(UI)/†; `headline`, `capabilities[]` and labels render nothing until supplied |
| 4b. **Nothing the card showed is lost on copy** | §13 "Copy with sources": the payload is the card in render order, and the check is that every (S) string on screen appears in the clipboard text — run per fixture |
| 5. Validator rejects an inferred state, a figure without an as-of, a citation outside the pack | Already in `scripts/assistant_contract.py:64-133`; this design adds the rules in §18.2, each classified HARD or SOFT so no soft defect voids a legally correct answer |
| 6. `prefers-reduced-motion` removes all motion; nothing exceeds 200ms | §17 (one 120ms opacity transition, and it is the only motion) |

---

## 25. Critique findings and dispositions

Two harsh critics — one for trust and legal accuracy, one for usability, design quality and founder
intent — returned **43 findings** against this spec (7 fatal, 27 major, 9 minor). Findings are kept in
full at `scratchpad/ux/critic_findings.json` for the run that produced them; each id below is theirs.

### 25.1 Rules this pass added, binding on Phase B

These are the fixes that are rules rather than redraws. Where a fix required redrawing six wireframes at
two widths, the rule is stated here and the redraw is Phase B's, listed in §25.2 as OPEN.

1. **The collapsed Sources summary keeps the two truths apart** (F5b, F7). In the pane the section is
   collapsed by default, so its summary is what most readers ever see. It carries **two lines, never
   one**: the ingestion basis under a dashed rule, and the in-force line under a solid rule. If a turn
   has more than one figure the summary gives a **count**, never a merged date sentence.
2. **A duty is printed once per turn** (F8b). On a document turn `scope_frame.sentence` is rendered
   verbatim, and any `not_confirmed[]` item whose `duty` also appears in `scope_frame.unchecked[]` is
   suppressed. The same three duties may not appear under two labels.
3. **"Copy with sources" copies the card, in card order** (F9b): every rendered element, abstentions
   first — state word, question, stamp, context band, `not_confirmed[]`, `superseded[]`, rows, figures
   with instrument and in-force date, citations with the text-basis sentence, `scope_frame.sentence`,
   `what_it_is_not`, and each `[n]` marker's target. Never a hand-picked subset. §24 check 4b is the test.
4. **`out_of_scope` renders the body or the reason, not both** (F16). `reason` opens by naming the body
   and its regulator, so when `reason` is present the structured `body.name` / `body.regulator` /
   `body.covers` lines are suppressed. Server wording is never restyled, so deduplication is a layout
   decision, not an edit to the string.
5. **A marker expands what it targets before moving focus** (F18). In the pane, activating `[n]` expands
   the Sources section first; the section is expanded whenever a marker targets it, so focus never
   enters a hidden subtree and `aria-describedby` never points into one. The description names the
   target: the cite for a citation, `figures[].key` plus the instrument for a figure.
6. **The change badge names both sides from echoed values** (F19): "About changed: the open document →
   the Act", not "changed from the previous turn", because a collapsed previous turn does not show its
   About. Both strings are the ContextBand text the client already renders.
7. **A negation pass over §13** (F21) — **corrected 2026-09-17 by the red team; three of its four
   edits were wrong and are withdrawn.** The in-force line reads `In force from 01-Dec-2025 · No end
   date recorded`, not "still current": the engine records no end date, it does not certify the
   present, and "still current" is a currency claim no field supports (red team L5). The link line
   stays `Gazette link: not recorded`: the 880(E) registration has no `downloaded_from` or
   `downloaded_at`, so "pending" would promise a copy nobody is fetching (L6). `No model used` stays
   in the stamp on every turn, because nothing else on the card says it (NG-4). What survives is the
   target: negations are merged into one line where they can be, never removed by making a claim.
8. **Group labels get one step of contrast** (F23). A label token is declared — DS H3, 14/600, sentence
   case — and size or weight contrast is reserved for the group carrying the turn's state: NOT CONFIRMED
   in `partial`, the figure block in `answered`. Six equal all-caps labels on the document turn is the
   flat-hierarchy failure C6 bars.
9. **The frame does not move when the first answer arrives** (F24). The 1440 empty state reserves the
   Sources column (rendered empty with its header), so the content column sits where it will sit once
   an answer exists. This costs nothing under C6 and needs no motion.
10. **A hash is shown whole or not at all** (F25). `cited_spans` sha256 values render behind
    `[Show the content hashes]`, in a wrapping mono block, and are included in the copy payload. A
    12-character prefix is decoration in a product whose thesis is verifiability.
11. **The As-of field accepts what Indian practitioners type** (F27): `DD-MM-YYYY`, `DD/MM/YYYY` and
    ISO on input, normalised to `DD-Mon-YYYY` on blur. It carries `aria-invalid`, an `aria-describedby`
    error id, and Ask stays enabled — an invalid date is a field error, never a blocked turn. (In v1 the
    field is read-only at today's date, §9; these rules bind whenever Phase C makes it editable.)
12. **The session rail reads state word first** (F13), matching §6 and §16's grayscale defence, and the
    rail is included in §24 check 1's grayscale test.
13. **`cited_spans` is labelled as what it is** (F14): "Sub-clauses the row named (resolved to s.2;
    sub-clause text not extracted)". The client may not assert that a sub-clause was read when the
    contract states its text is not extracted.
14. **The L-C2 claim is narrowed** (F15). Magesh's standard — a refusal is correct only when it says what
    was searched and not found — is met on the **detection-failure `partial`** (§7.12, the `located`
    item), not on `out_of_scope`, whose fixture carries no `evidence_pack`. §19 Q1 and the §20 row say so.

### 25.2 Dispositions

| id | sev | Finding, in one line | Outcome |
|---|---|---|---|
| F1 | fatal | The empty state cannot render: scope/capabilities have no field | **FIXED** — `GET /v1/scope` bootstrap specified (§19 Q1, §18.1) |
| F1b | fatal | A second figure drawn as a compressed line, dropping instrument and date | **FIXED** — every `figures[]` element renders through the identical FigureBlock |
| F2 | fatal | A past `as_of` has no defined semantics | **FIXED** — read-only at today in v1, with the rule if Phase C makes it editable (§9) |
| F2b | fatal | `CONFIRMED (12)` over 11 undetermined rows | **FIXED** — counts derive from the array; the group is renamed for what it holds (§18.2 rule 8) |
| F3 | fatal | "Copy with sources" omitted abstentions | **FIXED** — §25.1 rule 3, tested by §24 check 4b |
| F3b | fatal | Client-composed headline with `headline` absent from every fixture | **FIXED** — headline renders nothing until supplied; no amount permitted (§18.2 rule 1) |
| F4b | fatal | A content rule would void a legally correct response | **FIXED** — §18.2 split into HARD (void) and SOFT (suppress the element) |
| F10 | major | No drawn state for the outcomes that will dominate | **FIXED** — §7.12 draws the empty-`confirmed` partial and the undeclared-body screen |
| F10b | major | ServiceError never focused or announced | **FIXED** — focus-and-announce moved to the pipeline tail (§4.3) |
| F11 | major | A statute quote may be clipped mid-sub-section | **FIXED** — a clip may not end inside a numbered sub-section; the hidden count is server-derived |
| F11b | major | Every turn's accessible name is the state word | **FIXED** — the article is labelled question + state |
| F4 | major | Count client-computed from `scope_frame.checked_count` | **FIXED** — §18.2 rule 8 |
| F5 | major | "No model used" beside "not admitted for model use" | **FIXED** — §18.2 rule 6 suppresses model-facing detail |
| F5b | major | Collapsed summary merges the two as-of truths | **FIXED** — §25.1 rule 1 |
| F6 | major | A row's state word rendered without its full basis | **FIXED** — §18.2 rule 9; basis never truncated |
| F6b | major | Holds line marked C, but `scope` arrives only with a response | **FIXED** — §18.1 now **NEW, blocking** |
| F7 | major | Collapsed summary asserts both truths in one sentence | **FIXED** — §25.1 rule 1 |
| F7b | major | Two of the four "fences" on free text render nothing | **FIXED** — `capabilities[]` and `scope.bodies[]` are blocking Phase C deliverables |
| F8 | major | A citation looks checked; its link is a dead host | **FIXED** — §18.2 rule 4, a client-side allowlist excluding `indiacode.nic.in` |
| F8b | major | The same three duties printed under two labels | **FIXED** — §25.1 rule 2 |
| F9 | major | SUPERSEDED asserts the law moved, carrying no date for the move | **FIXED, then corrected** — the §18.2 rule 7 remedy was itself wrong and is withdrawn (red team L11, §26); the item now shows the instruments' own dates, and D9 is closed |
| F9b | major | Copy payload a hand-picked subset | **FIXED** — §25.1 rule 3 |
| F12 | major | What the client does with a malformed `what_it_is_not` | **FIXED** — §18.2 rule 3 (SOFT: block and heading dropped together) |
| F12b | major | Accent budget broken by the docked composer | **FIXED** — §14: Caution is a semantic status hue, outside the accent count |
| F13 | minor | Session rail inverts state-word-first order | **FIXED** — §25.1 rule 12 |
| F13b | major | At 700px the answer column is narrower than the Word pane | **FIXED** — panel fluid `min(384px, 40vw)`; one-column breakpoint raised; 768/1024 added to the capture set |
| F14 | minor | "Spans the row cited" asserts more than the contract carries | **FIXED** — §25.1 rule 13, and the wireframe redrawn |
| F14b | major | The capability list comes after the field it fills | **FIXED** — §15 tab order puts capability rows before the question |
| F15 | minor | L-C2 claimed for `out_of_scope`, which cannot meet it | **FIXED** — §25.1 rule 14 |
| F15b | major | `₹12,00,00,000` is a client-composed string for `120000000` | **FIXED** — §6 renders the value as it arrives; wireframes redrawn |
| F16 | major | `out_of_scope` prints body and regulator twice | **FIXED** — §25.1 rule 4 |
| F17 | major | Ink-40 at 1.7:1 carries the ServiceError boundary | **FIXED** — dashed **Ink-80** border |
| F18 | major | A marker moves focus into a collapsed subtree | **FIXED** — §25.1 rule 5 |
| F19 | major | The change badge names one side only | **FIXED** — §25.1 rule 6 |
| F20 | major | Two mono columns overflow at 320px | **FIXED as a rule** — label-over-value, no mono for fact keys; wireframe redrawn. **OPEN for Phase B:** §7.4 and §7.8 must also be drawn at 320 before sign-off (§24 check 2) |
| F21 | major | Five negations in the strongest state | **FIXED, then corrected** — §25.1 rule 7's remedies made claims no field supports; three withdrawn (§26) |
| F22 | major | Everything that makes it feel like Harvey exists only at ≥1100px | **OPEN — founder decision.** The critic is right that the pane is where the product lives (C7) and the Harvey frame is a web-only luxury. Bringing a docked source sheet with a turn header and a compact turn switcher down to 320–400px is a redesign of §7 and §10, not an edit. Recorded as the first question for Phase B, with §23 risk 2 |
| F23 | minor | Six equal all-caps labels, flat hierarchy | **FIXED** — §25.1 rule 8 |
| F24 | minor | The frame shifts when the first answer arrives | **FIXED** — §25.1 rule 9 |
| F25 | minor | A truncated hash is decoration | **FIXED** — §25.1 rule 10 |
| F26 | minor | SUPERSEDED shown while its own date flags contradict it | **REVERSED 2026-09-17** — the flags do not contradict it (red team L11); §18.2 rule 7 withdrawn |
| F27 | minor | A bespoke date parser rejects what Indian practitioners type | **FIXED** — §25.1 rule 11 |
| F28 | minor | §9 titled "six wordings" with five rows | **FIXED** — the sixth row added (D4) |

**Totals: 42 FIXED, 1 OPEN (F22, founder decision), 0 REJECTED.** No finding was rejected: the two
critics were given the spec, the contract and the audit, and every claim they made held on inspection.

The three passes that applied these findings hit the same failure twice — a single agent given all 43
findings against an 86KB spec stalled six times — so the batch that ran, the surgical edits and this
section were done in the main session. Recorded because it is a fact about how this document was made.

---

## 26. Red team — findings and dispositions (2026-09-16/17)

Four adversarial lenses read the built prototype (`web/assistant/`, commit `7f5255d`) against this spec,
the contract and the engine: legal accuracy and abstention (L), accessibility (A11Y), design quality
(DQ), NON_GOALS guard (NG). **52 findings: 4 fatal (3 distinct defects — DQ1 and L1 are one), 28 major, 20 minor.** Their verdict: "a debug view
with a form on top". Findings file (outside the repo): `~/.cache/placedon-ux-tools/redteam_findings.json`.

Method: the red-team assertions were added to `web/assistant/tools/accept.mjs` first; the old build
failed them (**233/396**). The rebuild (`2c21e09`) passes **403/403** across 6 fixtures × 5 widths plus
the empty state. Two engine-side findings were fixed in the contract builder (`ea627b7`). Two findings
proved this spec wrong (L5, L11) and are corrected above (§25.1 rule 7, §18.2 rule 7).

| ID | Sev | Finding (short) | Disposition |
|---|---|---|---|
| NG-1 | fatal | Ask reloads the page; default fixture reads as a live answer | **FIXED** `2c21e09` — submit prevented, status "Prototype: nothing was sent…", no fixture = empty state |
| DQ1 | fatal | `confirmed[]` never rendered in the card | **FIXED** `2c21e09` — every element rendered, rows and citations in their own groups |
| L1 | fatal | same, legal lens: a count heading over rows reading "not determined" | **FIXED** `2c21e09` — rows with state word and full basis; "None of these is a finding of compliance." |
| L2 | fatal | document turn has no `law_version`; Act-only rows read CURRENT at a 2024 date | **FIXED** `ea627b7` (validator + builder) and `2c21e09` (card: "It is not the law as it stood on 01-Jun-2024.") |
| NG-2 | major | empty state has no title; Holds line filled from the last answer | **FIXED** — §13 title and sub; Holds line removed until `GET /v1/scope` exists |
| NG-3 | major | composer copy "holds the law as it stands" overclaims | **FIXED** — "a current consolidation, not point-in-time law" |
| NG-4 | major | no model-use line | **FIXED** — stamp always states it; "Model use: not stated" when absent |
| NG-5 | major | model-facing strings leak through Sources | **FIXED** — one shared filter for `not_confirmed` and `evidence_pack.missing`; engine wording behind a disclosure |
| NG-6 | major | facts appear with no provenance | **FIXED** — "Facts sent with this request, entered in fields, not read from the question." |
| NG-7 | major | empty `confirmed` silent; Sources hidden | **FIXED** — "Confirmed: none"; panel says "Sources for this turn: none supplied." |
| NG-8 | major | follow-up does not say what it follows | **FIXED** — parent line + collapsed parent turn |
| DQ2 | major | row hierarchy flat, basis buried | **FIXED** — state word + basis lead the row; visible rule |
| DQ3 | major | 1440 layout has no rail, no sticky sources | **FIXED** — rail · answer · sticky Sources grid ≥1200px |
| DQ4 | major | composer takes 40% of the pane | **FIXED differently** — compacts at the top, not docked at the foot (§2 change 11) |
| DQ5 | major | accent overused, browser-blue radios | **FIXED** — Ink `accent-color`, Ink tab rule and pane Ask button, Ink-80 superseded rule |
| DQ6 | major | raw enums and mono sentences | **FIXED** — §13 display maps; mono only for refs, keys, hashes; dotted keys break at dots |
| DQ7 | major | context band not a strip; About ignores `context.kind` | **FIXED** |
| DQ8 | major | duplicate duties on the document turn | **FIXED** — scope frame first; not-confirmed items identified by provision |
| DQ9 | major | no h1, no wordmark, no empty state | **FIXED** — Playfair **not** added (self-hosted font = PLAN §5 dependency decision, founder) |
| A11Y-1 | major | submit reloads; nothing announced | **FIXED** — Enter asks, Shift+Enter new line, polite status. Focus-to-new-turn awaits a real `/v1/ask` |
| A11Y-2 | major | group labels are divs | **FIXED** — h3 |
| A11Y-3 | major | confirmed rows unreachable | **FIXED** (as DQ1) |
| A11Y-4 | major | records are tab stops that do nothing | **FIXED** — `[n]` markers → record (tabindex −1) → "Back to answer"; check 7 rewritten |
| A11Y-5 | major | input borders 1.2:1 | **FIXED** — Ink-80, 8.9:1; checked |
| L3 | major | empty-`confirmed` partial untested | **FIXED** — fixture `partial_nothing_confirmed` (`ea627b7`) + checks |
| L4 | major | identifiers dropped with model-facing detail | **FIXED** (as NG-5) — ref and state always shown |
| L5 | major | "still current" is a claim no field supports | **FIXED** — "No end date recorded"; **spec corrected** §25.1 rule 7 |
| L6 | major | 880(E) served CORROBORATED on an attestation with no download source | **OPEN — founder decision** (tighten `register_gsr880e.is_attested()` and re-attest). Client shows "Gazette link: not recorded" |
| L7 | major | "Source link: not recorded" when a link was recorded | **FIXED** — "on the retired host indiacode.nic.in, so it is not linked"; URL behind a disclosure, unrepaired |
| L8 | major | scope frame and not-confirmed repeat each other | **FIXED** (as DQ8) |
| L9 | major | superseded detail dropped; server strings built as chrome | **FIXED** — detail and status words rendered with `field()` |
| L10 | major | composer promises currency | **FIXED** (as NG-3) |
| NG-9 | minor | About control ignores the turn's context | **FIXED** |
| DQ10 | minor | Unicode glyphs misalign | **FIXED** — inline SVG, `aria-hidden` |
| DQ11 | minor | cramped label; As-of as an input; focus ring in shots | **FIXED** — As-of is text; shots taken before any focus |
| DQ12 | minor | `what_it_is_not` list as plain lines | **FIXED** — `<ul>` at body size |
| A11Y-6 | minor | disclosures lack `aria-expanded` | **FIXED** — checked |
| A11Y-7 | minor | no h1; aside unlabelled | **FIXED** |
| A11Y-8 | minor | glyph read aloud | **FIXED** |
| A11Y-9 | minor | vague link names, small targets | **FIXED** — "Source: {cite}", "Gazette copy of {instrument}" |
| A11Y-10 | minor | targets under 44px | **FIXED** for Ask, tabs, radios, markers, actions; inline disclosures 32px (above WCAG 2.5.8's 24px) |
| A11Y-11 | minor | label touches field | **FIXED** |
| A11Y-12 | minor | 11px text | **FIXED** — 12px minimum |
| A11Y-13 | minor | `disabled` hides the reason | **FIXED** — `aria-disabled` + described-by reason |
| A11Y-14 | minor | parent line not associated | **FIXED** — `aria-describedby` |
| A11Y-15 | minor | record has no text-basis line | **FIXED** — dashed rule and basis line in each record |
| A11Y-16 | minor | dead tabs are tab stops | **FIXED** — tablist, one stop, others `aria-disabled` |
| L11 | minor | spec rule 7 would hide a valid supersession | **FIXED** — **spec corrected**, §18.2 rule 7 withdrawn, D9 closed; check asserts the item renders |
| L12 | minor | spans rendered once, wrong index, `resolved` ignored | **FIXED** — per row, real path, "not found in the corpus" |
| L13 | minor | law-version line hardcoded | **FIXED** — derived from `basis` + `point_in_time_verified`; unknown basis → statement verbatim |
| L14 | minor | composed lines marked chrome escape check 6 | **FIXED** — composed lines use `field()` |
| L15 | minor | About radios ignore `context.kind` | **FIXED** (as NG-9) |

**Totals: 50 FIXED (4 of them by correcting this spec or the builder), 1 FIXED differently (DQ4),
1 OPEN (L6, founder decision).** Still open from §25: F22.

**What the checks still cannot see** (recorded so 403/403 is not read as more than it is): the verbatim
text keeps the source PDF's hard line breaks and literal `<sup>` markup, which is faithful and ragged;
"Copy with sources" copies rendered text only, so closed disclosures are not in the paste; the rail and
Sources borders end at one viewport height in full-page screenshots (they are sticky); no screen reader
was run, only DOM assertions; and every fixture is a saved response, so waiting, cancel and service-error
states (§7.3, §7.11) are drawn in the spec but not built.

---

## 27. Alignment with the finalized frontend (2026-09-17)

**Finding.** Everything above was designed against `Placedon-law-business-plan/docs/DESIGN_SYSTEM.md`
(2026-08-16). The frontend the founder calls finalized, `placedon-claude-legal-3300` (Next.js 16,
built 2026-09-11 to 09-15, and what https://www.placedon.com serves), uses a later, different system:
dark ink and cream, Brass Gold as the one accent, Cool Grey reserved for abstention, Fraunces / Inter /
IBM Plex Mono, and the voice "Ask. Verify. Cite. Or abstain." No backend Ask document mentioned that
repo. Evidence and every conflict (C1–C20): [research/ux/FRONTEND_ALIGNMENT_2026_09_17.md](research/ux/FRONTEND_ALIGNMENT_2026_09_17.md).

**Applied** (`5202f85`; 403/403 acceptance checks):

| Was | Now | Why |
|---|---|---|
| Light Parchment page, white cards | Web: the site's dark ink shell. Each answer is Compliance Note paper (`#fbf8f2`, ink `#171512`). Pane (≤400px): light cream | 3300 `layout.tsx:46` is dark only; `.ddoc-paper` is its answer artefact. Status hues fail on ink (Slate 2.60:1, Caution 2.77:1, abstain grey 3.29:1), so they appear only on paper |
| Slate accent | Brass Gold is the one accent element (the pane's current tab); gold-muted is used only for citation numbers on ink (4.72:1). Buttons are cream on ink (web) and ink on cream (pane) | 3300 `AGENTS.md:12-15` |
| Caution brown on NOT CONFIRMED | The site's abstention card: 3px Cool Grey rule, faint tint, dashed badge carrying the kind word | `AGENTS.md:14-15`; `surfaces.css:176-186` |
| Dashed rule = section-text basis | **Double** rule = section-text basis. Solid ink rule = figure (unchanged). Dashed = abstention, as on the site | The same mark cannot mean two things across the product |
| System serif / sans / Menlo | Fraunces / Inter / IBM Plex Mono named first; mono for every reference, figure, instrument and date. No font file in this repo: the runner loads the brand-kit fonts for screenshots (`FONTS_DIR`) | `AGENTS.md:16-18`. Copying 1.5 MB of fonts into the engine repo buys nothing the port will not get from `next/font` |
| "Partly answered" | "Abstained in part", and "Abstained" when `confirmed[]` is empty | "Partly answered" over a turn that answered nothing is an overclaim, and §7.12 says that turn will dominate. The site's promise is "Or abstain." The state and its glyph are still the server's (C3); the word is chosen from the server's own `confirmed[]`, as "Confirmed: none" already was |
| Pane tabs on the web | Pane tabs in the pane only. Web: eyebrow "Product · Ask" and the concept note "Product concept, shown on fixed sample responses. Nothing you type is sent: there is no answer endpoint yet." | `RAG-INTEGRATION.md:58-60`: "do not present a working chatbot". The Ask page already sent nothing; now it says so before anyone types |

**Kept stricter than the site:** 3px radius, no shadows or glass, motion ≤200ms (the site allows 250ms).
**Rejected:** labelling obligation rows with the site's "Determined" class badge. A row whose own state is
"Applies · not determined" under a badge reading "Determined" is the heading-contradicts-row failure
(C10, §13 partial groups).
**Accepted tension:** a nothing-confirmed turn shows the `partial` half-square beside "Abstained". The
glyph marks the server's state; the word states what the turn did.

**Open — founder decisions** (none blocks the prototype):
1. Confirm that `placedon-claude-legal-3300` is the design system of record. Its own `AGENTS.md:3` still
   says Next 15 + shadcn, and there is no shadcn in it.
2. Placement: the web Ask as a fifth product surface at `/product/ask` inside the site's `SurfaceShell`
   (report F5), concept-only until `/v1/ask` exists. Lifting the site's client ban (`types.ts:5`) is a
   decision for when the route ships, and belongs in that repo's `AGENTS.md`.
3. Dates: the Ask keeps `DD-Mon-YYYY` (in mono), which cannot be misread day/month. The site shows raw ISO
   and `formatIST` ("11 Sept 2026"). One convention should win.
4. Motion ceiling: 200ms (Ask) or 250ms (site). The site's own nav and button animations would fail the
   Ask check as they stand.
5. The Word add-in (`addin/taskpane.html`) still carries the retired Parchment / Slate / Caution tokens and
   a green `.row.ok`. Re-basing it is a separate change.
6. Contract questions for the frontend are listed in `web/assistant/contract.md` §9.
