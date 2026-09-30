# Research: Harvey-style features for India — connectors, web research, drafting, review tables, Office

2026-09-30 · /loop phase R · branch `claude/harvey-india-platform-analysis-d2mmqi` at e8ed19e

The question: the user pasted a Harvey product walkthrough (Assistant, web search over a
complaint, editable drafts with citations and version history, Word/Outlook, playbooks, Vault
synced to iManage/SharePoint, review tables over thousands of documents, workflows) and asked
whether our architecture is built this way, and if not, what the plan is.

## Verdict

**Partly.** The layer that decides law is further along than anything in the walkthrough: typed
refusal per body of law (`checker/scope.py`, `checker/events.py`), a verified cascade
(`checker/model_cascade.py`), quote-level grounding, and a human gate that stores reasons. The
layers that *gather* and *produce* are thin or absent: there is no source-connector framework, no
web research, drafting is one template, there are no review tables, and there is no Office add-in.

**One finding outranks every feature.** The gold set's dev split shows the ask path answering
questions it should refuse — including off-topic ones. Widening what the system reads (web,
connectors) before that gate holds would widen what it answers wrongly.

## Confidence

MEDIUM. Repository evidence is measured. Harvey's figures are vendor statements, unverified.
Two external items are INCONCLUSIVE (below).

## Evidence

### In this repository (measured 2026-09-30)

| Finding | Where |
|---|---|
| Gold set, dev split, `code_hash=711cab80fd9a`: answered-correctly **9/13**, refused-rightly **5/17**, 0 human labels. Wrong refusals include "What is the capital of France?", "Best time to visit Goa in December?", an open-offer (SEBI SAST) question, a merger-control (Competition Act) question. `off_tax_return` came back with retrieved provisions (S212, S2), which the harness counts as the worse failure. Held-out split NOT run. | `PYTHONPATH=. python3 eval/goldset/run.py` |
| The ask path's refusal is built to avoid wrongly refusing HELD law, and accepts missed refusals as "safe, and weak". The gold set shows the missed-refusal rate is the larger problem now. | `checker/ask_scope.py:1-25` |
| Controlled drafting exists, one template (AGM notice). Approval is blocked while any slot is MODEL_SUGGESTION or UNKNOWN. No model wired in. | `checker/drafting.py:1-24`, `checker/provenance_slots.py` |
| Official hosts are a closed set that can only be narrowed, never widened by a caller. | `checker/provenance.py:61-106` |
| Untrusted text: clause universal, delimiter only on concatenation; never wrap the extract path. | `checker/prompt_safety.py`, CLAUDE.md |
| Robots and TLS enforced in the fetch path, fails closed. | `checker/robots.py` |
| Playbook review (NDA, 10 DRAFT rules). | `checker/playbook.py`, `playbooks/nda_v1.json` |
| Durable queue with SKIP LOCKED, idempotent steps, saga cancel — the substrate a review table needs. | `gateway/jobs.py`, `gateway/worker.py` |
| One verb table generates REST, MCP and CLI (D6). | `gateway/verbs.py` |
| CUAD held locally for evaluation. | `corpus/benchmark/cuad/` |

### Outside (checked 2026-09-30)

