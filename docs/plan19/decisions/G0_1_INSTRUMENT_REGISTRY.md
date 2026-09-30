# G0.1 — How `acquisition_for` learns that an instrument is REGISTERED BUT NOT ATTESTED

Architect decision, 2026-09-25, for PLAN_19 step G0.1. Recorded before any code, per
PLAN_19 §2.2. Written to disk by the main session because the architect's Write tool
was disabled; the content is the architect's, and every repo claim in it was
independently re-verified before this file was created (see §8).

## 1. The decision, in one sentence

Add a Ring 0 module `checker/instrument_registry.py` that declares **only where to
look** — one static import per `scripts/register_*.py` plus the name of that module's
own record accessor and attestation predicate — and reads **every fact (title,
status, attestation) from the register module's own record at call time**;
`checker/currency.acquisition_for` consults it only after the existing
`prescribed_thresholds` path finds nothing, and returns a `PENDING` `Acquisition`
when a record exists and that module says it is not attested.

## 2. Options considered

### (a) A registry module in `checker/` — **CHOSEN, with one amendment**

Not in the shape the option implies. A registry that enumerates the modules *and
restates what they contain* is a second notion of truth. The amendment: it declares a
**pointer set only** — three things per entry, all facts about the Python API, none
about the law:

- the module (`scripts.register_kmp_rules`)
- the record accessor name (`"registration"`; `"review_record"` for s188)
- the attestation predicate name (`"is_servable"` for KMP, `"is_attested"` elsewhere)

Name, status and dates are read from the record the module returns.

**"Registered" is defined as "the module's record accessor returns a dict"** — not as
a list we keep. So the registry cannot assert a registration that does not exist.

How the remaining duplication (the module list) cannot disagree:

