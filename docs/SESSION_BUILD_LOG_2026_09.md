# Build log — the 2026-09 session

Everything built in this session, organised by area, with the honest state of each:
**built & green**, **blocked on a human step**, or **blocked on a contract**. 46
commits, all pushed to branch `engine/entailment`, full test suite green throughout.

---

## 1. Statute acquisition & currency

| What | Module | State |
|---|---|---|
| Currency engine — obligation-level "is the law current" (CURRENT / NOT_YET_IN_FORCE / SUPERSEDED / UNACQUIRED) | `checker/currency.py` | **built** |
| G.S.R. 700(E) small-company thresholds — downloaded via a real browser (Composio), verified, **attested (reviewer NS)** | `scripts/register_gsr700e.py`, `corpus/rules/gsr_700e_2022.txt` | **built — thresholds now live** (₹4cr/₹40cr servable) |
| s.188 members'-approval threshold (Rule 15) — staged for review, refuses until attested | `checker/s188_threshold.py`, `scripts/register_s188_rule15.py` | **blocked on a human**: a reviewer must verify the per-type limbs (goods ~25% turnover etc., amended 2019) and run `--attest` |

## 2. Retrieval (RAG) — proven techniques, measured

| What | Module | State |
|---|---|---|
| Structural chunker — splits a section on its own units (sub-section/proviso/limb) | `checker/structural_chunk.py` | **built** |
| Path-addressable corpus index | `checker/structural_index.py` | **built** |
| Admission-gated structural retrieval | `checker/structural_retrieve.py` | **built** |
| Claim → chunk grounding via the E3→E6 entailment gate | `checker/ground_span.py` | **built** |
| **BM25 ranker** (Robertson & Zaragoza 2009), zero-dep — retrieval **0.20 → 0.62** | `checker/lexical_rank.py`, `checker/chunk_retrieval.py` | **built, shipped** |
| Cross-section retrieval — "which section governs this question" (**p@1 0.73, recall@5 0.93**) | `checker/corpus_retrieval.py` | **built** |
| Retrieval eval harnesses (within-section + 45-case cross-section) | `checker/retrieval_eval.py`, `checker/cross_section_eval.py` | **built** |
| Embedding dependency (Decision B) | — | **deferred by decision**: revisit only if the eval shows BM25 insufficient; add dense + RRF (Cormack 2009) + cross-encoder rerank (Nogueira & Cho 2019) only if a ≥8-pt held-out lift justifies it |

## 3. Deciders — grounded in corpus text, abstention-first

| Section | Module / row | What it decides | State |
|---|---|---|---|
| 8 periodic duties (s.96 AGM, s.173 board, s.149/149(3), s.137, s.92, s.135, s.2(85)) | `checker/obligations.py` | applicability + satisfaction, five states | **built** |
| s.185 loans to directors | `checker/s185.py` | PROHIBITED / conditional / exempt / not-caught | **built** |
| s.186 loan & investment ceiling | `checker/s186.py` | 60%/100% limit → special resolution | **built** |
| s.188 related-party transactions | `checker/s188.py` | Board / members' approval (threshold-gated) | **built** |
| s.184 director interest disclosure | `checker/s184.py` | disclose-and-abstain (>2% / partner / member) | **built** |
| s.180(1)(c) board borrowing limit | `checker/s180.py` | borrow beyond capital+reserves → special resolution | **built** |
| s.177 audit committee | `obligations.py` row | listed-public decided; class refuses (S-177-RULES) | **built (class blocked on rule)** |
| s.203 KMP | `obligations.py` row | entirely prescribed → refuses (S-203-RULES) | **built (blocked on rule)** |
| Corporate Entity Graph — the substrate all transaction deciders run on | `checker/entity_graph.py` | typed, dated relationships; tri-state (absence ≠ denial) | **built** |

## 4. The product surface

| What | Module | State |
|---|---|---|
| Pre-diligence evidence pack — dated, cited, gap-explicit, breaches-first | `checker/diligence_pack.py` | **built** |
| Shareable HTML memo (published artifact) | `claude.ai/code/artifact/92c0d823-…` | **built — ready to send to a CS** |
| JSON API — `POST /v1/compliance-pack`, `GET /v1/health` (validated, no model) | `checker/api.py`, `scripts/serve_api.py` | **built** |
| Gmail outreach draft (unsent, no recipient) | your Gmail Drafts | **built — you add a recipient and send** |

## 5. Live corporate data (the "Bloomberg" fusion, done legally)

| What | Module | State |
|---|---|---|
| Corporate-data seam — registry record → entity graph | `checker/corporate_data.py` | **built** |
| Licensed MCA21 aggregator adapter — refuses without a contracted API key; no scraping path | `checker/mca_aggregator.py` | **blocked on a contract**: sign one MCA-sanctioned aggregator (Surepass/FileSure-class), set `MCA_AGG_BASE_URL` + `MCA_AGG_API_KEY` |

## 6. Strategy & plans (grounded, not speculative)

- `docs/TECHNICAL_PLAN_EVIDENCED_2026_09.md` — competitor architecture from **primary sources fetched live** (Harvey/Legora/Spellbook — none trains a foundation model).
- `docs/MODEL_DEVELOPMENT_PLAN.md` — the model approach (rent + verify, not train); primary-source-verified.
- `docs/BLOOMBERG_FOR_INDIA_ANALYSIS.md` — the vision analysis + the three lines not to cross (no scraping, no LLM-as-truth, no scope-creep globe).
- `docs/BUILD_ROADMAP.md` — the master roadmap (from a 4-agent decomposition); critical path = get one CS to react.
- `docs/NEXT_MOVE_PLAN_2026_09_04.md` — the autonomous-loop runbook.

---

## The discipline that held throughout (non-negotiable)
- **Licensed access, never scraping** (MCA21 via contracted aggregator; case law via Indian Kanoon attribution; statute via human browser download).
- **A model never decides or cites** — it proposes; the E3→E6 gate disposes; a human attests thresholds.
- **Refuse on unacquired rules; DOES_NOT_APPLY and CANNOT_DETERMINE never collapse.**
- **Assurance memo, never an operative instrument. No foundation-model training.**
- **No new dependency without a measured reason.** (Still zero third-party deps.)

## The three steps only a human can take (in priority order)
1. **Send the memo to one Company Secretary** — the draft is in your Gmail; the gate on everything.
2. **Sign one MCA21 aggregator** — unlocks live corporate data through the whole engine.
3. **Attest the s.188 / audit-committee / KMP rules** after review — turns three refusals into determinate answers.

Everything a machine can build is built and green. The three above are yours.
