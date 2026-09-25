# 03: Architecture: the object model, the watch engine, and one verb table for every surface

This extends PLAN_17 §2 (the shells) and PLAN_18 (the beta's technical design). The shells,
the rings and the release gate do not change. Everything here slots into them.

## 1. What is added, shell by shell

```
SHELL 5 OPERATIONS   + watch delivery SLOs · alert-precision review (human sample)
SHELL 4 SURFACES     + verb table → CLI · MCP · HTTP (generated, parity-tested)
                     + terminal (grammar over the verb table; web, in -3300)
SHELL 3 PLATFORM       (PLAN_18 unchanged: gateway, identity, tenancy, Vault, jobs)
SHELL 2 INTELLIGENCE + derivation evaluator (witness sets → evidence state)
                     + citator treatment proposals (model proposes, human labels)
SHELL 1 EVIDENCE     + ontology v1 (typed objects, every property Observed[T])
                     + observation store (bitemporal, append-only)
                     + watch engine (subscriptions, impact propagation)
                     + entity resolution (exact-id linking; Fellegi–Sunter proposals)
                     + citation graph (Ring 2 source, Ring 1 structure)
SHELL 0 LEGAL CORE     nothing new
```

| New module | Ring (`checker/rings.py`) | Depends on | Phase |
|---|---|---|---|
| `checker/ontology.py` | 1 | `provenance`, `licence`, `legal_ref` | G1 |
| `checker/observation_store.py` | 1 | `ontology`, the storage pattern of `operation_store` | G1 |
| `checker/derivation.py` | 1 (pure algebra, no I/O) | `provenance`, `lattice` | G2 |
| `checker/watch.py` | 1 | `event_log`, `entity_graph`, `obligations`, `derivation` | G3 |
| `checker/verbs.py` | 4 (surface), imports down only | `api`, `mcp/tools` | G4 |
| `checker/citator/` | 2 (feed) and 1 (graph) | `feeds/common`, `derivation` | G5 |
| `checker/resolve.py` | 1 | `entity_graph`, `party_resolution` | G6 |

The ring of every new module is registered in `rings.py`, in the same commit that creates it.
The existing AST check (including RT-01's dynamic-import ban and RT-02's transitive closure) then
enforces it without new machinery.

## 2. Ontology v1: typed objects, where every property is an observation

**Gotham's idea (01 §1.1):** one object model that every source maps into. **Our constraint:**
types change only by a reviewed commit, never at runtime.

```python
# checker/ontology.py   (Ring 1; stdlib only)
@dataclass(frozen=True)
class Observed(Generic[T]):
    value: T | Unknown               # Unknown is a type, never None and never 0
    source: SourceRef                # provenance.Source shape: url, sha256, fetched_at
    valid: Interval                  # when it was true in the world (checker/interval.py)
    known_at: datetime               # when WE recorded it (transaction time)
    evidence: str                    # a provenance.STATES member
    licence: frozenset[str]          # PLAN_08 Axis D rights held for this value

OBJECT_TYPES = ("Company", "Individual", "Instrument", "Provision", "Obligation",
                "Document", "Matter", "Judgment", "Observation")
LINK_TYPES   = entity_graph.Rel values + ("AMENDS", "CITES", "TREATS", "CONCERNS",
                "EVIDENCES")
```

**Rules, each enforced by a test in the module's `_test()`:**

1. **Types come from existing modules.** `LINK_TYPES` is built from `entity_graph.Rel`, so the
   entity graph and the ontology cannot diverge.
2. **Individuals are handles, not people.** `Individual` carries an opaque id. It never carries
   a name, DIN, PAN or address, the line `entity_graph.py:22-27` [R] already holds. The mapping
   from handle to person lives in the tenant's Vault (PLAN_18 §2.8), under RLS.
3. **Evidence is never inferred for the object.** An object has no evidence state of its own.
   Every rollup is computed by `derivation.py` (§4) and carries its witness.
4. **A new object type needs** a ring assignment, a licence rule and an entry in
   `docs/plan19/03_ARCHITECTURE.md`. Adding one without those fails the gate.

## 3. The observation store: bitemporal and append-only

`event_log.py` already models `at` (valid time) and `known_at` (transaction time). Its docstring
says `known_at` cannot answer "what was knowable to us on 31 March?" until a store exists [R].
This is that store.

```python
# checker/observation_store.py   (Ring 1)
def append(obs: Observed, *, actor: Identity) -> ObsId      # log first, then index
def as_of(entity: str, prop: str, *, valid_at: date, known_at: datetime) -> list[Observed]
def history(entity: str, prop: str) -> list[Observed]       # every version, never collapsed
def retract(obs_id: ObsId, *, reason: str, actor: Identity) -> ObsId
                                                            # a NEW row whose evidence is
                                                            # RETRACTED; nothing is deleted
```

It reuses the four properties `operation_store.py` was red-teamed into:

- RT-08: the log is written first;
- RT-09: writes are atomic;
- RT-11: a lost update is refused;
- RT-12: a minimum source shape is required.

The rule that matters is **nothing is updated in place and nothing is deleted.** A correction is
a new observation with a later `known_at`. That is what makes "what did Themis tell this client on
31 March, and on what basis?" reproducible years later. It is the audit property Gotham sells to
governments, and the property a law firm needs when an opinion is challenged.

**Storage:** JSONL on disk for the beta, the same as the operation store. It moves to the PLAN_18
Postgres `observations` table at M4, with RLS by tenant for tenant-contributed rows. The shared
corpus rows carry `tenant_id IS NULL` and are readable by all.

## 4. Derivations: every conclusion stores its witnesses

Today `lattice.worst_of` computes one rollup per call and returns one witness [R]. That handles a
single derivation. It cannot express the following:

- *"This obligation is established by the statute (VERIFIED) **or** by a corroborated secondary
  source, and it needs the threshold notification (CORROBORATED) **and** the company's paid-up
  capital (INFERRED from an upload)."*
- *"When the threshold notification is retracted, which of the 4,000 conclusions served this
  month change?"*

`derivation.py` stores each conclusion's **minimal witness sets**. 04 §2 proves the algebra. The
interface:

```python
# checker/derivation.py   (Ring 1, pure)
@dataclass(frozen=True)
class Derivation:
    conclusion: str                         # a stable id, e.g. "obl:s185:CIN:2026-03-31"
    witnesses: frozenset[frozenset[str]]    # OR over sets, AND within a set; minimal

def evaluate(d: Derivation, state_of: Callable[[str], str]) -> Verdict
    # max over witness sets of (min over members); witness = the weakest member of the best set
def dependents(fact_id: str) -> set[str]    # reverse index: which conclusions mention fact_id
def reevaluate(fact_id: str) -> list[tuple[str, Verdict, Verdict]]   # (conclusion, before, after)
```

**The guard that the algebra cannot give.** Alternative derivations are OR-ed only when they
yield the **same conclusion value**. Two routes that disagree (one source says ₹10 crore, another
₹4 crore) are a `SOURCE_CONFLICT` [R: `provenance.py:160`], never a max. `evaluate` refuses mixed
values, and a test proves the refusal.

## 5. The watch engine

**The question a lawyer's monitoring asks:** *what changed that alters the legal position of a
company or matter I care about, and on what basis?*

Impact propagation is reachability over typed edges that already exist:

```
Instrument --AMENDS--> Provision --grounds--> Obligation --applies-to--> Company --in--> Matter
  (eGazette feed)    (event_log.affected_by)  (obligations.py)   (company_profile / entity_graph)
```

```python
# checker/watch.py   (Ring 1)
@dataclass(frozen=True)
class Subscription:
    tenant: str; matter: str
    target: str                    # a Company handle, a Provision ref, or an Instrument fragment
    kinds: frozenset[str]          # LAW_CHANGE, COMPANY_FACT, CASE_TREATMENT, SIGNAL

@dataclass(frozen=True)
class Alert:
    subscription: Subscription
    path: tuple[str, ...]          # the edge path from the change to the target: the reason
    derivation: Derivation         # so its evidence state is computed, not asserted
    output_class: str              # VERIFIED_FACT | DETERMINISTIC_CONSEQUENCE | SIGNAL
    known_at: datetime

def on_observation(obs: Observed) -> list[Alert]    # incremental: only paths through obs
```

**Rules:**

1. **An alert is a derivation, not a score.** Its evidence state comes from `derivation.evaluate`.
   A `SIGNAL` alert says so in its first word on every surface.
2. **Deterministic by default.** No statistical anomaly alert ships without meeting 04 §5's
   false-alarm budget. At 10,000 monitored companies, a 1% per-period false-alarm rate is 100
   false alerts per period. That is why statistical alerts are off.
3. **Refusal-preserving.** An instrument that is registered but not read produces an alert whose
   consequence reads `BASIS_UNACQUIRED` [R: `event_log.py`], never an invented consequence.
   Watching law we do not hold produces the scope refusal, not silence.
4. **Incremental.** `on_observation` walks only the edges reachable from the new observation, in
   the semi-naive style (04 §4). A full recompute is a nightly consistency check that must agree
   exactly. If it disagrees, that is a defect.

**Known defect to fix first (G0):** `currency.acquisition_for` matches by unanchored substring,
so "Companies Act 2013" or "G.S.R." alone return `read=True`. It also returns `None` for
registered-but-pending instruments, conflating "unknown" with "not attested". The watch engine
propagates from exactly this function, so it must be fixed before G3.

## 6. One verb table, three surfaces (API → MCP → CLI)

**The problem.** Today the HTTP routes (`checker/api.py`, 8 routes), the MCP tools
(`checker/mcp/tools.py`, 13 read tools) and the planned CLI (PLAN_17 M3) are three hand-written
lists. AGENTS.md in `-3300` already records one drift: it documented a `/standing` route that did
not exist.

**The design.** One declarative table is the only place a verb is defined. Each surface is
generated from it, and a parity test fails the gate if any surface has a verb the table lacks,
or the reverse.

```python
# checker/verbs.py   (Shell 4)
@dataclass(frozen=True)
class Verb:
    name: str                 # "company.events"
    mnemonic: str             # "EVT", for the terminal (§7)
    action: str               # READ | WRITE | ATTEST   (mcp/policy.py vocabulary)
    params: tuple[Param, ...] # typed; generates the JSON Schema for MCP and argparse for the CLI
    handler: Callable         # calls api.handle or a Ring 0/1 function; never a model
    http: tuple[str, str] | None   # ("GET", "/v1/company/{cin}/events")
    output_classes: frozenset[str]

VERBS: tuple[Verb, ...] = (...)

def mcp_tools() -> list[dict]      # replaces the hand-written list in mcp/tools.py
def cli_parser() -> ArgumentParser # scripts/themis (PLAN_17 M3)
def http_routes() -> dict          # what the gateway (PLAN_18 §2.1) mounts
```

**Invariants tested:**

- the three surfaces cover the same verb set;
- every `WRITE` or `ATTEST` verb is absent from MCP until PLAN_18 §2.12's token identity lands
  (the RT-10 lesson);
- every handler is deterministic, so identical input returns an identical payload, byte for byte,
  on every surface.

**Integration path, in order:**

1. The verb table wraps today's 8 routes and 13 tools with **no behaviour change**. The parity
   test goes green on current behaviour.
2. The CLI is generated (PLAN_17 M3).
3. The gateway mounts `http_routes()` (M3).
4. MCP over HTTP with OAuth 2.1 (M9, PLAN_18 §2.12).
5. New verbs are added: `watch.*` (G3), `case.cite` (G5), `entity.resolve` (G6).

## 7. The terminal

**What Bloomberg's density actually is [I].** Keyboard-first commands, fixed-width columns,
every figure in mono, and no navigation chrome. It is a UI discipline. It needs no more data than
we have.

**Grammar.** `<TARGET> <MNEMONIC> [args] ⏎`, parsed into exactly one `Verb`:

```
CO U74999DL2015PTC000001 EVT              company.events       (as of today)
CO U74999DL2015PTC000001 OBL 2026-03-31   company.obligations  (as of a date)
SEC 185 VER 2019-03-31                    law.version          (s.185 as in force that day)
INS "G.S.R. 880(E)" IMP                   instrument.impact
CASE "(2019) 4 SCC 17" CITE               case.cite            (G5; refuses until built)
WATCH ADD CO U74999DL2015PTC000001        watch.subscribe      (WRITE: identity required)
?  s.185 loan to director's relative       ask                  (the Ask pipeline, PLAN_18 §2.4)
```

**Rendering rules (AGENTS.md in `-3300`):**

- mono for every section, figure, instrument and date;
- abstain-grey `#5B6472` only for abstention;
- a transport failure never renders as an abstention (`EngineResult<T>`);
- one gold accent per view.

The terminal is a page in the logged-in app (PLAN_17 M10). It calls the gateway, never the engine
directly, because the engine is server-only (AGENTS.md). **The CLI and the web terminal share one
grammar file**, so a lawyer who learns one has learned both.

## 8. The citator (case-law currency)

```
Ring 2  checker/citator/source_sc.py     SC corpus (AWS Open Data); fetch via feeds/common
Ring 1  checker/citator/extract.py       citation strings → normalised Judgment refs (regex; measured)
Ring 1  checker/citator/graph.py         CITES edges; TREATS edges carry a human label or are SIGNAL
Ring 1  checker/citator/status.py        good_law(ref, as_of) → Verdict via derivation.evaluate
```

`good_law` has four outcomes:

- `NEGATIVE_TREATMENT` with the witness: this judgment, overruled by that one, on that date, a
  human-labelled treatment;
- `NO_NEGATIVE_TREATMENT_FOUND` **within the corpus held, as of that corpus's `known_at`**, with
  the corpus boundary stated;
- `UNKNOWN`: the citation could not be resolved;
- `NOT_HELD`: a court we do not hold.

Never plain "good law". Absence of a found treatment is not a finding of approval: the same
tri-state discipline as `entity_graph`.

## 9. Entity resolution

1. **Exact identifiers only make a SERVABLE edge:** CIN, LLPIN, DIN. `party_resolution.inspect`
   already validates CIN shape and flags OCR-like candidates [R].
2. **Everything else is a proposal.** Fellegi–Sunter match weights (04 §6) rank candidate links
   between name-only mentions (a sanctions entry, a judgment party, a counterparty in a contract)
   and known entities. A proposal lands in the review queue (`review_queue.py`) [R]. It never
   becomes an edge without a human attestation.
3. **No new dependency.** Splink (MoJ, MIT-licensed) is the reference implementation, but it
   brings DuckDB or Spark. The EM estimation of m/u probabilities is about 150 lines of standard
   library at our volumes. **Stated reason:** `CLAUDE.md` forbids a new dependency without one.
   Splink stays the **reference against which our implementation is tested** (same inputs, same
   weights to 1e-6), not a runtime import. The architect subagent records this decision before
   G6 starts.

## 10. What does not change

- `checker.api.handle` stays deterministic and standard-library (PLAN_18 §2.2).
- `release.may_release` is the only door to a user. Nothing in this plan adds a second.
- The MCP surface stays read-only until identity comes from a validated token.
- No model creates an event, a date, an edge, or a consequence (`event_log.py` docstring). Models
  may propose a citation treatment or an entity link, and phrase a title from verified fields.
  Nothing more.
