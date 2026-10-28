# EVAL — document excerpt retrieval (`gateway.document_evidence.collect`)

Owner: T (tester). Harness: `scripts/eval_document_retrieval.py` (stdlib only).

    PYTHONPATH=. python3 scripts/eval_document_retrieval.py [--split dev|heldout|all] [--json out.json] [--impl module:function] [--synthetic-only]

## Method

- **Data.** CUAD v1 test set (`corpus/benchmark/cuad/test.json`, CC BY 4.0): 102 contracts, SQuAD
  format, lawyer-annotated clause spans. Only answerable questions (≥1 gold span) are scored.
- **Split (non-circular).** dev = contracts 0–50 (612 answerable questions, 1,243 gold spans);
  held-out = 51–101. Every iteration tunes on dev only. Held-out is run **once**, after the
  algorithm is frozen (L7); the script warns when it is requested. Gold comes from CUAD
  annotators, never from any retriever's output, so the metric cannot reward the system for
  agreeing with itself.
- **Queries.** Each CUAD question is the template `... related to "CATEGORY" ... Details: DETAILS`.
  Two variants per question, reported separately:
  - **long** = `What does the contract say about <CATEGORY>? <DETAILS>` (lawyer-style);
  - **short** = `<CATEGORY>` alone (what users actually type).
- **Call.** `collect(query, {"c": {"text": context, "name": title}})`, one contract per call.
- **Relevance = span overlap.** A passage `[start, end)` is relevant if it overlaps any gold span
  `[answer_start, answer_start + len(text))` (half-open; touching is not overlap). Overlap, not
  containment or exact match, because the retriever returns paragraph-shaped passages (≤1,200
  chars) while CUAD spans range from a few words to 2,139 chars (median 193); the question the
  product asks is "did we show the reader the place the lawyer marked?", and overlap answers it
  with the exact offsets the product already guarantees.
- **Metrics** (per query, then averaged over queries):
  - **R@k** (k=1,3,8): 1 if any relevant passage is within the top k.
  - **MRR**: 1/rank of the first relevant passage, 0 if none.
  - **prec** (precision of what is shown): relevant returned / returned; 0 when nothing returned.
  - **shown**: mean passages returned (cap is MAX_PASSAGES = 8).
  - **empty**: share of answerable queries with status `NO_MATCH`.
  - **unsrch**: share of queries where the document was never searched (status `UNAVAILABLE`,
    here always because the contract exceeds `MAX_DOCUMENT_CHARS` = 200,000). Split out from
    `empty` so a limit is not mistaken for a ranking failure; both count as misses in R@k/MRR.
- **Synthetic suite** (embedded in the script, hand-built, **no real client data**): an 8-page text
  joined by `\f`; page 3 holds the fee clause, page 6 the termination clause, the other six pages are
  administrative filler that repeats the word "period". A case **passes** only when the top
  passage is on the gold page **and** every shown passage is on the gold page. Follow-up pairs are
  scored twice: second question alone, and with the first question prepended (what naive
  history expansion would buy).
- Deterministic: two consecutive runs give byte-identical metrics (wall time excluded).

## Baseline — current implementation, dev split (2026-10-28)

`impl=gateway.document_evidence:collect`, 51 contracts, 612 answerable questions, wall 8.2 s.

| variant | R@1 | R@3 | R@8 | MRR | prec | shown | empty | unsrch |
|---|---|---|---|---|---|---|---|---|
| long  | 0.193 | 0.382 | 0.546 | **0.306** | 0.109 | 6.50 | 0.015 | 0.062 |
| short | 0.175 | 0.358 | 0.492 | **0.282** | 0.162 | 4.49 | 0.100 | 0.062 |

Read: with the lawyer-style query the right clause is the first excerpt one time in five, and is
anywhere in the eight excerpts barely half the time — while 6.5 excerpts are shown, about 1 in 9 of
them relevant. The short query is shown fewer excerpts but goes empty on 10% of answerable questions.

