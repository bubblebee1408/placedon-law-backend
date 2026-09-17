# Loop report — Themis, 20 moves, 17–18 September 2026

Founder away. Runbook: [`LOOP_THEMIS_20_MOVES_2026_09_17.md`](LOOP_THEMIS_20_MOVES_2026_09_17.md).
Every number below was produced on this machine and is tagged **MEASURED**,
**SOURCED**, **INFERRED** or **UNVERIFIED**.

---

## 1. The one-line result

**The live-data pipeline exists and runs.** Two feeds poll real sources, a firewall
stops any of it reaching a legal decision, and the test gate went from **163 to 175
suites, GREEN at every commit** (MEASURED, the pre-commit hook's own
`HARNESS_RESULT` line). Fourteen commits landed. Four moves are blocked on the
founder; one on a permission.

## 2. What now runs, with its live numbers

| Thing | Live evidence (MEASURED 2026-09-17/18) |
|---|---|
| **OFAC SDN feed** `checker/feeds/ofac_sdn.py` | 19,385 of 19,385 records parsed, matching the file's own stated `Record_Count`; 29,076,910 bytes; published 09/16/2026 |
| **Vessel index by IMO** | 1,540 vessels → **1,527 indexed by IMO, 1,527 with a valid check digit**; 13 carry no IMO-shaped id |
| **OFAC change-watcher** `scripts/watch_ofac.py` | baseline established; reports uids added/removed and changed programs between polls |
| **Gazette watcher** `checker/feeds/egazette.py`, `scripts/watch_gazette.py` | 7 gazettes listed (4 extraordinary, 3 weekly), high-water serial **276299**; 3 weeklies flagged ministry-UNKNOWN |
| **Gazette digest** `scripts/gazette_digest.py` | renders the watcher's log; on a new MCA instrument it names the ledger gap and nothing more |
| **The ring firewall** `checker/rings.py` | 28/28; zero Ring 0 or Ring 1 modules import upward; all of `checker.feeds` is Ring 2 **by package**, so a feed nobody registers is still fenced |

## 3. The five findings worth keeping

1. **A number that had never been measured was wrong.** `FEATURES.md` said in one
   place "2 of 15 rows refuse" and in another "four obligations refuse".
   **MEASURED** against the register: 15 rows, and **exactly 2** blocked on an
   unheld delegated rule (s.177, s.203). The third undetermined row (CSR, s.135) is
   blocked on missing company facts, not a rule. "Four" was never reachable. Both
   sentences now carry the measured number and the command that produced it.
2. **IBBI is the first Indian register that is lawfully usable.** Its own Copyright
   Policy (SOURCED, quoted verbatim, re-verified by this session):
   *"Material featured on this site may be reproduced free of charge in any format
   or media without requiring specific permission"*, subject to accuracy, no
   derogatory or misleading context, and prominent source credit. Every other
   register checked is blocked, forbidden by terms, or paid.
3. **A trust-store gap made a correct source look broken.** eGazette serves only its
   leaf certificate. Two pinned intermediates now complete the chain; OpenSSL proves
   both directions — with the trusted bundle the chain verifies, and the
   intermediates **alone fail**, so they anchor nothing.
4. **robots.txt: a 403 was being read as permission.** BSE answers its robots.txt
   with an Akamai "Access Denied". The old rule treated every 4xx as "no rules
   published". Denials and rate limits now stay closed; genuine absences (404/410)
   still allow, so no working host was lost.
5. **A missing record was being rendered as an absence of events.** The digest
   showed a poll with seven new serials as "(nothing new this poll)" because that
   log entry predated item records. Fixed at integration: it now names the serials
   and says the details were not written down.

## 4. Moves — final state

| # | Move | State |
|---|---|---|
| 1 | Gazette watcher committed | **DONE** `234dca2` |
| 2 | Push the branch | **DONE by side effect** — the peer session pushed the shared branch; `origin` is 1 commit behind HEAD. A direct push from this session was **denied by the permission classifier** and not worked around |
| 3–5 | OFAC delta watcher, vessel index, cached artifacts | **DONE** `7ec9272` |
| 6 | Register source audit (SEBI/IBBI/MCA/RBI/CIBIL) | **DONE** `e68f938` |
| 7 | Technical report, evidence-tagged | **DONE** `979e177` (6,696 words) |
| 8 | robots.txt 401/403 is a refusal | **DONE** `54eba61` |
| 9 | Hook prints the real suite count | **DONE** `86e24a2` |
| 10–13 | FEATURES/CLAUDE.md numbers, digest, ledger signal | **DONE** `c2d7c0d` |
| 14 | Red team of the Ring 2 layer | **DONE** — 6 FATAL, 4 MAJOR, 3 MINOR; **11 closed**, 2 open by decision |
| 15 | Integrate agent commits one at a time | **DONE** — four agents, integrated by named file only |
| 16 | This report | **DONE** |
| 17 | **SD-005** — accept the split words as a source defect, or acquire a cleaner rendering of G.S.R. 240(E) | **BLOCKED — founder** |
| 18 | **SEBI debarred route** — OpenSanctions licence, written permission, or drop it | **BLOCKED — founder.** §3.2 changes this: IBBI may be the better first Indian feed |
| 19 | **Licence confirmation** for OFAC and eGazette | **BLOCKED — founder/lawyer.** Both feeds refuse commercial serving until then |
| 20 | **H-C — send the Company Secretary outreach** | **BLOCKED — founder.** Open since 4 September |

