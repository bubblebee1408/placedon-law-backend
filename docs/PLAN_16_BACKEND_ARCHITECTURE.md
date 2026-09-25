# PLAN 16 — the backend a user actually meets

Started 25-09-2026. **This is the spine, not the finished plan.** Three research streams are
running (token economics, vault/verification architecture, compliance + DPDP); their numbers land in
the slots marked ⟨RESEARCH⟩. What is written here are the decisions the repository has already made
and must not casually unmake.

---

## 0. The rule this plan is subordinate to

The product's claim is not "we answer legal questions". It is **"the model explains, the code
decides, the record verifies."** Every architectural choice below is judged against whether it keeps
that true under load, under cost pressure, and under a customer asking for a faster answer.

Three existing mechanisms enforce it and are **not up for renegotiation**:

| Mechanism | File | What it forbids |
|---|---|---|
| The ring firewall | `checker/rings.py` | Ring 0 cannot import ML. A prediction can never become a legal determination by accident. 36/36 tests, including transitive and dynamic imports. |
| The admission gate | `checker/admission.py` | Nothing is servable until `production_usable` is true. Today that is **one** instrument. |
| The calibration contract | `checker/calibration_contract.py` | No probability is shown to a user until its calibration is measured. |

A feature that needs one of these relaxed is not a feature; it is a different product.

---

## 1. What already exists, so we build on it rather than beside it

- **`backend/budget.py`** — runtime budget enforcement before every model call. Already has a
  `PRICING` table, `cost_inr()` with batch discount, a `Verdict` (allowed / mode / reason /
  spent_today / spent_month), a `Store` **Protocol** with a `FileStore` implementation, and three
  modes: `normal · budget · offline`.
  Two of its design rules carry into everything below:
  - **"A budget guard must only ever be wrong in the expensive direction."** It deliberately encodes
    list price, not the discount we currently receive, because a guard that under-estimates silently
    starts admitting calls it should refuse the day a promotion ends.
  - **Exhaustion is not an error.** The product degrades to template mode and says so. Never a
    silent failure, never a guess.
- **`checker/mcp/`** — thirteen read-only tools, `_policy` and `_boundary` on every response, no
  write of any kind. Structurally a BYOMCP server (see `docs/research/CONNECTORS_AND_THE_WHITE_SPACE_2026_09_25.md`).
- **`checker/operations.py`** — a watchlist can trigger an operation; operations create four task
  types; `EvidenceBudget` is a named count, not a score.
- **`scripts/serve_ask.py`** — the demo server, loopback only, refusing uploads by field name.

`budget.py`'s `Store` Protocol is the seam. Per-tenant metering is an implementation of it, not a
rewrite.

---

## 2. Tokens — the questions, and which are already answered

| Question the founder asked | Status |
|---|---|
| How many tokens should we use per user? | ⟨RESEARCH⟩ — needs the worked cost model |
| Where are tokens stored? | **Decided in shape**: `Store` Protocol. `FileStore` today; Postgres/Redis behind the same interface. The logic does not change. |
| What does "unlimited" mean? | ⟨RESEARCH⟩ — but see §2.1: it cannot mean unmetered |
| Rate limiting | ⟨RESEARCH⟩ for algorithm; **decided** that a refusal must be a stated mode, not a 500 |
| How long a context can we handle? | ⟨RESEARCH⟩ — and note the correctness hazard in §2.2 |

### 2.1 "Unlimited" is a pricing word, not an architecture word
Whatever is sold, the backend meters. The reason is not commercial, it is evidential: a bill a
customer disputes must be explainable **per user action** — one document check, one summary — not
per raw API call. That means the usage event is keyed to the action, and the model calls hang off
it. Designing it the other way round makes the bill unexplainable and the cost unattributable.

### 2.2 Caching has a correctness hazard specific to us
A result cache keyed on document hash is the obvious win and it is **dangerous here**: the same
document, asked the same question, has a *different correct answer* after the law changes. Any cache
key must include the **law version** (`checker/currency.py`'s as-of), or we will serve a confident
answer about superseded law — the exact failure the product exists to prevent, arriving through an
optimisation. ⟨RESEARCH⟩ fills in the rest of the caching strategy; this constraint binds it.

---

## 3. The funnel — how a customer's data gets in

The founder's model is Harvey's: the user connects their systems and works inside our workspace.
Research already settled the hard part, and the answer is uncomfortable:

- **MCA21 has no OAuth, no delegation and no API.** A customer *cannot* connect their MCA account.
  The only documented lawful inbound route for filing data is **customer-in-the-loop upload** — they
  fetch the document from MCA21 themselves and give it to us.
- Document systems (Microsoft Graph, Google Workspace, iManage, NetDocuments, DocuSign) *are*
  connectable by OAuth, and Graph is first by install base among Indian CS and in-house teams.

**This forces a decision the prototype has so far avoided.** `serve_ask.py` refuses uploads by field
name, deliberately and well. But if customer-in-the-loop upload is the only lawful path for filing
data, then a vault is not a feature we might add — it is the only inbound door that exists. The
refusal was right for a demo with no storage story; it cannot survive contact with a real customer.

What a vault obliges us to build, none of which exists today: per-tenant isolation and encryption,
retention and deletion, an audit trail, and a DPDP position on sending a client's document to a
US-hosted model. ⟨RESEARCH⟩ on all four.

---

## 4. The dashboard — what it may show

Constrained by the admission gate, not by design taste. A dashboard may show an obligation only if
its instrument is `production_usable`. **Today that is one instrument**, and the honest dashboard is
correspondingly small.

⟨RESEARCH⟩ supplies the real Companies Act compliance calendar — obligation, section, trigger,
deadline rule, form, consequence. Two design rules already apply to it:

1. **A deadline is computed, not stored.** "Within 30 days of the AGM" is a rule; the date is
   derived from a fact the customer supplied, and the derivation must be shown.
2. **An obligation we cannot decide must read as undetermined, never as compliant.** D3's finding —
   an invented `company_class` silently deciding s.2(85) — is the shape of this failure, and it
   reached a card that said nothing was decided.

---

## 5. Open questions this plan must close before any feature is built

1. Vault or no vault — and if yes, the DPDP and confidentiality position, in writing.
2. The context strategy: retrieval, long-context, or hybrid, decided on measured cost and measured
   accuracy rather than on preference.
3. Where the model call lives: request path, queue, or batch — and the latency a lawyer tolerates.
4. What "unlimited" is sold as, and what the meter does underneath.
5. Whether the MCP server becomes a distribution channel (OAuth 2.1 + PKCE, remote transport) before
   or after the first paying customer.

Nothing in §5 is a coding task yet. Each is a decision with a cost attached, and the research
running now is what attaches the costs.
