# M10 — `checker/ontology.py`: four things PLAN_19 §2 names that do not exist

Architect record, 2026-09-26, for move 10 of
`.claude/plans/loop-twenty-moves-2026-09-26.md` (PLAN_19 G1.1). Written before any
code, per PLAN_19 §2.2, because the module adds a ring entry.

## 0. Why this is longer than a ring assignment

PLAN_19 `03_ARCHITECTURE.md` §2 specifies the module in fourteen lines of Python.
**Four of the types it builds on do not exist**, and two of them do not exist in a way
that would have produced a working-looking module resting on nothing. Each was checked
directly.

| §2 says | Reality | Checked by |
|---|---|---|
| `valid: Interval  # checker/interval.py` | **`checker/interval.py` is a STATISTICS module** — `wilson`, `binom_test`, `mcnemar`, `bootstrap_ci`. It has no interval-of-time type, and never did | `grep -n "^class\|^def" checker/interval.py` |
| an `Interval` type exists somewhere | **No validity-period type exists anywhere in `checker/`.** The only `Interval*` names are `interval.IntervalError` and `derived_date.IntervalNotInSource` — both exception classes in unrelated modules | `grep -rn "^class .*Interval\|^class Validity\|^class Period" checker/*.py` |
| `source: SourceRef  # provenance.Source shape: url, sha256, fetched_at` | **`provenance.Source` is ABSENT.** The real type is `provenance.SourceRecord`, and none of the three field names matches: `source_url`, `artifact_sha256`, `retrieved_on` — plus `official` and `accessibility`, which §2 omits and which are load-bearing | enumerated `provenance`'s dataclasses |
| `value: T \| Unknown  # Unknown is a type` | **No `Unknown` type exists.** Three *string* constants do, with three different values: `assessment.UNKNOWN = "UNKNOWN"`, `entail_role.UNKNOWN = "unknown"`, `matrix_view.UNKNOWN = ""` | `grep -rn "^class Unknown\|^UNKNOWN = "` |

What §2 gets right, verified: `entity_graph.Rel` exists as an Enum with exactly six
members — `DIRECTOR_OF`, `RELATIVE_OF`, `CONTROLS`, `HOLDS_SHARES_IN`, `PARTNER_IN`,
`MEMBER_OF` — and `entity_graph`'s docstring already holds the handles rule verbatim:
*"Entities are opaque ids with a kind… This module stores no names, addresses, DINs or
other PII."*

## 1. The decisions

### 1.1 `SourceRef` **is** `provenance.SourceRecord`. No new shape.

Reuse, not restatement. §2's own Rule 1 requires `LINK_TYPES` to be built from
`entity_graph.Rel` *"so the entity graph and the ontology cannot diverge"* — the same
argument applies with more force to provenance, which is the module this product's
claims rest on. A second source shape with three renamed fields would be two notions of
truth about where a fact came from.

Consequence: `Observed.source` carries `official` and `accessibility` too, which §2's
three-field sketch would have dropped. `accessibility` is what `feeds/` uses to
distinguish "the source said nothing" from "the source did not answer", and losing it
here would have re-created that hole one layer up.

### 1.2 `Validity` is a new small type in `ontology.py`, matching the repo's existing convention exactly

There is nothing to reuse, so this is new — but it is new *naming*, not new *semantics*.
The convention already used by `prescribed_thresholds.Threshold` is an
`effective_from` / `effective_to` pair where `None` means "still in force so far as we
know", with containment:

```python
def covers(self, as_of: date) -> bool:          # Threshold.covers, lines 72-75
    if as_of < self.effective_from: return False
    return self.effective_to is None or as_of <= self.effective_to
```

`Validity.covers` **must be byte-identical in behaviour**, inclusive at both ends, and a
test asserts the two agree on a shared grid of dates. Two containment rules that differ
by a day at a boundary is how point-in-time answers go quietly wrong, and
`docs/TEMPORAL_PROOF.md` exists because this repository has already paid for boundary
behaviour once.

`Validity` does NOT go in `checker/interval.py`. That module is statistics; putting a
date type in it because the word matches would make the next reader's grep lie.

### 1.3 `Unknown` is a singleton sentinel type, and the three existing `UNKNOWN` strings are left alone

§2's requirement is right and the reason is strong: `None` and `0` are both real values
in this domain — a company can have `0` charges, and `None` is what a missing dict key
returns. A sentinel that is *neither* is the only way `Observed.value` can say "we looked
and do not know" without colliding with an answer.

But a fourth `UNKNOWN` would be the problem this module is supposed to avoid. So:

- `Unknown` is a **distinct type with one instance** (`UNKNOWN`), not a string.
- It is **not** exported as a replacement for the three existing constants, which are
  local display/enum values in `assessment`, `entail_role` and `matrix_view` with three
  different string values. Unifying them is a separate change with its own blast radius,
  and is **recorded as open**, not done here.
- A test asserts `UNKNOWN is not None`, `UNKNOWN != 0`, `UNKNOWN != ""`, and
  `bool(UNKNOWN) is False` — so `if value:` cannot silently treat it as present, which
  is the presence-versus-content family below.

### 1.4 Ring 1, registered

`"checker.ontology": RING_1` in `rings.py:REGISTRY`. Not left unregistered: an
unregistered target is never flagged by `violations()`, which is the hole `PACKAGE_RINGS`
was added to close. Ring 1 because it depends on `entity_graph` (Ring 1) and
`provenance` (Ring 0) — downward and sideways, both permitted. **No Ring 0 decider may
import it**, and `rings.py` enforces that by test rather than by convention.

Static imports only; `violations()` bans `importlib` in a registered Ring 0/1 module
outside `_test()`.

## 2. The failure family this module must not repeat

From `docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md` and
`RED_TEAM_INSTRUMENT_REGISTRY_2026_09_26.md`, four instances in two days:

> **A guard that tests for PRESENCE is not a guard that tests for CONTENT.**

`hasattr` swallowing a missing API; `.get(default)` turning missing into plausible; a
`source` check that tested non-emptiness instead of meaning; a fragment check that did
the same. Concretely, for this module:

1. `Observed.value` must not accept `None` as a stand-in for unknown — that is the whole
   point of `Unknown`, and `__post_init__` raises on `None`.
2. `Observed.evidence` must be a member of `provenance.STATES`, checked, not a free
   string. An evidence word nobody validated is an evidence word nobody can rely on.
3. `Observed.licence` must be non-empty. An empty frozenset reads as "no restrictions"
   and means "nobody recorded any" — PLAN_08 Axis D's `LICENCE_UNVERIFIED` exists
   because those are opposite facts.
4. `Individual` carries **no** name/DIN/PAN/address field, proved by a **dataclass-field
   scan**, not by inspection. A comment saying so is not a test.

## 3. What this module does not do

No store, no persistence, no `as_of` query — that is move 11 (`observation_store.py`).
No rollup and no evidence state of its own: §2 Rule 3 puts every rollup in
`derivation.py` (move 13) with its witness. No new dependency. It decides nothing about
law.

## 4. Recorded as open, not done

- The three inconsistent `UNKNOWN` string constants (`"UNKNOWN"` / `"unknown"` / `""`).
- `OBJECT_TYPES` includes `Judgment`, which belongs to G5 (the citator) and is
  `[BLOCKED]` on counsel's answer about the CC-BY grant. The type name is declared;
  nothing constructs one.