## 5. Decisions taken without asking, and why

- **Integrate agent work by named file, never by merging its branch.** The subagent
  worktree tool branches from `origin/main`, 22 commits behind and not an ancestor
  (lesson **S10**). One agent copied the feed code into its own worktree to compile
  at all; merging that would have regressed files already on the branch.
- **Anchor the OFAC watcher's paths to the repo root.** They were cwd-relative: run
  from anywhere else, the watcher would have written a fresh state and silently
  started over, losing every delta. Verified by a live run from `/tmp`.
- **Git-ignore the feed cache.** Each OFAC artifact is 29 MB.
- **Keep both feeds at `LICENCE_UNVERIFIED`.** Neither source states its
  redistribution terms. US government works (17 U.S.C. §105) and Copyright Act 1957
  s.52(1)(q) are the likely bases, but that is **INFERRED** — the layer refuses
  commercial serving until a person confirms it.
- **Never bypass the pre-commit gate.** `SKIP_TESTS=1` was available at every
  blocked commit and was not used once.

## 6. What is NOT true yet — read before quoting anything

- **No practitioner has reviewed any output.** No real-document benchmark exists.
- **Neither feed may be served commercially** (§5).
- **Screening is exact-match only** — it misses transliterations and unlisted
  aliases. It produces candidates for a person, never a decision.
- **The Gazette digest is delivery v0**: a page. There is no subscription, no
  alert, no email.
- **No feed touches a legal decision**, and `rings.py` is what makes that a test
  rather than a promise.
- **Two red-team findings remain OPEN by decision**: RT-03 (an empty 200 body is a
  legal ACCESSIBLE result) and RT-10 (licence enforcement is advisory — nothing
  calls `is_servable_commercially()` outside tests). Both belong to a serving layer
  that does not exist yet.

## 6a. The red team, and what it found (move 14)

Thirteen findings, every one proven with a runnable snippet. **Eleven are fixed**,
each with the test that would have caught it (`28c7ba3`, `d408ffe`, `4041a8f`).

| Finding | Why it mattered |
|---|---|
| **RT-14 FATAL** | `scripts/ingest_companies_act.py` fetched the **statutory corpus** with TLS verification disabled and a spoofed Chrome user agent — the one fetch here where a man-in-the-middle rewrites the law. Pre-existing, not new code. Dormant only because its host is dead |
| **RT-08 FATAL** | Both watchers wrote state **before** the log. An ordinary kill between the two consumed the alert permanently. Now log-then-state, fsynced, proven by a crash test |
| **RT-07 FATAL** | A listing that went **backwards** produced an empty gap range and read as a clean poll. Now a failed poll that holds the mark |
| **RT-04 FATAL** | A body shorter than its declared length was served as complete — half the SDN list would have been hashed and parsed as the whole source |
| **RT-01 / RT-02 FATAL** | The firewall saw only direct, static imports: `importlib.import_module` walked straight past it, and any unregistered helper was an invisible laundering hop. Now transitively closed, with dynamic-import machinery refused in a decider |
| **RT-11 MAJOR** | One nested `<span>` would truncate the Ministry cell and silence the MCA alert with every test still green |
| **RT-09, RT-05, RT-12, RT-13** | Non-atomic state writes; a relative redirect blamed on a missing header; ID/date never cross-checked; a Unicode-digit IMO keying an unreachable index entry |

**Open by decision:** RT-03 and RT-10 (§6).

**The lesson worth carrying:** the layer written today held up better than the code
around it. The single worst finding was a two-line TLS bypass that had been sitting
in the corpus ingestion path.

## 7. What I would do next

1. **Send the outreach** (move 20). Fourteen days open. Everything above is
   infrastructure for a question a practitioner has still not been asked.
2. **Decide the licence question** (move 19) — it is what stands between two working
   feeds and a product that may show their data.
3. **Build the IBBI feed** (§3.2) — the first Indian register with clean terms, and
   the machinery for it already exists.
4. **Disposition the red team's findings** when they land, before any feed grows.