1. **A filesystem completeness test** — `sorted(p.stem for p in
   (ROOT/"scripts").glob("register_*.py"))` must equal the declared set. The same
   technique `rings.py:146-157` used to close its analogous hole ("a feed is Ring 2
   because of WHERE it lives, and cannot escape by being forgotten"). `Path.glob` is
   not a dynamic import, so it does not trip RT-01.
2. **Failure direction is loud or backwards-compatible.** A wrong accessor name
   raises `AttributeError` at first call; a forgotten module degrades that instrument
   to `None`, i.e. today's behaviour, and the glob test goes red. Neither path can
   make an unattested instrument read as attested, because `read` is only ever the
   value the register module's own predicate returned.

### (b) `corpus/sources/index.json` written by the register scripts — LOST, twice over

It cannot be built: it requires editing `scripts/register_*.py` (do-not-touch), and
there is no other writer. And it *is* the second notion of truth: delete
`corpus/sources/pas_rules_registration.json` and the index still says PAS is
registered — the same failure class `prescribed_thresholds.py:141-145` exists to
avoid ("A constant saying CORROBORATED can outlive the artifact it was asserting")
and `staleness.py:70` ("derived from disk — never a hand-edited constant").

### (c) `acquisition_for` importing the script modules directly — LOST on cohesion, not legality

It is permitted: `currency.py:335,362,428` and `prescribed_thresholds.py:148,248`
already import `scripts.register_*`, and `ring_of("scripts.register_gsr700e")` is
`None` (`scripts/` is deliberately unclassified), so the firewall does not object. It
loses because it puts six adapter branches inside a Ring 0 decider — the shape
`staleness.py:88-117` already has, which `docs/LOOP_INTELLIGENCE_V0.md:78-79` already
calls "one shape copy-pasted five times" — and makes `acquisition_for` the place the
seventh instrument gets forgotten.

### (d) Reuse `checker/staleness.py`'s inventory — the strongest alternative, LOST on four checkable facts

1. Keyed by `rule_id` (`staleness.py:168-181`), an internal ledger code **no caller of
   `acquisition_for` holds** — both live callers pass a Gazette-style *name*
   (`operations.py:270`, `tools.py:183`).
2. Covers 5 of 6 registrations: PAS and SEBI LODR are absent from
   `staleness.DEPENDENCIES:123-165`.
3. Adding them would corrupt its meaning — a `RuleDependency` carries `governs`, and
   PAS/SEBI govern no obligation, so they would enter with `governs=()` and inflate
   "N of M dependencies need action" (`staleness.py:233`).
4. It would close a deliberately-open cycle: `staleness.py:34` imports `currency` at
   module level while `currency.py:180` imports `staleness` lazily inside a function
   ("lazy: staleness imports us").

**Therefore the registry must not import `checker.staleness`, and vice versa.**

## 3. Ring and `rings.py` consequence

**Ring 0.** Add `"checker.instrument_registry": RING_0` to `rings.py:REGISTRY`. Not
left unregistered, because an unregistered target is never flagged
(`rings.py:229-245`) — the exact hole `PACKAGE_RINGS` was added to close.

1. **No dynamic imports outside its own `_test()`.** `violations()` runs
   `_dynamic_import_uses` on every registered Ring 0/1 module, banning
   `__import__`/`eval`/`exec`/`import_module`/`sys.modules[...]`. **So the obvious
   implementation — `importlib` over a glob — is structurally banned once
   registered**; enumeration must be six static `import` statements. (The evasion that
   exists today and must not be copied: `checker/matrix_view.py:460` and
   `scripts/slice_s173.py:157` use `importlib.import_module("scripts.register_gsr700e")`,
   unflagged only because those modules are unregistered.)
2. Static `import scripts.register_*` is permitted — `ring_of` returns `None`,
   `_leaks_upward` never flags it.
3. **No new firewall exposure.** `_reachable_unregistered` already walks
   `checker.currency` → `checker.staleness` → `scripts.register_gsr700e`/
   `register_kmp_rules`/`register_gsr880e`. Those files are already in the closure.
4. Only `checker.currency` (Ring 0) imports it. `checker.operations` is Ring 2 and
   `checker.mcp` is Ring 2 by package; both consume `acquisition_for` downward, which
   is allowed.
5. No new runtime dependency — `dataclasses`, `pathlib`, repo modules only.

## 4. The `affected_by` agreement

### 4.1 Do NOT anchor. Both keep substring matching.

Verified: `affected_by` is `frag in t.instrument.lower()` (`currency.py:237-238`);
`acquisition_for` is the same (`currency.py:285-288`). **Neither has a normaliser.**

What *is* done — the honest reading of "the same normaliser" — is extracting one
private `_matches(fragment, instrument_name) -> bool` used by both, with the
empty-fragment refusal inside it.

This closes a real latent disagreement: `affected_by` does not strip and does not
refuse empty, so **`affected_by("")` returns `['CA13-S2-85-SMALL']` today while
`acquisition_for("")` returns `None`** — the docstring's "Matched exactly as
`affected_by` matches" (`currency.py:272`) **is already false**, and the agreement
test never catches it because it is only asserted with `"880"`. Tightening
`affected_by("")` to `[]` is a fix: `operations.py:270` feeds it a Gazette trigger,
and an empty trigger currently manufactures work.

### 4.2 The agreement test is deliberately broken in one direction and replaced

The biconditional at `currency.py:471-472` cannot survive and should not: KMP is
registered but sets no threshold in `all_thresholds()`, so `affected_by("249(E)") == []`
while `acquisition_for("249(E)")` must be `PENDING`. "Moves no obligation we declare"
and "nobody has read it" are different facts. Replacement, strictly stronger:

1. The structurally guaranteed implication the old test actually protected:
   `affected_by(f)` non-empty ⟹ `acquisition_for(f) is not None`.
2. The asymmetry, named and pinned: a registered instrument setting no declared
   threshold has `affected_by(f) == []` and `acquisition_for(f).status == PENDING`,
   asserted on the KMP title with a comment saying this is the deliberate break.
3. One matcher, proved: `_matches` is the module's only containment test, and
   `affected_by("")`/`acquisition_for("")` now agree.

## 5. `Acquisition`, and caller branching

```python
ACQUIRED = "ACQUIRED"   # attested, and the deciding module permits reliance
PENDING  = "PENDING"    # a registration record exists; no person has attested it

@dataclass(frozen=True)
class Acquisition:
    instrument: str               # full name: Threshold.instrument, or the record's own title
    status: str                   # ACQUIRED | PENDING
    read: bool                    # == (status == ACQUIRED). Derived, never independent.
    state: str                    # the answering record's own evidence word, verbatim
    source_url: str               # "" when the record names none -- never invented
    effective_from: date | None   # None when nothing dated is on record -- never invented
    note: str = ""
    answered_from: str = ""       # witness: "checker.prescribed_thresholds" | "scripts.register_kmp_rules"
```

**"Not registered at all" stays `None`** — giving it a status would invite callers to
treat it as a kind of record.

`read` is **kept** so the ACQUIRED case at both call sites is untouched — on the
threshold path it stays `all(t.servable for t in hits)` through `release.may_release`;
on the registry path it is the module's own predicate (`is_servable` for KMP, where
attested deliberately != servable).

`effective_from` **becomes `date | None`** — forced, because registration records
carry no commencement date in general and inventing one is a fabricated legal date.

`state` is the answering record's own word verbatim, which creates a mixed vocabulary
that must not be laundered (provenance states on the threshold path;
`PENDING_HUMAN_REVIEW`/`CORROBORATED` on the registry path). **`answered_from` is what
tells a reader which they are looking at**, and a verdict with no witness is unusable.

**Consultation order: threshold path first, unchanged** — so 700(E)/880(E) cannot
regress; registry second; `None` only if neither matched.

### `operations.py:291`

