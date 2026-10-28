# DECISION — document excerpt retrieval (L3)

Agent R, 2026-10-28. Inputs: RESEARCH_retrieval.md (sources S1–S19), EVAL_retrieval.md (T's baseline,
verified by the orchestrator). No code edited. Sources are cited by their S-number.

## 0. Baseline this decision is designed against (CUAD dev, contracts 0–50, 612 answerable q)

| variant | R@1 | R@3 | R@8 | MRR | prec | shown | empty | unsrch |
|---|---|---|---|---|---|---|---|---|
| long  | 0.193 | 0.382 | 0.546 | 0.306 | 0.109 | 6.50 | 0.015 | 0.062 |
| short | 0.175 | 0.358 | 0.492 | 0.282 | 0.162 | 4.49 | 0.100 | 0.062 |

Synthetic: notice-period FAIL (8/8 pages), fee PASS, semantic-gap PASS by accident, both follow-ups FAIL
alone / PASS with the prior question prepended.

## 1. Decision in one paragraph

Phase 1 replaces `overlap / sqrt(len(terms))` with **Okapi BM25** over the passages of the documents being
searched in this call (S1), on tokens that are **Porter2-stemmed if ASCII-Latin**, **NFC-normalised and
unstemmed otherwise** (S3, S4); it then **cuts the ranked list relative to this query's top score** with a
**common-term guard** instead of always filling 8 slots (principle from S5–S7, rule ours); and when the
question is elliptical or matches nothing it **expands with the previous user question's terms at half
weight** (HQE, S14, weight ours). Everything is stdlib, deterministic, model-free; `_spans()` and therefore
every offset is untouched; scores never leave `collect()`; NO_MATCH still means "no passage shares an index
term with the question". Phase 1b (separately switchable) adds a small preamble/date rule for metadata
questions. Phase 2 (dense leg + RRF) and phase 3 (reranker) are gated on bake-offs and residency approval.

## 2. Phase 1 — specification

### 2.1 Tokenisation (`_tokens(text) -> list[str]`, replaces the set-returning `_terms`)

Same character rule as today's `_terms` — the Indian-script fix stays exactly as it is:

```
for char in casefold(text) + ' ':
    if char.isalnum() or unicodedata.category(char).startswith('M'): token.append(char)
    elif token: emit(''.join(token)); token.clear()
emit(word):
    word = unicodedata.normalize('NFC', word)      # token only; the stored text is never normalised (S4)
    if len(word) <= 1 or word in STOP: drop
    if word is all ASCII a–z: word = porter2(word)   # digits / mixed / other scripts: unstemmed
    yield word                                      # a LIST: term frequency is kept for BM25
```

- **NFC, not NFKC** (S4: NFKC erases distinctions; NFC makes precomposed and decomposed nukta forms equal).
  Normalisation can change a token's length; that is safe *only because* tokens are never used for offsets.
  Offsets come from `_spans()` on the raw text, unchanged.
- Numbers survive (`30`, `2026`), unlike `checker/lexical_rank.tokenize` (`[a-z]+`, len ≥ 3), which is why that
  tokenizer is **not** reused.
- Hyphenated words split (`co-exclusive` → `co`, `exclusive`) — this is what makes the short "Exclusivity"
  query match (`exclusivity`→`exclus`, `exclusive`→`exclus`).

**Stoplist** = today's `_STOP` (already contains `agreement contract clause section document file …`) **plus**
legal-drafting function words and our query-template words:
`shall such herein hereof hereto hereunder thereof therein thereto will also any there whether related regarding concerning`.
Deliberately **not** stopworded: `party/parties`, `date`, `name`, `notice`, `term`, `not`, `no`. Common legal words
are handled by IDF (S1), not by a list — a list would silently delete the Parties question and negations.
Stoplist is applied to the casefolded surface form before stemming.

### 2.2 Stemming — Snowball English (Porter2), full algorithm, English ASCII tokens only (S3)

