# Research appendix A: zero-cost model stack datasheet (research agent, 2026-09-30)

## Evidence quality

**Everything here is [S].** It comes from search-engine snippets only. WebFetch was egress-blocked for:

- ai.google.dev
- console.groq.com
- inference-docs.cerebras.ai
- openrouter.ai
- docs.github.com
- modelcontextprotocol.io
- huggingface.co

Every row must be checked on the vendor's own page before anyone relies on it.

## Free LLM API tiers

| Provider | Free models and limits | Trains on free-tier data? | Notes |
|---|---|---|---|
| Gemini API (unpaid) | ~20 RPD per Flash model; ~500 RPD on Flash-Lite; 2.5-series returns 404 for new keys | **Yes.** Used "to provide, improve, and develop Google products… machine learning technologies"; "human reviewers may read" | India supported. **Public text only** |
| Groq | Llama 3.3 70B / 3.1 8B left the free tier on 2026-08-16. Free now: gpt-oss-120b, gpt-oss-20b, a Qwen ~27B. 30 RPM, 1,000 RPD, 8K TPM, 200K TPD | **No.** "not permitted to use Inputs or Outputs for training"; abuse logs kept ≤30 days; ZDR can be switched on | US only. OpenAI-compatible |
| Cerebras | **No permanent free tier since 2026-07-21.** $5 one-time credit, card required | No training | Trial only |
| OpenRouter `:free` | 20 RPM; 50 RPD (1,000 after $10 of credit) | **Yes.** Logged "for feedback and training" by the model creator | Public text only |
| Mistral Experiment | ~1 rps, ~1B tokens/month | **Yes by default** (opt-out in Admin Console) | Evaluation only |
| GitHub Models | **Retired 2026-07-30** | — | — |
| Cloudflare Workers AI | 10,000 Neurons/day (~15–25 calls/day on an 8B model) | No training | — |
| HF Inference Providers | $0.10/month free credit | Downstream provider policy applies | — |
| NVIDIA build.nvidia.com | ~40 RPM | Trial terms: "no personal or confidential data", traffic logged | Not for production |
| Cohere trial | 1,000 calls/month | Used for R&D | **Not for commercial use** |
| Azure for Students | $100 per 12 months | **No.** Prompts "NOT used to improve… without explicit permission" | Global Standard may process outside India |

## Local open-weight models (8.6 GB laptop, or Kaggle's 30 GPU-hours/week)

**Licence OK for commercial use:**

- Qwen3 / Qwen3.5 small: Apache 2.0.
- Phi-4-mini: MIT.
- Llama 3.x: community licence.
- Ministral 3B/8B: Apache 2.0.
- Gemma 4: Apache 2.0 (UNVERIFIED).
- InLegalBERT: MIT.
- IndicTrans2 and IndicBERT v2: MIT.
- Sarvam 30B/105B: Apache 2.0. Too large for the laptop.

**Traps:**

- Qwen2.5-3B/72B: non-commercial.
- jina-embeddings-v3 and jina-reranker-v2: CC BY-NC.
- **Gemma 3's prohibited-use policy bans "unauthorized or unlicensed practice of any profession including… legal"**, so counsel must review it.
- InLegalLLaMA: one repo is under the Llama 2 licence.

## Embeddings and rerankers

| Option | Terms |
|---|---|
| bge-m3 | Permissive |
| bge-reranker-v2-m3 | Apache 2.0 |
| nomic-embed v1.5 | Apache 2.0 |
| multilingual-e5 | MIT |
| gte-Qwen2 | Apache 2.0 |
| Voyage free tokens (200M; 50M for voyage-law-2) | ToS grants a "perpetual… license to use customer content to train"; opting out may void the free tokens |

**Retrieval evidence:**

- **MLEB** (Isaacus, Oct 2025): NDCG@10 Kanon 2 86.03, Voyage 3 Large 85.71. India is not included.
- **LegalBench-RAG:** a general reranker underperformed no reranker.
- **No benchmark covers Indian corporate law.**

## Infrastructure

| Service | Free limit | Caveat |
|---|---|---|
| GitHub Actions | Unlimited on public repos; 2,000 min/month on private | Public cron disabled after 60 days idle. The ToS clause on activity "unrelated to the… software project" makes daily scraping **OPEN** |
| Cloudflare Workers | 100k req/day, 10 ms CPU, 5 crons | 10 ms is too little for PDF parsing |
| Neon | 0.5 GB | — |
| Supabase | 500 MB | Pauses after 1 week idle |
| R2 | 10 GB, free egress | — |

## MCP and CLI

**Current MCP spec: 2026-07-28.**

- Protocol sessions and the init handshake are removed.
- Streamable HTTP with OAuth 2.1.
- Servers MUST publish RFC 9728 Protected Resource Metadata; clients MUST send an RFC 8707 `resource`.
- Dynamic Client Registration is deprecated in favour of Client ID Metadata Documents.
- For stdio, credentials come from the environment.
- Python and TypeScript are Tier 1 SDKs.
- The reference postgres, github and sqlite servers are archived.

**CLIs:**

- Claude Code: no free plan.
- Gemini CLI: free personal path discontinued on 2026-06-18 [S, single source].
- Codex CLI: low cap on ChatGPT Free.
- aider and `llm` (Apache 2.0): bring your own model, including Ollama.

## Labelling tools

- **Argilla** (Apache 2.0): span questions, multiple annotators, Krippendorff's α documented for v1.x (v2 UNVERIFIED).
- **Label Studio Community** (Apache 2.0): review workflow and agreement metrics are Enterprise-only.
- **doccano:** MIT.

## Recommended zero-cost roles

| Role | Choice | May see |
|---|---|---|
| Client-document generator | Azure gpt-5-mini | CLIENT OK |
| Client-document fallback | Local Qwen3.5-4B / Phi-4-mini (Ollama) | CLIENT OK |
| Public text | Groq gpt-oss-120b | PUBLIC only |
| Public-text overflow | Gemini Flash-Lite, OpenRouter `:free` | PUBLIC only; both train |
| Retrieval | BM25 + bge-m3 locally | — |
| Reranker | bge-reranker-v2-m3, off until it wins on our own eval set | — |
| Scheduler | GitHub Actions on a private repo | — |
| Store | Neon + R2 | Public only |
| Labelling | Argilla, self-hosted | — |
| CLI | `llm` + aider | — |
