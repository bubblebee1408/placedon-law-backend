# Loop runbook — Themis, the next 20 moves

Created 2026-09-17 evening, founder away. Pattern: **plan → runbook → subagents →
/loop until every row is DONE or BLOCKED**. Decisions are made and recorded here,
not asked. Founder-only calls stay BLOCKED with their evidence.

## Standing rules for every move

1. **The gate is the contract.** `./scripts/run_tests.sh` must end
   `HARNESS_RESULT … status=GREEN`. A move that lowers it is reverted.
2. **Never bypass the pre-commit hook.** `SKIP_TESTS=1` is not used.
3. **Shared tree.** Another session ("Text field probe with gemma3:1b") is editing
   `checker/provenance.py`, `checker/prescribed_thresholds.py`,
   `scripts/register_gsr700e.py`, `scripts/register_gsr880e.py`. **No move touches
   those files.** Subagents work in isolated git worktrees; results come back as
   commits and are integrated one at a time.
4. **Stage by explicit path only**, with a grep guard against the other session's
   files. The index is shared; staged files are never left waiting.
5. **Read a source's terms before the first content fetch** (lesson S9).
6. **Nothing is installed.** Standard library, plus what is already declared.
7. **One logical change per commit.** Commit, then push the branch.
8. **Ring discipline.** Nothing in `checker/feeds/` may be imported by a Ring 0
   decider; `checker/rings.py` enforces it by test.

## The 20 moves

Lanes: **ME** = this session · **A/B/C/D** = subagents (worktree-isolated) ·
**H** = founder only.

| # | Move | Lane | Done when | State |
|---|---|---|---|---|
| 1 | Commit the Gazette watcher (6 files, verified clean in isolation) | ME | On the branch, hook GREEN | DONE `234dca2` |
| 2 | Push the branch after each landed commit | ME | `origin` matches local | BLOCKED — push denied by the permission classifier; founder must allow it |
| 3 | OFAC delta watcher: added / removed SDN uids between polls, same high-water discipline as the Gazette runner | A | `scripts/watch_ofac.py --test` GREEN; live run records a baseline | running |
| 4 | OFAC vessel index by IMO number — the lawful "God's Eye ships" | A | `lookup_vessel(imo)` tested offline; live count reported | running |
| 5 | Cache OFAC artifacts through `feeds/common/cache.py` so a delta is computed from hashed, dated files | A | Two polls produce two dated artifacts; delta reads them | running |
| 6 | Source audit, read-only: SEBI's own orders + terms, IBBI, MCA defaulter lists, RBI wilful defaulters | B | `docs/research/SOURCE_AUDIT_REGISTERS_2026_09_17.md`, every row SOURCED or UNVERIFIED | DONE `e68f938` — IBBI BUILDABLE (quote re-verified); SEBI, RBI forbidden by terms; MCA, CIBIL blocked |
| 7 | Technical report, publishable, every number tagged MEASURED/SOURCED/INFERRED with its commit | C | `docs/THEMIS_TECHNICAL_REPORT_2026_09_17.md` | DONE `979e177` (integration note added) |
| 8 | `robots.py`: a 401/403 on robots.txt is a block, not "no rules" (BSE finding) | ME | Test: 403 → not loaded; 404 → allow-all; gate GREEN | DONE `54eba61` |
| 9 | Pre-commit hook prints the real suite count instead of the stale "147" | ME | Hook label computed; `harness_regression.sh` still passes | DONE `86e24a2` — hook now prints `suites=173 … GREEN` |
| 10 | Reconcile FEATURES.md "2 of 15" vs "four obligations refuse" from `obligations.py` itself | D | One number, with the command that produced it | running (agent D, worktree wave2-d) |
| 11 | FEATURES.md F5 + PLAN_15 status: watcher BUILT, delivery remaining | D | Status lines name files and commits | running (agent D) — also CLAUDE.md 527→529 |
| 12 | Gazette digest: render new/UNKNOWN/UNSEEN items as a dated markdown report — delivery v0, no legal inference | D | `reports/gazette_digest.md` from the watcher log; test GREEN | running (agent D) |
| 13 | Link the watcher to `corpus_currency`: a new MCA instrument raises "ledger may be behind", never a conclusion | D | Digest shows it; no Ring 0 import | running (agent D) |
| 14 | Red-team every new Ring 2 module (fail-closed, licence, blindness, ring boundary) | E | Findings dispositioned | queued (wave 3) |
| 15 | Integrate subagent commits one at a time; gate after each | ME | Each lands GREEN | continuous — B, C integrated as single files |
| 16 | Final report: what runs, what is designed, what is blocked | ME | `docs/LOOP_THEMIS_20_MOVES_REPORT.md` | last |
| 17 | **SD-005 decision** — accept split words as source defect or acquire a cleaner rendering | H | Founder decision | BLOCKED |
| 18 | **SEBI debarred route** — OpenSanctions licence / written permission / SEBI orders | H | Founder decision | BLOCKED |
| 19 | **Licence confirmation** for OFAC and eGazette (Copyright Act s.52(1)(q) reading) | H | A lawyer's or the source's own words | BLOCKED |
| 20 | **H-C — send the Company Secretary outreach** (`docs/H001_FIND_A_CS.md` §1) | H | Message sent | BLOCKED (thirteen days) |

## Stop condition

Every row is DONE or BLOCKED with evidence, the gate is GREEN on the branch, the
branch is pushed, and the report is written. Or: two consecutive loop ticks make no
progress for reasons outside this session — then stop and report.

## Log

- 17-09 evening — runbook written; wave 1 (A, B, C) launched in isolated worktrees.
  Move 1 blocked on the peer session's red working tree; a one-shot idle
  subscription is armed on that session.
- 17-09 evening — moves 1, 8, 9 landed; B and C integrated; gate 173 GREEN on every commit.
- **S10 — subagent worktrees branch from `origin/main` (`eb48905`), not from this branch.**
  That base is 22 commits behind and not an ancestor. B and C were single new files, so
  harmless; A copied the feed code into its worktree in its own commit (`573baac`), which
  must NOT be merged. Rule from now on: integrate **only the files an agent was asked to
  produce**, never its branch; and create wave worktrees by hand from HEAD
  (`git worktree add -b wave2-d .claude/worktrees/wave2-d HEAD`). `.claude/worktrees/` is
  git-ignored.
- Push (move 2) denied by the auto-mode classifier as out-of-place publication. Not
  worked around. 13 commits are local on `loop/bookmark-godseye-v0`.
- The peer session committed `c072b01` and continues on provenance/registration files;
  every commit here stages explicit paths only and waits out its index lock.
