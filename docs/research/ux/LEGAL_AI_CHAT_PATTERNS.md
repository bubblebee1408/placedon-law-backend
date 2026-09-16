# Legal-AI chat patterns and trust evidence — research for PLAN_13 (Ask section)

Researched 2026-09-15. Public sources only; no logins. Markers: **SOURCED** (URL opened this session) ·
**INFERRED** (reasoning) · **UNVERIFIED** (seen only in a search snippet, or page not retrievable).
"Could not find" below means "not on the pages listed", never "does not exist".

---

## Question

1. How do CoCounsel, Lexis+ (Protégé), Spellbook, Legora and vLex Vincent present a grounded assistant —
   composer, citation display, abstention / "could not find" states, jurisdiction or source scoping
   before asking, document-context vs general mode?
2. What does peer-reviewed / major-lab evidence say about citation display and verification,
   abstention and uncertainty wording, over-reliance, and streaming?
3. Are the external claims already in `Placedon-law-business-plan/docs/UX_INTERACTION_SPEC.md` accurate?

## Sources checked

**Vendor / help centre (opened):**
- https://www.thomsonreuters.com/en-ca/help/cocounsel/legal/skills/understanding-cocounsel-skills/ai-assisted-research
- https://www.lexisnexis.com/en-us/products/lexis-plus-protege/legal-research.page (WebFetch failed "header overflow"; retrieved with curl + browser UA)
- https://help.spellbook.legal/en/articles/10438652-how-to-use-spellbook-s-associate-an-overview
- https://help.spellbook.legal/en/articles/9926382-how-to-use-ask-spellbook-s-built-in-assistant
- https://legora.com/blog/a-new-assistant-experience-in-legora
- https://legora.com/product/tabular-review
- https://support.vlex.com/vincent-by-vlex/vincent/getting-started-with-vincent/your-first-analysis-asking-a-research-question
- https://support.vlex.com/vincent-by-vlex/vincent/getting-started-with-vincent/understanding-vincents-unique-features

**Secondary (law-library guides, opened):**
- https://lawlibguides.usc.edu/c.php?g=1447399&p=10757364 (USC Gould; last updated 18 Jul 2026)
- https://sites.psu.edu/keepingitbrief/2025/11/05/overview-of-protege-lexiss-generative-ai-feature/ (Penn State Law blog)

**Returned 404 (evidence of nothing):**
- https://support.vlex.com/features/vincent/ask-a-research-question
- https://www.thomsonreuters.com/en-us/help/cocounsel/legal/skills/skills-prompts-workflows/westlaw-deep-research
- https://www.thomsonreuters.com/en-us/help/cocounsel/legal/skills

**Research (opened):**
- Magesh et al. — https://arxiv.org/abs/2405.20362 and full PDF https://arxiv.org/pdf/2405.20362
- Amershi et al. CHI 2019 — http://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf (PDF text extracted)
- Google PAIR — https://pair.withgoogle.com/chapter/explainability-trust/ and https://pair.withgoogle.com/chapter/errors-failing/
- Zhang, Liao & Bellamy — https://arxiv.org/abs/2001.02114
- Liu, Zhang & Liang — https://arxiv.org/abs/2304.09848
- Ding et al. — https://arxiv.org/abs/2501.01303
- Kim et al. — https://arxiv.org/abs/2405.00623
- Passi, Dhanorkar & Vorvoreanu (Microsoft, 2024) — https://www.microsoft.com/en-us/research/publication/appropriate-reliance-on-generative-ai-research-synthesis/ and PDF https://www.microsoft.com/en-us/research/wp-content/uploads/2024/03/GenAI_AppropriateReliance_Published2024-3-21.pdf
- Buçinca, Malaya & Gajos — https://arxiv.org/abs/2102.09692
- Sun et al. — https://arxiv.org/abs/2606.25489
- Swoopes, Holloway & Glassman — https://arxiv.org/abs/2503.16114
- Cox et al. — https://arxiv.org/abs/2601.16720
- Microsoft HAX toolkit landing page — https://www.microsoft.com/en-us/haxtoolkit/ai-guidelines/ (did not render the guideline text; Amershi PDF used instead)

