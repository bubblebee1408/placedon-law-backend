# PLAN 23 — Orchestration

**Written 2026-09-30. A design document: it specifies what is to be built, and naming a
module here is not a claim that it exists.** Read before touching `agents/` or `gateway/`.

Every rule in §2 is derived from a finding in §1, and each finding carries its source.
Where the source is a vendor writing about its own system it is marked **vendor-reported**
and is not treated as independent evidence — the same rule PLAN_22 applies to Harvey's
figures.

---

## 1. Evidence → rules

### 1.1 Multi-agent gains are often minimal, and the failures are design failures

**MAST** — Cemri et al., *Why Do Multi-Agent LLM Systems Fail?*, arXiv:2503.13657, built
from **1,642 annotated traces**. Multi-agent gains over a single agent are often minimal,
and the failure taxonomy is dominated by **system design**, **inter-agent misalignment**
and **task verification** — not by model capability.

> **Rule.** **Code owns the plans and the hand-offs.** No model decides what runs next or
> what another step is told. **Every output is verified by code.** Every failure recorded
> is **tagged with its MAST category**, so the failure distribution here can be compared
> with the published one instead of guessed at.

### 1.2 Workflows and agents are different things

**Anthropic, "Building Effective Agents"** — *vendor*. Distinguishes **workflows** (LLM
steps on predefined code paths) from **agents** (the model directs its own process), and
names five patterns: **chaining**, **routing**, **parallelization**,
**orchestrator-workers**, **evaluator-optimizer**.

> **Rule.** **A workflow for every task whose shape is known** — which is nearly all of
> them here, because the intents are fixed. **Orchestrator-workers only where the subtasks
> are genuinely not known in advance.** An agent chosen for a task a workflow could do is
> an unbounded token budget bought for nothing.

### 1.3 Multi-agent systems are expensive, and tokens are the cost

**Anthropic multi-agent research system** — *vendor-reported*: roughly **15× the tokens**
of a chat interaction, with **token use explaining about 80% of performance variance**.

> **Rule.** **Cap the number of workers and the tokens per run**, both declared in the plan
> before it executes. **Citation checking is a separate step**, not something a worker is
> asked to do about its own output.

### 1.4 Models do not self-correct without external input

Huang et al., **ICLR 2024** — no *intrinsic* self-correction: without external feedback,
a model asked to revise does not reliably improve and frequently degrades.

> **Rule.** **Retry only on a reason supplied by an external verifier**, **at most once**,
> and the retry may only **narrow** — tighten the question, cut the evidence packet, drop a
> claim. A retry that widens is a second guess dressed as a correction.

### 1.5 Cascades cut cost, and the escalation signal must be external

**FrugalGPT**; **RouteLLM**, **ICLR 2025**. Routing a cheap model first and escalating
selectively preserves quality at a fraction of the cost.

> **Rule.** **Small model first; escalate only when the verifier rejects the output.**
> **Never escalate on the model's own confidence** — that is the same unreliable
> self-assessment §1.4 rules out, used as a spending decision.

### 1.6 Legal RAG hallucinates at a measured rate

Magesh et al., **JELS 2025**: **17–33% hallucination** in legal RAG systems. (The same
measurement PLAN_22 and AGENTS.md already forbid overclaiming against.)

> **Rule.** **Every sentence is traced to a verbatim span or it is dropped.** Already the
> behaviour of `checker/quoted_span.py`; this plan does not relax it anywhere.

### 1.7 Long contexts lose their middle

Liu et al., **TACL 2024**, *lost in the middle*: retrieval accuracy falls for material
placed in the middle of a long context.

> **Rule.** **Small evidence packets. The key passage first. Document order preserved**
> thereafter, so a reader checking a citation finds the text where the document puts it.

### 1.8 Reviewers under-check what a machine has already answered

Goddard et al., **JAMIA 2012**, automation bias.

> **Rule.** The review UI **forces the quote to be viewed** before a finding can be
> accepted. **No approve-all.** A control that lets a reviewer clear a page without reading
> it converts the human gate into a rubber stamp and records it as an approval.

