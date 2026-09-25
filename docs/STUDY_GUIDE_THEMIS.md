# Study guide — how Themis works, and the ideas it is built on

Written 2026-09-24 for the founder. Plain language first, then the precise
version, then where it lives in the code. Read it alongside
[PLAN_16](PLAN_16_RESEARCH_PROGRAMME.md) (research) and
[PLAN_17](PLAN_17_BETA_BUILD.md) (build).

---

## Part 1 — The product in one page

A lawyer asks a question or uploads a document. Themis answers **only** from law
it actually holds, says **which notification** each statement rests on and from
**what date**, and **refuses** — visibly — where it cannot prove the answer.

Three things make that possible:

1. **A deterministic core.** Code, not a model, decides what the law requires.
   A model may *write* the explanation; it may never *decide* it.
2. **A record of the law over time.** The corpus knows when each provision
   changed, so a question about 2021 is answered with 2021's law.
3. **Checks on everything a model writes.** Every sentence must quote its source
   exactly, or it is shown as refused.

The motto in the README: *"The model may propose. The system must verify. The
reviewer decides."*

---

## Part 2 — The concepts

### 2.1 RAG (retrieval-augmented generation)

**Plainly:** instead of asking a model to answer from memory, you first *find*
the relevant text (retrieval) and give it to the model with the question
(augmented generation).

**Why it is not enough on its own:** Stanford measured commercial legal RAG tools
hallucinating **17–33%** of the time (Magesh et al., 2025). Retrieval can fetch the
wrong text, the wrong *version* of the right text, or not enough text — and the
model will often answer anyway.

**In Themis:** retrieval is `checker/structural_retrieve.py` /
`checker/legal_retrieval.py`; the answer path is `checker/ask.py`.

### 2.2 Keyword search (BM25) vs. meaning search (dense vectors)

- **BM25** scores documents by matching words, weighted by how rare the word is.
  Excellent for law, where exact terms ("small company", "s.188",
  "related party") matter.
- **Dense retrieval** turns text into vectors of numbers and finds text with
  similar *meaning*, even with different words.
- **Hybrid** uses both.

**What the repo measured:** on 70 frozen questions, BM25 and a dense model
(MiniLM) scored 0.71 vs. 0.73 at top-1 — **not distinguishable** (McNemar
p = 0.648). With 70 questions you cannot tell them apart; that is why PLAN_17
grows the test set before changing the retriever. Anthropic's "contextual
retrieval" write-up reports hybrid search plus reranking cutting retrieval
failures by up to 67% — on *their* data. Ours has to be measured on ours.

### 2.3 Chunking and structure

Retrieval works on pieces ("chunks"). Cutting a statute every 500 characters
breaks provisos away from their sections. Themis chunks along the statute's own
structure — section → sub-section → proviso (`checker/structural_chunk.py`) — so a
retrieved piece is always a real legal unit that can be quoted.

### 2.4 Time: "as of" and currency

Law changes. G.S.R. 880(E) moved the small-company thresholds from 1 December
2025. A question "was this company small on 1 June 2025?" needs the **old** figure;
"is it small today?" needs the **new** one.

- `checker/as_of.py` answers with the text in force on a date.
- `checker/currency.py` and `checker/staleness.py` say whether a stored answer is
  still current.
- The **Gazette watcher** (`checker/feeds/egazette.py`) notices new
  notifications, so the corpus itself does not silently go stale.

The engine once served a superseded threshold as current for nine months. That
incident is the product's origin story, and the reason currency is checked by
machine.

### 2.5 Abstention (refusing)

**Plainly:** saying "I cannot verify this" instead of guessing.

Themis refuses at several points, each for a stated reason:

| Where | Refuses when | Code |
|---|---|---|
| Scope | The question is about law we do not hold (e.g. FEMA) | `checker/scope.py` |
| Facts | A company fact needed to decide is missing | `checker/obligations.py` |
| Rules | A delegated rule the section depends on is not held | `blocked_by` in obligations |
| Sources | An instrument is not attested | `checker/admission.py` |
| Sentences | A sentence cannot be traced to a span | `checker/lawyer_summary.py` |
| Context (new, M7) | Retrieved text is not enough to answer | sufficiency gate |

A refusal is **not** "no obligation applies". Mixing those two up is the most
dangerous error a compliance tool can make, which is why `scope.py` exists.

### 2.6 "Sufficient context" (Google, ICLR 2025)

**The finding:** big models answer correctly when the retrieved text is
sufficient — but when it is **not**, they still answer, and often wrongly,
instead of abstaining.