**Searches run for streaming-and-trust evidence:** "user study streaming LLM response incremental text effect on
trust perceived reliability"; "experiment streaming vs non-streaming chatbot response display trust perceived
quality user study CHI arxiv". Results were vendor/blog posts or adjacent studies (below). No
peer-reviewed study that manipulates token streaming and measures trust was found.

---

## Evidence found

### A. Competitor products

| id | claim | marker | URL |
|---|---|---|---|
| A1 | Westlaw/CoCounsel AI-Assisted Research: "You can make up to 3 jurisdiction selections… Selecting more than 3 jurisdictions defaults to a nationwide search." | SOURCED | https://www.thomsonreuters.com/en-ca/help/cocounsel/legal/skills/understanding-cocounsel-skills/ai-assisted-research |
| A2 | Same product: citations are hyperlinked inline references with bracketed resource numbers; selecting a number opens the resource in a **side panel** | UNVERIFIED (source check 2026-09-15: page says "hyperlinked in-line citations and resource reference numbers in brackets"; selecting the in-line citation "will open that resource in Westlaw", i.e. leaves for Westlaw; selecting the bracketed number "will open the side panel and scroll to that resource" within "the list of all relevant resources and snippets". The panel is a resource/snippet list, not the resource itself opened in a panel) | same as A1 |
| A3 | Same product: "up to 5 follow-up questions… within 24 hours of the initial question" | SOURCED | same as A1 |
| A4 | Same product publishes a list of query types it does not handle (Boolean, analytics, outcome predictions, multi-jurisdiction comparisons, historical law-change summaries, etc.) | SOURCED | same as A1 |
| A5 | Westlaw Deep Research "returns a structured report with inline citations and a Sources tab"; user can "set a jurisdiction"; USC lists unsupported request types (dockets, analytics, predictions, foreign law) | SOURCED (secondary: law-library guide, not the vendor) | https://lawlibguides.usc.edu/c.php?g=1447399&p=10757364 |
| A6 | Westlaw shows an "unable to answer" message when no relevant authority is found | UNVERIFIED — search-engine summary only; not on the pages opened | — |
| A7 | Lexis+ with Protégé: "Every legal citation in your response is verified and flagged with Shepard's signals"; answers can be grounded "in uploaded context documents, organization knowledge, and prior work" | SOURCED (vendor marketing) | https://www.lexisnexis.com/en-us/products/lexis-plus-protege/legal-research.page |
| A8 | Protégé offers separate modes Ask / Draft / Summarize / Documents; for Ask, "A list of the materials used to generate the response… is provided below the textual response"; sources can be limited to civil or criminal | SOURCED (secondary, Penn State Law blog, Nov 2025) | https://sites.psu.edu/keepingitbrief/2025/11/05/overview-of-protege-lexiss-generative-ai-feature/ |
| A9 | Lexis+ with Protégé replaced Lexis+ AI (Feb 2026) | UNVERIFIED — LawNext headline in search results; article not opened | https://www.lawnext.com/2026/02/lexisnexis-launches-lexis-with-protege-replacing-lexis-ai-with-an-end-to-end-workflow-platform.html |
| A10 | Spellbook splits surfaces: Word add-in for single-document work; Associate (web) "is built for multi-document tasks" with uploaded files | SOURCED | https://help.spellbook.legal/en/articles/10438652-how-to-use-spellbook-s-associate-an-overview |
| A11 | Spellbook Ask works across "an entire document or a specific selection of text"; a **"Legal Sources" toggle** switches to answers "grounded in trusted, jurisdiction-specific legal sources like CanLII and EDGAR" | SOURCED | https://help.spellbook.legal/en/articles/9926382-how-to-use-ask-spellbook-s-built-in-assistant |
| A12 | Spellbook help does not describe how citations are displayed or what happens when nothing is found | SOURCED (absence on that page only) | same as A11 |
| A13 | Legora Assistant (1 Dec 2025): a **Sources** dropdown in the composer — Legal Research / Web search / Database Search / Deep Research; files attached by typing **@**; "All your tools, files, prompts, and workflows now live in menus"; voice mode | SOURCED | https://legora.com/blog/a-new-assistant-experience-in-legora |
| A14 | Legora Tabular Review: insights "cited to its source" | SOURCED (vendor marketing) | https://legora.com/product/tabular-review |
| A15 | Legora tabular cells "can be expanded to show reasoning and source documents" | UNVERIFIED — search summary; not on the page as fetched | — |
| A16 | vLex Vincent: the jurisdiction selector sits "below the question box"; the answer appears "on the left, with a full list of the authorities Vincent cited on the right"; the memo includes a section on "counterarguments or limitations" | SOURCED | https://support.vlex.com/vincent-by-vlex/vincent/getting-started-with-vincent/your-first-analysis-asking-a-research-question |
| A17 | Vincent: "The list of authorities next to each answer is your most powerful tool. Before relying on any statement, take a moment to click through to the primary source" | SOURCED | https://support.vlex.com/vincent-by-vlex/vincent/getting-started-with-vincent/understanding-vincents-unique-features |
| A18 | Vincent's jurisdiction defaults to the user's saved default jurisdiction | UNVERIFIED — search summary; "Managing Your Default Jurisdictions" page not opened | — |
| A19 | No opened page for any of the five products documents a designed "could not find" / abstention **state** (its wording or layout). All five instead push verification onto the user | SOURCED as absence on the pages listed; INFERRED as a market pattern | pages above |

