# Agent architecture plan

Status: **PROPOSAL. Nothing here is built.** No code was written for this document.
Written 2026-08-31 against the repository as it stands at that date.

Every number in §5 is reproducible with `python3 backend/budget.py` or the one-liners quoted
beside it. Every claim about existing behaviour names the file and function it came from. Places
where I am guessing are marked **GUESS** or **UNVERIFIED** inline and collected in §10.

**No web access was available in the session that produced this.** Model identifiers, provider
pricing and competitor capabilities are therefore taken from files already in the repo
(`backend/budget.py`, `docs/PROVIDER_DECISION.md`) or from model knowledge, and are marked
UNVERIFIED. `docs/PROVIDER_DECISION.md` §7 is explicit that identifiers rot in months; check them
against the registry before a line of code is written.

---

## 0. Disambiguation: two things are called "agents" in this repo

`.claude/agents/` holds **build-time** subagent definitions — `cost-governor`, `legal-verifier`,
`benchmark-engineer`. Those are development tooling. They are not the product and they never touch
a user's matter.

This document is about **runtime** agents: the steps the product executes when a user asks a legal
question or uploads a document. The two must not share a name in code. Proposal: runtime steps are
called **steps**, not agents, and live in `checker/`. The word "agent" stays reserved for
`.claude/agents/`.

The rest of this document uses "role" for the conceptual decomposition the task asked for and
"step" for the thing that actually executes.

---

## 1. The thesis

> The model may propose. The system must verify. The reviewer decides.

Most multi-agent legal systems put a language model in every box and then add a language model
"critic" on top. That critic is drawn from the same distribution as the thing it is critiquing, so
it shares its failure modes — `docs/MODEL_PLAN.md` already records the refusal: *"LLM-as-judge is
unsafe here. Magesh et al. refused it outright; Cymbler et al. used deterministic regex nuggets
because an LLM judge inherits the same recency bias it is meant to detect."*

This repo has something almost nobody else has: **a verifier cascade that cannot hallucinate its
own critique.** E3/E4/E5/E6 (`checker/entail_baseline.py`, `entail_binding.py`, `entail_role.py`,
`entail_qualifier.py`) are regex, sentence segmentation and type reasoning. They are readable,
testable, explainable to a regulator, cost ₹0 to run, and are gated by
`checker/metric_policy.evaluate_gate` on four axes at once.

Measured today (`PYTHONPATH=. python3 checker/metric_policy.py`, 67 strict rows,
20 ENTAILED / 47 NOT_ENTAILED, majority baseline 0.70 accuracy at F1 0.00):

```
RELEASE GATE — PASS
  false accepts   :      2   ceiling 10
  F1              :   0.58   floor   0.40
  abstention      :   0.00   cap     0.25
  per bucket:
    dropped_qualifier     n=9    FA=0    F1=0.00
    paraphrase            n=15   FA=0    F1=0.64
    wrong_binding         n=43   FA=2    F1=0.44
```

**The design rule that follows: the deterministic spine owns every decision with legal
consequence. Language models are permitted only at the two ends — reading unstructured input, and
writing prose over an already-decided result — and both ends are verified by exact-match against
something that already exists.**

Two of six roles may call a model. Four may not, ever.

---

## 2. Agent decomposition

### 2.1 The table

| # | Role | LLM or deterministic | Existing home | What stops it being wrong |
|---|---|---|---|---|
| 1 | **Planner / orchestrator** | **Deterministic. Never an LLM.** | new `checker/orchestrator.py`; routing logic exists in `checker/ask_engine.is_applicability_question()` | A static task graph per matter type. There is no step where a model chooses the next step. |
| 2 | **Retriever** | **Deterministic. Never an LLM.** | `checker/retrieve.retrieve()`, `legal_retrieval.resolve()`, `text_search.search()`, `section_index.section_by_number()` | The rule already enforced in `retrieve.py`: *a query that names a provision is answered by the resolver or not at all.* |
| 3 | **Extractor** (document → typed facts) | **LLM permitted.** Tier: cheapest. | new `checker/extract_adapter.py`; target type is `checker/matter.Matter` | Every extracted value must be a **verbatim span present in the uploaded document**, checked by exact substring match. Not present → slot becomes `UNKNOWN` (`checker/provenance_slots.py`). |
| 4 | **Analyst** (applicability, dates, arithmetic) | **Deterministic. Never an LLM.** | `applicability.evaluate()`, `checker/agm.py`, `checker/s173_slice.review()`, `checker/s96_slice.card()`, `checker/as_of.py`, `checker/commencement.py` | `applicability.py` docstring: *"This is the component that decides whether a legal provision applies to a company — NEVER the LLM."* `docs/MODEL_PLAN.md`: *"A model here is a regression."* |
| 5 | **Critic / verifier** | **Deterministic. Never an LLM.** | `claim_verifier.verify_all()` then E6→E5→E4→E3, gated by `metric_policy` | See §3. This is the asset. Putting a model here would destroy it. |
| 6 | **Formatter / narrator** | **Two paths.** Documents: deterministic slot-fill (`checker/drafting.py`). Prose narration: **LLM permitted**, cheapest tier. | `checker/drafting.draft_agm_notice()`, `checker/provenance_slots.py` | Model prose is labelled `MODEL_SUGGESTION`, and `drafting.approve()` **raises** on any `MODEL_SUGGESTION` or `UNKNOWN` slot. Structural, not a warning. |
| 7 | **Reviewer** (the role the six-box taxonomy omits) | **Human. Never automated.** | `checker/review_queue.py`, `review_record.append()`, `promotion_preview.build()`, `checker/admission.py` | Nothing in `review_record.py` can reach a gold label; promotion is a separate explicit step. |

### 2.2 Why the planner is not a model, stated properly