Today `if acq is None or not acq.read:` raises one BLOCKING requirement asking to
*"Acquire and attest"* — false for a held, hashed, registered instrument, and exactly
the "queue nobody can ever empty" its own comment warns about. Split into two variants
of the **same requirement id**: `read_id = _rid(instrument, "read")` **must not
change**, because downstream requirements carry `depends_on=(read_id,)`.

- `acq is None` → unchanged question, `LEGAL_RESEARCH`, unchanged `minimum_evidence`.
- `status == PENDING` → *"**Attest** {acq.instrument}: a named reviewer must confirm
  identity and that the operative clause is verbatim. It is already held and
  registered ({acq.answered_from})."*; specialist `HUMAN_REVIEW` — confirming a held
  file is review, not research; `minimum_evidence` = "a named reviewer's attestation
  recorded against the existing registration".
- `criticality` stays `BLOCKING` in both: unattested is still unservable.

### `mcp/tools.py:220`

Two branches become three.

- `None` → keep today's sentence (true: no record).
- `PENDING` → *"It is registered and held ({acq.answered_from}) but **no reviewer has
  attested it**, so nothing may be served from it yet."*
- `ACQUIRED` → today's sentence **with one required fix**: line 223 calls
  `acq.effective_from.isoformat()` unguarded and **will raise `AttributeError`** on
  the first attested registry-only instrument (SEBI LODR after `--attest`); guard it
  and print "commencement not recorded".

No other caller exists (repo-wide grep: `operations.py:291`, `tools.py:220`,
`currency.py`'s `_test()`).

## 6. Where the PLAN_19 step is wrong

**6.1** *"the same normaliser `affected_by` uses"* names something that does not exist
— `affected_by` is `lower()` + `in`, nothing else.

**6.2 "anchored" is not a tightening; it would RE-OPEN PLAN_17 M1.3.** Both callers
pass the same Gazette-style name fragment to both functions. Anchor
`acquisition_for` alone and every real call returns `None` while `affected_by` still
returns obligations — so `operations.py:292` raises the BLOCKING "nobody has read it"
requirement forever and `tools.py:228` prints the constant sentence M1.3 was filed to
delete. Anchor **both** and `affected_by` breaks for `event_log.py:213`,
`sweep.py:260`, `api.py:604`, `tools.py:174`, `operations.py:270`, plus the committed
expectations `affected_by("880(E)") == ["CA13-S2-85-SMALL"]` (`event_log.py:348`) and
`affected_by("G.S.R. 700(E)")` (`currency.py:396`).

**6.3** *"whole registered instrument ids"* has no referent in the matching domain.
What is matched is `Threshold.instrument`, a prose name. The only `instrument_id`
fields live inside registration records, and no caller holds one. An id-exact matcher
would have **zero live callers**.

**6.4** The step is under-specified on the part that matters. **PENDING cannot be
derived from the matcher at all**: `all_thresholds()` is four rows over two
instruments, so no matching change makes KMP, PAS, SEBI LODR or Rule 15 visible. The
step needs a new data source and does not say so.

**6.5 There are SIX register scripts, not five**, and three of six break the assumed
surface. `scripts/register_s188_rule15.py` exposes **`review_record()`, not
`registration()`**, writes to `corpus/rules/s188_rule15_review.json` not
`corpus/sources/`, and keys the name as `instrument` not `title`.
`register_sebi_lodr.py` has no `attestation_gaps`. `register_kmp_rules.py` is the one
module where attested != servable by design. **This is precisely why the registry
declares the accessor per entry.**

**6.6** A pre-existing inconsistency the step does not mention: `affected_by("")`
returns an obligation today while `acquisition_for("")` returns `None`. Folded into
§4.1.

## 7. What this does not do

Does not change how 700(E)/880(E) are answered (threshold path first, untouched).
Does not poll anything — `PENDING` makes no claim a successor would be discovered.
Does not make anything newly servable — `read` is still the deciding module's own
word. Does not touch `scripts/register_*.py`.

## 8. Independent re-verification by the main session

The architect could not run a shell and did not have `docs/plan19/` on its worktree,
so it flagged §6 as written against the quoted step text only. Three load-bearing
claims were re-checked directly before this file was written:

| Claim | Check | Result |
|---|---|---|
| Six register scripts, not five | `ls scripts/register_*.py \| wc -l` | **6** |
| s188 exposes `review_record()` not `registration()` | `grep -n "def review_record\|def registration" scripts/register_s188_rule15.py` | **`review_record()` at line 68, no `registration`** |
| `affected_by("")` returns an obligation | `affected_by("")` | **`['CA13-S2-85-SMALL']`**, while `acquisition_for("")` is `None` |
| `tools.py` calls `effective_from.isoformat()` unguarded | read lines 220-226 | **confirmed, unguarded** |

All four hold. The decision proceeds on that basis.