### B. Verification of claims already in UX_INTERACTION_SPEC.md

| id | claim in spec | finding | marker | URL |
|---|---|---|---|---|
| B1 | Magesh: hallucinated = "falsely asserts that a source supports a statement"; tools hallucinate 17–33% | **Confirmed.** Paper: "if a model makes a false statement or falsely asserts that a source supports a statement, that constitutes a hallucination" (§4.3). Abstract gives "between 17% and 33%" | SOURCED | https://arxiv.org/pdf/2405.20362 |
| B2 | Magesh: Ask Practical Law AI incomplete 62% | **Confirmed**: "Lexis+ AI, Westlaw AI-AR, and Ask Practical Law AI provide incomplete answers 18%, 25% and 62% of the time". **Nuance the spec omits:** the paper counts *refusals and correct-but-uncited answers* as incomplete, and says the low responsiveness "can be explained by its more limited universe of documents", which is a narrow-corpus effect like ours | SOURCED | https://arxiv.org/pdf/2405.20362 |
| B3 | Magesh: Ask Practical Law AI is "the *worst* performer" | **Overstated.** The paper says it has "the highest rate" of incomplete answers; Westlaw "hallucinates nearly twice as often as the other legal tools". "Worst" depends on the metric | SOURCED (the text); INFERRED (the correction) | https://arxiv.org/pdf/2405.20362 |
| B4 | Magesh venue "JELS 2025" | Not checked; arXiv v1 (30 May 2024) was read | UNVERIFIED | https://arxiv.org/abs/2405.20362 |
| B5 | Amershi G10 "gracefully degrade… when uncertain" | **Truncated.** Full text: "Engage in disambiguation or gracefully degrade the AI system's services when uncertain about a user's goals." G10 is about uncertainty over **user intent**, not evidentiary uncertainty. Citing it for PARTIAL stretches it; G2 fits better. G1 "Make clear what the system can do." and G2 "Make clear how well the system can do what it can do." confirmed; G11 "Make clear why the system did what it did." | SOURCED (text); INFERRED (fit) | http://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf |
| B6 | PAIR: "explain why a certain result couldn't be given and provide alternative paths forward" | **Quote confirmed, but it is in the Errors + Graceful Failure chapter**, not the explainability-trust URL the spec links. Fix the link | SOURCED | https://pair.withgoogle.com/chapter/errors-failing/ |
| B7 | PAIR: "don't show confidence if it doesn't change the decision" | **Paraphrase is stronger than the source.** Actual: "If it doesn't make an impact on user decision making, consider not showing it" and "if the confidence level could be misleading for less-savvy users, reconsider how it's displayed, or whether to display it at all." | SOURCED | https://pair.withgoogle.com/chapter/explainability-trust/ |
| B8 | Zhang, Liao & Bellamy: confidence scores calibrate trust but do not improve decisions | **Confirmed**: "confidence score can help calibrate people's trust in an AI model" but "trust calibration alone is not sufficient to improve AI-assisted decision making" | SOURCED | https://arxiv.org/abs/2001.02114 |