## Synthetic suite — baseline

| case | mode | gold | pages shown | result |
|---|---|---|---|---|
| notice-period ("What notice period does the termination clause require?") | alone | p6 | [6,1,2,4,5,7,8,3] — 8 of 8 | **FAIL** (bug reproduced: right page first, then all seven others) |
| fee-and-due ("How much is the monthly fee and when is payment due?") | alone | p3 | [3] | PASS |
| semantic-gap ("When can a party end the agreement early?") | alone | p6 | [6] | PASS — **by accident**: "party" occurs only on p6 ("Either party may terminate"); "end"/"early" match nothing. Not evidence that the semantic gap is closed; a rewording without "party" would fail. |
| followup-termination: "What does the termination clause say?" → "And how long is that?" | second alone | p6 | [] NO_MATCH | **FAIL** |
| | with history | p6 | [6] | PASS |
| followup-fee: "How much is the monthly fee?" → "And what if it is paid late?" | second alone | p3 | [] NO_MATCH | **FAIL** |
| | with history | p3 | [3] | PASS |

History prepending turns both follow-up failures into passes on this suite.

## Observed failure patterns (dev)

Weakest categories by long-query MRR: Most Favored Nation, Volume Restriction, Unlimited License (0.00),
Document Name 0.05 (n=51), Warranty Duration 0.07, Parties 0.10 (n=51), Agreement Date 0.12 (n=49),
Revenue/Profit Sharing 0.12, Insurance 0.13. Best: Renewal Term 0.77, Termination For Convenience 0.70,
Governing Law 0.65. Full per-category table is in the `--json` output (`cuad.by_category`).

1. **Over-broad matches: one common word pulls in passages.** No term weighting and no cut-off,
   so the long query's generic words ("party", "use", "certain", "requirement") match nearly every
   paragraph: 6.5 shown, precision 0.109.
   - Insurance, contract 0: *"…Is there a requirement for insurance that must be maintained by one
     party for the benefit of the counterparty?"* → top passage is a shipping-documents list ("One copy
     of insurance coverage…"); gold "To be covered by the Seller for 110% invoice value against All
     Risks and War Risk." is rank 4 of 8.
   - Volume Restriction, contract 12: 8 passages shown, top is a license clause matched on "use";
     gold (the retweet cap "up to three (3) social media posts") never appears.
2. **Metadata questions (name, parties, date) have no lexical handle.** Their gold text is a heading
   or a date, which shares no content word with the question; together these three categories are
   151 of 612 dev questions.
   - Document Name, contract 0: *"…Document Name? The name of the contract"* — "contract" and
     "document" are stopwords, so only "name" survives; top passage is an invoicing clause; gold is
     the title "SUPPLY CONTRACT".
   - Agreement Date, contract 1: top is "IN WITNESS WHEREOF … as of the date first set forth above."
     (matched "date"); gold "6th day of April, 1999".
   - Parties, contract 0: top is the governing-law clause (matched "parties"); gold "The seller:" is rank 4.
3. **No morphology / jargon → empty short queries.** short `empty` = 0.100 vs 0.015 for long.
   - Exclusivity, contract 2: query "Exclusivity" → NO_MATCH; gold says "co-exclusive basis".
     (Exclusivity short-query empty rate 65%.)
   - Rofr/Rofo/Rofn: short query empty on 11/11 — the acronym never appears; gold is "Excite will
     negotiate exclusively with Sponsor … in good faith".
4. **Contracts over the size limit are never searched.** 2 dev contracts (18: 249,551 chars; 21:
   229,670) exceed `MAX_DOCUMENT_CHARS` = 200,000 → `UNAVAILABLE` for all 38 of their questions
   (6.2% of dev). This caps R@8 at 0.938 for any ranking change; it is a limit decision, not a
   ranking bug, and must be reported separately so a ranking iteration is not credited or blamed for it.
