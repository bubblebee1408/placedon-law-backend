# Tenancy, retention, and what to charge for

Researched 2026-09-10. Written now, before the persistence layer exists, because
every constraint here is cheap to design in and expensive to retrofit.

## 1. The line that should govern the whole persistence design

Harvey published why they built their own agent runtime. This is the load-bearing
sentence:

> *"There is a tempting shortcut — store data during the run and call a deletion
> endpoint afterward — but that isn't zero retention; it is **retention followed
> by deletion**."*
> — [harvey.ai, why we built our own cloud agent infrastructure](https://www.harvey.ai/en-US/blog/why-we-built-our-own-cloud-agent-infrastructure)

And on why standard cloud agent services do not fit:

> *"Every law firm and enterprise contract Harvey signs requires ZDR… ZDR means
> designing the runtime so customer data is not written into durable application
> storage by default."* … *"The agent's entire lifecycle runs inside our security
> boundary. State is scoped to the session and purged."*

**The consequence for us is a rule, not a preference: a client document must never
be written to durable application storage.** Working state — the document text, an
extractor's proposals, retrieved spans — lives in memory for the request and dies
with it. What may persist is what carries no client content: the *result* of a
check, hash-stamped, and our own corpus.

This is a runtime discipline, not a product you can buy. The LLM providers' own
ZDR settings cover *their* logging, not our application's state store.

## 2. Tenancy — and a correction to the obvious answer

Microsoft's Azure Architecture Center uses **legal software as its canonical
example** of a workload where "a deployment always contains a single tenant",
because customers "insist on having their own dedicated infrastructure to
maintain compliance." That reads like a mandate for database-per-tenant.

**But the market leaders do not do that**, and their own security pages say so:

| Vendor | What they actually state |
|---|---|
| **Harvey** | *"Customer data for each customer is **logically separated** to prevent any commingling"* — shared infrastructure, logical isolation. Azure-hosted. SOC 2 Type II, ISO 27001, ISO 42001 |
| **SpotDraft** | *"logically separated **within a secure multi-tenant infrastructure**"* — GCP, with data residency in US, EU, **India**, Middle East |
| Relativity | discloses FedRAMP for its Government offering; isolation architecture behind a gated whitepaper — UNVERIFIED |
| iManage / NetDocuments | no public statement found — **UNVERIFIED, not "they don't"** |

So the isolation lever these vendors actually *sell* is **logical separation +
regional residency + certifications**, not dedicated infrastructure. Dedicated
infra appears to be an enterprise upsell, not the default.

**What to build:** shared application tier, **dedicated schema (or database) per
firm** at the data layer, and the ephemeral rule from §1 applied to everything
carrying client content. That is stronger than what Harvey advertises, cheaper
than database-per-tenant, and it is defensible in a security review without a
sales conversation. Cell-based blast-radius sharding is a later problem and a
reliability concern, not a confidentiality one.

## 3. India — DPDP, and where the burden actually falls

- **No blanket data-localisation mandate.** DPDP 2023 uses a **blocklist**:
  transfers are permitted except to countries the government restricts by
  notification — the inverse of GDPR's adequacy model. So India-hosting is a
  trust and procurement argument, not a legal requirement.
- **The statutory burden sits on the Data Fiduciary** — our *customer* — not on
  us as processor. They will flow security, breach-notification and accuracy
  obligations down to us contractually, and the headline penalties (reported
  minimum ₹50 crore) attach mainly to them. **That shapes the sales
  conversation:** we are not asking them to accept our risk, we are reducing
  theirs.
- **UNVERIFIED and worth closing with counsel:** the exact processor-obligation
  sections. The primary Gazette PDFs were unreachable; a law-firm client alert is
  the better route than the gazette.

## 4. Pricing — and the trap our own product creates

Every vendor that could be verified prices the same way: **sales-quoted, seats
and/or a volume metric, never tokens or queries.** No verified vendor publishes a
metered price list. Harvey and Legora publish no pricing at all; SpotDraft states
per-user or contract-volume.

**The trap, and it is specific to us.** This product's distinguishing behaviour is
that it *refuses* when it cannot verify. Price per query, per answer or per token
and the incentive inverts: **the business earns more when the system is more
confident, and less when it correctly abstains.** A pricing model that punishes
the product's central virtue will eventually bend the product.

So the metric must be **orthogonal to whether we answered or refused**:

| Charge on | Why it is safe |
|---|---|
| Seats | Unrelated to answer rate |
| Documents checked | A refusal is still a check, and still the answer they needed |
| Companies / matters monitored | The monitor's value is the watching, not the alerting |
| **Never** per answer, per query, per token | Rewards false confidence; punishes correct refusal |

**"Documents checked" is the right primary metric.** A document where we say *"this
relies on a threshold that moved on 01-12-2025"* and a document where we say *"we
cannot verify this without G.S.R. 880(E)"* are worth the same to the lawyer — both
stopped them relying on something unchecked — and should be worth the same to us.

## 5. Honest gaps

Flagged rather than filled:

- **Indian procurement thresholds and typical deal sizes — not found.** No
  sourced figure. Direct conversations with three to five target buyers will
  beat public sourcing here anyway.
- **No named precedent for pricing an abstention-heavy product.** The observed
  seat+volume pattern is structurally compatible, but that is circumstantial, not
  a precedent.
- **Anthropic's and Google's formal ZDR mechanics** — Anthropic's terms state
  customer content is not trained on and set a 30-day post-termination deletion,
  but a named ZDR toggle equivalent to OpenAI's `store=false` was not confirmed.
- **iManage / NetDocuments isolation architecture** — no public statement found.
