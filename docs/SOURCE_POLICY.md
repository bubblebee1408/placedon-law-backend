# Source Policy

Sources are kept in strict layers. A conclusion may only rest on the layer that supports it.

| Layer | Examples | May support |
|---|---|---|
| **Canonical legal** | India Code, Gazette, MCA notifications, Acts, Rules | **Legal conclusions** |
| **Licensed databases** | Indian Kanoon (with attribution) | Search, cross-check |
| **Public professional** | ICSI Guidance Notes and Secretarial Standards, law-firm guidance, regulator material | Workflow understanding, template structure |
| **Community** | Reddit, CAclubindia, TaxGuru comments | **Discovering questions and language only.** Never a legal source |
| **Product pages** | Competitor sites | Recording competitor claims, labelled as claims |
| **Internal benchmark** | `tests/`, benchmark fixtures | Measuring Placedon's own performance |

## Hard rules
- A current consolidated Act is **never** historical ground truth. See `docs/RETRACTIONS.md` R-1.
- A secondary compilation (TaxGuru, Taxscan, law-firm alert) is never primary proof.
- Every answer shown to a lawyer identifies: source, provision, relevant date, confidence.
- Never bypass the MCA WAF, robots restrictions, access controls or source terms. Where a source is
  closed, report it closed and name the licensed alternative.
- Never obtain private minutes or confidential client documents.
- Never repair a defective government source. Flag it, preserve it verbatim.

## Known access state
| Source | Status |
|---|---|
| India Code | Open. robots.txt disallows only `/discover` and `/simple-search` |
| eGazette | Open, needs a cookieless session token in the URL path |
| MCA | **Closed** — Akamai WAF, 403 to automated access |
| RBI | Terms prohibit commercial use **and caching**. Route via gazetted notification |
| Indian Kanoon | Open with attribution. ₹10,000/mo free non-commercial tier — application open |
| SEBI | Open. robots.txt disallows only `/js` and `/css` |
| Reddit | Blocked without OAuth credentials |