**The method:** a model is used as a *rater* that labels whether the context is
sufficient to answer (their best rater, Gemini 1.5 Pro with one example, was
**93%** accurate against human labels). That label is combined with the model's
own confidence in a simple logistic regression, and the system abstains when the
predicted chance of error is too high.

**How Themis uses it (PLAN_17 M7):** only as a gate that can **withhold**. If the
rater says "insufficient", Themis refuses and says what is missing. If it says
"sufficient", the answer still has to pass every other check. A rater that could
*permit* an answer would put a model in a decision path.

### 2.7 Span tracing (attribution)

**Plainly:** every sentence must point at the exact words in a source that support
it.

**The research:** ALCE (EMNLP 2023) found even the best models lacked full citation
support about half the time on one dataset. FActScore (EMNLP 2023) splits text into
atomic facts and checks each against a source.

**In Themis:** `checker/lawyer_summary.py` checks each *clause* (not just each
sentence — a true clause cannot "pay" for a false one joined to it), requires the
quoted text to be **byte-identical** to the source, and refuses anything else.
Note: a competitor (GC AI) also advertises character-level quotes, so tracing is
table stakes, not a moat on its own.

### 2.8 Calibration

**Plainly:** a system is *calibrated* if, when it says "90% sure", it is right about
90% of the time.

**The trap:** you need many examples to *measure* calibration. The repo computed
this exactly (`checker/calibration_contract.py`):

- Even a **perfect** forecaster saying "90%" on **20** items shows an expected
  calibration error of about **0.051** — just from chance. So "ECE < 0.05" cannot
  be demonstrated with 20 items, no matter how good the system is.
- For "will Parliament amend this section?", the corpus has about **6** amending
  events. The floor is about **0.106**. That question can never be answered with
  an honest probability here.

This is why Themis shows **ordered levels** and **counts**, not percentages.

### 2.9 Conformal prediction — a guarantee without trusting the model

**Plainly:** a way to turn *any* model's scores into a statistical promise, using a
small set of checked examples, with no assumptions about how the model works.