| Claim | Source | Quality |
|---|---|---|
| Harvey: 74,000 lawyers, 700 organisations, 58 countries, 25 h/month saved, 100+ model calls per prompt, review tables "96% accuracy that exceeds contract attorneys" | The walkthrough the user pasted | VENDOR, unverified. The 96% figure was **not found** in Harvey's published Contract Intelligence benchmark post, which describes 4,000+ data points and a human comparison: https://www.harvey.ai/blog/contract-intelligence-benchmark |
| Harvey 2026: Library unifies prompts, agents, playbooks; Assistant surfaces workflow and upload suggestions in-thread; Word-format editing in Assistant; Vault redesign | https://www.harvey.ai/blog/the-brief-april-2026 | VENDOR (product changelog) |
| Indian Kanoon has a paid, prepaid API: ₹500 free on sign-up; non-commercial ₹10,000/month after verification; search ≈ ₹5 per 100 results, full text +₹0.20 per record | https://api.indiankanoon.org/pricing/ | PRIMARY (vendor's own price page). API terms not yet read → OPEN |
| SCC Online and Manupatra: no public developer API | Third-party comparison blogs only | **INCONCLUSIVE.** Could not verify from the publishers. "Could not find" is not "does not exist" |
| MCA company master data is published on the Open Government Data platform (data.gov.in) | Third-party wrappers describe it; the OGD dataset itself not yet opened | SECONDARY → OPEN until the OGD resource is fetched and its licence read |
| Bing Search APIs retired 11 Aug 2025; Microsoft points to "Grounding with Bing Search" inside Azure AI Agents, which returns context to an agent, not a result list | https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement | PRIMARY |
| Brave Search API: free tier removed Feb 2026; metered at $5 per 1,000 requests with $5 monthly credit | https://api-dashboard.search.brave.com/documentation/pricing (and press coverage) | PRIMARY page listed; figures from coverage → confirm before any spend |
| Word JavaScript API exposes TrackedChange and Comment objects; no built-in granular diff — the add-in must compute its own diff and make targeted edits | https://learn.microsoft.com/en-us/javascript/api/word/word.trackedchange | PRIMARY |
| Generative search engines: only 51.5% of sentences fully supported by citations; 74.5% of citations support their sentence | Liu, Zhang, Liang, Findings of EMNLP 2023, https://arxiv.org/abs/2304.09848 | PEER-REVIEWED |
| Indirect prompt injection: instructions planted in retrieved data (web pages, documents) hijack LLM-integrated apps | Greshake et al., AISec 2023, https://arxiv.org/abs/2302.12173; OWASP LLM01:2025 | PEER-REVIEWED |
| Clause extraction on CUAD across 19 LLMs: best F1 0.644 (GPT-4.1 mini); open models often return a false "no related clause" | ContractEval, arXiv:2508.03080 | PREPRINT |

## Contradictions found

1. **Scope design vs runtime.** `scope.py` and CLAUDE.md say a DECLARED body gets an active
   refusal. The gold set shows the ask path answering SEBI SAST, Competition and DPDP
   practitioner questions. The design is right; the runtime does not enforce it on this path.
2. **"Permitted sources only" vs web research.** CLAUDE.md lists the permitted legal sources; the
   open web is not one. Resolution: web evidence may support **facts** (a news report, a company's
   own statement), labelled as web evidence, and can never support a statement of law or reach
   VERIFIED.
3. **"Models phrase, code decides" vs free-form drafts.** A client email is prose. Resolution
   already exists in `provenance_slots.py`: every sentence that states law must bind to a verified
   claim and carry its citation; everything else is MODEL_SUGGESTION, visibly marked, and blocks
   approval until a person edits or accepts it.
4. **Brand tokens vs the user's direction.** AGENTS.md (frontend) mandates a gold accent and cool
   grey `#5B6472` for abstention. On 2026-09-30 the user directed a black primary button and no
   blue-toned grey. That is the owner's decision; AGENTS.md must change in the same commit as the
   tokens, or the next agent will "fix" it back.
5. **Harvey's 96%** appears in marketing copy but not in the benchmark post found. Not repeated as fact.

## Options

| | Complexity | Cost | Risk | User value |
|---|---|---|---|---|
| **A. Parity sprint** — build connectors, web research, drafting, review tables and Office in parallel | High | High (several paid APIs at once) | High: widens what the system reads while refusals fail 12/17 | High on paper, low in trust |
| **B. Trust-first sequence** — fix the refusal gate, then a tiered source framework, then web research, drafting with versions, review tables, Word | Medium | Rises one dependency at a time, each escalated | Low: every step is gated by a measured check | High, and defensible to a lawyer |
| **C. Integrate only** — expose the engine as an MCP server inside other platforms, build none of this | Low | Low | Low | Low on its own; keep as a side channel (PLAN_22 D7) |

## Recommendation

**B.** Every Harvey feature the user listed is reachable on this architecture, and the queue,
verb table, grounding and slot provenance mean most of it is extension, not new foundations. But the
order is not negotiable: refusals first, because each later step increases what the system reads.

## Open questions

- Indian Kanoon API terms (caching, attribution, commercial use) — read before H1 ships.
- Web search vendor — a new paid dependency; escalate (Brave, Azure "Grounding with Bing", others).
- SCC Online / Manupatra enterprise access — ask the publishers directly.
- iManage / NetDocuments partner access — unverified; SharePoint via Microsoft Graph needs the
  customer's Entra app consent.
- Client documents are personal data in many cases. DPDP is out of *product* scope, but our own
  processing of client data is a separate legal question for counsel — OPEN.
- `RESEARCH_LOG.md`, which the /loop track guard reads, does not exist in this repository; this
  file carries the evidence instead. [TRACK: product]