- Why the full algorithm and not Porter step 1: step 1 alone (S2) does not conflate `termination`/`terminate`
  (needs ATION→ATE and step 4), which is root cause 3 verbatim. Why Porter2 over Porter 1980: Porter 1980 merges
  `general`/`generate` → `gener`; Porter2's R1 prefix exception (`gener`, `commun`, `arsen`, `past`, `univers`,
  `later`, `emerg`, `organ`, `inter`) keeps them apart (S3).
- Implement from the snowballstem.org specification in a new stdlib module `gateway/english_stem.py`
  (~150 lines: prelude, R1/R2, steps 0, 1a, 1b, 1c, 2, 3, 4, 5, exceptional/invariant forms). Memoise per call
  with a plain dict (vocabulary of one call is bounded by `MAX_TOTAL_CHARS`).
- Expected stems (unit-test vectors): `termination, terminate, terminated, terminating → termin`;
  `parties, party → parti`; `exclusivity, exclusive, exclusively → exclus`; `general → general`;
  `generate → generat`; `news → news`; `notices, notice → notic`; `assignment, assign → assign`.
- Indian scripts: **unstemmed** (no verified Indian-language stemmer, RESEARCH §b). Recall loss on inflected Hindi
  forms is accepted and listed as a limitation.

### 2.3 Term weighting — BM25 over the passages of this call (S1)

Collection C = every passage `_spans()` yields for every document with status SEARCHED in this `collect()` call.
N = |C|, n_t = number of passages containing t, dl_p = number of index tokens in p, avgdl = mean dl over C.

```
idf(t)       = ln(1 + (N − n_t + 0.5) / (n_t + 0.5))        # non-negative variant (lexical_rank.py), S1 eq. 3.3 + 1
bm25(t, p)   = idf(t) · tf(t,p)·(k1 + 1) / (tf(t,p) + k1·(1 − b + b·dl_p / avgdl))
score(p)     = Σ_{t ∈ Q} w_t · bm25(t, p)                    # Q = UNIQUE query terms, summed in sorted(t) order
k1 = 1.2, b = 0.75                                           # inside S1's 1.2<k1<2, 0.5<b<0.8
```

- Unique query terms (qtf = 1): the CUAD "Details" text and natural questions repeat the topic word; S1 says qtf
  saturation is unimportant, so the simplest choice costs nothing measurable. Not a tuning knob.
