# Loop runbook — the Themis Intelligence Gateway

Pattern **`sequential`**, mode **`safe`**. Created 2026-09-24.
Implements the integration plan of 2026-09-23 (gateway / MCP / registries),
**minus the parts of it this repository already has** — see §0.

## 0. Pre-flight: what the plan proposes that already exists

Measured 2026-09-24, before any code was written. Building these again would have
been the expensive kind of mistake.

| Plan section | Proposal | Reality |
|---|---|---|
| §5 Model Registry | "formalize your providers" | **`checker/router.py` already is one.** Five providers wired: `anthropic_model`, `gemini_model`, `voyage_model`, `sarvam_model`, `ollama_runner` |
| §6 Model Router | route on capability/accuracy/cost/latency/context/sensitivity/licence | **Exists, and is deliberately narrower.** `route()` is a deterministic function of **four declared facts** — modality, consequence, volume, availability. Its docstring: *"A model that picks the model is one step from a model that picks the answer."* Widening it to eight soft criteria would undo that |
| §20 "put the provider behind an interface" | `ModelProvider` protocol | `model_adapter.py` + `router.Route` already do this. **"sarcasm" in the plan is `sarvam`** — the Indian model, wired as a `Candidate` |
| §5 capability declarations | JSON capability blocks | `router.CANDIDATES` carries `role / provider / model / incumbent / bakeoff / adopt_when`. A candidate is **adopted only when it beats the incumbent on a frozen eval** — L-15 applied to model choice. Stronger than a capability string |
| §18 prediction downstream | baselines → calibration → interval | `calibration_contract.py` (exact binomial ECE floors), `lattice.py`, L-15 |
| §11 Operation Model | requirement graph → tasks | Built 2026-09-23, `checker/operations.py`, live |

**Conclusion: the registry and router are not the gap.** The gap is §22 — *"the
first MCP server should actually be Themis itself"* — and §14, the policy gate.

## 1. The two questions this loop must keep answering

The founder asked them, and they are the design constraints, not commentary.

### "How does a lawyer actually use this?"

A lawyer never calls a tool. What reaches them is one sentence:

> *"G.S.R. 880(E) was published on 1 December 2025. It touches the small-company
> threshold, which two of your matters depend on. Nobody has read it yet. Here is
> the PDF, and here are the four things that must be established before anyone can
> say whether it changes anything."*

Everything in this loop exists to produce that sentence **and to refuse to produce
it when the evidence is not there.** If a build step does not move toward it, it is
not in this loop.

### "How does the orchestration really use it?"

Not as a chat partner. As a **world-state and evidence supplier** that can refuse:

```
orchestrator: themis.search_law(query, as_of)      -> spans + evidence state
orchestrator: themis.get_obligations(company)      -> rows, some ABSTAINED
orchestrator: themis.create_operation(instrument)  -> requirements, none answered
orchestrator: themis.submit_evidence(req, source)  -> ACCEPTED or REFUSED + why
```

The orchestrator decides *what work is required*. Themis supplies the world-state
and the evidence, and **says no** when a question reaches past what is held. The
harness verifies. No tool returns a legal conclusion, because no tool has one.

## 2. Scope of this loop

| In | Out |
|---|---|
| `checker/mcp/` — tool registry, policy gate, stdio MCP server | A new model registry (exists) |
| ~12 read-only tools over evidence, law, entity, operations | Any tool that writes to the corpus |
| A policy decision recorded for **every** call | Azure, Foundry, deployment |
| Offline tests for every tool and every refusal | Training any model |
| The lawyer sentence, rendered from real data | OpenAI integration (not wired; do not invent one) |

## 3. The rules this loop may not break

1. **Read-only.** No MCP tool may attest an instrument, admit a source, or write to
   the corpus. Attestation is human-gated (`admission.py`), and an agent that can
   attest is an agent that can manufacture the evidence the product sells.
2. **Refusals travel verbatim.** `out_of_scope`, `CANNOT_DETERMINE`,
   `LICENCE_UNVERIFIED`, `NOT_ESTABLISHED` reach the caller unsmoothed. A gateway
   that tidies a refusal into prose is the failure this repo exists to prevent.
3. **Every call is policy-decided and recorded** — actor, tenant, tool, action,
   purpose → ALLOW/DENY, deterministically.
4. **The rings hold.** `checker/mcp` is Ring 2. No Ring 0 decider may import it;
   `rings.py` enforces it by test.
5. **The gate is the contract.** `HARNESS_RESULT ... status=GREEN` or the step is
   reverted, not debugged forward.
6. **No new runtime dependency.** MCP is JSON-RPC over stdio; the standard library
   speaks it.

## 4. Queue

| # | Step | Done when |
|---|---|---|
| G1 | `checker/mcp/policy.py` — the decision, with a recorded reason | ALLOW/DENY tested both ways; a write action is DENIED by default |
| G2 | `checker/mcp/tools.py` — registry + JSON schemas over `api.handle()` | Every tool has a schema, a policy class, and a test |
| G3 | `checker/mcp/server.py` — stdio JSON-RPC: `initialize`, `tools/list`, `tools/call` | A real MCP handshake answered offline |
| G4 | `scripts/themis_mcp.py` — the entry point, `themis mcp serve` shape | Runs; a hand-written MCP session gets tool output |
| G5 | The lawyer sentence — a tool that renders it from a real instrument | Rendered from G.S.R. 880(E) with its refusals intact |
| G6 | Docs + register suites + commit each step | Gate GREEN at every commit |

## 5. Stop condition

Every queue row DONE or BLOCKED with evidence, gate GREEN, branch pushed. Or: two
consecutive iterations make no progress for reasons outside this session.

**Explicitly not a stop condition:** "the architecture is complete". It never is,
and this repository's documented failure mode is mistaking architecture for
progress. H-C — one practising Company Secretary reacting to the pack — has been
open since 4 September and is unaffected by everything in this loop.

## 6. Log

- 24-09 — pre-flight: §0 measured. Registry/router already exist and are stronger
  than the plan's version; scope narrowed to MCP + policy accordingly.
