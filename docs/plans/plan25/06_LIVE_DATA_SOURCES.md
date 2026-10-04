# 06: Daily live data, source by source, for every body of law

**Rules that bind every row** (`CLAUDE.md`):

- Permitted sources only.
- robots.txt and the source's terms are honoured, and a 5xx response on robots.txt fails
  closed (`checker/robots.py`).
- The MCA WAF (web application firewall) is never bypassed.
- A 404 or a block is evidence of nothing.
- **"Access: OPEN" means the terms have not been read and quoted.** An OPEN source is not
  wired until a person pastes the clause into `docs/research/`.

## 1. Sources

| Source | Body of law | What it gives | Ring | Adapter | Access |
|---|---|---|---|---|---|
| eGazette | all | new notifications; the currency engine's input | 0→2 | `checker/feeds/egazette.py` **BUILT** | Permitted by browser; listing only. **The instrument number is inside the PDF**, so identifying it is a human-gated task (PLAN_24 01) |
| India Code | all | consolidated text | 0 | acquisition scripts | **robots.txt returns 5xx → fetcher fails closed** (R-012). Human browser download with the URL and date recorded |
| OFAC SDN | sanctions (counterparty) | listings | 2 | **BUILT** | public domain |
| IBBI | IBC | orders, registrations | 2 | **BUILT** | per PLAN_19 02 |
| SEBI RSS | SEBI | orders and circulars | 2 | NEW (PLAN_19 G3.2) | robots permits (PLAN_19 02) |
| SEBI adjudication / settlement orders | SEBI | penalty records for forum analytics | 2 | NEW | OPEN |
| RBI compounding orders | FEMA | compounding amounts for analytics | 2 | NEW | OPEN |
| NCLT / NCLAT orders | Companies Act, IBC, Competition | case records for `rates` and `survival` | 2 | NEW | **OPEN**: the terms have never been read; the most important one for the wedge |
| CCI orders | Competition | case records | 2 | NEW | OPEN |
| data.gov.in MCA master data | Companies Act (company facts) | CIN, class, capital | 1 | NEW (G3.3) | GODL-India; **API key and ZIP only, never crawl** |
| Supreme Court / High Court judgments (AWS Open Data) | all (citator) | judgments 1950– | 2 | NEW (G5) | CC-BY-4.0 applied by the maintainer. **Counsel must confirm it covers court text** |
| Open India Law (Vaquill) | all (unheld-Act text, for the scope lexicon) | 1.1M legislation sections, 12.8M judgments | reference | NEW | CC BY 4.0 data. **The record we already hold has wrong metadata**, so check every item |
| Development Data Lab | district courts | 81M cases 2010–18 | research | none | **CC BY-NC-SA: not for commercial use** |
| NJDG | pendency statistics | aggregates | citation only | none | The open API is for government only |
| NSE / Zauba | — | — | — | **not built** | NSE forbids scraping; Zauba's provenance is unexplained (PLAN_19 02) |

## 2. The daily schedule

```
06:15 IST  GitHub Actions (private repo) or cron
  watch_gazette   → new items → observation_store → operations (identify instrument: human)
  watch_ofac      → diff → entity_graph matches → operations
  watch_ibbi      → diff → operations
  watch_sebi      → RSS → observation_store (SIGNAL) → operations        [NEW]
  health          → per-feed: last good observed_at, age vs TTL, live? (≥1 record admitted)
                    STALENESS_WARNING if age > TTL; a HUMAN_REVIEW operation if dead > 2 runs
weekly     forecast recompute: rates / survival over ForumCase rows (when a lawful source exists)
monthly    ACI/conformal recalibration per stratum; learning_report
on change  recall: currency.affected_by(instrument) → runs ⋈ law_versions → notices
```

**Why GitHub Actions and not the jobs worker:** the code audit found no worker daemon
running (appendix D F3), and the existing watch scripts are already single-shot with exit
codes 0/2/1. Cron plus script is the simplest thing that works.

**Open question:** do GitHub's terms allow daily fetching "unrelated to the software
project"? If they do not, the fallback is the laptop's cron, or after funding a small VM in
India.

## 3. God's Eye patterns to port into `checker/feeds/common/`

MIT code patterns, no data taken. Evidence and file paths are in appendix D §D.

1. **Staleness with a TTL and a status page.** `cache.latest(source)` returns the data's
   age. `/v1/health` shows each feed's last good time.
2. **Partial success.** One dead sub-source does not fail the sweep. It opens an operation
   saying "source unreadable since X". It is never silent.
3. **Atomic admission.** A non-empty batch where every row is invalid counts as
   *unavailable*, and the high-water mark does not advance.
4. **Error taxonomy.** 429 means waiting as long as Retry-After says. 401/403 means denied:
   stop and tell a human.
5. **Liveness.** A feed is live only if it admitted at least one recognised record.

**Also wire the `RateGovernor` that already exists** (`checker/feeds/common/rate.py`). No
adapter uses it today.
