# 04: Models, free now and paid after funding, reached through API, MCP and CLI

**Evidence:** `.claude/loops/…_A_FREE_MODELS.md`. **Every row is [S]:** read in search
results, not on the vendor's page, as of 2026-09-30. Check a vendor's page before relying
on a limit, because these change monthly.

## 1. The rule that decides which model may see what

This is already enforced in code (`checker/public_only.py`, `gateway/models.py`):

- **Client or matter documents** go only to a host that is contractually barred from
  training on them, in an accepted region. Today that is **Azure**, and nothing else.
- **Public text** (statutes, Gazette notifications, published orders) may go to a free host.
- **A free tier that trains on inputs gets public text only**, and even then only after the
  PLAN_22 D3 amendment below.

## 2. The zero-cost stack

| Role | Model / host | Terms that matter | Limit | May see |
|---|---|---|---|---|
| Narrate over client documents | **Azure gpt-5-mini / llama-3-3-70b** (existing) | no training without permission | $100 per 12 months of student credit | CLIENT |
| Offline fallback for client documents | **Ollama + Qwen3.5-4B or Phi-4-mini** (Apache / MIT) | nothing leaves the machine | ~4B parameters on 8.6 GB; slow | CLIENT |
| Bulk public text (Gazette summaries, lexicon drafting) | **Groq gpt-oss-120b** | "not permitted to use Inputs or Outputs for training"; zero data retention available | 1,000 requests/day, 200K tokens/day; US | PUBLIC |
| Overflow for public text | Gemini Flash-Lite (~500 requests/day) | **trains, and humans may read** | per project | PUBLIC |
| Embeddings | **bge-m3** locally; BM25 stays the incumbent | permissive | CPU | CLIENT |
| Reranker | bge-reranker-v2-m3, **off** until it wins our own bake-off | LegalBench-RAG: a general reranker hurt | CPU | CLIENT |
| Indian languages | IndicTrans2, IndicBERT v2, InLegalBERT (all MIT) | — | local | CLIENT |
| Labelling UI | **Argilla**, self-hosted (Apache 2.0) | spans, multiple annotators | — | CLIENT |
| Database / storage | Neon (0.5 GB) + Cloudflare R2 (10 GB) | — | — | PUBLIC until a processing agreement is reviewed |
| Scheduler | GitHub Actions, private repo | whether daily scraping fits the ToS is **OPEN** | 2,000 min/month | PUBLIC |

**Gone or unsafe. Remove them from any plan that still names them:**

- GitHub Models (retired 2026-07-30).
- Groq's Llama 3.x models (off the free tier 2026-08-16).
- Cerebras' permanent free tier (ended 2026-07-21).
- The free Gemini CLI (discontinued 2026-06-18).
- Qwen2.5-3B/72B: non-commercial licence.
- jina v3 embeddings and reranker: CC BY-NC.
- **Gemma 3's prohibited-use policy names "unlicensed practice of… legal" professions.**
  Counsel must read it before Gemma 3 is used.

**Decision needed from the founder:** amend PLAN_22 D3 ("every model call inside Azure").
The proposed wording: *"Public text may additionally go to a host whose terms prohibit
training on inputs (today: Groq). Client text: Azure only."* Until then, Groq stays off.

## 3. How a free model is added. Five edits, no new framework

These come from the code audit, appendix D §B:

1. An adapter `checker/groq_model.py` with `as_text_model(origin=...)`. It calls
   `public_only.refuse_matter` and `verify_prompt` before any socket opens. Copy the shape
   of `azure_model.py`.
2. A row in `router._PREFERENCE`, **only after a bake-off win** (PLAN_22 D2: a
   non-overlapping 95% CI, and a person edits the table).
3. `router.providers_available()` gains the key check.
4. `gateway/models.SERVEABLE` plus a `serve()` branch, restricted to public-origin text.
5. A quota constant in `backend/budget.py`. **Also fix the known gap:** Azure calls are
   recorded at ₹0, so the ₹3,500 cap never binds (appendix D §A).

## 4. After funding: what changes, and what triggers it

| Role | Upgrade | Trigger |
|---|---|---|
| Client-document model | Azure pay-as-you-go, **regional deployment in India**; Claude via an India-resident route once confirmed live | first paid pilot, or a client's residency clause |
| Frontier reasoning | Claude Opus / GPT-class through the same router signature | a bake-off win on our own eval set, non-overlapping CI |
| Embeddings | voyage-law-2 or Kanon 2 **with the training opt-out** | local bge-m3 recall falls short on the Indian eval set |
| Reranker | paid reranker | it beats *no* reranker on our set |
| Local / private | a GPU box running Sarvam 30B or a Qwen 27B-class model | a client refuses cloud processing |
| Database | Neon Launch / Supabase Pro with backups | 0.5 GB reached, or backups needed |
| Labelling | Label Studio Enterprise or Prodigy | more than 2 annotators need formal review and agreement metrics |

**What never changes on upgrade:**

- The model still only phrases; code decides.
- Every clause is quoted byte-identically.
- The promotion gate runs.

A more capable model is a better narrator. It is never a new authority.

## 5. API, MCP and CLI: which to use for what

| Surface | Use | State |
|---|---|---|
| **REST `/v2/<verb>`** | The product contract: the web app, the Word add-in, a client's systems | BUILT, with hashed keys, RLS and audit |
| **MCP `themis.<verb>`** | Lawyers' AI assistants (Claude, and **Harvey via its bring-your-own-MCP feature**, see file 07) | stdio BUILT, local only, identity is a claim. **Hosted HTTP + OAuth 2.1 (MCP spec 2026-07-28, RFC 9728 metadata) is NOT built.** Offer no firm MCP access before it is |
| **CLI `placedon <verb>`** | engineers, cron, CI, the labelling scripts | BUILT |

**Two MCP issues to fix before any outside use** (appendix D §C):

- `themis.review_contract` is marked read-only but makes a **billed Azure call** from an
  unauthenticated stdio caller.
- `themis.ask` on MCP is the engine's `/v1` ask, not the verb.

Both are listed in file 08's first prompt.