An LLM planner decides which law to look at. Deciding which law applies **is the product**. A
planner that picks "check s.173" for an AGM question has made a legal error that no downstream
verifier catches, because every claim it then produces about s.173 will verify perfectly against
s.173. The cascade checks *claim against cited span*; it has no opinion on whether that was the
right span to fetch.

So the plan is data, not generation. Concretely: a dict of matter type → ordered step list, e.g.

```
"AGM_DEADLINE"      -> [fill_matter, resolve_s96, reconstruct_as_of, compute_deadline, card, narrate?]
"BOARD_MEETING_GAP" -> [fill_matter, resolve_s173, classify_company, review_gaps, card, narrate?]
```

Both already exist as vertical slices (`s96_slice.py`, `s173_slice.py`). The orchestrator's job is
to run them, log each step, and stop on the first abstention. It is a state machine, roughly 150
lines, ₹0 to run, and self-testing in the repo's `[PASS]`/`[FAIL]` style.

An unknown matter type is a refusal, not a fallback to "let the model figure it out."

### 2.3 Why the retriever is not a model

`checker/retrieve.py`'s docstring records the exact bug that embeddings would make worse:

> `"rule 4"` → legal_retrieval abstains (no Rules corpus exists) → text_search falls through and
> returns Act s.398, s.469 → the pack marks them usable

Act-versus-Rule collision. `s.173` and `rule 173` are lexically near-identical and would be
**embedding neighbours**, which is precisely the failure a dense retriever cannot distinguish and
an exact resolver refuses outright. See §6 for the arithmetic.

### 2.4 The extractor is the one genuine LLM job

Reading a scanned board notice and producing `{meeting_date, company_class, previous_agm_date}` is
unstructured-input parsing. Regex over arbitrary firm templates is a losing game, and every
template a firm customises is a private fork (CLAUDE.md, "The wedge").

What makes it safe is that **extraction output is checkable against a source we hold**:

1. The model returns, per slot, a value **and the verbatim substring of the document it came
   from**, with a character offset.
2. `extract_adapter` asserts the quoted substring occurs at that offset in `document_text`. Not
   fuzzy — exact, after whitespace normalisation only.
3. Slot value must be derivable from the quoted span by a deterministic parser
   (`matter._parse_date` already exists for dates).
4. Any failure → slot is `UNKNOWN`, never guessed. `matter.Matter` construction then refuses a
   contradictory or half-filled matter, and `missing_for_agm()` names the gap to the user
   **before** any computation is attempted.

This is the same trick the whole repo runs on: the model proposes a location in evidence we
already hold, and code checks the location. It cannot invent a date, because a date not in the
document has no span.

### 2.5 The narrator is optional and is never load-bearing

`checker/drafting.py` and `provenance_slots.py` already produce a filed-quality AGM notice with
zero model involvement, because every value is a typed slot with a provenance label. The only
thing a model adds is readable prose around a card that has already been decided.

That prose enters as `MODEL_SUGGESTION`, which blocks approval by construction. If the budget is
exhausted the narrator is simply skipped and the user sees the card — a strictly less pleasant,
equally correct answer. **The product must be complete and correct with the narrator disabled.**
That is the test.

---

## 3. Where E3–E6 and the metric_policy gate sit

### 3.1 The per-answer path (runtime)

```
retrieve.retrieve(query, mode=MODE_MODEL)      deterministic
      -> EvidencePack (closed world; admission.py already filtered it)
model_adapter.run(task, model)                 THE ONLY LLM CALL IN THIS PATH
      -> 3 pre-call refusals, then parse, then 3 post-parse downgrades
      -> ModelResult(claims=...)  every claim cites an id that IS in the pack
claim_verifier.verify_all(claims, pack)        deterministic, cheap, necessary-condition triage
      -> INVALID_CITATION / UNSUPPORTED / PARTIAL / LEXICAL_CANDIDATE
      -> tops out at LEXICAL_CANDIDATE; establishes_support() is False for it
FOR EACH surviving claim:
    resolve claim.evidence_ids -> the served source span
    cascade(source_span, claim.text)           E6 -> E5 -> E4 -> E3   deterministic
      -> accept | refuse
grounding_policy state assignment              deterministic ceiling, see 3.3
attribution.attribute(...)                     names WHICH stage failed
      -> RETRIEVED / ADMITTED / SERVED / CITED / GROUNDED
```

The cascade order is fixed and is **not** a tunable:

```
E6 (GATE)       runs first, may only ever REFUSE, never accept
E5 (SPECIALIST) role/type compatibility; abstains on most claims
E4 (SPECIALIST) quantity-to-obligation binding; abstains where no binding extracts
E3 (GENERAL)    lexical/date/number/quote baseline; total function, always answers
```

`metric_policy.MODULE_ROLES` records those roles, and `metric_policy._test()` proves the gate
property that makes the order safe: *"the E6 gate only ever converts an accept into a refusal."*

### 3.2 BLOCKER — the cascade exists only inside a test

`grep -rn "def cascade" checker/*.py` returns exactly one hit: **`checker/metric_policy.py:181`,
inside `_test()`.**

There is no importable object that both the release gate and the runtime can share. If the runtime
re-implements the order, the gate is scoring a different predictor than the one serving users, and
the four-axis guarantee evaporates silently. This is the single highest-priority prerequisite in
this plan and it is Stage 0 (§7).

Fix: lift it into `checker/cascade.py` exposing

```
judge(source_span: str, claim: str) -> CascadeVerdict   # .accepted, .decided_by, .trail
predict(row) -> bool                                    # the shape metric_policy.evaluate_gate wants
```

and have `metric_policy._test()` import it rather than define it. The gate then scores production
code by construction.

### 3.3 What an accept from the cascade is allowed to mean

`checker/grounding_policy.py` is explicit: *"E3's acceptance is `CLAIM_PARTIALLY_MATCHED`. Calling
that GROUNDED is the exact error this module exists to prevent."*

Proposed mapping, to be enforced in `cascade.py` and asserted in its self-test:

