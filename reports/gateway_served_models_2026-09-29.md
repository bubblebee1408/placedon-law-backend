# The gateway on served models — 2026-09-29

Build-order step 4, with `ask` and `review_contract` calling the router's served Azure route
instead of running with no model.

**Server:** PostgreSQL 18.6 (Postgres.app), database `placedon_dev`, application role
`placedon_app` (NOSUPERUSER, NOBYPASSRLS).
**Model:** `azure:llama-3-3-70b`, the bake-off's fallback, degraded=true (Claude preferred,
no credit), region **UAE North**.

## review_contract — fixture N02, marked TEST DATA

    $ placedon review-contract --text "<NDA fixture N02>" --name N02 --test-data yes

    NDA-01  DEVIATES     'five years' (5) against the standard maximum '3 years' (3)
    NDA-02  MATCHES      'India' against the accepted list [...]
    NDA-03  MATCHES      'Mumbai' against the accepted list [...]
    NDA-04  MATCHES      present, which is the standard
    NDA-05  MATCHES      present, which is the standard
    NDA-06  MATCHES      present, which is the standard
    NDA-07  MATCHES      present, which is the standard
    NDA-08  MATCHES      the clause is absent, which is the standard
    NDA-09  MATCHES      the clause is absent, which is the standard
    NDA-10  MATCHES      'Rs 50,00,000' (5e+06) against the standard maximum '1 crore' (1e+07)

    unverified: []        requires_review: true     playbook: DRAFT

Real findings from a live model. N02 is the five-year fixture and NDA-01 is the deviation it
was built to produce. Nothing was UNVERIFIED: every value the model returned was re-derived
from a span that occurs in the contract.

## runs-trace — a SEPARATE process, reading Postgres

    intake     ANSWERED  provider=-      model=-                    region=-          cost=None
    document   ANSWERED  provider=azure  model=azure/llama-3-3-70b  region=UAE North  cost_inr=0.0
    playbook   ANSWERED  provider=-      model=-                    region=-          cost=None

`cost=None` on intake and playbook is not zero: no model was called on those steps. `0.0` on
`document` means a call WAS made and estimated at zero against `MONTHLY_CAP_INR` — Azure
credit is a separate pot no counter here watches.

## ask — a cited answer

    $ placedon ask --question "What is the time limit for holding an annual general meeting
                               under section 96?"
    PARTIAL   azure/llama-3-3-70b   degraded

    [1 of 4 sentence(s) the model wrote did not trace to admitted evidence and are not part
     of this summary. They are preserved in full below.]

    1. Not more than fifteen months shall elapse between the date of one annual general
       meeting of a company and that of the next.
       — Companies Act 2013, s.96 [226:348]
    2. The first annual general meeting shall be held within a period of nine months from
       the date of closing of the first financial year of the company.
       — Companies Act 2013, s.96 [409:524]
    3. The Registrar may extend the time within which any annual general meeting, other
       than the first annual general meeting, shall be held, by a period not exceeding
       three months.
       — Companies Act 2013, s.96 [845:1043]

## ask — a named refusal, on a different question

    $ placedon ask --question "How many meetings of the Board must a company hold in a year?"
    REFUSED   NOTHING_TRACED   dropped=2

    "all 2 sentence(s) the model wrote failed to trace to admitted evidence, so there is no
     summary. The sentences are preserved below as a record of what was refused."

    trace:  research  REFUSED  azure  azure/llama-3-3-70b  UAE North  cost_inr=0.0

The same question answered PARTIAL on an earlier call. A live model is not reproducible at
temperature 0, and the pipeline reports what happened on THIS call rather than smoothing it.
Both outcomes are named; neither is a silent UNVERIFIED.

## Persistence and isolation

    CLI tenant    runs=1 steps=2 propositions=4 regions=['UAE North']
    other tenant  runs=0 steps=0 propositions=0 regions=[]

## PLAN_22 D3 — test data only

A contract NOT marked test data is refused before anything is sent, naming the region:

    "this is a client document and the deployment region is 'UAE North', which nobody has
     confirmed as acceptable for client data (PLAN_22 D3). Set
     PLACEDON_ACCEPT_REGION='UAE North' to state that decision, or mark the document as
     test data. Nothing was sent."

Every contract in this report is a synthetic fixture from `agents/review_contract.fixtures()`.
No client document was sent, and while the deployment is in UAE North none may be.
