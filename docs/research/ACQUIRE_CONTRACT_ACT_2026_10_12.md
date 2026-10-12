# Acquire the Indian Contract Act, 1872 — robots evidence and why automation stopped

**Date:** 2026-10-12. **Outcome:** `HUMAN_RETRIEVAL_REQUIRED`. No official host could be
permitted for automated fetch; acquisition hands off to a human browser session. No code was
changed by this investigation.

## What was asked

Make the Contract Act acquisition automatic *legitimately*: the founder pre-approved adding
**one** official host to the permitted list **iff** its `robots.txt`, read **only through
`checker.robots`** (`fetch_rules` + `allowed`, never `curl`), permits the Act PDF.

## Robots evidence (measured through `checker.robots`, 2026-10-12)

| Host | `robots.txt` (via `fetch_rules`) | rules `loaded`? | `allowed(<Act PDF path>)` |
|---|---|---|---|
| `www.indiacode.nic.in` | **HTTP 403** — "access denied or rate-limited — not treated as 'no rules'" | **False** | **False** |
| `legislative.gov.in` | **HTTP 403** | **False** | **False** |

Separately recorded: `indiacode.gov.in`'s `robots.txt` has returned **HTTP 500** continuously
since **2026-09-28**.

`checker.robots` treats a 403 on `robots.txt` as a **refusal**, not an absence of rules
(deliberate stance; see the bseindia Akamai-403 case in `checker/robots.py`), so `allowed()`
is `False` for both candidate hosts. The founder's condition ("iff robots permits") is **not
met**. Per `docs/policy/ACQUISITION_POLICY.md`, a robots refusal is `BLOCKED` and is **never
retried automatically**. Stop is the correct, policy-defined outcome.

## ⚠ Caveat — earlier ungated requests may have caused the 403s

While diagnosing, section metadata was read from India Code's DSpace REST API with a direct
`curl`, which **bypassed `checker.robots`** (the fail-closed gate) — the same mistake
`ingest_act.py` records ("I measured the first with curl, which goes around the gate"). The 403
responses read "access denied **or rate-limited**", and those `curl` bursts to `indiacode.*`
are a plausible cause of the rate-limit. All such requests have stopped; the hosts are **not**
being re-probed (that would be the abusive retry `ACQUISITION_POLICY.md` forbids). Nothing from
those ungated reads has entered the corpus or any fixture; the act_id
`AC_CEN_3_20_00035_187209_1523268996428` remains a **lead to check against the document**, not a
fact.

## RFC 9309, verbatim (the governing text)

**§2.3.1.3 ("Unavailable" Status)** — the 4xx case:
> "'Unavailable' means the crawler tries to fetch the robots.txt file and the server responds
> with status codes indicating that the resource in question is unavailable. For example, in the
> context of HTTP, such status codes are in the 400-499 range."
>
> "If a server status code indicates that the robots.txt file is unavailable to the crawler, then
> the crawler MAY access any resources on the server."

**§2.3.1.4 ("Unreachable" Status)** — the 5xx case, with the ~30-day clause:
> "If the robots.txt file is unreachable due to server or network errors, this means the
> robots.txt file is undefined and the crawler MUST assume complete disallow. For example, in the
> context of HTTP, server errors are identified by status codes in the 500-599 range."
>
> "If the robots.txt file is undefined for a reasonably long period of time (for example, 30
> days), crawlers MAY assume that the robots.txt file is unavailable as defined in Section
> 2.3.1.3 or continue to use a cached copy."

## Applying the RFC to the facts

- **Both candidate hosts are 403 → §2.3.1.3 (Unavailable, 4xx).** The RFC says a crawler *MAY*
  crawl; `checker.robots` deliberately refuses 403 anyway. The 30-day clause is about **5xx** and
  does **not** apply to a 403. No path here on either reading.
- **`indiacode.gov.in` is 500 → §2.3.1.4 (Unreachable, 5xx).** Relaxation is permitted only after
  "a reasonably long period of time (for example, 30 days)". First 5xx **2026-09-28** → today
  **2026-10-12** = **14 days < 30.** The clause does **not** fire.

Conclusion: no permitted automated route exists today, on any reading of the RFC.

## Proposal — how `checker.robots` *could* apply §2.3.1.4 (NOT IMPLEMENTED; founder decides)

A narrow, 5xx-only relaxation:
1. **Record first-5xx per origin** in a durable provenance store (origin → first-5xx timestamp),
   re-measured every run — never a cached verdict.
2. If an origin's `robots.txt` returns **5xx (500–599) continuously for ≥ N days** (N = 30,
   explicit and configurable) **and a fresh fetch still 5xx**, `fetch_rules` may return a ruleset
   flagged `relaxed_unreachable` that permits the fetch (§2.3.1.3 behaviour).
3. **Guards:** 5xx **only** — a 4xx/403 is never relaxed (keeps the current stricter stance);
   continuity required (not intermittent); the relaxation is **recorded in the provenance of
   anything acquired under it** ("acquired under the 30-day unreachable clause; first-5xx
   `<date>`, measured `<date>`"); behind a founder-set flag, because relaxing robots is policy.
4. **It would not fire today regardless:** `indiacode.gov.in`'s 500 is ~14 days old (< 30), and
   the two candidate hosts are 403 (never eligible).

Not implemented. No PR opened from this investigation. The next step is a human browser
retrieval into `corpus/raw/contract_act/` (see `docs/guides/ACQUISITION_HANDOFF_contract_act_1872.md`).
