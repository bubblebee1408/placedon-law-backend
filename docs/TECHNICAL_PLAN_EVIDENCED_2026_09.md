# Evidenced technical plan — what the market actually builds, and what we build

Written 2026-09-04. Unlike `docs/COMPETITOR_PATTERN_ANALYSIS.md` (which states, at
its head, *"Web access was unavailable for this pass, so no claim below was checked
against any source"*), **every competitor fact in §1 was fetched today from the
vendor's own public page** and is cited. This document upgrades those earlier
UNVERIFIED claims to sourced ones and derives the backend plan from them.

It answers five questions in order: the algorithm, the model strategy ("how we
train / command the AI"), the dataset, the features, and the workflow.

---

## 0. The finding that reframes the whole question

The question was "how are we going to *train* the AI models." The evidence says:
**you don't, and neither does anyone winning this market.**

Harvey, Legora, and Spellbook are the three most-funded players in exactly our
lane. **None of them trains a foundation model.** All three orchestrate
*someone else's* frontier models (Claude, GPT) plus cheaper open models behind a
routing layer, and put their engineering into everything *around* the model:
grounding, verification, playbooks, agent orchestration, and regulatory currency.

- Spellbook, in its own words, uses "state-of-the-art LLMs like GPT5 and Opus."
- Harvey ships Claude Opus 5, Claude Sonnet 5, GPT-5.6, and Fable 5.1 as
  *selectable* models and says a firm "will need to be able to run on essentially
  any model."
- Legora's architecture puts "Large Language Models" as **layer 1 of 7** — the
  commodity floor, not the product.

So "train the model" is the wrong axis to compete on. The moat every one of them
is actually building is **the verification-and-currency layer on top of a model
they rent.** That is precisely the layer this repo already builds. `CLAUDE.md`'s
rule *"Do not train a foundation model"* is not a limitation — it is the same bet
the market leaders made.

What we *command*, then, is orchestration, not training. §2 is exactly that.

---

## 1. The evidence (fetched 2026-09-04, cited)

| Player | Verified fact | Source |
|---|---|---|
| **Harvey** | Built its *own* cloud agent infrastructure because managed platforms don't meet legal needs; model choice is "just a routing decision" behind an abstraction layer | harvey.ai/blog — "Why we Built our own Cloud Agent Infrastructure" |
| **Harvey** | Multi-model by necessity: "a client that builds its own models will not allow its outside counsel to send sensitive legal matters through a competitor's model" | ibid. |
| **Harvey** | Zero Data Retention is *architected in*, not bolted on: "customer data is not written into durable application storage by default" | ibid. |
| **Harvey** | Routing to cheaper/open models where "good enough" yields "3-5x cost reductions versus a frontier-only approach"; validated by their Legal Agent Benchmark (LAB) | ibid. |
| **Harvey** | Product surface: Vault (docs), Tenet (research), Horizon Scanning (regulatory monitoring), Memory (personalization), multi-agent Playbook Review, Outlook inbox | harvey.ai/blog index |
| **Legora** | "aOS" = 7 layers: (1) LLMs, (2) Agentic Harness, (3) Data & Integrations, (4) Context & Knowledge, (5) Legal Capabilities, (6) Products & Interfaces, (7) Security & Governance | legora.com |
| **Legora** | Agent does plan → execute → review → deliver; **Monitors** = "continuously scans global regulation to surface relevant changes"; Tabular Review; multi-jurisdiction research | legora.com |
| **Legora** | ISO 42001, ISO 27001, SOC 2 Type II, GDPR, HIPAA | legora.com |
| **Spellbook** | Word/Google-Docs-native review + redline + draft; "state-of-the-art LLMs like GPT5 and Opus" | spellbook.com |
| **Spellbook** | **Playbooks** encode company-specific standards; **Ask** gives "answers you can trust, with citations"; benchmarks a contract "to thousands of similar agreements" | spellbook.com |
| **Spellbook** | **Spellbook Associate** = multi-document agent for drafting/review; "zero data retention" with LLM providers | spellbook.com |

### The convergent architecture (all three, independently)

1. **Model-agnostic routing.** A layer that normalizes many models; picking one is
   a routing decision, chosen for quality/cost/conflict per task.
2. **Zero Data Retention as architecture**, not a delete button.
3. **Cost routing** — cheap/open model where good enough, frontier only where needed
   (Harvey's explicit 3-5x).
4. **Playbook grounding** — the customer's own standards encoded as the yardstick.
5. **Agentic loop** — plan → execute → review → deliver, over multiple documents.
6. **Citations / grounding** to a source, not free recall.
7. **Regulatory currency** as a first-class product (Legora *Monitors*, Harvey
   *Horizon Scanning*). Both leaders sell "the law changed" as a feature.

Pattern 7 is the strategic tell: the two best-funded players independently decided
that *keeping law current* is worth a headline product. That is Placedon's stated
moat ("currency, not citation"). The market just validated it.

---

## 2. Model strategy — how we "command" the AI (no training)

We adopt the exact pattern all three use, sized to one engineer.

**Tier 0 — Deterministic, no model (₹0).**
The obligation register, threshold logic, small-company classification, the AGM/
board/CSR deciders, and the E3→E6 entailment gate. This is `checker/` today. Most
answers never touch a model. *This is our unfair advantage:* competitors route a
model at every step; a compliance obligation is a decidable predicate, so we route
*nothing* for the parts that are decidable.

**Tier 1 — Cheap/open extraction (~₹0.38 measured).**
Pull a fact from a document (a date from a filing, an amount from a P&L). A small
or open model is "good enough"; the deterministic layer then *verifies* the
extraction against the statute. Model proposes, system verifies.

**Tier 2 — Frontier, gated (Opus/Sonnet-class).**
Only for genuinely hard language: reconciling an ambiguous clause, drafting a memo
narrative. Never trusted raw — output must pass the E-gate or be marked
NOT_ESTABLISHED. Chosen per `checker/model_adapter.py` rules already in the repo.

**Routing rule:** default to the lowest tier that can answer; escalate only on a
named trigger; log which tier answered. This is Harvey's routing thesis at our
scale, and it keeps COGS near zero because Tier 0 carries the load.

**What about fine-tuning?** Not a foundation model — ever. The only defensible
narrow training later is (a) a **retrieval embedding** fine-tune on our statutory
corpus so search finds the right section, and (b) a small **classifier** for
"which obligation does this fact touch." Both are weeks-not-months, both are
optional, and neither is on the critical path. Ship Tier 0 first.

---

## 3. The backend algorithm, end to end

The pipeline that turns company facts into a verified compliance position:

```
1. INTAKE        CompanyProfile (facts only; unknown ≠ zero; money in whole rupees;
                 every figure bound to its financial year).           [company_profile.py]

2. REGISTER      Generate the obligation register FROM THE FACTS, not from documents.
                 One row per duty the Companies Act imposes on this company.
                 The valuable rows have no document behind them.            [obligations.py]

3. CLASSIFY      Derive status the law keys on (small company s.2(85), listed, s.8…)
                 with asymmetric relief: NOT-SMALL needs one definitive fail;
                 SMALL needs every limb known-and-satisfied.                  [classify.py]

4. DECIDE        Per row, run the decider → one of five states:
                 APPLIES_SATISFIED / APPLIES_NOT_SATISFIED / APPLIES_UNDETERMINED /
                 DOES_NOT_APPLY / CANNOT_DETERMINE.  "doesn't attach" and "can't tell
                 if it attaches" never collapse.  No row goes green while any limb
                 is unreached (limbs_not_decided).            [obligations.py deciders]

5. GROUND        Every APPLIES row carries the statute span + Gazette instrument
                 behind it. Bare statutory text is never emitted (s.52(1)(q)(ii)).

6. VERIFY        Any model-proposed span passes the deterministic entailment cascade
                 E3→E4→E5→E6 or it does not ship. This is the line competitors draw
                 with an LLM-judge; we draw it deterministically.        [checker/cascade.py]

7. RENDER        The pre-diligence evidence pack: position on a date, cited, with an
                 explicit "what we could NOT verify" list. Breaches ordered first.
                 Deterministic — no model in the render path.          [diligence_pack.py]

8. SERVE         Loopback HTTP, POST-only for facts (never in a URL/query log),
                 no-store + CSP headers.                    [matrix_view.py, serve_matrix.py]
```

The inversion (step 2) is the whole product and is the one thing none of the three
competitors do: **they are document-in tools** (feed a contract, get a review).
Placedon is **facts-in**: the missing filing is itself the finding. Spellbook
reviews the contract you have; Placedon tells you the resolution you never passed.

---

## 4. The dataset — what we actually need (and don't)

We do **not** need a training corpus for a foundation model. We need three curated,
version-controlled assets, and two already exist:

1. **The statutory corpus** — Companies Act 2013 sections + the Gazette instruments
   (G.S.R./S.O.) that set thresholds, content-hashed, with a law-effective-date
   distinct from the artifact version. *This is the moat asset — currency lives
   here.* Gaps today: G.S.R. 700(E) small-company amounts (S-002, needs a human
   browser download; `scripts/register_gsr700e.py` is the intake).

2. **The entailment benchmark** — the frozen, span-hashed pair set that gates
   releases (v3, governed by `benchmark_versions.py`). Immutable versions,
   comparability=false when a label moves. *This is our LAB* — Harvey's Legal
   Agent Benchmark analogue, at our scale.

3. **The obligation fixtures** — the company-fact scenarios each decider is proven
   against (the s.96 false-green, the s.173 cross-year bug, etc. are all fixtures
   now). This is a *behavioural* test set, not a model training set.

The strategic point: our data work is **corpus curation and currency**, not label
farming for a train run. That is cheaper, defensible, and it is the exact axis
Legora Monitors / Harvey Horizon Scanning compete on.

---

## 5. Features — parity vs. wedge

| Competitor feature (sourced) | Placedon posture |
|---|---|
| Playbooks (Spellbook) — encode company standards | **We ground to *statute*, not a customer playbook.** The Companies Act is the playbook, and it is the same for every company, so it is a shared asset we curate once. |
| Ask, with citations (Spellbook) | Same discipline; ours *abstains* (NOT_ESTABLISHED) rather than answering when the corpus is silent — a stricter bar. |
| Monitors / Horizon Scanning — regulatory change | **This is our roadmap headline.** Currency is already the corpus's design (law-effective-date). Build the diff-and-alert on top. |
| Tabular / multi-doc Associate (Legora/Spellbook) | Our register *is* tabular — one row per obligation — but generated from facts, not documents. |
| Redline / draft operative documents | **Deliberately NOT built.** Drafting a legally operative instrument makes the system the proposer of a defective document — a larger liability surface. Held for a governance decision (see `STRATEGY_REVIEW_RESPONSE.md` §3.2). |
| Zero Data Retention | Adopt as architecture: facts in POST body, no-store, no durable write of client facts. Already the serve-layer posture. |
| Multi-model routing | Adopt (§2). Our Tier 0 means we route *less* than they do. |

The wedge in one line: **they verify the document you have; we verify the
obligations you can't see, against statute you can trust is current.**

---

## 6. Skills & workflow (the loop)

The build loop, unchanged and evidence-consistent:

```
propose → verify → decide
  ├─ model proposes (Tier 1/2)         — never trusted raw
  ├─ deterministic system verifies      — E3→E6 gate, decider states
  └─ reviewer decides                    — the human keeps the pen
```

Each module self-tests ([PASS]/[FAIL], N/N), zero third-party deps, Python 3.12,
`scripts/run_tests.sh` (69 suites green today). New law or new obligation enters
only through a fixture + a frozen benchmark row. Currency updates enter only
through corpus intake with a new law-effective-date, never by editing a constant.

---

## 7. Real today vs. build-ahead

**Real and green today:** intake, register, classify, 8 obligations with deciders,
the E3→E6 gate, the evidence pack, the loopback serve layer, immutable benchmark
governance, provenance/reproducibility (fresh clone passes).

**The honest build-ahead, in order:**
1. **S-002 corpus gap** — acquire G.S.R. 700(E) (human download; blocks small-co
   amounts). *Cheapest highest-value item.*
2. **Currency engine** — the Monitors/Horizon-Scanning analogue: diff a new Gazette
   instrument against the corpus, flag affected obligation rows. This is the moat
   feature the market just validated twice.
3. **Model tiering** — wire the routing rule in `model_adapter.py` so Tier 1
   extraction has a cheap default and a frontier escalation trigger.
4. **More obligations** — s.185/186/188 need a Corporate Entity Graph (shareholding,
   interest, inter-company) first; that graph is the real next data structure.

Note the discipline this document does **not** relax: every one of items 2-4 is a
guess about what a practitioner needs until one reviews the register. The evidence
here tells us *what to build*; it does not tell us *whether a CS agrees the rows are
right*. Those are different questions, and only the second one is answered by a
person, not a competitor's blog.

---

## 8. Sources

- Harvey — "Why we Built our own Cloud Agent Infrastructure", harvey.ai/blog (fetched 2026-09-04)
- Harvey — blog index (product surface: Vault, Tenet, Horizon Scanning, Memory, Playbook Review), harvey.ai/blog (fetched 2026-09-04)
- Legora — legora.com, "aOS" 7-layer architecture, Agent, Monitors, Tabular Review (fetched 2026-09-04)
- Spellbook — spellbook.com, Review/Redline/Draft, Playbooks, Ask, Associate, ZDR (fetched 2026-09-04)

All four fetched live; each row in §1 is attributable to the vendor's own page.
Inference (e.g. "this validates our currency thesis") is labelled as such and is
not stated as a vendor fact.