5. **Follow-ups without content words go empty** (synthetic): "And how long is that?" returns
   NO_MATCH; prepending the prior question fixes both pairs here.

## Caveats

- **Overlap is generous.** A passage counts relevant if it holds any part of a gold span, even a
  few characters of a 2,000-char answer; R@k and precision overstate "the reader saw the whole clause".
  13 of 1,243 dev gold spans exceed the 1,200-char passage cap and can only ever be partially shown.
- **CUAD is US SEC-filed contracts in English**, not Indian corporate documents; it measures lexical
  clause finding, not our audit domain. No page breaks, so page-level behaviour is covered only by
  the synthetic suite.
- **The query templates are ours.** "What does the contract say about X? <Details>" is one plausible
  lawyer phrasing; the Details text is CUAD's annotation guidance, sometimes phrased as a definition
  ("The name of the contract") rather than a question. The short variant (category only) is a lower
  bound on what users type, not a sample of real queries.
- **One gold set per question.** CUAD annotators may miss a relevant clause; a "false positive"
  passage can be genuinely relevant. Precision is therefore a lower bound.
- **Synthetic suite is 7 runs on one hand-built document**; it reproduces known bugs and shows
  direction, it is not a rate. The semantic-gap case passes by accident (see above).
- Held-out (contracts 51–101) has **not** been run.

---

# Phase 1 (L5, 2026-10-29): BM25 + Porter2 + relative cut + guard + previous_query

The implementation evaluated is the uncommitted worktree `gateway/document_evidence.py` plus `english_stem.py`.
It runs on the dev split only. Held-out has **not** been run.

**Harness changes**, all in `scripts/eval_document_retrieval.py`:
- `--set NAME=value` overrides a constant of the `--impl` module and clears the `_index_form` lru_cache.
- Searched-only rows are marked `*`. They cover 574 questions; contracts 18 and 21, which exceed `MAX_DOCUMENT_CHARS`, are excluded.
- `per_query` records go into the JSON.
- Follow-up cases now run in three modes:
  - `second-alone`;
  - `previous_query`, which is `collect(q2, docs, previous_query=q1)` and is the mode acceptance uses;
  - `prepend-all`, which is the old comparison.
- New synthetic cases: `semantic-gap-2`, `followup-no-cue` ("How long is that?") and `followup-chain-3`.
- Per DECISION §8, one filler page (p8) now contains "end" ("Folder access lapses at the end of each quarter."), so the semantic-gap trap is real. The baseline was re-run on the new text: the old `semantic-gap` case is now FAIL [6, 8] for the baseline too. The PASS recorded in L2 was the accident noted there.

**Baseline** is the `origin/main` file, copied to a scratch module and run with
`--impl baseline_document_evidence:collect`. The numbers are identical to L2.

## Results (dev, 612 answerable questions)

| config | long MRR | R@1 | R@8 | prec | shown | empty | short MRR | short R@8 | short empty |
|---|---|---|---|---|---|---|---|---|---|
| baseline (origin/main) | 0.306 | 0.193 | 0.546 | 0.109 | 6.50 | 0.015 | 0.282 | 0.492 | 0.100 |
| phase 1 defaults (K1 1.2, B 0.75, α 0.5) | 0.428 | 0.338 | 0.596 | 0.202 | 4.87 | 0.011 | 0.404 | 0.557 | 0.051 |
| strict §9 rule (K1 1.2, **B 0.4**, α 0.5) | 0.449 | 0.356 | 0.623 | 0.213 | 4.89 | 0.011 | 0.438 | 0.583 | 0.051 |
| **recommended (K1 1.2, B 0.4, α 0.6)** | **0.440** | 0.356 | 0.587 | 0.254 | 3.94 | 0.011 | 0.434 | 0.562 | 0.051 |

Searched-only figures for the recommended config: long MRR 0.469, R@8 0.625, precision 0.271; short MRR 0.462.
Unsearched stays at 0.062 in every config. That is the size limit, not ranking.

