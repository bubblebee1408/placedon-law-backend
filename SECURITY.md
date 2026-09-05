# Security

How credentials, models and agents are handled here, and the properties that must hold.

## Reporting

Found something? Open a private security advisory on the repository rather than a public
issue.

## The two repositories, and why the split matters

| Repository | Visibility | Contents |
|---|---|---|
| `placedon-law-backend` (this one) | **PRIVATE** | The engine, the statute corpus, source artefacts |
| `Placedon-law-business-plan` | **PUBLIC** | Business plan, research record, measured results |

The public repository contains a **partial, stale snapshot** of `backend/` — 145 files
against this repository's 980, without the corpus. Do not treat it as the engine, and do
not sync this repository into it. Anything committed to a public repository is
world-readable and remains in history after deletion.

## Credentials

- **Never commit a secret.** `.env` and `.env.local` are gitignored; `.env.example` is
  the only environment file in version control and carries no real values.
- **Environment variables only.** No key is ever read from a file in the repository, a
  command-line argument, or a default constant.
- Current variables are documented in `.env.example`: `OLLAMA_BASE_URL`,
  `OLLAMA_MODEL`, `ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `LLM_MODE`, `MCA_AGG_BASE_URL`,
  `MCA_AGG_API_KEY`.
- If a key is ever exposed, **rotate it first** and clean history second. History
  rewriting does not un-publish a value that was already fetched.

## No implicit network access

Every module that could reach the network refuses to construct until configured:

- `checker/ollama_runner.py` has **no default host**. Without an explicit `base_url` or
  `OLLAMA_BASE_URL` it raises `NotConfigured`. A module that quietly talks to localhost
  is a module that surprises someone, and an outbound call is always a decision.
- `checker/mca_aggregator.py` has **no default endpoint and no scraping fallback**. An
  AST check rejects `playwright`, `selenium`, `bs4` and `requests` imports. Corporate
  data is licensed access only.
- `checker/dense_index.py` sets `HF_HUB_OFFLINE=1` and loads from the local cache; a
  missing model is a refusal, never a download mid-run.

Failures are **loud**. An unreachable model raises rather than falling back to a stub —
a legal answer produced by an unrequested substitute is worse than no answer.

## The model is the least trusted component

This is a security property, not only a quality one. A model that can assert a legal
conclusion is a model that can be prompt-injected into asserting one.

- `checker/model_adapter.py` applies **four refusals before any model call**, because a
  prompt is not a safety mechanism.
- Output citing an evidence id absent from the pack is **rejected, not repaired** — a
  citation to something absent is the signature of a fabricated one.
- Everything downstream **fails closed**: malformed output becomes
  `INSUFFICIENT_EVIDENCE`, never an exception and never an answer.
- `checker/annotation.py` **refuses to let a model adjudicate** a disagreement between
  human annotators, by name.
- No model sits in a decision path. Retrieval ranks, deciders decide, the E3→E6 gate
  verifies. The model narrates and extracts.

## Model calls are attested and reproducible

`checker/ollama_runner.py` records, for every call: model name, server-reported digest,
exact options, and SHA-256 of both prompt and response. `temperature=0` and a fixed seed
are **defaults, not options** — a system that answers the same question two ways cannot
be audited. Raising the temperature is allowed, and the attestation then records
`deterministic=False`, so a non-reproducible answer is always visibly one.

Given an answer, you can name which artefact produced it, from which prompt, under which
settings. Without that, "the AI said so" is unfalsifiable, and an unfalsifiable claim has
no place in an evidence pack.

## Data handling

- **No employee-level PII.** `CompanyProfile` is aggregate-only by design.
- `checker/entity_graph.py` deliberately stores **no names, addresses or DINs** — an id
  is a handle the caller maps to a real entity.
- Never obtain private minutes or confidential company documents.
- Permitted sources only: official legislation, the Gazette, public ICSI specimens,
  public listed-company disclosures, Indian Kanoon under its attribution terms.
- **Never bypass** a WAF, robots restriction, access control or source term. A platform
  one cease-and-desist from zero cannot sell risk reduction.

## For AI agents working in this repository

Read `CLAUDE.md` first; its rules bind you. In addition:

- Do not add a dependency without a stated reason.
- Do not commit `.env`, `*.pkl` caches, or `__pycache__`.
- Do not weaken a refusal to make a test pass. The refusals are the product.
- Do not publish a number you did not measure, and state the sample size on every metric.
- If you are about to make an outbound network call, stop and confirm it is configured
  deliberately rather than by a default.