- Summation in sorted term order makes the float result bit-identical across runs (determinism test).
- `w_t = 1` for current-question terms; `w_t = W_HISTORY` for history-only terms (§2.5).
- **No proximity/phrase bonus**: S1 reports small gains even where it works. Revisit only with a measured case.
- **Streaming, two passes, bounded memory.** Pass 1 over `_spans()` builds `df` (a Counter of the *set* of each
  passage's tokens), N and total length — memory is the vocabulary, not the passages. Pass 2 re-tokenises each
  passage, scores it, and keeps the best `MAX_PASSAGES` in the existing `bisect.insort` list with the existing
  tie-break `(-score, ordinal, position)`. Tokenising twice is the price of the < 8 MiB guarantee; it must fit the
  wall-time budget in §6.

### 2.4 Ranked-list truncation — relative cut-off + common-term guard

S6 shows fixed k is the weakest truncation policy; S5–S7 show the cut should follow *this query's* score
distribution; all of their estimators are trained or parametric fits, so phase 1 uses the model-free core of the
idea. BM25 scores are not comparable across queries, which rules out an absolute threshold.

```
s_max = top candidate's score; if s_max == 0 → NO_MATCH (unchanged meaning)
keep p  iff  score(p) ≥ ALPHA · s_max                       # ALPHA = 0.5 (relative cut, INFERRED from S5–S7)
        and  (guard_off  or  p matches ≥ 1 query term t with n_t ≤ N / 2)
guard_off  ⇔  N < 4  or  no query term that occurs in any passage has n_t ≤ N/2
the top passage is always kept; at most MAX_PASSAGES = 8
```

- The **guard** is what stops "period"-only filler pages: a passage whose only shared words occur in more than half
  the passages is not shown when some rarer query word exists. The **guard_off** clauses keep NO_MATCH honest: a
  query whose matching words are *all* common (e.g. "what about the period?") still returns its best matches rather
  than a false "no match"; tiny collections (N < 4, e.g. the one-paragraph Hindi test) are not guarded because df is
  meaningless there.
- Notice-period example, worked: Q = {notic, period, termin, requir}; filler pages match only `period`
  (n_t ≈ N → idf near 0, and fails the guard); page 6 matches `notic`, `period`, `termin`. Expected shown: page 6 only.

### 2.5 Follow-ups — deterministic historical query expansion (S14, adapted)

New keyword-only parameter: `collect(query, documents, *, enabled=True, previous_query: str | None = None)`.

```
current   = unique tokens(query)
expand    = previous_query  and  (
              FOLLOW_UP.match(query)                          # cue: ^(and|also|what about|how about|what if|
                                                              #   is that|does that|can (it|that|they)|...)\b
              or not current
              or s_max(current alone) == 0
              or every current term that matches anything has n_t > N/2 )
if expand:
    Q = current (w = 1)  ∪  (tokens(previous_query) − current) (w = W_HISTORY = 0.5)
```

- From S14 we take: expansion from the previous turn, **M = 1** (best MAP in S14's grid), expansion only for
  non-first turns, and more expansion when the current utterance's best BM25 score is low (S14's QPP, here reduced to
  the zero/common-only test because S14's absolute η does not transfer). S14 concatenates at equal weight;
  **W_HISTORY = 0.5 is ours** (INFERRED): it lets the follow-up's own words decide the order whenever it has any.
- `previous_query` is **the previous USER message's text only** — never an assistant answer (CLAUDE.md: prior
  assistant answers are not evidence), never the expanded query of that turn (M = 1, no chains; 3-turn chains are a
  documented limitation and a T test case).
- Disclosure: when expanded, `result['history_query'] = previous_query[:500]` and a limitation line:
  `'This question was read together with your previous question in this conversation.'` A reader must be able to see
  why an excerpt about termination answers "And how long is that?".
- Caller: `gateway/verbs.py::_dispatch_conversation` passes the text of the last `role == 'user'` message in
  `store.read_messages(cid)` with ordinal below the current turn's. No change to the no-attachment follow-up refusal
  at verbs.py:2820. **Orchestrator must check** that `intake.classify` routes "And how long is that?" with files to
  RESEARCH_QUESTION; if not, the expansion never runs in the product even though `collect()` passes.

### 2.6 What does not change

`_spans()`, `MAX_PASSAGE_CHARS`, page handling, overview mode (round-robin sampling is untouched — overview never
scores), document limits, `EvidencePassage` keys (no score field), statuses, `description()` texts. The limitation
"Keyword matching can miss relevant wording; no match does not establish absence." stays and stays true.

### 2.7 Pseudo-code — new question-mode ranking path in `collect()`

```python
searched = []                                  # (position, did, raw, row, sha) for SEARCHED docs (existing checks)
df, N, total_len = Counter(), 0, 0
for _, _, raw, _, _ in searched:               # PASS 1: statistics only
    for start, end in _spans(raw):
        toks = _tokens(raw[start:end]); N += 1; total_len += len(toks); df.update(set(toks))
avgdl = total_len / N if N else 0.0

def ranked(weights):                           # PASS 2: score, keep top MAX_PASSAGES
    cands = []
    for position, did, raw, row, sha in searched:
        for ordinal, (start, end) in enumerate(_spans(raw)):
            tf = Counter(_tokens(raw[start:end]))
            s = sum(w * bm25(t, tf, df, N, avgdl) for t, w in sorted(weights.items()) if t in tf)
            if s > 0: insort_top_k(cands, (-s, ordinal, position, passage(...), frozenset(tf) & weights.keys()))
    return cands

weights = {t: 1.0 for t in set(_tokens(query))}
cands = ranked(weights)
if previous_query and needs_history(query, weights, cands, df, N):
    weights |= {t: W_HISTORY for t in set(_tokens(previous_query)) - weights.keys()}
    cands = ranked(weights); result['history_query'] = previous_query[:500]; result['limitations'].append(...)
rare = {t for t in weights if 0 < df[t] <= N / 2}
guard = N >= 4 and bool(rare)
s_max = -cands[0][0] if cands else 0.0
kept = [c for i, c in enumerate(cands)
        if i == 0 or (-c[0] >= ALPHA * s_max and (not guard or c[4] & rare))]
result['passages'] = [c[3] for c in kept]      # scores and term sets are discarded here
```

(Row counters `total_passages` are filled in pass 1; `shown_passages`/`excerpt_chars` unchanged.)

## 3. Phase 1b — metadata questions (separate switch `PREAMBLE_PRIOR`, separate iteration)

Finding 2: Document Name, Parties, Agreement Date are 151/612 dev questions (MRR 0.05–0.12) and their gold text
(title, party names, a date) shares no word with the question. No opened source addresses this; the rule below is
**engineering, not literature**, and is CUAD-shaped, so it is kept switchable and judged on held-out like the rest.
It is justified because "who are the parties / what is this agreement called / when was it signed" is a question
lawyers genuinely ask of an attached contract, and a deterministic answer location exists (the preamble).

```
intent = stems(query) ∩ {name, titl, parti, date}  — fires only if, after removing intent stems,
         the query has ≤ 1 other content term   (so "termination date", "notice to the other party" do not fire
         unless they are near-bare)
TITLE/PARTY intent: the first 2 passages of each searched document are placed first (in document order)
DATE intent: the first passage among the first 5 of each document matching DATE_RE is placed first
         DATE_RE = day-month-year ("6th day of April, 1999", "6 April 1999"), month-day-year ("April 6, 1999"),
                   numeric dd/mm/yyyy | dd-mm-yyyy | dd.mm.yyyy
BM25-kept passages follow, de-duplicated, total still ≤ MAX_PASSAGES.
```

Acceptance for 1b (dev): each of the three categories' MRR ≥ 0.30; MRR of the other 38 categories unchanged within
±0.005; overall precision drop ≤ 0.01. If it fails, it is dropped, not tuned beyond the two rounds.
Known gaps: Hindi dates, "Effective Date" defined elsewhere, titles on a cover page with no text layer.

## 4. Explicitly scoped out of phase 1 (with reasons)

| Item | Decision | Why |
|---|---|---|
| Acronym/synonym table (ROFR, MFN, IP …) | **Out** | No authoritative public table was opened (RESEARCH, unresolved); building one from CUAD's 41 category names would tune to the eval (circular); and the motivating case would not be fixed — the ROFR gold text is "negotiate exclusively … in good faith", which contains neither the acronym nor its expansion. Revisit with real user queries, from a cited glossary, measured on held-out. |
| Raising `MAX_DOCUMENT_CHARS` (200,000) | **Out of this loop** | 2 dev contracts (6.2% of questions) are never searched; R@8 ceiling 0.938. That is a memory/latency/limit decision with its own product consequences (limits in verbs.py byte checks, frontend copy), not a ranking change; mixing it in would credit ranking with a limit change. T reports metrics **both** over all questions and over searched-only. Separate ticket. |
| Semantic gap ("end the agreement" → "terminate") | **Phase 2** | No lexical method closes it (S9, S12). Phase 1 must answer it with an honest NO_MATCH, never with a wrong page. |
| Proximity / phrase bonus | Out | S1: small gains. |
| Indian-language stemming | Out | No verified stemmer (RESEARCH §b). |
| Deterministic heading/context prefix (vault_search.py style, S19's idea without a model) | **Phase 1c candidate** | Model-free and already proven in-repo for vault chunks; but it adds index-only text and must keep offsets on the passage. Only if phase 1 leaves headings-only clauses (e.g. "12. TERMINATION" separated from its body) as a top failure. |

## 5. Phase 2 and 3 (later, separately approved)

**Phase 2 — hybrid dense.** A dense leg over the same passages, called only through `gateway/models.serve` and the
declared providers: Azure embeddings in `centralindia` (PLAN_22 region rule), Voyage `voyage-law-2` **only after its
processing location is confirmed** (PLAN_22 D4), or an on-device embedding model (no data leaves the machine).
Client document text is the payload, so residency applies to every passage embedded. Fusion: **RRF, k = 60** (S8;
`checker/fusion.py` `RRF_K`), ranks only, never scores. Truncation on the fused list: union of the BM25-kept set (§2.4)
and the dense top-2, ordered by RRF. Refuse, never silently fall back, when the dense leg is unavailable
(`checker/chunk_fusion.py` pattern) — or degrade to BM25 *with a stated limitation*, which is a product decision.
Adopt only if (i) BM25 and dense error sets on CUAD dev are substantially disjoint (chunk_fusion precondition) and (ii)
PLAN_21's `adopt_when` holds: non-overlapping intervals on dev, confirmed once on held-out. LegalBench-RAG (S16) is the
warning that dense is not a free win on contracts.

**Phase 3 — reranker.** First an explainable linear reranker over named features (`checker/reranker.py` approach); a
cross-encoder (S11) only with a measured gain, approval and the same residency rules. S16's CUAD evidence on rerankers is
inconsistent; S19's −67% is vendor-reported. Not planned until phase 2 is decided.

## 6. Files to change (phase 1)

| File | Change |
|---|---|
| `gateway/english_stem.py` | **new**, stdlib Porter2 (`stem(word) -> str`), with a `--test` self-check registered in `scripts/run_tests.sh` |
| `gateway/document_evidence.py` | `_tokens`, extended `_STOP`, BM25 two-pass ranking, cut-off + guard, `previous_query`, `history_query`, `FOLLOW_UP`; constants `K1, B, ALPHA, W_HISTORY, PREAMBLE_PRIOR` (module-level so T can override them in the harness) |
| `gateway/verbs.py` | `_dispatch_conversation`: pass the previous user message text as `previous_query` |
| `tests/test_document_evidence.py` | unit tests below (already discovered by `scripts/conversation_regression_checks.py`) |
| `scripts/eval_document_retrieval.py` (T) | `--set NAME=value` constant overrides; follow-up cases call `collect(q2, docs, previous_query=q1)`; searched-only metrics; new synthetic case (§8) |

## 7. Unit tests to add (L4)

1. `test_common_word_does_not_pull_in_filler_pages` — 8-page synthetic: notice-period question → only page 6.
2. `test_inflections_match_via_stemming` — query "When can we terminate?" matches a passage saying "Termination".
3. `test_stemmer_reference_vectors` — table in §2.2 plus ≥ 30 pairs from the Snowball published vocabulary.
4. `test_general_and_generate_do_not_merge` — query "general" does not return a passage containing only "generate".
5. `test_cutoff_keeps_two_strong_clauses` — "termination for cause" and "termination for convenience" passages both shown
   for "termination".
6. `test_common_only_query_is_not_reported_as_no_match` — every passage contains "period"; query "period" → EXCERPTS_FOUND.
7. `test_no_shared_term_is_still_no_match` — unchanged meaning and description text.
8. `test_indic_nfc_equivalent_forms_match_and_offsets_are_original` — decomposed-nukta query vs precomposed text (and vice
   versa); `text[start:end]` equals the original bytes, not the normalised form. Existing Hindi test still passes.
9. `test_passage_keys_never_include_a_score` — keys == `EvidencePassage` keys.
10. `test_followup_expands_from_previous_question` — "And how long is that?" with previous "What does the termination
    clause say?" → page 6 only; `history_query` set; limitation line present.
11. `test_clear_new_question_ignores_history` — previous fee question, current "What is the governing law?" → no fee passage,
    no `history_query`.
12. `test_history_is_previous_user_message_not_assistant` — verbs-level: an assistant reply between turns is not used.
13. `test_question_mode_bounded_memory` — the tiny-paragraphs fixture with a *question* query: peak < 8 MiB.
14. `test_ranking_is_deterministic` — two calls, identical passages and order.
15. Phase 1b only: `test_preamble_prior_title_parties_date` and `test_preamble_prior_does_not_fire_on_clause_question`.

## 8. New synthetic case for T (finding 6)

`semantic-gap-2`: "When may this be brought to an end before it expires?" over the same 8-page document. After stopwords and
stemming its terms are {brought, end, expir}; page 6 says "Either party may terminate this agreement upon thirty days' written
notice" and shares none of them; make sure no filler page contains `end`/`expir` (or add one filler page that contains "end"
to make the trap real). **Phase 1 expected: NO_MATCH, or page 6 only. A non-gold page is a FAIL.** This case is the phase-2
motivation, not a phase-1 target.

Also: `followup-chain-3` (three turns, third depends on the first) — expected phase-1 FAIL, documents the M = 1 limit.

## 9. Tuning (dev only, contracts 0–50) and acceptance

Sweep order (each stage fixes the previous stage's winner; default kept unless a challenger beats it by > 0.01 dev MRR —
protects against fitting noise on 612 questions):

1. Switches with defaults: stemming {off, on} × guard {off, on}.
2. `ALPHA` ∈ {0.3, 0.4, 0.5, 0.6, 0.7}.
3. `K1` ∈ {0.9, 1.2, 1.5, 2.0} × `B` ∈ {0.4, 0.6, 0.75, 0.9}.
4. `W_HISTORY` ∈ {0.3, 0.5, 1.0} — synthetic follow-up suite only (CUAD has no follow-ups).
5. Phase 1b `PREAMBLE_PRIOR` {off, on} — separately, after 1–4 are frozen.

Objective: maximise long-query MRR subject to the R@8 floor; tie-break precision, then fewer shown.

**Acceptance (dev, long query, all 612 questions):** MRR ≥ 0.356 (+0.05); precision ≥ 0.20; R@8 ≥ 0.526 (≤ 2 points below
0.546, the runbook's stop condition); shown ≤ 4.0; empty ≤ 0.035.
**Short query:** MRR ≥ 0.30; empty ≤ 0.08 (must not exceed 0.100); R@8 ≥ 0.472.
**Synthetic:** notice-period PASS (page 6 only); fee PASS; both follow-ups PASS with `previous_query` (not by prepending);
semantic-gap-2 NO_MATCH or gold-only.
**Engineering:** gate GREEN; memory test < 8 MiB; dev wall time ≤ 16.4 s (2 × 8.2 s); byte-identical metrics on re-run.
**Held-out (51–101), once, after freeze:** MRR and precision improve over the held-out baseline; R@8 not more than 2 points
below it. If dev passes and held-out fails, report the negative result; do not re-tune on held-out.
**Stop:** the runbook's conditions apply unchanged — notably, if after 2 tuning rounds dev MRR **and** precision cannot beat
baseline without R@8 dropping > 2 points, report and do not ship.

## 10. Risks and how each is tested

| Risk | Test |
|---|---|
| Stemming false merge (`general/generate` under Porter 1980; legal pairs like `account/accounting`, `provision/provide`) | Unit 3–4 vectors; T lists the dev queries whose rank changed by stemming alone (stage 1 diff) for a human skim |
| Stemming makes a precise query broader (more matches → more shown) | Stage 1 reports shown and precision with stemming on vs off |
| Relative cut drops a correct second clause (two relevant clauses, second scores < 0.5 × first) | Unit 5; T reports R@3/R@8 vs baseline and the count of questions with ≥ 2 gold spans whose second span was cut |
| Guard turns a real match into a false NO_MATCH | Unit 6–7; empty-rate ceilings in §9 |
| IDF unstable on tiny collections (one short document) | `N < 4` guard-off; existing one-paragraph Hindi test |
| History drags in the old topic after a topic change | Unit 11; expansion only on cue/empty/common-only |
| Follow-up cue regex misses a real follow-up ("how long?") | Then expansion falls back to the empty/common-only trigger; T adds one cue-less follow-up case |
| Product never calls the expansion (classifier routes the follow-up elsewhere) | Orchestrator checks `intake.classify` with files; harness browser check in L7 |
| Memory regression from two passes | Unit 13 |
| Latency regression (tokenising twice + stemming) | Dev wall-time ceiling 16.4 s |
| Non-determinism from float summation order | Sorted summation; unit 14; byte-identical metrics |
| Phase 1b fires on clause questions ("termination date") | Unit 15b; non-metadata MRR ±0.005 criterion |
| Score leaks to a reader | Unit 9 |
| NFC changes offsets | Unit 8 asserts the quote equals the original, un-normalised text |
| Overfitting the dev split | > 0.01 rule; held-out once; metadata and size-limit effects reported separately |