### 1.9 Long-running work needs compensations, not just retries

**Sagas** — Garcia-Molina & Salem, **1987**.

> **Rule.** **A long run is steps plus compensations.** Every step that changes state
> declares how to undo it, so a run that dies half-way is recoverable rather than
> ambiguous.

### 1.10 One reasoning type per intent, with its own eval set

**LegalBench** (**162 tasks**) and **CUAD**.

> **Rule.** **One reasoning type and one evaluation set per intent.** An intent that mixes
> two cannot be measured, because a regression in one is invisible behind the other.

### 1.11 What this repository has already measured

- A **date filter runs before the model**, not after.
- **BM25 is the default** retrieval.
- The **entailment gate's precision is 0.83**.

> **Rule.** These are the starting points, and each is a number to be beaten with a
> measurement, not replaced with a preference.

---

## 2. The model — twelve layers

| # | Layer | What it does |
|---|---|---|
| **0** | **Gate** | Admission. Nothing enters without passing it. |
| **1** | **Intake** | **Fixed intents.** A request is one of a closed set or it is refused. |
| **2** | **Plan compiler** | Emits a **typed DAG** with **budgets** and **timeouts**. Code, not a model. |
| **3** | **Durable executor** | A **saga**. **Postgres queue with `SELECT … FOR UPDATE SKIP LOCKED`**. **Idempotent, resumable, cancellable.** |
| **4** | **Modes** | **(a)** workflow · **(b)** fan-out per document or clause · **(c)** bounded decomposition, **at most 4 sub-questions** · **(d)** watch |
| **5** | **Router** | The **verified cascade** of §1.5. |
| **6** | **L0 verify** | Verification **in code**. |
| **7** | **Critic** | May **flag or remove only**. **At most one narrowing correction** (§1.4). |
| **8** | **Synthesis** | **Order-preserving. Cited material only.** |
| **9** | **Human gate** | §1.8 applies to its UI. |
| **10** | **Record** | **Cost, region, the law versions used, the MAST tag.** |
| **11** | **Recall** | **A law changes → the past answers it affects are identified.** |

---

## 3. The rules, standing

1. **Code decides the plan, the status, the authority and the date.** Not a model, on any
   of the four.
2. **Every model output is verified by code** before anything downstream sees it.
3. **Escalate on verifier rejection only.**
4. **Every run is durable and priced.**
5. **Every human decision is stored as labelled data.** A reviewer's judgement is the
   scarcest input this system has, and discarding it is how a product stays at n=0 labels
   for a year.

---

## 4. Build steps

O1–O9, each with its done criterion. Order is as agreed; none is started by this document.

| Step | Work | Done when |
|---|---|---|
| **O1** | Finish `review_document`, `runs.approve`, and the playbook text | All three exist and are gated |
| **O2** | Durable executor v2 | A run survives a process restart and resumes |
| **O3** | Verified cascade | Escalation happens on verifier rejection and on nothing else |
| **O4** | Fan-out due diligence | A document set is reviewed per document within the declared worker cap |
| **O5** | Bounded research decomposition | No run exceeds 4 sub-questions |
| **O6** | Review queue with anti-automation-bias UI | The quote must be viewed; no approve-all control exists |
| **O7** | Watch → recall | A law change identifies the past answers it affects |
| **O8** | MAST failure tagging + weekly report | Every recorded failure carries a MAST category and the report is produced |
| **O9** | Answer cache keyed on law versions | A cached answer is invalidated by a change to a law version it used |

---

## 5. What this document does not claim

- **It is a design, not a status.** Layers 2–11 name work to be built. `agents/` and
  `gateway/` today implement a subset, and the gap is the point of §4.
- **Two of its eleven findings are vendor material** (§1.2, §1.3) and are marked. They are
  used for their patterns and their order of magnitude, not as independent evidence.
- **No figure here is an accuracy claim about this product.** The 17–33% in §1.6 is a
  measurement of *other* legal RAG systems and is the reason for a rule, not a benchmark
  this system has been run against.