## Sweep (DECISION §9; each stage keeps the default unless the challenger beats it by > 0.01 dev long MRR)

1. **Stemming × guard.**

   | stemming | guard | MRR | R@8 | prec | shown | short empty |
   |---|---|---|---|---|---|---|
   | off | off | 0.395 | 0.546 | 0.199 | 4.58 | 0.100 |
   | off | on | 0.395 | 0.546 | 0.199 | 4.58 | 0.100 |
   | on | off | 0.428 | 0.596 | 0.202 | 4.87 | 0.051 |
   | on | on | 0.428 | 0.596 | 0.202 | 4.87 | 0.051 |

   - Stemming adds +0.033 MRR, so it is kept **on**.
   - **The guard is inert.** With it on or off, every per-query top-1 and MRR is identical on CUAD. It is also identical on the synthetic suite at every α tested (0.3–0.7), because the relative cut alone already drops the "period"-only filler pages. The default (on) is kept because it costs nothing, but nothing measured here supports it. It is a candidate for deletion in L6.
2. **α** (B 0.75).

   | α | MRR | R@8 | prec | shown |
   |---|---|---|---|---|
   | 0.3 | 0.4376 | 0.636 | 0.139 | 6.32 |
   | 0.4 | 0.437 | 0.631 | 0.166 | 5.71 |
   | 0.5 | 0.4279 | 0.596 | 0.202 | 4.87 |
   | 0.6 | 0.419 | 0.562 | 0.242 | 3.91 |
   | 0.7 | 0.403 | 0.507 | 0.278 | 2.91 |

   The best challenger, 0.3, beats 0.5 by +0.0097, which is not more than 0.01. **α stays 0.5.**
3. **K1 × B** (α 0.5; 16 cells; the full table is in the scratch sweep JSON).
   - **B = 0.4 is best in every K1 row.** The best cell is K1 1.2 / B 0.4 at MRR 0.4491, which is +0.021 over the default, so **B becomes 0.4**.
   - K1 values within the B 0.4 row span 0.4445–0.4491, all within 0.01, so **K1 stays 1.2**.
   - Re-checking α at B 0.4 gives 0.3: 0.4558, 0.4: 0.4537, 0.5: 0.4491, 0.55: 0.4448, 0.6: 0.4400, 0.65: 0.4328, 0.7: 0.4232. No α beats 0.5 by more than 0.01.
4. **W_HISTORY ∈ {0.3, 0.5, 1.0}** gives identical synthetic results at all three weights: every previous_query follow-up PASSES and chain-3 FAILS. The suite cannot tell the weights apart, because none of the follow-up questions has its own matching term. **W_HISTORY stays 0.5.**

## Acceptance (DECISION §9)

Columns: **strict** = K1 1.2 / B 0.4 / α 0.5; **rec.** = K1 1.2 / B 0.4 / α 0.6.

| threshold | strict | rec. |
|---|---|---|
| long MRR ≥ 0.356 | 0.449 PASS | 0.440 PASS |
| long precision ≥ 0.20 | 0.213 PASS | 0.254 PASS |
| long R@8 ≥ 0.526 | 0.623 PASS | 0.587 PASS |
| long shown ≤ 4.0 | **4.89 FAIL** | 3.94 PASS |
| long empty ≤ 0.035 | 0.011 PASS | 0.011 PASS |
| short MRR ≥ 0.30 | 0.438 PASS | 0.434 PASS |
| short empty ≤ 0.08 | 0.051 PASS | 0.051 PASS |
| short R@8 ≥ 0.472 | 0.583 PASS | 0.562 PASS |
| synthetic notice-period: page 6 only | PASS | PASS |
| synthetic fee: page 3 only | PASS | PASS |
| synthetic follow-ups, using previous_query (termination, fee, no-cue) | PASS ×3 | PASS ×3 |
| synthetic semantic-gap-2: NO_MATCH or gold only | **FAIL** [6, 8] | **FAIL** [6, 8] |
| dev wall time ≤ 16.4 s | 15.74 s PASS | 15.75 s PASS |
| byte-identical metrics on re-run | PASS | PASS |
| gate GREEN | not run by T (orchestrator owns it) | same |
| memory unit test < 8 MiB | not run by T (unit test 13, part of the gate) | same |
| followup-chain-3 (expected FAIL, documents M = 1) | FAIL as expected | FAIL as expected |