| Cascade outcome | Grounding state | May be served as support? |
|---|---|---|
| E6 refused | (claim dropped) | no |
| E5 or E4 refused | (claim dropped) | no |
| E3 accepted, E4/E5 abstained | `CLAIM_PARTIALLY_MATCHED` | **no** — shown as "terms match, entailment not established" |
| E4 or E5 accepted **and** E6 found no dropped qualifier | `CLAIM_QUALIFIERS_CHECKED` | yes, labelled, never as "verified" |
| `CLAIM_ENTAILED` | reserved | nothing in this repo can produce it today |
| `HUMAN_APPROVED` | via `review_queue` | yes |

Note the consequence, and it is subtle enough to state plainly: **the cascade cannot abstain**,
because E3 is a total function (abstention 0.00 in the gate output above). Verifier-level
uncertainty therefore does not surface as "I don't know" — it surfaces as a **ceiling on the
grounding state**. A weak E3-only accept never reaches a state that permits serving. That is the
design, but anyone reading "abstention 0.00" as "the verifier is always sure" has misread it, and
the code should carry that comment.

### 3.4 Where `metric_policy` sits — and where it does not

`metric_policy.evaluate_gate` **is not in the request path.** It scores a *configuration* against
a *frozen set of 67 rows*. It cannot say anything about one live answer.

- **CI / pre-release:** `evaluate_gate(cascade.predict, rows, eval_taxonomy.bucket_of)` must PASS
  before any change to a verifier module, any new step, and any change of model or
  `PROMPT_VERSION`. A model change is a configuration change and re-runs the gate.
- **Per-answer:** the runtime analogue is `attribution.attribute()`, which names the failing stage
  (RETRIEVED / ADMITTED / SERVED / CITED / GROUNDED) and carries `system_behaved_correctly` so a
  correct refusal is never scored as a failure.

Two additional gate obligations this plan adds:

1. **Every LLM step gets its own gate row set before it ships.** A step with no fixture set cannot
   ship — including the extractor, which needs its own set (documents with known field values,
   including documents where the field is genuinely absent).
2. **`dropped_qualifier` F1 is 0.00 at n=9.** E6 refuses correctly (FA=0) but never accepts, so
   that bucket has zero true positives. It is the largest unserved gap in the verifier and the
   highest-value deterministic work available. It should be fixed before any trained model is
   contemplated (§9.4).

Stale-comment flag: `metric_policy.py`'s header says *"cascade currently 4 [false accepts] ... F1
0.49"*. Measured today it is **FA 2, F1 0.58**. The comment drifted. Fix in Stage 0.

---

## 4. What `model_adapter.py` must change to

### 4.1 The three pre-call refusals are load-bearing and do not change

From `run()`:

1. `pack.mode != "MODEL"` → `AdapterError`. A REVIEW pack never reaches a model.
2. `not evidence_ids(pack)` → `INSUFFICIENT_EVIDENCE`, **no model call at all**.
3. A claim citing an id not in `allowed` → rejected in `_parse`, never repaired.

Plus the post-parse downgrades (`DECISION_DOWNGRADED`, `DECISION_WITHOUT_CLAIMS`, the
duplicate-`claim_id` rule that rejects **every** copy so emission order cannot decide a legal
conclusion).

**None of these may be relaxed for multi-step work.** The temptation multi-step creates is a
shared "conversation" across steps, which turns `allowed` into a union across packs. That is the
mechanism by which step 3 cites step 1's evidence for a claim step 1 never made.

### 4.2 The core architectural decision: `run()` stays single-shot and stateless

Multi-step is achieved by the **orchestrator calling `run()` N times with N different
`ModelTask`s and N different packs**. There is no conversation object, no message history, no
tool-calling loop inside the adapter.

Consequences, all good:

- `allowed = evidence_ids(pack)` is re-derived per call from that call's own pack. Refusal 3 holds
  per step, exactly as it does today.
- Each step is independently cacheable and independently replayable.
- A step failure is a step failure, not a corrupted 12-turn history.

**Hard rule to write into the docstring:** a prior step's output may enter a later prompt **only
as typed facts** (a `Matter`, a computed date with its working), **never as evidence ids and never
as free prose**. The evidence-id namespace is permanently closed to `pack.usable` keys. A step's
claim is not evidence for the next step.

### 4.3 Concrete changes

**(a) `TASK_SPECS` registry, and a fourth pre-call refusal.**
`ModelTask.task_type` is a free string today and nothing reads it. Introduce
`TASK_SPECS: dict[str, TaskSpec]` mapping task type → (instruction block, permitted decisions,
permitted claim types, `prompt_version`). `run()` refuses an unregistered `task_type` **before**
building a prompt. This makes multi-step legible: the set of things a model may be asked is a
finite, reviewable list in one file, not whatever an orchestrator chose to type.

**(b) Wire the budget guard. This is a real, current gap.**
`grep -rn "budget" checker/*.py` returns nothing. `backend/budget.BudgetTracker.can_make_call()`
exists, is tested, enforces ₹3,500/month and ₹116.67/day, and **is not consulted by the one place
an LLM may be called.** Add as pre-call refusal #0, before the mode check:

```
verdict = tracker.can_make_call(model=..., input_tokens=..., output_tokens=...)
if not verdict.allowed:
    return ModelResult(decision=INSUFFICIENT_EVIDENCE,
                       warnings=(f"BUDGET_EXHAUSTED: {verdict.reason}",), ...)
```

Fail-closed: a corrupt ledger already yields `offline` mode and refuses to spend. Abstention with
a stated reason is the correct behaviour; a silent downgrade to a cheaper model is not.

**(c) `ModelResult` carries its own cost.**
Add `input_tokens`, `output_tokens`, `cost_inr`, `task_type`, `step_id`. Per-matter cost is then
summed from the step log, measured rather than estimated. Today nothing records what a call cost.