### C. New evidence (not in the spec)

| id | claim | marker | URL |
|---|---|---|---|
| C1 | Magesh define **misgrounded** as "cited but misinterpret the source or reference an inapplicable source", and count documents "inappropriate to the jurisdiction of interest" as misgrounded. Out-of-jurisdiction retrieval is scored as hallucination | SOURCED | https://arxiv.org/pdf/2405.20362 |
| C2 | Magesh count a refusal as *correct* only for false-premise questions, and only when it "mentions the fact that no pertinent sources were found". A stock refusal ("I cannot provide you with any information on this topic.") is coded as incomplete | SOURCED | https://arxiv.org/pdf/2405.20362 |
| C3 | Magesh: longer answers "require substantially more time to check, verify, and validate, as every proposition and citation has to be independently evaluated" | SOURCED | https://arxiv.org/pdf/2405.20362 |
| C4 | Generative search engines: "only 51.5% of generated sentences are fully supported by citations" and "only 74.5% of citations support their associated sentence"; responses "appear informative" anyway | SOURCED | https://arxiv.org/abs/2304.09848 |
| C5 | Citations raise trust **even when random**; participants who **checked** citations reported lower trust (AAAI 2025) | SOURCED | https://arxiv.org/abs/2501.01303 |
| C6 | First-person uncertainty ("I'm not sure, but…") lowered agreement with the system and **raised accuracy** (N=404, preregistered). The impersonal form ("It's not clear, but…") had weaker, non-significant effects | SOURCED | https://arxiv.org/abs/2405.00623 |
| C7 | Microsoft synthesis: verification-focused explanations, first-person uncertainty and self-critique reduce overreliance "by lowering the cost of verification", but "these strategies can backfire and result in increased overreliance"; "users find verification-focused explanations convincing even when they contain contradictions and fabrications, leading to a substantial loss in user accuracy" (caveat, p.9, citing Si et al. 2023) | SOURCED | https://www.microsoft.com/en-us/research/wp-content/uploads/2024/03/GenAI_AppropriateReliance_Published2024-3-21.pdf |
| C8 | Cognitive forcing functions reduced overreliance more than simple explainable-AI displays, but users rated them **less favourably**, and people high in Need for Cognition benefited more | SOURCED | https://arxiv.org/abs/2102.09692 |
| C9 | Rationale presentation timing (instant / delayed / on-demand) showed "no reliable presentation-format effects". Correctness and certainty framing drove trust (N=68 online + N=54 eye-tracking) | SOURCED | https://arxiv.org/abs/2606.25489 |
| C10 | Showing multiple sampled responses can counter undue trust (CHI 2024 TREW workshop paper) | SOURCED | https://arxiv.org/abs/2503.16114 |
| C11 | "Watching AI Think" tests visible pre-response *thinking content* in supportive dialogue, not token streaming | SOURCED (design only) | https://arxiv.org/abs/2601.16720 |
| C12 | Peer-reviewed evidence that **token streaming** itself changes trust or verification | Could not find with the two searches listed. Claims that streaming "elevates trust" appeared only on vendor blogs (byaiteam.com, thefrontkit.com) and are not evidence | UNVERIFIED |

---

## Evidence quality

- **Competitor UI:** weak to moderate. Help-centre pages are first-party but describe features in prose. There are
  no screenshots I could verify, and marketing pages (A7, A14) are claims, not behaviour. Two law-library guides
  (A5, A8) are independent but secondary. Three vendor URLs 404'd. Nothing here was observed in a live product.
- **Magesh et al.:** strong (preregistered, full paper read). It evaluates 2024 versions of products that have since
  been rebranded or replaced (A9, UNVERIFIED), so the rates are historical.
- **HCI:** Kim (N=404, preregistered, FAccT), Buçinca (CSCW), Liu (EMNLP Findings) and Ding (AAAI) are peer-reviewed
  lab studies. None uses legal professionals; Kim's task was medical. Transfer to Company Secretaries is **INFERRED**.
  Sun et al. is a CHI extended abstract with small N. The Microsoft synthesis is a literature review, not new data.