Notes on the acceptance lines:
- **semantic-gap-2.** Page 6 matches only on "may" ("Either party may terminate"), and page 8 matches on "end". Without the trap page, both semantic-gap cases return [6] only, again by accident ("may" or "parti"). This is lexical retrieval behaving as designed. DECISION §8 calls this case "the phase-2 motivation, not a phase-1 target", but §9 lists it as an acceptance line, so it is recorded as FAIL.
- **Wall time** is 2.2× the baseline measured today (7.25 s), with 0.65 s of headroom below the ceiling. Any further pass over the text would breach it.

## Recommended frozen parameters

**STEMMING = True, guard on (MIN_GUARD_PASSAGES 4, COMMON_SHARE 0.5), K1 = 1.2, B = 0.4, ALPHA = 0.6, W_HISTORY = 0.5.**

Why α = 0.6 and not the literal stage-2 winner of 0.5:
- With B = 0.4 frozen, α 0.6 scores 0.4400 MRR against 0.4491 for α 0.5. That gap of 0.009 is inside the 0.01 band that §9 treats as noise.
- §9's tie-break order is precision first, then fewer shown. α 0.6 wins both: precision 0.254 vs 0.213, and 3.94 shown vs 4.89.
- α 0.6 is the only setting that passes every CUAD threshold. α 0.5 fails "shown ≤ 4.0".
- The cost is R@8, 0.587 vs 0.623. That is still 4.1 points above the baseline.
- **This reads the noise band as a tie band. That is a departure from the literal sweep rule ("keep the default unless beaten"), and the orchestrator should approve it explicitly before freezing.** If it is not approved, the strict freeze is α 0.5 / B 0.4, and phase 1 then fails acceptance on "shown".

## Risk checks (DECISION §10)

- **Stemming-only top-1 changes** (stemming off vs on, guard on, defaults otherwise):
  - long: 185 queries changed; 51 newly correct at R@1, 32 newly wrong, 102 changed with no R@1 change;
  - short: 190 changed; 51 better, 12 worse.
  - Fifteen long-query examples for a human skim are below. Arrows give R@1 off → on; top-1 text is truncated.
    1. c0 Governing Law 0→1: "commodity according to the state of defect(s)…" → "21. Law application It will be governed by the law of…"
    2. c2 License Grant 0→1: "10.1.9 it has the exclusive right to promote…" → "8.1.1 Valeant Property. Dova acknowledges that Valeant owns or is licensed…"
    3. c3 Irrevocable Or Perpetual License 0→1: "2. Grant of Rights 2.1 Retention of EKR…" → "shall have the right during the Term to register domain names…"
    4. c7 Document Name 0→0: NO_MATCH → "9.7. Confidentiality. The material terms of this agreement…"
    5. c12 Anti-Assignment **1→0**: "16. Force Majeure…" → "24. Amendment. No amendment, alteration, modification…"
    6. c15 Expiration Date **1→0**: "b) The term of this Agreement will begin on the Effective Date…" → "a) [****] will be due to Excite on the Effective Date…"
    7. c17 Post-Termination Services 0→0: "22. Force Majeure…" → "15. Option to Produce Water…"
    8. c24 Agreement Date 0→0: "materials or workmanship starting from the date…" → "Exhibit C Development Plan April 28, 2016…"
    9. c25 License Grant 0→0: "2. Grant of License." → "(e) NOW THEREFORE, for and in consideration…"
    10. c28 Anti-Assignment **1→0**: "stock of Product that is of merchantable quality…" → "PROVIDED UNDER THIS AGREEMENT WILL NOT INFRINGE ANY PATENT…"
    11. c30 Affiliate License-Licensee 0→0: "(o) references to any Person include such Person's successors and assigns…" → "(a) The foregoing licenses shall be assignable… to any Affiliate"
    12. c36 Change Of Control 0→1: "to any right or remedy both parties may have…" → "(e) If control of either party shall pass from the present shareholders…"
    13. c39 Exclusivity 0→1: "…entitled to recover reasonable attorney's fees…" → "PARTIES" is Berkshire, and any affiliates of Berkshire…"
    14. c42 Parties 0→0: "Entire Agreement…" → "(c) Constellation shall be solely responsible…"
    15. c46 Competitive Restriction Exception 0→1: "than before one of the above-named courts…" → "…except as set forth in Section 2.4. 2.3 Non-Compete Covenant…"
  - The "worse" cases skimmed (c12, c28) are stems that merge with the query's generic words ("assign"/"assigns", "provid"), not legal false merges like general/generate. The net effect is clearly positive.