**(d) A `ModelClient` protocol alongside the bare callable.**
`run(task, model=<callable>)` means the adapter cannot know which model ran or what it cost —
`model_name` is passed in as a string and trusted. Introduce:

```
class ModelClient(Protocol):
    name: str
    tier: str                 # "cheap" | "standard"
    def count_tokens(self, prompt: str) -> int: ...
    def __call__(self, prompt: str) -> tuple[str, int, int]: ...   # text, in_tok, out_tok
```

Keep `Callable[[str], str]` accepted for `StubModel`, which must stay — its docstring is right
that the contract should be provable without spending money, and it *"is not a simulation of model
quality and must never be scored as one."*

**(e) A `TIER_FOR_TASK` map, not a router.**
Model choice is a **static per-task-type constant**, not a runtime decision. Anything that looks
at the input and picks a model is a router, a router is a policy, and a policy that changes which
model answers changes the configuration the release gate scored. Constants; change them in a
commit; re-run the gate.

**(f) What does NOT go into `model_adapter.py`: extraction.**
The extractor's evidence is the **uploaded document**, not the Act. Its pack is legitimately
empty, so pre-call refusal 2 would fire and abstain — correctly, by `run()`'s rules. Do not add a
DOCUMENT pack mode and do not weaken refusal 2 to accommodate it.

Instead: a separate `checker/extract_adapter.py` with its own three refusals, shaped the same way:

1. no `document_text`, or the document has no admitted hash → refuse before the call;
2. output slot with no quoted span → rejected, not repaired;
3. quoted span not present verbatim in `document_text` → rejected — *a quotation from a document
   that does not contain it is the signature of a fabricated one*, the exact parallel of refusal 3.

Two adapters, two closed worlds, neither weakened to fit the other.

---

## 5. Model routing and cost arithmetic

### 5.1 Ground truth

From `backend/budget.py`: monthly cap **₹3,500**, derived daily cap **₹116.67**, USD/INR **95.23**
(6 Aug 2026). Anthropic list pricing, USD per million tokens, as pinned in `PRICING`:
haiku-4-5 (1.00 / 5.00), sonnet-5 (3.00 / 15.00), opus-5 (5.00 / 25.00). Batch API is 50% off and
is modelled. **List prices are deliberate**: *"a budget guard must only ever be wrong in the
expensive direction."*

Measured prompt size, not estimated — `build_prompt()` on a real one-provision MODEL pack:

```
s.173 pack: 7,238 chars  ≈ 1,809 tokens (chars/4, APPROX)   1 usable provision
s.96  pack: 6,285 chars  ≈ 1,571 tokens (chars/4, APPROX)   1 usable provision
```

`budget.py`'s 6,700-token default corresponds to a three-provision pack. Single-provision packs —
which is what the exact resolver returns for a named-provision query — are **~3.7× cheaper** than
the budget module assumes.

### 5.2 Per-call cost, reproducible

`PYTHONPATH=. python3 -c "from backend.budget import cost_inr; print(cost_inr('claude-haiku-4-5', 1800, 700))"`

| Step | in / out | haiku-4-5 | sonnet-5 | opus-5 |
|---|---|---|---|---|
| classify / route (if ever needed) | 600 / 120 | ₹0.1143 | ₹0.3428 | ₹0.5714 |
| **extractor** (document → slots) | 2000 / 400 | **₹0.3809** | ₹1.1428 | ₹1.9046 |
| **answer** (1-provision pack, measured) | 1800 / 700 | **₹0.5047** | ₹1.5142 | ₹2.5236 |
| answer (3-provision pack) | 6700 / 700 | ₹0.9713 | ₹2.9140 | ₹4.8567 |
| **narrator** (card → prose) | 2500 / 600 | **₹0.5238** | ₹1.5713 | ₹2.6188 |

Batch API halves every figure. Monthly volume at the ₹3,500 cap: 6,934 one-provision haiku answers
vs 720 three-provision opus answers — a **9.6×** difference in how many users the same budget
serves.

### 5.3 The routing decision

| Step | Model | Why |
|---|---|---|
| Planner, retriever, analyst, verifier | **none** | ₹0.00. Deterministic. |
| Extractor | **haiku tier (cheap)** | Span-copying under exact-match verification. Obedience, not reasoning — `docs/PROVIDER_DECISION.md` §4: *"You don't need the smartest model. You need obedience, not creativity."* A stronger model does not copy a substring more accurately. |
| Answer step | **haiku tier (cheap)**, standard tier only if the gate demonstrably improves | `PROVIDER_DECISION.md`: *"model choice is a cost lever, not a correctness lever"* — because `applicability.py` decides and the cascade rejects. That claim is now **testable**: run the gate with each tier's claims in the loop and compare. Until measured, cheap. |
| Narrator | **haiku tier (cheap)** | Prose over a decided card. Output is `MODEL_SUGGESTION` and cannot be approved regardless of quality. |
| Anything opus-tier | **not routed there** | Reserved for offline analysis, never the request path. `docs/MODEL_PLAN.md` finding 2: *stronger-reasoning models are worse at temporal applicability* — they collapse onto "apply the current law", which is the exact failure this product exists to catch. Spending 5× for a documented regression is not a trade-off. |

### 5.4 Per-matter cost

One matter = one document upload + one legal question + one narrated card.

| Configuration | Steps | Cost |
|---|---|---|
| **Stage 1 (deterministic only)** | 0 LLM calls | **₹0.0000** |
| **Stage 2 (+ extractor)** | 1 × extractor | **₹0.3809** |
| **Stage 3 (+ answer)** | extractor + answer | **₹0.8856** |
| **Stage 4 (+ narrator)** | extractor + answer + narrator | **₹1.4094** |
| Same, all sonnet | | ₹4.2283 |
| Full stack, batched | | ₹0.7047 |

At ₹1.4094 per fully-featured matter the ₹3,500 cap buys **~2,483 matters/month**, or ~82/day
against the ₹116.67 daily cap. At Stage 2 it buys ~9,188.