**Worked example (Mohri & Hashimoto's version, simplified):**

1. Take 19 past questions that a lawyer has checked. The model's answer to each is
   split into claims, and each claim has a confidence score.
2. For each question, find the **highest score given to a false claim** in that
   answer (0 if every claim was true). Call it *r*. That is the threshold you
   would have needed to remove every false claim from that answer.
3. Sort the 19 values of *r*. With α = 0.05 (a 5% error allowance), the rule picks
   the ⌈(19 + 1) × 0.95⌉ = 19th smallest — here the **largest** one — as the
   threshold τ.
4. For a new question, **keep only claims scoring above τ**.

**The guarantee:** if the new question is like the calibration questions
("exchangeable"), then with probability at least 95% **every claim kept in the
answer is true**. Fewer claims survive when the model is unsure — the answer
"backs off" to what is safe.

**The catch:** 19 questions is the minimum for α = 0.05; the answer gets less
conservative with more data. A related, separate calculation: to show an error
*rate* below 5% with 95% confidence from an audit with no errors found, you need
**59** clean checked answers; below 1%, **299**. That is why the pilot must collect
lawyer-checked answers (PLAN_17 M12).

**Improvement (Cherian, Gibbs, Candès, NeurIPS 2024):** the basic guarantee is an
average over all topics; it can be weaker on a hard topic. Their method makes it
hold per topic and throws away fewer true claims.

### 2.10 The ring firewall (non-interference)

**Plainly:** a guarantee that live feeds and predictions can never change a legal
decision.

**The idea (Goguen & Meseguer, 1982):** a system has *non-interference* if changing
the "high" inputs never changes the "low" outputs. For Themis, feeds and
predictions are "high"; legal decisions are "low".

**In code:** `checker/rings.py` reads the source of every legal-decision module and
fails the test suite if any of them imports a feed or prediction module — directly,
through a helper, or through dynamic imports. A red team found two holes in the
first version; both are now closed and tested.

### 2.11 Multi-tenancy and row-level security

**Plainly:** many companies share one system, and none may ever see another's data.

**Row-level security (RLS):** a PostgreSQL feature where the *database* adds
"… AND tenant_id = <this customer>" to every query. If application code forgets,
the database still refuses. PLAN_17 M4 includes a test that deliberately removes
a policy to prove the tests would catch it.

**Ethical walls:** within one company, a lawyer sees only the matters they are a
member of.

### 2.12 Encryption and deleting for good

- **Encryption at rest:** stored data is encrypted.
- **Envelope encryption:** each customer's data is encrypted with its own *data key*;
  that key is itself encrypted by a master key kept in Azure Key Vault.
- **Crypto-shredding:** to delete a customer completely, destroy their key. Every
  copy — including backups you forgot about — becomes unreadable.

### 2.13 Zero data retention with model providers

When a prompt is sent to a model provider, the provider may keep it. Azure OpenAI
keeps prompts for 30 days for abuse monitoring **unless** you are approved for
*modified abuse monitoring*, which requires an Enterprise Agreement or Microsoft
Customer Agreement. Harvey's rule, quoted in PLAN_07: storing and then deleting is
not zero retention — it is retention followed by deletion.

### 2.14 Data residency

Where data is processed and stored. Azure's regional deployments in India process
in the chosen region. Claude via Bedrock in India has so far used *global*
cross-region inference; Anthropic announced India in-country inference in August
2026. Until that is confirmed live, client documents do not go to Claude
(PLAN_17 §2.2).

### 2.15 Sign-in: SSO, OIDC and Entra ID

**Single sign-on** lets a lawyer use their existing company Microsoft account.
**OpenID Connect (OIDC)** is the standard that carries "who is this" in a signed
token. Themis checks the token's signature, issuer, audience and expiry, accepts
only work accounts, and only from companies on the beta allow-list.

### 2.16 MCP (Model Context Protocol)

A standard way for AI assistants (Claude Code, other agents) to call tools. Themis
already exposes 13 **read-only** tools (`checker/mcp/`). The current specification
(2026-07-28) makes servers stateless and treats them as OAuth 2.1 resource servers;
PLAN_17 M9 upgrades to it. Rule kept: no agent can write, submit or attest.

### 2.17 DPDP Act and Rules

India's data protection law. The Rules were notified on 13 November 2025 with a
phased start: the Data Protection Board at once; consent managers from November
2026; the core obligations (consent, security, breach reporting, retention,
erasure) from **May 2027**. Customer documents contain other people's personal data
(directors' names, PAN, DIN), so counsel must advise before any of it is used for
evaluation or training.

---

## Part 3 — Reading order

### The code (about one day)

1. `README.md`, `CLAUDE.md`, `docs/NON_GOALS.md`
2. `checker/scope.py` — what is held and what refuses
3. `checker/obligations.py` — the heart of the deterministic core (skim)
4. `checker/as_of.py`, `checker/currency.py` — time
5. `checker/ask.py` then `web/assistant/contract.md` — the Ask contract
6. `checker/lawyer_summary.py` — span tracing, and its "what still gets through"
7. `checker/rings.py` — the firewall
8. `checker/operations.py`, `scripts/themis_slice.py --demo` — live events to work
9. `checker/mcp/tools.py` — how an agent sees Themis
10. `docs/RETRACTIONS.md`, `docs/FAILURE_MODES.md` — what went wrong, and why it matters

### The papers (in this order)

1. Magesh et al., *Hallucination-Free?* (J. Empirical Legal Studies, 2025) — the
   problem
2. Joren et al., *Sufficient Context* (ICLR 2025) — when to refuse
3. Gao et al., *ALCE* and Min et al., *FActScore* (EMNLP 2023) — citations and
   atomic facts
4. Angelopoulos & Bates, *A Gentle Introduction to Conformal Prediction* — the
   statistics, readable
5. Mohri & Hashimoto, *Conformal Factuality Guarantees* (ICML 2024) — the method
   for C1
6. Cherian, Gibbs, Candès (NeurIPS 2024) — the improvement
7. Miller, *Adding Error Bars to Evals* (2024) — how to report numbers honestly
8. Guha et al., *LegalBench* (NeurIPS 2023) and Joshi et al., *IL-TUR* (ACL 2024) —
   legal benchmarks, incl. India
9. The four 2025–26 temporal legal RAG papers in PLAN_16 §2.4 — the prior art for
   our currency paper

Links are in PLAN_16's source list.

---

## Part 4 — Glossary

| Term | Meaning here |
|---|---|
| Abstain / refuse | Say "cannot verify" with the reason, instead of answering |
| Attested | A person has checked an instrument's text and source and recorded it |
| Corpus | The law we hold: 529 Companies Act sections plus rules and notifications |
| Decider | Code that decides whether an obligation applies (Ring 0) |
| Evidence budget | The count of open blocking requirements on an operation |
| Held / declared | Law we have acquired vs. law we list as in scope but do not yet hold |
| Operation | Work created by an event (e.g. a Gazette notification), never a finding |
| Ring 0–3 | Legal core → company data → live feeds → predictions |
| Span | An exact piece of source text, identified by position |
| Tenant | One customer company |
| Vault | A customer's stored documents, under their control |
