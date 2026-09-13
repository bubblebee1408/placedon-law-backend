# Handoff — acquire the Prospectus and Allotment Rules 2014

**Automation stopped safely. This needs a human with a browser. It is a 10-minute task.**

Sibling of [ACQUISITION_HANDOFF_board_rules_2014](ACQUISITION_HANDOFF_board_rules_2014.md),
and it follows the same policy: [ACQUISITION_POLICY](ACQUISITION_POLICY.md).

---

## Why this one is worth doing first

It is the only outstanding acquisition that converts a **refusal into an answer** on a
screen a buyer looks at.

| | Before | After |
|---|---|---|
| `assess("paid_up_capital")` | `UNBOUNDED_BLIND` — no width, names this rule | `BOUNDED_BLIND`, floor at *N* days |
| `capital_headroom()` on an allotment that fits | `UNRESOLVABLE` | **`AGREES`** |

That second row is the demo. Today the strip says *"it fits the register's headroom, which
is an upper bound only"* — correct, and unsatisfying. After attestation it says the
allotment fits, and still carries the bound.

Both states are tested (`checker/mca_reconcile.py`, "acquiring and attesting the Allotment
Rules turns this refusal into an answer"), so the payoff is wired, not promised.

---

## Why automation cannot finish this

Same wall as every other Indian primary source, and `CLAUDE.md` forbids going around it:

> Do not bypass the MCA WAF, robots restrictions, access controls, or source terms.

`mca.gov.in` returns 403 to us. India Code serves files from static addresses that are
*discovered* through dynamic pages, and those 403 as well. A browser session is not subject
to the same block. This is a permission boundary, not a technical one, and the correct
response to it is a person, not a workaround.

---

## What to get

**The principal Rules** — *"The Companies (Prospectus and Allotment of Securities) Rules,
2014"*, notified 31 March 2014.

**Not an amendment.** The titles differ by one word, and this trap has already cost this
repository real time:

- ✅ `Companies (Prospectus and Allotment of Securities) Rules, 2014`
- ❌ `Companies (Prospectus and Allotment of Securities) **Amendment** Rules, 2018`
- ❌ `... **Second Amendment** Rules, ...`

An amendment says *"further to amend"* and consists of substitutions. It does not contain
rule 12 whole, so registering one would record a fragment as the principal rule. The script
refuses this automatically — but knowing it saves you a download.

**Where to look**, in order of preference:
1. `egazette.gov.in` — the Gazette is primary and settles the question
2. `indiacode.gov.in` — the live host (**not** `.nic.in`, which is dead)
3. `mca.gov.in` → Acts & Rules → Rules

---

## What the script checks, so you do not have to

```bash
python3 scripts/register_pas_rules.py ~/Downloads/pas_rules_2014.pdf
```

| Check | Outcome if it fails |
|---|---|
| Title carries "Prospectus and Allotment of Securities" | `WRONG_INSTRUMENT` |
| Carries the year 2014 | `WRONG_INSTRUMENT` |
| Is not an Amendment sharing the title | `WRONG_INSTRUMENT` |
| Rule 12 names a period **and** Form PAS-3 | `CLAUSE_NOT_FOUND` |
| Text extracted at all | `UNREADABLE` |

**Nothing is written unless every check passes**, and the file is stored verbatim with a
SHA-256. No repair, no normalisation, no reflow.

**The period is read out of the file, not assumed.** There is no thirty-day constant
anywhere in the script. If the page says sixty, the record says sixty, and the bound in
`mca_snapshot` becomes sixty. A number typed in from memory would be exactly the unsourced
claim this project exists to refuse.

---

## Then the part only you can do

```bash
python3 scripts/register_pas_rules.py --attest <your-reviewer-id>
```

You are certifying three things. Read them before typing it:

1. **Identity** — this file is the principal Rules, not one of the Amendment Rules.
2. **Clause** — the period and form recorded match the words on the page. The script prints
   both; check them against the PDF with your own eyes.
3. **Currency** — no later amendment substituting rule 12 was found, or the ones found are
   named in the record.

**A script attesting to itself defeats the whole design.** Two human checks are what
separate a stored file from usable law here, and the second check is you.

---

## Verify it took

```bash
./scripts/run_tests.sh
```

`checker/mca_snapshot.py` should now report `BOUNDED_BLIND` for paid-up capital, and
`checker/mca_reconcile.py`'s headroom rule should reach `AGREES`.

---

## The other one, when you have time

**Companies (Appointment and Qualification of Directors) Rules, 2014, rule 12A** — DIR-3
KYC. It bounds `din_status` the same way. Lower value: it does not turn a refusal into an
answer, it only lets us say more than *"the register says so"* about a deactivated DIN.

Worth noting what it does **not** buy. The correction in `checker/mca_reconcile.py` — that
a deactivated DIN does not vacate the office, because s.167(1) is a closed list that does
not reach the status of a DIN — rests on the **Act**, which we already hold. Acquiring
rule 12A would not change that answer. It would only bound the staleness of the status.