**Near-zero at rest holds trivially**: idle cost is ₹0 because there is no vector index to host,
no embedding service, no queue worker, and the deterministic path (`assess.py`, `applicability.py`,
`s173_slice.review`, `agm.py`, the whole cascade) costs nothing to run. `docs/assess.py` header:
*"the free checker costs ₹0 to run — the whole path is deterministic Python."*

**Cache dividend.** With the step cache of §6.3, re-running a matter after the user corrects one
fact re-runs only the steps whose inputs changed. Correcting a *fact* invalidates extractor-
downstream steps; correcting *nothing* costs ₹0. **GUESS:** I estimate iteration is 2–4× per
matter in real use, which would make the effective per-matter figure closer to ₹1.4–₹2.0 rather
than N × ₹1.4094 — but this is a guess with no user data behind it and must be measured, not
assumed, before it appears in any plan or pitch.

### 5.5 What is deliberately not in the arithmetic

- **Prompt caching.** Anthropic offers prompt caching; whether it applies profitably to this
  shape (packs differ per query; the shared prefix is only the ~700-token `INSTRUCTION` block) is
  **UNVERIFIED** — no web access this session. Do not plan savings on it. If it works it is upside.
- **Retries.** Budget must be charged on the *attempt*, not the success. A retried call is a
  second call.
- **Introductory pricing.** `budget.py` notes sonnet-5 had introductory pricing through
  2026-08-31 — i.e. **today**. List prices are used deliberately.

---

## 6. State and memory between steps, without a vector DB

### 6.1 `checker/retrieval.py`'s argument, and whether it still holds

`retrieval.py` argues against vector search: *"the corpus is 30 sections ... loading torch to rank
thirty paragraphs costs ~2GB of dependencies and several seconds of cold start to beat a scan that
finishes in under a millisecond ... When the corpus reaches the four labour codes (~500 sections)
this becomes the right call; today it is cargo cult."*

**Honest flag: that file's own stated trigger has arguably been reached.** `retrieval.py` serves
the **PoSH** corpus (30 sections, `corpus/provisions/posh_act_2013.json`) — a leftover from the HR
era, and R-010 in `research/TASKS.md` is an open task to retire it. The Companies Act corpus is
**529 records / 474 mapped sections** (`corpus/companies_act/`, `checker/section_index.py`), which
is the "~500 sections" number its own docstring names.

So the argument is not carried over by inheritance. It has to be re-made on today's corpus. Here
it is, with arithmetic:

**Storage is not the objection.** 500 sections × 384 dims × 4 bytes = **768 KB**. Trivial. Anyone
arguing against a vector DB on index size is arguing badly.

**The objections that actually hold:**

1. **Dependency and cold start.** `sentence-transformers` + torch is ~2 GB. CLAUDE.md: *"No new
   dependency without a stated reason."* `docs/MODEL_PLAN.md`: *"The repo has zero third-party
   dependencies and does this today."* A 2 GB dependency to rank 500 short documents is a large
   bill for a small ranking problem.
2. **The query shape is exact-match, and BM25 wins there.** `docs/NON_GOALS.md` already cites
   Sciavolino et al. (EMNLP 2021): BM25 wins on entity-rich exact match. Our queries are
   `"s.173"`, `"rule 4"`, `"section 96"`. `section_index.section_by_number("173")` resolves that
   in O(1) with a hand-verified map, at 474/517 coverage and 12/12 verified against India Code's
   own REST API.
3. **The decisive one: embeddings make this repo's known bug worse.** `retrieve.py`'s docstring
   records the Act-versus-Rule collision — `"rule 4"` falling through to Act s.398/s.469. `s.173`
   and `rule 173` are near-identical strings *and* near-identical in embedding space. A dense
   retriever cannot refuse; it always returns its nearest neighbour with a plausible score. The
   exact resolver's ability to **abstain** is the property that fixes the bug, and it is exactly
   the property a similarity search does not have.
4. **Cost at rest.** A hosted vector DB has a monthly floor. The whole budget is ₹3,500/month,
   against which `research/TASKS.md` H-002 records that a ₹10,000/month data licence *"exceeds the
   whole budget."* Anything with a standing monthly fee competes with the entire API spend.

**Conclusion: not overturned.** Revisit when — and only when — a measured retrieval benchmark
(the successor to `scripts/bench_retrieval.py`, on the Companies Act corpus, not PoSH) shows
recall@3 below ~0.90 on real practitioner phrasings that name no provision. That benchmark does
not exist and building it is cheaper than the vector DB it would justify.

### 6.2 What carries state instead

Three artefacts, all typed, all already existing or trivially derived:

