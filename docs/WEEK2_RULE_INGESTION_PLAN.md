# Week 2 — subordinate Rules: source and namespace first

**Scope rule for this week: no substantive legal applicability rules.** Week 2 establishes
identity and provenance for the Rules. Meaning comes after the plumbing is sound, not alongside it.

## Why the Rules, and why carefully

The Companies (Meetings of Board and its Powers) Rules, 2014 are made under ss.173, 175, 177, 178,
179, 184, 185, 186, 187, 188, 189 and 191 — which is nearly the whole MVP section list. The MVP
cannot answer a board-meeting question from the Act alone.

The hazard is already proven in this repo: the Act and the Rules **collide by number**. `56` is
both "Transfer and transmission of securities" (Act) and "Director to intimate DIN" (a Rule). That
collision produced wrong mappings during Week 1 and was only caught by title comparison.

## Preconditions — all met before Week 2 starts

- [x] `checker/legal_ref.py` — number alone never resolves; `AmbiguousReference` on collision
- [x] `checker/provenance.py` — evidence states with an enforced promotion rule
- [x] `checker/mvp_freeze.py` — 17 MVP mappings pinned, incl. ACT→RULE flip detection
- [x] Source PDF preserved in-repo and hashed (was in `/tmp`, would have been lost)
- [x] `scripts/run_tests.sh` — 9 suites, 223 checks

## Tasks

**2.1 — Acquire the Rules.** India Code serves them at a `type=rule` upload path. Record a
`SourceRecord` with retrieval date, hash, and accessibility **before** parsing. If blocked, the
record says BLOCKED and Week 2 stops at that task rather than substituting an unofficial mirror.
Third-party reproductions (`ca2013.com`, `vlex`) are **not** permitted sources under
`docs/SOURCE_POLICY.md`.

**2.2 — Ingest into a separate namespace.** `RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R<n>`.
Never into `corpus/companies_act/`. A rule and a section must not be able to share a store key.

**2.3 — Link rules to their enabling sections.** A rule made under s.173 must carry
`ACT:COMPANIES_ACT_2013:S173`, and the link must come from the rule's own text, not inferred from
its number. Rule 3 is not "the rule for s.3".

**2.4 — Effective dates.** The Rules commenced 1 April 2014, while the Act's sections commenced on
varied dates. Store `effective_from` per instrument, not per corpus.

**2.5 — Collision fixtures.** Extend `COLLISION_FIXTURE` with same-number-different-instrument,
same-title-different-version, and superseded-by-amendment cases.

## Open question, carried from Week 1

Versioning within an instrument — an amended rule at two effective dates — is **OPEN**. The
qualified key has no time component; `checker/as_of.py` handles point-in-time separately. These two
must be reconciled **before** rule amendments are ingested, or an amended rule will silently
overwrite its predecessor.

## Out of scope

Substantive applicability rules · a second statute · UI · drafting · retrieval quality work.
