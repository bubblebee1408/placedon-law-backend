# Company profile — entered once, reused

Status: built (migration 032). Code: `gateway/company_profile.py`, `gateway/store/` (`memory.py`, `postgres.py`)
(`read_company_profile`, `set_company_profile`), `gateway/verbs/company.py` (`company_profile.get`,
`company_profile.set`, `_profile_facts`). Proof: `tests/test_company_profile.py`,
`scripts/company_profile_integration.py --run`.

## Why

The Company screen reads facts from an MCA master-data page (`company_facts.extract`) and
lets a person confirm each one, but nothing stored them: the browser kept them, colleagues
never saw them, and Calendar and every question asked for them again. `ask` and
`events.assess` already took `company_facts` per request. This stores the confirmed set once
per firm and reuses it.

## One profile per firm

The buyer is an in-house legal team, so the firm (tenant) **is** the company. One profile per
tenant; no matter is involved. **Per-matter profiles could be added later** (a law firm serving
several clients would need them) by adding a nullable `matter_id` and the 028 matter policies;
nothing in this schema forecloses that, and nothing builds it before there is such a buyer.

## Schema — `company_profile_facts` (032)

One row per confirmed fact:

| column | meaning |
|---|---|
| `field` | one of `checker/sources/company_facts.FIELDS` (cin, name, status, roc, address, state, incorporated_on, listed) or `company_class` |
| `value` | the confirmed value |
| `basis` | `USER_FACT` (typed) or `COMPANY_FACT` (read from an MCA page) |
| `source_label` | "you told us", or "MCA master data, as uploaded by the user on YYYY-MM-DD" |
| `quoted_span` | the source line, for a document fact; empty for a typed one (CHECK) |
| `uploaded_on` | the date the MCA page was uploaded; NULL for a typed fact (CHECK) |
| `confirmed_by`, `confirmed_at` | who said yes, and when |
| `reason` | why this change was made |
| `superseded_at`, `superseded_by` | set once, when a later save replaces or drops the fact |

The current profile is the rows with `superseded_at IS NULL`, at most one per field (partial
unique index). A save that changes or omits a fact **supersedes** its row and inserts a new
one; an unchanged fact keeps its row, so who confirmed it and when are not overwritten. A
trigger refuses DELETE and any edit except superseding a current row once. Nothing is removed.

## Which fields, and which not

* **The eight MCA fields** — the backend already models them with their basis, span and
  personal-data rules (`company_facts.CompanyFact`). Every rule there applies on save: no
  director name or DIN, a document fact must quote its line, a typed fact may not, only
  `listed`, `state` and `cin` may be typed.
* **`company_class`** (private, public, opc — `checker/company_profile.CompanyClass`) — the
  one field `calendar.upcoming` cannot run without that is a stable fact about the company and
  is not on the MCA page the extractor reads. Typed only. (The calendar screen also offers
  "section8", which the backend's `CompanyClass` does not have; the profile takes the
  backend's three.) Incorporation date is already `incorporated_on`.
* **Not here: paid-up capital, turnover, net worth, profit, borrowings, deposits.** In the
  obligations register each is a `Figure` bound to a financial year; a stored figure goes
  stale silently the next year, which is the guessed fact this engine refuses. No screen
  collects them today. Add them with their year when one does.
* **Not here: financial year end, director counts.** The calendar takes FY end as a dated
  anchor for one year; counts change. Both stay per use.

## Verbs

* `company_profile.get` — VIEWER. Current facts with provenance. Off MCP (company data).
* `company_profile.set` — LAWYER (admins inherit). Takes the **whole** profile as a list of
  confirmed facts plus a `reason` (at least 10 characters, as other access writes). An
  unconfirmed fact, a bad field, a mismatched label or a duplicate refuses the whole save.
  A write verb, so off MCP and audited by `gateway/app.py` like every write.

## What uses it

When a request carries **no** `company_facts` (the key is absent):

* `events.assess` reads the stored facts. This **changes answers**: a firm whose profile says
  listed now gets the SEBI bodies on every assessment. The response says
  `company_facts.from = "company_profile"`. A request's own `facts` win field by field and
  are named in `overridden_by_request`; an explicit `company_facts` (even `[]`) replaces the
  profile entirely.
* `ask` attaches the stored facts as `user_facts` with `user_facts_from = "company_profile"`.
  As with request facts they are shown, not used to build the answer. They are attached
  after the answer, so the answer cache stays fact-free and keeps serving hits.
* `conversation.send` needs no change: it dispatches to these verbs with the caller's context,
  so the fallback applies to its turns too.
* `calendar.upcoming` does not read it; the web screen pre-fills from it and the person can
  change any field per use.

## Firm isolation — proof

* RLS: ENABLE + FORCE, `tenant_isolation` on `app.tenant_id` (derived and asserted by
  `gateway/schema.py`). Restrictive insert and update policies require the row to be written
  as the connection's own actor, so nobody can confirm a fact in someone else's name.
* `scripts/company_profile_integration.py --run` (in CI, against a throwaway database as the
  NOBYPASSRLS app role): firm B reads none of firm A's facts through the verb or a raw
  SELECT, and firm B's `events.assess` and conversation turn are unchanged by A's profile;
  the database refuses DELETE, an edit and a forged `confirmed_by`.