- **Cut second gold span.** 198 long questions have at least 2 gold spans (searched contracts). "Partial" means at least one gold span was shown and at least one was not.

  | config | partial | all spans shown | fewer spans than baseline | more spans than baseline |
  |---|---|---|---|---|
  | baseline | 58 | 58 | – | – |
  | defaults (α 0.5) | 61 | 64 | 33 | 41 |
  | α 0.6 (B 0.75) | 66 | 57 | 42 | 40 |
  | α 0.3 | 64 | 72 | 23 | 46 |

  The relative cut does drop later clauses: at α 0.6, 42 questions lose a span the baseline had shown, while 40 gain one.
- **Wall time.** Baseline 7.25 s; phase 1 15.7–15.9 s, which is within the ceiling but tight.

## New failure patterns (recommended config vs baseline)

Long queries that lost every relevant passage from the shown list: 36. Long queries that newly gained one: 61.

1. **Truncation removes lucky low-rank hits on metadata questions.** Parties falls from 0.10 to 0.05 MRR (n = 51). It accounts for 11 of the 36 lost questions; Agreement Date and Effective Date account for 3 each. The baseline showed 6–8 passages, and one of the lower ones often happened to contain "the Seller" or the preamble.
   - c0 Parties: the top-1 passage is still the governing-law clause; the rank-4 "The seller:" hit is now cut.
   - c29 Parties: the top-1 is now a logo-usage clause; the baseline's NOW THEREFORE preamble line, which had overlapped gold, is gone.

   Phase 1b (PREAMBLE_PRIOR) is the planned remedy. Document Name is unchanged at 0.05→0.06, and Agreement Date improves from 0.12 to 0.18.
2. **A rare but off-topic word wins the top slot, and the cut then removes the real clause.**
   - c32 Agreement Date: the top passage is an arbitration-award clause, matched on the date and "payable" vocabulary; the gold "dated as of …" line is cut.
   - c24 No-Solicit Of Customers: the top passage is "8.4. Marks…", matched on "solicit"-adjacent wording; gold is cut (n = 1).

   BM25's idf favours the rarest shared word even when that word is incidental.
3. **Follow-ups work for exactly one turn.** `followup-chain-3` ("And can that be waived?" after "And how long is that?", which itself came after the termination question) returns NO_MATCH. The previous question contributes only "long", which matches nothing. `prepend-all` passes, which shows what M > 1 or carrying the expanded query forward would buy. This is the documented M = 1 limit.
4. **Lexical semantic gaps remain** (semantic-gap and semantic-gap-2 return [6, 8]). An unrelated "end" on a filler page is shown next to the termination clause, and the termination clause is found only through incidental words ("may", "party").
5. **Unchanged:** the 2 over-limit contracts (6.2% of dev) are still never searched. Short "Rofr/Rofo/Rofn" stays empty, because no stem bridges an acronym.