**(a) The `Matter` is the memory.** `checker/matter.py` is immutable, refuses contradictory
construction (*"'This is the first AGM' together with 'the previous AGM was on 10 May 2025' is not
a hard case; it is two mutually exclusive claims"*), refuses half-population before a legal
calculation, and labels every value's origin via `provenance()`. Steps take a `Matter` and return
a new `Matter`. This is the whole inter-step channel for facts.

**(b) The `EvidencePack` is the working set, rebuilt per step.** Deterministic from the query, so
it needs no storage. Recorded in the log by its key set and content hash so a run is replayable.

**(c) The step log is the trail.** New `checker/step_log.py`, append-only JSONL, same discipline as
`review_record.append()` (*"A decision that turns out to be wrong is superseded by a later record
naming it, not edited in place"*). One record per step:

```
step_id, matter_id, task_type, prompt_version, model_name, tier,
pack_keys[], pack_sha256, input_tokens, output_tokens, cost_inr,
decision, claims[], rejected_claims[], cascade_verdicts[], attribution_stage,
started_at, finished_at
```

This gives audit, per-matter measured cost, replay, and the cache key — from one artefact.

### 6.3 The cache

`cache_key = sha256(prompt_version || model_name || full_prompt_text)`.

The prompt is a pure function of (task spec, question, matter facts, pack), so an identical key
means an identical request and the stored response may be reused at **₹0**. Store as JSON on disk
next to the step log; `FileStore` in `backend/budget.py` is the pattern.

Invalidation is by construction, not by TTL: `prompt_version` changes, model changes, a fact
changes, or the corpus record changes → the key changes → a real call. There is nothing to expire
and nothing to get stale, which is the correct property for a system whose whole premise is
statutory currency.

### 6.4 What deliberately does not carry between steps

- **Raw model prose.** Unverifiable, therefore not a carrier.
- **Chain-of-thought / scratchpads.** Same reason, worse: it *reads* like reasoning, which invites
  a later step to treat it as established.
- **A conversation history.** §4.2.
- **Claims as evidence.** §4.2. A claim is a proposition under test, never a premise.

The one-sentence rule: **if it isn't typed and checkable, it doesn't cross a step boundary.**

---

## 7. Failure and abstention behaviour, level by level

Fail-closed everywhere. In every row, the fallback is *less answer*, never *unsupported answer*.

| Level | Uncertainty signal | Behaviour | User sees | Cost |
|---|---|---|---|---|
| Orchestrator | unknown matter type | refuse; do not improvise a plan | "not a matter type this system handles" | ₹0 |
| Orchestrator | a step abstains | **halt that branch**; do not run dependents on a missing input | the partial card + the named gap | ₹0 |
| Budget | `can_make_call()` false | whole LLM tier goes dark; deterministic path still answers | card without prose, and *why* | ₹0 |
| Budget | ledger corrupt | `offline` mode, refuse to spend against an unknown balance | as above | ₹0 |
| Retriever | query names a provision, resolver can't resolve it | `ROUTE_ABSTAIN`. **Never** fall through to text search | "we hold no admitted text for that provision" | ₹0 |
| Retriever | no query match at all | `retrieval.SCAN_FLOOR` — below 2, return nothing rather than three weak matches | "no provision matched" | ₹0 |
| Admission | material not `PRODUCTION_USABLE` | withheld from the MODEL pack, and **reported as withheld**, never silently dropped | "found, cannot be used, here's why" | ₹0 |
| Evidence pack | nothing usable | `insufficient_evidence` → `INSUFFICIENT_EVIDENCE`, **no model call** | abstention with a reason | ₹0 |
| Extractor | span not verbatim in document | slot → `UNKNOWN`; never repaired | "we couldn't find this in your document — please confirm" | call already paid |
| Extractor | model returns malformed output | mirror `run()`: abstain with a parse-failure warning, never raise | as above | call already paid |
| Matter | contradictory facts | construction **raises** | the contradiction, named | ₹0 |
| Matter | half-populated | `missing_for_agm()` names the gap *before* computing | the specific missing fact | ₹0 |
| Adapter | REVIEW pack | `AdapterError` — hard refusal | internal error, not a legal answer | ₹0 |
| Adapter | citation outside pack | claim rejected, never repaired | claim absent + rejection reason in the trail | call paid |
| Adapter | duplicate `claim_id` | **all** copies rejected; order decides nothing | as above | call paid |
| Adapter | conclusion with no surviving claim | downgraded to `INSUFFICIENT_EVIDENCE` | abstention with a reason | call paid |
| Adapter | unparseable output | `INSUFFICIENT_EVIDENCE` + `MODEL_OUTPUT_PARSE_FAILURE`, raw preserved | abstention | call paid |
| Verifier | E6 finds a dropped qualifier | claim dropped, whatever E3/E4/E5 said | claim absent + reason | ₹0 |
| Verifier | only E3 accepts | ceiling `CLAIM_PARTIALLY_MATCHED`; **not** servable as support | "terms match; entailment not established" | ₹0 |
| Verifier | every claim dropped | the answer is an abstention, not a shorter answer | "we could not support any statement here" | ₹0 |
| Gate | `evaluate_gate` fails in CI | the configuration does not ship | nothing | ₹0 |
| Formatter | any `MODEL_SUGGESTION` / `UNKNOWN` slot | `approve()` **raises** | draft marked not approvable, with the blocking slot named | ₹0 |
| Reviewer | restrict or reject | requires a written reason (`review_queue`) | — | ₹0 |

Two invariants to assert in tests, because they are the ones that erode quietly:

1. **No path exists from any model output to a served legal statement that does not pass the
   cascade.** Assert by construction — the card builder accepts only cascade-stamped claims.
2. **Every abstention names a reason.** `run()` already enforces this (*"INSUFFICIENT_EVIDENCE
   returned without a stated reason"*); the orchestrator must too.

---

## 8. Staged build order

Each stage ships something, is gated, and states what it does **not** claim.

### Stage 0 — make the verifier importable (days, no LLM, no user value)

- `checker/cascade.py`: lift `cascade()` out of `metric_policy._test()` (§3.2). `metric_policy`
  imports it. Add the grounding-state mapping of §3.3.
- `checker/step_log.py`: append-only JSONL step records.
- Fix the stale FA/F1 comment in `metric_policy.py` (4/0.49 → 2/0.58).
- Wire `backend/budget.can_make_call()` into `model_adapter.run()` as refusal #0 (§4.3b).

**Does not claim:** anything new. This is the prerequisite that stops the gate and the runtime from
scoring different code.
**Gate:** `metric_policy` still PASSes, with identical numbers, importing the lifted module.

### Stage 1 — the deterministic orchestrator, two sections (weeks, no LLM) ← *smallest increment with real user value*

- `checker/orchestrator.py`: static task graph, per-step logging, halt-on-abstain.
- Two matter types wired end to end: `BOARD_MEETING_GAP` (`s173_slice.review`) and `AGM_DEADLINE`
  (`s96_slice.card` + `agm.py`).
- Facts typed by hand into a `Matter`. Output is an evidence card where every figure carries its
  source and every gap is named.

**Cost: ₹0.00 per matter.** No API key required to run the product.

**Does not claim:** it reads documents; it covers any section beyond s.96 and s.173; it establishes
entailment; it is accurate — B-001 (the 30–50 document benchmark, *CRITICAL PATH* in
`research/TASKS.md`) does not exist yet, and CLAUDE.md forbids claiming legal accuracy without an
independent benchmark.

**Why this first:** it proves the loop, produces the step log every later stage depends on, and is
the fallback every later stage degrades to when the budget is exhausted. If Stage 1 is not
independently useful, adding a model will not make it so.

### Stage 2 — the extractor (first LLM step)

- `checker/extract_adapter.py` (§4.3f): its own three refusals, span-verified output.
- Its own fixture set, including documents where the field is genuinely absent, and its own gate
  row set before it ships (§3.4).
- Haiku tier. **₹0.3809/document.**

**Does not claim:** the document is legally correct or complete; extraction is exhaustive. An
`UNKNOWN` slot means "we did not find it", never "it is not there."

### Stage 3 — the answer step, shadow first

- Real model behind `model_adapter.run()`, output through `claim_verifier` → `cascade` →
  `attribution`.
- **Shadow mode first**: run it, log it, do not serve it. Score against the frozen 67 rows and the
  `eval_taxonomy.build_fixtures()` abstention set.
- **Serving gate:** `evaluate_gate` still PASSes with the model's claims in the loop — false
  accepts ≤ 10, F1 ≥ 0.40, abstention ≤ 0.25, per-bucket reported — **and** no bucket regresses
  against Stage 1's deterministic numbers.
- Haiku tier by default; standard tier only if the gate measurably improves, which tests
  `PROVIDER_DECISION.md`'s claim that model choice is a cost lever rather than a correctness one.
- Cumulative **₹0.8856/matter.**

**Does not claim:** `GROUNDED` — that requires entailment, which `docs/MODEL_PLAN.md` names as *the
gap* and `claim_verifier.py` says plainly nothing in the repo can produce. Claims top out at
`CLAIM_QUALIFIERS_CHECKED`.

### Stage 4 — the narrator

- Prose over an already-decided card. Cheapest tier. `MODEL_SUGGESTION`-labelled, so
  `drafting.approve()` blocks. Skipped entirely when the budget is short.
- Cumulative **₹1.4094/matter**, ~2,483 matters/month at the cap.

**Does not claim:** anything legal. The prose is presentation over a decided result.

### Stage 5 — breadth (BLOCKED)

More sections, more matter types. **Blocked on B-001** (corporate-law benchmark, 30–50 documents
*including defective ones*) and **H-001** (review by 1–2 practising corporate lawyers). Both are
open in `research/TASKS.md`, and H-001 is recorded as gating *claims*, not development. Widening
coverage before the benchmark exists means widening the surface over which we cannot say whether
we are right.

---

## 9. What we are NOT building, and why

### 9.1 A vector database / embedding retrieval

Covered in §6.1. Short form: 768 KB of vectors is not the cost — 2 GB of dependency, a second
inference surface, a standing monthly fee against a ₹3,500 budget, and **a retriever that cannot
abstain** are. Point 3 is decisive: the repo's known Act-versus-Rule collision (`retrieve.py`) is a
bug embeddings make *worse*, because `s.173` and `rule 173` are near neighbours in exactly the
space a dense retriever ranks in. `docs/NON_GOALS.md` already lists this; §6.1 re-derives it on the
Companies Act corpus rather than inheriting an argument made about a 30-section PoSH corpus.

**Revisit when:** a Companies Act retrieval benchmark shows recall@3 < ~0.90 on real practitioner
phrasings that name no provision. Build the benchmark first; it is cheaper than the thing it would
justify.

### 9.2 Fan-out parallelism over large document sets

The capability shape — dispatch N parallel agents across hundreds or thousands of documents in a
data room, aggregate their findings. (**UNVERIFIED / not a competitor claim:** I am describing a
capability shape from general knowledge, not asserting what any named product does. CLAUDE.md:
*"No unsupported product, market, legal, or competitor claims."*)

Four reasons not to:

1. **Budget.** Parallelism multiplies spend and changes nothing about correctness. 100 documents
   × ₹0.38 = ₹38 for one matter — a third of the entire *daily* cap (₹116.67) on one user.
2. **No corpus.** We hold one Act. CLAUDE.md forbids obtaining private minutes or confidential
   company documents, which is what a data room is made of.
3. **The closed world doesn't fan out cheaply.** Each parallel branch needs its own admitted pack
   and its own citation-id namespace (§4.2). Sharing one is exactly the failure mode refusal 3
   prevents. Not sharing means N packs, N calls, N× cost — i.e. it is not really parallelism, it
   is just volume.
4. **It is the wrong wedge.** CLAUDE.md's wedge is one document, checked properly, against current
   law. Depth per document, not documents per hour.

### 9.3 Playbook / deviation comparison

Comparing a clause against a firm's standard playbook and flagging deviations.

1. **Source policy forbids the input.** It needs the firm's private precedent library. CLAUDE.md:
   *"Do not obtain private minutes or confidential company documents."*
2. **It is not the defect we detect.** The wedge (CLAUDE.md) is that customising a ComplyRelax
   template *stops legal updates* — the defect is **drift from the statute**, not stylistic
   deviation from a house style. A playbook check would flag a document that matches the firm's
   standard and is three amendments out of date as *clean*. That is the failure inverted.
3. **No ground truth.** A deviation is only a defect if the playbook is right, and nothing in this
   system can verify a private playbook.

### 9.4 Model training, fine-tuning, or a foundation model

CLAUDE.md: *"Not a foundation-model project."* `docs/MODEL_PLAN.md`: *"we are not training a
foundation model, and the LLM is the least trusted component in the system."* `docs/NON_GOALS.md`:
*"Fine-tuning or a foundation model — No data rights, no budget, and not the moat."*

**One tension to record honestly.** `docs/MODEL_PLAN.md` does propose one trained model: a
fine-tuned NLI head for claim–source entailment, calling it *"the one place where a trained model
earns its place."* **This plan does not authorise it, and the reason is the measurement.**

The deterministic cascade is at FA 2, F1 0.58 with zero training. The per-bucket breakdown says
where the remaining value is: `dropped_qualifier` sits at **F1 0.00, n=9** — E6 refuses correctly
but never accepts, so that bucket has no true positives at all. That is a gap in a *deterministic*
module, addressable by reading nine claims and extending `entail_qualifier.qualifiers_in()`. It
costs a day and no data rights.

Training an NLI head, by contrast, needs labelled data that needs review capacity that is blocked
behind H-001 (zero expert review to date), produces an artefact that cannot be read or explained to
a regulator, and would have to beat a baseline that keeps improving for free. Fix the 0.00 bucket
first. If the cascade then plateaus below what the product needs, revisit with the measurement in
hand.

### 9.5 LLM-as-judge, self-critique, and self-consistency voting

A model reviewing its own or another model's output. Refused outright — `docs/MODEL_PLAN.md`
records Magesh et al. refusing it and Cymbler et al. using deterministic nuggets instead, *because
an LLM judge inherits the same recency bias it is meant to detect.*

This includes the fashionable variants: self-consistency sampling, N-way voting, "reflection"
passes. All of them multiply cost by N and all of them measure agreement among samples from one
distribution, which is not evidence about the law. The cascade already gives a critique that
cannot hallucinate. Adding a model critic on top would make the system *more* expensive and *less*
auditable.

### 9.6 Autonomous tool-calling / ReAct-style loops

A model that decides its own next action decides which provision to look at, and applicability is
the one thing that must never be the model's call (`applicability.py`, `docs/MODEL_PLAN.md`). It
also makes cost unbounded per matter, against a ₹116.67 daily cap. Static task graphs; the model
never chooses a step.

### 9.7 A general legal chatbot

Already a non-goal (`docs/NON_GOALS.md`): *"Puts us against Lexlegis and every frontier model, and
abandons the wedge."* Nothing in this architecture should make one accidentally easy to ship.

---

## 10. Guesses, gaps, and things to check before writing code

Marked so a reader can tell verified from asserted.

| # | Item | Status |
|---|---|---|
| 1 | Model IDs `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5` and their per-million pricing | **UNVERIFIED** — taken from `backend/budget.py`. No web access this session. `PROVIDER_DECISION.md` §7 documents three prior plans that each named a retired identifier. **Check the registry before any code.** |
| 2 | Token counts in §5 | **APPROX** — `chars / 4`, not a tokenizer. Char counts are measured; the divisor is a convention. Re-measure with the provider's token counter. |
| 3 | USD/INR 95.23 | Dated 2026-08-06 in `budget.py`. Stale by ~3.5 weeks. |
| 4 | Prompt caching economics | **UNVERIFIED**. Not modelled. Treat as upside only. |
| 5 | Batch API 50% discount | Modelled in `budget.py`; not independently re-verified this session. Batch is also latency-asynchronous, which may not suit an interactive request path. |
| 6 | "2–4× iteration per matter" (§5.4) | **GUESS.** No user data. Must be measured before it appears anywhere else. |
| 7 | Fan-out parallelism as a competitor capability (§9.2) | **UNVERIFIED / not a competitor claim.** Capability shape from model knowledge only. |
| 8 | `retrieval.py`'s anti-vector argument was made about a **30-section PoSH corpus**, not the ~500-section Companies Act corpus | **Confirmed defect in the inherited reasoning.** §6.1 re-derives it. R-010 (retire HR-era PoSH assets) is open in `research/TASKS.md`. |
| 9 | `cascade()` exists only inside `metric_policy._test()` (line 181) | **Confirmed** by grep. Stage 0 blocker. |
| 10 | No `checker/` module imports `backend.budget` | **Confirmed** by grep. The only place an LLM may be called does not consult the only budget guard. Stage 0. |
| 11 | `metric_policy.py` header says FA 4 / F1 0.49; measured today FA 2 / F1 0.58 | **Confirmed stale comment.** Stage 0. |
| 12 | Whether a cheap model's claims keep the release gate PASSing | **UNMEASURED.** This is the load-bearing assumption of the whole routing table (§5.3) and Stage 3 exists to measure it before serving. If it fails, the honest response is to ship Stage 1 + 2 only, not to buy a bigger model. |
| 13 | Extractor accuracy on real Indian corporate documents | **UNMEASURED.** `corpus/testdocs/` has 30 documents, 18 real. No extraction fixtures exist. Stage 2 must build them. |
| 14 | Everything downstream of accuracy | **B-001 is open and marked CRITICAL PATH.** Until it exists, no stage may claim accuracy — CLAUDE.md: *"Never claim legal accuracy without an independent benchmark."* |

---

## 11. One-paragraph summary

Six roles; four of them are code that cannot hallucinate, and the two that may call a model sit at
the input and output edges where their output is checkable by exact match against something we
already hold. The existing E3–E6 cascade is the critic, and the first job is to lift it out of a
test function so the release gate and the runtime score the same object. Multi-step work is N
independent single-shot `run()` calls over N independent packs — never a conversation — so all
three pre-call refusals hold per step, and the only thing crossing a step boundary is a typed,
contradiction-refusing `Matter` plus an append-only step log that doubles as the cache. Routing is
a constant, not a router: everything goes to the cheap tier, because `applicability.py` decides and
the cascade rejects, and because stronger models are documented to be *worse* at exactly the
temporal-applicability failure this product exists to catch. A fully-featured matter costs about
₹1.41 and the ₹3,500 monthly cap buys roughly 2,483 of them; the deterministic-only path costs ₹0
and must remain a complete, correct product on its own. Everything fails closed to *less answer*,
never to an unsupported one.
