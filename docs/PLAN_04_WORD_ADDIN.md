# The v1 product surface — a Word task-pane add-in

## Why Word, and why this is the whole product for v1

The research settles the delivery question. Harvey ships Word and Outlook
add-ins; Bloomberg Law's contract product lives inside Word. The adoption blocker
in Indian legal teams is **workflow fit and IT friction**, not price and not a
confidentiality veto — top Indian firms already send client-matter data to a US
cloud vendor.

And the distribution path is far lighter than expected: **admin-deployed via the
Microsoft 365 Admin Center requires no AppSource review, no Partner Center
enrolment and no public listing.** An IT admin uploads a manifest and pushes it to
named users. Live the same week.

## What it dodges

This is the reason to build it first. Every blocker the research surfaced applies
to *other* products, not this one.

| Verified blocker | Does the add-in hit it? |
|---|---|
| No MCA API, no verifiable authorised reseller | **No** — works on the open document |
| No Gazette feed | **No** — we serve only instruments we hold |
| OCR on scanned Indian paper | **No** — the file is already a `.docx` |
| No citator | **No** |
| IT procurement friction | **No** — admin-deployed |
| Confidentiality objection | **Reduced** — stays in the tenant |

**OCR becomes a v2 concern**, needed only for bulk review of scanned archives.
That defers the single largest technical risk without slowing the product.

## The one function

> **Check the document open in front of the lawyer against law current on the date
> that matters — and refuse where it cannot verify.**

This is the wedge already stated in `CLAUDE.md`: document generation is
commoditised, every firm's templates are a private fork drifting from the law,
and *the defect is only detectable at the output.* The add-in is where the output
is.

## The flow

```
[lawyer has a document open]
        │
        ├─ 1. EXTRACT           the facts the document asserts and the dates it turns on
        │                       (extraction_schema — model proposes, every span verified)
        │
        ├─ 2. DATE              which law was in force on the DOCUMENT'S date, not today's
        │                       (as_of — this is the step everyone else skips)
        │
        ├─ 3. DECIDE            applicability and obligations on those facts
        │                       (obligations, s185/186/188 — no model)
        │
        ├─ 4. CHECK CURRENCY    is every figure and rule relied on still in force?
        │                       (currency + staleness — the ₹4 crore check)
        │
        └─ 5. RENDER            three kinds of line, never blurred:
                                  ✓ verified   — cited, dated, sourced
                                  ⚠ superseded — the instrument that moved it, named
                                  ○ cannot say — what is missing, and the reference
```

Step 4 is the one no competitor performs. Step 5's third state is the product's
character: it is the line a lawyer trusts precisely because the tool declined.

## What renders in the sidebar

Three sections, in this order — worst first, because a reader scanning for risk
should not have to scroll past what is fine.

1. **Superseded** — "This document relies on ₹4 crore. G.S.R. 880(E) of
   01-12-2025 raised it to ₹10 crore." With the instrument, the date, and a link
   to the held artifact.
2. **Cannot verify** — the row, what is missing, and the acquisition reference.
   Never a silent omission.
3. **Verified** — collapsed by default. Each line carries provision, date and
   source hash.

**No score. No confidence percentage.** Status is ordinal — a prior safety
benchmark showed confidence scores inverting trust, and this repo already bars
them.

## What it must never do in v1

- Draft or edit the document. Reading and reporting is a different liability
  surface from writing, and mixing them on day one loses the argument that this is
  an audit layer.
- Show a green tick for the whole document. It covers a named set of obligations,
  not the whole Act. The pack already says this on its face; the sidebar must too.
- Send the document anywhere it does not need to go. The narration model (role 17)
  sees only the evidence pack, never the client's document body.

## Build shape

- **Frontend:** Office.js task pane, hosted as a static page over HTTPS.
- **Backend:** the existing `checker/api.py` `handle()` — already a pure function
  returning `(status, body)`, already testable without a server. One new route.
- **Auth/tenancy:** none in v1. A single design partner, admin-deployed.
- **Effort:** 2–6 weeks for an MVP by someone who knows Office.js. **This estimate
  is INFERRED — no credible sourced benchmark was found.** Treat it as a planning
  figure, not a commitment.

## The gate before any of it

**The four unacquired rules.** Today the pack answers 11 of 15 rows and refuses
four — s.2(85), s.177, s.188, s.203 — because the delegated rules behind them are
unheld or unreviewed. An add-in that refuses a quarter of its rows demos badly.

Acquiring and attesting those four is a day of human work and raises the quality
of every downstream surface at once. **It should happen before the add-in, not
after.**
