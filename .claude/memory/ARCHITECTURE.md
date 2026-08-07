# System Architecture

> Corrections applied from `SPEC_ERRATA.md`. Where this disagrees with `MASTER_SPEC.md`, this wins.

## Shipped today
| Layer | Choice | Note |
|---|---|---|
| Checker UI | Server-rendered HTML, inline CSS, **no build step** | Live, ~0.6s, one file. See errata E-10 before replacing with Next.js. |
| API | FastAPI + Pydantic v2 | `checker/app.py` |
| Decision engine | **Pure Python, no LLM** | `applicability.py` (10/10), `jurisdiction.py` (11/11) |
| Jurisdiction | district > state > national | `jurisdiction.py` — district fallback is *refusable* (errata E-8) |
| Corpus | JSON on disk | `corpus/provisions/posh_act_2013.json`, 30/30 sections, all `verified_by: null` |
| Ingest | pdfplumber + regex + TOC oracle | `scripts/ingest_posh.py` |
| Hosting | Vercel serverless | `api/index.py` — the rewrite replaces the path, so the original rides in `?__p=` |

## Not built yet
| Layer | Choice | When |
|---|---|---|
| LLM | **`claude-haiku-4-5`** for serving (~₹0.97/answer); `claude-opus-5` via Batch API for the proof artifact | C-3. **Never `claude-3-5-sonnet` — retired 2025-10-28, 404s.** |
| LLM access | One file: `backend/services/llm.py`. Nothing else calls Anthropic. | C-3 |
| Budget guard | `backend/budget.py` — checked before every call | Built |
| Database | Supabase Postgres | When JSON stops being enough. Not yet. |
| Retrieval | SQL by topic + citation | 30 sections. **Vector search is V1.5** (errata E-6). |
| Email / WhatsApp | Resend / Twilio | V1.5 |

## Layer rule
**Engine makes no external calls.** Pure Python, deterministic, testable without a network.
**Services owns every external API.** One wrapper per provider.
A model in the applicability decision path is rejected by `architect` regardless of how much
simpler it looks.

## Deterministic-first
If `applicability.py` plus a template produces the output, that is the design. ₹0 and no failure
mode. The Company Health Scan makes **no LLM call at all** — that is why the free tier has no
marginal cost, which is a structural advantage over any incumbent.