## Result

1. **Scoping before the question is standard in legal AI** (SOURCED A1, A5, A11, A13, A16). Westlaw caps jurisdictions
   at 3, Vincent puts the jurisdiction selector below the question box, Spellbook toggles "Legal Sources", and
   Legora has a Sources dropdown. Magesh (C1) gives the reason: an out-of-jurisdiction source counts as a hallucination.
2. **Two citation layouts dominate:** inline markers plus a side panel or tab (Westlaw A2/A5, Vincent A16), or a list
   below the answer (Protégé A8). None of the pages opened shows provenance **dates** next to figures (INFERRED from
   absence; see A19). C2 is still unoccupied.
3. **No competitor documents a designed abstention state** on the pages checked (A19). They publish lists of
   unsupported query types (A4, A5) and tell the user to verify (A17, A8).
4. **Citations are a trust amplifier independent of correctness** (C4, C5). A visible chip is not evidence of
   grounding, which is Magesh's point restated in HCI terms. The design must make checking cheap (C3, C7), not
   merely possible.
5. **Wording of uncertainty matters.** First-person hedges beat impersonal ones (C6). But certainty cues raise
   trust whether or not they are warranted (C9), and every mitigation can backfire (C7).
6. **Streaming:** no evidence either way on trust (C12). The closest study (C9) finds *when* reasoning appears
   matters less than whether it is correct. That removes any evidence-based argument *for* streaming prose before
   the state is decided.
7. **The spec needs four corrections:** B3 ("worst"), B5 (G10 scope), B6 (PAIR link), B7 (PAIR paraphrase).

## Unresolved issues

- A6, A15, A18 are UNVERIFIED. The actual Westlaw "unable to answer" wording and layout are unknown.
- How any competitor renders a no-result state visually: **not found** on public pages; it would need a vendor
  demo video or conference talk (not searched).
- Harvey was out of scope for this file (another researcher).
- B4 venue not checked.
- There is no legal-practitioner study of first-person vs impersonal uncertainty. Kim's finding may not transfer to
  a statutory-currency tool whose abstentions are rule-based, not model-felt (INFERRED).
