# Integrations checklist — every key and permission, in the order to get them

Written 5 Oct 2026 as move 18 of the overnight runbook. This is **tomorrow's agenda**.

Each row says: where the credential goes, which verb it unlocks, who issues it, and what it
costs. **Where a figure is not confirmed from the provider's own page, this document says
UNVERIFIED rather than a number.** A checklist with a plausible invented price is worse than
one with a gap, because the gap gets checked.

`.env.example` is the machine-readable half: every variable the code actually reads, swept
from `os.environ` lookups rather than written from memory.

## The one rule that applies to all of them

**A missing key is never an empty result.** Every connector raises `KEY_MISSING`
(`checker/sources/connector_base.py`) rather than returning `[]`, because an empty list
already means "we searched and found nothing" — and an abstention built on that would be a
verified product state resting on a fiction. So an unkeyed integration is *visibly* unkeyed,
and nothing in this list can half-work.

## Order of acquisition

The order is by **what unblocks the most, soonest**, not by cost.

| # | Integration | Unblocks | Effort |
|---|---|---|---|
| 1 | AWS Bedrock (ap-south-1) | every model path, in-region | account + model access request |
| 2 | AWS S3 (ap-south-1) | the vault on a real deployment | minutes, once the account exists |
| 3 | data.gov.in (OGD) | company master data without scraping | self-serve key |
| 4 | Indian Kanoon | case law as LICENSED support | commercial contact |
| 5 | AWS Textract (ap-south-1) | scanned documents (`CANNOT_READ` today) | account; per-page cost |
| 6 | API Setu / DigiLocker | the official-record checks in `document.verify` | organisation onboarding |
| 7 | GST Suvidha Provider | GSTIN verification | commercial contract |
| 8 | SHCIL / e-stamping | stamp-duty questions | commercial, state by state |
| 9 | EBC / commentary | secondary sources | publisher licence |

---

## 1. AWS Bedrock — ap-south-1 (Mumbai)

| | |
|---|---|
| **Goes in** | the AWS credential chain (role preferred, not a static key in `.env`) |
| **Unlocks** | every model path: `ask`, `review_contract`, `review_document`, `review_grid_cell`, the MA1 workers, the critic |
| **Issued by** | AWS, per account; **model access is a separate request per model family** |
| **Cost** | per input/output token, per model. **UNVERIFIED here** — read the Bedrock pricing page for ap-south-1 on the day |
| **Blocks today** | a review table cell cannot reach FOUND: it dispatches, the worker claims it, and the cell fails `NO_MODEL` |

Held until you say "AWS is ready" (job B1). Two things to get right on the day:

- **ap-south-1, not us-east-1.** The standing rule is AWS Mumbai for everything in
  production. `backend/budget.py` prices per model and refuses to record `0.0` for a billed
  provider — in Python and again as a database CHECK — so a model with no price on record
  reports `UNPRICED` rather than free.
- **Model access is not account access.** A fresh account can call no model family until each
  is requested, and the request is not instant. Do this first.

## 2. AWS S3 — ap-south-1

| | |
|---|---|
| **Goes in** | the AWS credential chain; bucket name in the deployment config |
| **Unlocks** | `gateway/filestore.S3FileStore` — the vault on anything that is not a laptop |
| **Issued by** | AWS |
| **Cost** | storage + requests. Small relative to models. **Figure UNVERIFIED** |

