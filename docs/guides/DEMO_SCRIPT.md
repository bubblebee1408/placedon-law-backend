# Demo script — three contracts and three questions

**Measured 29-09-2026** against the live gateway: PostgreSQL 18.6, `azure/llama-3-3-70b`
deployed in UAE North, playbook `playbooks/nda_v1.json` (DRAFT). Every status and every
sentence below is what the system returned, twice, not what it is expected to return.

Nothing in this script is a client document. All three contracts are fixtures built in
`agents/review_contract.py`, and the `test_data` tick is the caller stating so — the model
is in UAE North and PLAN_22 D3 does not permit a client contract there.

---

## The contract set: three fixtures, all four statuses

Chosen so that each one differs from a clean NDA in exactly ONE way, and between them
every status the playbook can return appears at least once.

| Fixture | What is different about it | The status it demonstrates |
|---|---|---|
| **N02** | Term reads "five years" instead of three | `DEVIATES` |
| **N05** | Clause 1, the definition of Confidential Information, is cut out of the text | `MISSING` |
| **N06** | A non-compete is added as clause 9 | `NEEDS_LAWYER` |

`MATCHES` appears on every one of them — it is most of every run, which is the point.

### What each actually returned

**N02 — nine MATCHES and one DEVIATES.** 9 clauses read.

```
NDA-01  DEVIATES   'five years' (5) against the standard maximum '3 years' (3)
NDA-02 … NDA-10    MATCHES
```

The standard beside that row now reads *"Confidentiality lasts no more than 3 years from
signature."* with *"A longer obligation costs more to administer than it is usually worth,
and is the term most often negotiated down."* underneath. Both are DRAFT.

**N05 — one MISSING, and three rows that refuse to be graded.** 8 clauses read.

```
NDA-04  MISSING        the standard expects this clause and none was extracted
NDA-05  NEEDS_LAWYER   the value could not be re-derived from a verbatim span
NDA-06  NEEDS_LAWYER   ” 
NDA-07  NEEDS_LAWYER   ”
```

The three `NEEDS_LAWYER` rows are not in the offline fixture's expectations, and they are
**reproducible** — the same three appeared on both live runs. The live model proposed spans
for those clauses that span verification could not find in the document, so the pipeline
refused to grade them rather than grade a value with no evidence behind it. A demo should
show this rather than hide it: it is the mechanism working, and the "Not graded" panel
below the table is where it is explained.

It is also a real signal about extraction, not only about the demo: deleting one clause
from a contract made three OTHER clauses fail verification. That is worth chasing, and it
is not chased here.

**N06 — one NEEDS_LAWYER, by rule rather than by accident.** 10 clauses read.

```
NDA-08  NEEDS_LAWYER   present, and not in the approved list. Code cannot decide whether
                       this form is acceptable; a person has to look
NDA-01 … NDA-10 (rest) MATCHES
```

This is the `NEEDS_LAWYER` to demonstrate, because the rule is *designed* to return it. The
ones on N05 come from a failed extraction and could change with the model; this one comes
from `must_be_absent_or_approved` and will not.

---

## The three questions

| # | Question | What comes back |
|---|---|---|
| 1 | What is the quorum for a meeting of the Board under section 174? | `ANSWERED` — every sentence traced |
| 2 | What is the time limit for holding an annual general meeting under section 96? | `PARTIAL` — some traced, some dropped |
| 3 | What are the penalties for insider trading under the SEBI PIT Regulations? | `REFUSED` — `NO_EVIDENCE` |

### 1. A cited answer

Two sentences, both traced, both from `Companies Act 2013, s.174`:

```
1. The quorum for a meeting of the Board of Directors of a company shall be one-third of
   its total strength or two directors, whichever is higher.        — s.174 [4:146]
2. The participation of the directors by video conferencing or by other audio visual
   means shall also be counted for the purposes of quorum.          — s.174 [147:311]
```

Reason line: *every sentence traced*. Identical on both runs, spans included.

### 2. A partial answer

Status `PARTIAL`, reason *3 sentence(s) traced, 1 dropped as unsupported*. The header on
screen reads "Partial answer" and the body opens with the count of what was dropped, before
the sentences that survived.

**The counts move between runs and must not be quoted as a figure.** Both runs on
29-09-2026 gave 3 traced and 1 dropped; a run earlier the same day, through the browser,
gave 1 traced and 1 dropped on the same question. The model writes a different number of
sentences each time, so a different number survive grounding. What is stable is the
STATUS and the fact that the dropped ones are counted rather than quietly removed.

### 3. A named refusal

Status `REFUSED`, code `NO_EVIDENCE`, no model called, cost `UNPRICED`:

> retrieval abstained: the question cited nothing this corpus resolves, so no model was
> called. That is not the same as there being no such provision.

Say the second sentence out loud during a demo. It is the difference between this and a
system that answers everything.

Two alternates, both refused the same way if a second is wanted: *"What stamp duty is
payable on a share transfer in Maharashtra?"* and *"How many meetings of the Board must a
company hold in a year under section 173?"* — the second is worth knowing about because it
is a **Companies Act** question, inside the held corpus, that retrieval still could not
resolve. It refuses rather than guesses, which is correct, but it is a retrieval gap and
not a scope one.

---

## Running it

The console is the website repo's /app section; its RUN_LOCALLY runbook has the exact
commands to start Postgres, the gateway and the web app. In short: start the database,
start the gateway, start the web app, open `/app`.

Then, in order:

1. **Ask** → paste question 1. Point at the bold **Section 174** and the mono evidence line
   beneath it: the claim and its basis are set in different type on purpose.
2. **Ask** → paste question 2. Point at "Partial answer" and the dropped count.
3. **Ask** → paste question 3. Point at the grey abstain register and the refusal code.
4. **Contracts** → tick *"This is a test document"*, paste N02, Review. Nine MATCHES, one
   DEVIATES, and the standard column filled on every row.
5. **Contracts** → N05. The MISSING row, then the "Not graded" panel.
6. **Contracts** → N06. The NEEDS_LAWYER row, and the sentence that says code has no view.
7. **Runs** → open the last run's trace. Three steps, the model, UAE North, and the rupee
   cost with the price query it came from. Two steps read `UNPRICED`, which is not zero.

The fixture text for N02, N05 and N06 is generated by `fixtures()` in
`agents/review_contract.py`; print one with
`PYTHONPATH=. python3 -c "from agents.review_contract import fixtures; print({f.id: f.text for f in fixtures()}['N02'])"`.

## What not to say while demonstrating this

- Not "the system found a problem with this contract." It found a difference from a
  **DRAFT playbook no lawyer has approved**, and the screen says so on every run.
- Not any accuracy or hallucination rate. There is no benchmark behind one.
- Not "it costs about X per review." The same review cost ₹0.0473 and ₹0.0492 minutes
  apart. Costs on that screen are per-run facts.
- Not "it abstained, so there is no such provision." The refusal text explicitly says that
  is not what it means.