- C12: streaming and trust remains open.
- Passi & Vorvoreanu 2022 (https://www.microsoft.com/en-us/research/wp-content/uploads/2022/06/Aether-Overreliance-on-AI-Review-Final-6.21.22.pdf) was found but not opened.

## Recommended next action

1. Fix UX_INTERACTION_SPEC.md B3, B5, B6, B7 in the next business-plan edit. This file does not edit it: that repo
   is public and out of this task's write scope.
2. For A6 and the abstention-state gap, search Thomson Reuters / vLex / Legora public webinar recordings on YouTube
   for a no-result screen. Record the timestamp URL.
3. Add a falsification test to PLAN_13 §7 built on C5. In the ten conversations, check whether practitioners open
   the Source panel at all. If they don't, citation chips are decoration, and the as-of date must stay inline (C2).

---

## What this means for the Ask section design

| # | Pattern | Verdict | Reason (tied to C1–C10 and evidence) |
|---|---|---|---|
| 1 | Scope control **above/below the composer, always visible** (Vincent A16, Legora A13, Spellbook A11) | **Keep** | Answers §2 Q1: prevents out-of-scope before submit. It is the industry pattern, and Magesh C1 scores wrong-jurisdiction sources as hallucination. PLACEDON variant: show scope as a *fact* ("Companies Act 2013 · as of 15-Sep-2026"), not a picker of things we don't hold (C1, C10: the DPDP chip was exactly that failure) |
| 2 | Multi-select scope picker (Westlaw 3 jurisdictions, Legora 4 source types) | **Reject for v1** | One body of law held. A picker implies choice we can't honour and would re-create C10's out-of-scope chip. Declared-but-not-held bodies belong in the `out_of_scope` answer, not the composer (C1, C3) |
| 3 | "This document / General" context switch (Spellbook Legal Sources toggle A11; Protégé separate Documents mode A8) | **Adapt** | Answers §2 Q7. Spellbook proves the toggle is a known pattern in a Word add-in (C7). Make the active context a **labelled segmented control plus a per-turn stamp** ("About: Board minutes 12-Mar.docx"), never a small toggle. The falsifier in PLAN_13 §7 is users missing the difference |
| 4 | Inline citation markers + **side panel** (Westlaw A2, Vincent A16) | **Adapt** | The panel pattern fits web width. But a bracketed number does not satisfy C2 (instrument + as-of visible without a click). Inline element = instrument + as-of text; the panel carries verbatim text and the currency strip. At 320px the panel becomes a push-down section, not a drawer (C7) |
| 5 | Sources list **below** the answer (Protégé A8) | **Adapt for task pane** | Workable at 320–400px (C7) where a side panel is impossible. It still cannot replace inline as-of (C2) |
| 6 | A citation chip as the trust signal | **Reject as sufficient** | Ding C5: random citations raise trust; Liu C4: 25% of citations don't support their sentence. A chip without verbatim text and date is the misgrounding pattern (Magesh B1). Pair every chip with the quoted words on open |
| 7 | "Trust but verify" disclaimer boilerplate (Vincent A17, Protégé A8) | **Reject** | Pushes the verification cost onto the user, which C7 says drives overreliance or abandonment. PLACEDON's job (C2) is to have done the dating. A disclaimer would read as hedging (PLAN_13 §7 falsifier 3) |
| 8 | Published list of what the system can't do (Westlaw A4, USC A5) | **Keep, relocate** | Amershi G1/G2 (B5). Show it as the composer's empty-state capability list, generated from `checker/bundles.py` and `checker/scope.py`, so suggested questions are real (PLAN_13 §4, C1) |
| 9 | Stock refusal ("I cannot answer that question") | **Reject** | Magesh C2 codes it as incomplete. Only a refusal that says *what was searched and not found* scores as correct. `out_of_scope` must name the Act asked about, what we hold, and what we'd need to acquire (CLAUDE.md scope rule; C3, C5) |
| 10 | PAIR "explain why… and provide alternative paths forward" (B6) | **Keep** | Supports PARTIAL showing verbatim text plus a next step. Cite the errors-failing chapter, not explainability-trust |
| 11 | First-person hedging in answers ("I'm not sure, but…") (Kim C6) | **Adapt carefully** | The evidence favours first person over impersonal. But PLACEDON's states are server-decided rule outcomes (C3), not model feelings, and C9 shows certainty cues sway trust regardless of correctness. Use first-person-plural **statements of fact about the check** ("We have not dated the prescribed amount. We will not state a figure."), which the spec already does. Do not add model-voiced hedges to ANSWERED |
| 12 | Confidence percentages | **Reject (reconfirmed)** | Zhang B8 confirmed; PAIR B7 (weaker than the spec's paraphrase, still supportive); C4 |
| 13 | Token streaming of answer prose | **Reject** | No evidence it helps trust (C12). Sun C9: timing matters less than correctness. Streaming shows unverified prose before the server decides the state, which violates C3. Stage captions only (C4), ≤200ms transitions (C6) |
| 14 | Follow-up cap (Westlaw: 5 within 24h, A3) | **Adapt** | Evidence that a legal vendor bounds threads. PLACEDON bounds by **re-grounding each turn** with its own as-of stamp (§2 Q4), not by count. A count cap is arbitrary without usage data |
| 15 | Long memo answers with analysis + "counterarguments or limitations" (Vincent A16) | **Reject for v1** | Magesh C3: length multiplies propositions to verify. The spec's short heading + figure block + verbatim source keeps checking cost low (C7). Vincent's explicit "limitations" section is worth keeping in spirit, and PARTIAL's NOT CONFIRMED block already is that |
| 16 | @-mention files, voice mode, Tabular-Review-from-chat (Legora A13) | **Reject** | §2 Q8: no named user need. File drop contradicts the rejected document-upload decision (UX spec §5). Voice is not a v1 surface (C7) |
| 17 | Cognitive-forcing friction (e.g. user commits before seeing an answer) (Buçinca C8) | **Reject for v1, note** | Reduces overreliance but is rated unfavourably, and benefits high-NFC users more. Wrong trade for a 10-conversation validation phase. Opening the verbatim source in one click is the low-friction substitute (C7) |