`LocalFileStore` is what the local runbook (`RUN_LOCALLY.md`, arriving with PR #67)
uses and is fine for one machine. Note
the defect found on 5 Oct: `LocalFileStore.get` returns `None` for a key it does not hold
rather than raising, and `document.verify` now checks for that explicitly — **confirm
`S3FileStore` does not have the same shape** before trusting it.

## 3. data.gov.in (OGD)

| | |
|---|---|
| **Goes in** | `PLACEDON_DATA_GOV_IN_KEY` |
| **Unlocks** | `checker/sources/data_gov_in.py`; company master data at tier OFFICIAL_LIVE |
| **Issued by** | data.gov.in, self-serve on registration |
| **Cost** | no charge for the key. Rate limits apply — **the limit is UNVERIFIED**, read the API page |
| **Terms** | recorded in `checker/sources/terms.py` as `data_gov_in` |

Two things already true in the code and worth knowing before you use it:

- A **`resource_id` is required** per query. There is no default dataset, deliberately: a
  default would let a caller read a different dataset from the one it believed, and the rows
  would look fine.
- Its **ATTRIBUTION clause is recorded `OPEN`** — meaning nobody has read it. An unread term
  is OPEN, never assumed permissive. **Read that clause before the first production use**, and
  the connector will start carrying it automatically, because the attribution comes from the
  terms record rather than from a string in the connector.

## 4. Indian Kanoon

| | |
|---|---|
| **Goes in** | `PLACEDON_INDIANKANOON_KEY` |
| **Unlocks** | `checker/sources/indiankanoon.py`; case law at tier LICENSED |
| **Issued by** | Indian Kanoon, by commercial arrangement — not self-serve |
| **Cost** | **UNVERIFIED.** Their API terms mention per-call pricing; get it in writing |
| **Terms** | recorded as `indiankanoon`, including the RAG-and-logo attribution clause |

**LICENSED can never make an answer VERIFIED.** Enforced in code since move 7: a sentence
quoting a real, byte-matched span of a judgment is refused `TIER_CANNOT_VERIFY`, and the
refusal says the citation was good and the tier was not. So case law can *support* an answer
and never *be* one.

Attribution is not optional and not ours to word: `terms.attribution_for` returns the clause's
own quoted text and `evidence.Evidence` refuses a LICENSED row without one.

## 5. AWS Textract — ap-south-1

| | |
|---|---|
| **Goes in** | the AWS credential chain |
| **Unlocks** | documents currently `CANNOT_READ` — a scan with no text layer |
| **Issued by** | AWS |
| **Cost** | **per page.** Figure UNVERIFIED; this is the one on the list most likely to surprise, because a diligence set is thousands of pages |

`vault.status` already counts `unsearchable` documents, so the size of this problem is
measurable before paying for it. **Measure it first.**

## 6. API Setu / DigiLocker  `[NEEDS FOUNDER]`

| | |
|---|---|
| **Goes in** | not yet in `.env.example` — nothing reads it, because nothing is built |
| **Unlocks** | the two official-record checks in `document.verify`, both `NOT_CHECKED` today |
| **Issued by** | NeGD / MeitY, by organisation onboarding — **not a signup form** |
| **Cost** | **UNVERIFIED**; onboarding is the cost, in time |

This is the one that changes what the product can *say*. `document.verify` reports
`official_issuer_match` and `official_record_match` as `NOT_CHECKED` with the reason named, so
**a genuine document reports INCOMPLETE_VERIFICATION today** — correct, because COMPLETE would
claim we established something we did not look at.

One consequence to plan for, recorded in `.claude/loops/DECISION_document_checks_table.md`:
the moment an official-record check reaches a live registry, its answer **depends on when it
was asked**, and an unstored answer becomes unrecoverable. That is the trigger to store the
individual check lines in `document_checks`, which today are deliberately derived.

## 7. GST Suvidha Provider

| | |
|---|---|
| **Goes in** | nothing reads it yet |
| **Unlocks** | GSTIN verification; `checker/doc_classifier.py` already classifies invoices |
| **Issued by** | a licensed GSP — commercial contract, not a public API |
| **Cost** | **UNVERIFIED**, per-call plus a subscription in most offers |

## 8. SHCIL / e-stamping

| | |
|---|---|
| **Goes in** | nothing reads it yet |
| **Unlocks** | stamp-duty questions — which `checker/scope.py` currently REFUSES by name |
| **Issued by** | Stock Holding Corporation of India, state by state |
| **Cost** | **UNVERIFIED** |

Note the scope interaction: the Stamp Act is DECLARED and not HELD, and
`scope.py`'s report says *"DECLARED is an active refusal, not a weaker form of HELD"*. A
stamping integration gives us *facts about a document*, not the *law*. Do not let one be
mistaken for the other: `checker/doc_validity` would still return `NOT_DETERMINED` for a rule
resting on the Stamp Act, and that is correct.

## 9. EBC / commentary

| | |
|---|---|
| **Goes in** | nothing reads it yet |
| **Unlocks** | secondary sources |
| **Issued by** | Eastern Book Company, publisher licence |
| **Cost** | **UNVERIFIED** |

Lowest priority on purpose. Commentary is somebody's reading of the law, so it could only
ever be LICENSED at best — it can support and never verify — and we do not yet hold the
primary text of most bodies it would discuss.

---

## Not a key, but on the same list

These block work and are not credentials:

- **A per-document-class validity rule table** (A-021). `document.check` returns
  NOT_DETERMINED for every document because nothing says which class expires under which
  provision. **Needs counsel, not code** — and deliberately not solved by accepting a rule
  from the caller, because nothing checks a caller's quote against the held corpus.
- **Which identifier a review table speaks** (A-018). A grid addresses documents by content
  hash and the vault by uuid; the console cannot turn one into the other without carrying the
  hash itself. **A product decision.**
- **The unheld bodies of law** (G0.3, still blocked). Seven bodies are DECLARED and not HELD.
  Until their primary text is acquired, `scope.py` refuses questions about them by name,
  which is the honest answer and also a limit on what any of the above can unlock.

## What to check after each key lands

1. `./scripts/verify_green.sh` — the gate, before anything else.
2. The connector's own suite: with the key set it should parse a **fixture**, not reach the
   host. No test in this repository makes a network call, and both connectors assert by AST
   that they import no HTTP client.
3. `backend/budget.py` — a newly billed provider with no price on record reports `UNPRICED`,
   never ₹0.00. Add the price in the same change that adds the key.
4. `checker/sources/terms.py` — if a term was `OPEN` and you have now read it, record the
   clause **verbatim**. An unread term is OPEN; a summarised one is worse than unread.
