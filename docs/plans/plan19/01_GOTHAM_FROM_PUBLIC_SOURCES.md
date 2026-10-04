# 01: What Gotham is, from public material, and what transfers

## 0. Method and limits

The only sources used are Palantir's own patents (Google Patents, Justia), Palantir's public
documentation (`palantir.com/docs`), and Palantir's own marketing PDFs. The UK G-Cloud 14 service
definition for Gotham was located but **could not be fetched**, because this environment's egress
proxy blocked it. It is the best public architecture description and should be read by a person.
Secondary analyses (Scribd, HackMD, a patent-analysis blog) turned up in search and are **not
relied on**.

Gotham is closed-source. Nothing below describes code, only public claims about behaviour.

## 1. The five load-bearing mechanisms

### 1.1 A dynamic ontology: the schema is data [V]

US 7,962,495 B2, *Creating data in a data store using a dynamic ontology*, was filed on
2006-11-20 and granted on 2011-06-14. The inventors are Gettings, Jain and McGrew; the assignee is
Palantir Technologies. As its claims were summarised:

- The ontology is created from user input, and consists of **object types** and **property types**.
- **Parser definitions** transform input data into values those property types accept.
- The attributes of object types and property types can be edited at any time.

Continuations extend the family, for example US 9,589,014 B2 and US 12,386,803 (granted
2025-08-12).

**What it means:** analysts work on *objects* (Person, Organisation, Event, Document), not on
tables. A new source is integrated by writing a parser into existing types, not by adding a table.
That is why a Gotham deployment can absorb a new feed without a schema migration.

**What transfers:** the idea of a single typed object model that every source maps into.
**What does not:** "editable at any time". In a legal product, a type change is a change to what
a finding *means*. Our types change by a reviewed commit, with a test (see 03 §2).

### 1.2 Provenance and access control on the property, not the row [V]

Palantir's Nexus Peering patents describe:

- replicating **ACL changes** on "a secured component of a data object" between sites
  (US 2015/0261847 A1 and relatives);
- translating between sites that use **different classification schemes**, by agreed translation
  rules.

Palantir's *Secure Collaboration* PDF says artifacts such as documents, slides and maps
**"automatically update to the highest security level of their content."**

**What it means:** security and provenance attach to individual properties. A composite inherits
the **join** (the most restrictive) of what it contains. That is Denning's lattice model of secure
information flow (CACM, 1976). *[I: the citation is mine, not Palantir's.]*

**What transfers, and is already built:**

- `checker/lattice.py` [R] implements "the worst thing wins", with a named witness. That is the
  same join, applied to evidence state rather than classification.
- `checker/release.py` [R] is the single gate: only `CORROBORATED` or `VERIFIED` evidence may
  reach a user.
- PLAN_08 Axis D (licence and redistribution) is the classification scheme's analogue. A fact
  from a CC-BY source joined with a fact from a non-redistributable source yields a view that may
  not be redistributed.

**What is missing:** the join is computed per call, not stored per property. 04 §2 gives the
algebra that lets it be stored and re-evaluated.

### 1.3 Graph, map and timeline are three projections of one object set [V]

Palantir's public Object Explorer documentation (Foundry, which Gotham integrates with) describes:

- search from keyword to property filter;
- exploration of result sets;
- a per-object view;
- a graph of link types between object types.

**What it means:** the analyst never leaves the object set. Graph, table, timeline and map are
views of it. That is the part of "Gotham for lawyers" that is really a UI decision.

**What transfers:** graph and timeline. For an Indian corporate lawyer:

- the graph is `checker/entity_graph.py` [R], covering directors, relatives, control and
  shareholding;
- the timeline is `checker/event_log.py` [R], which is bitemporal, with `at` and `known_at`.

**What does not:** the map. Geography carries no legal weight in a Companies Act question. The
3-D globe was declined in PLAN_08 §5 and BLOOMBERG_FOR_INDIA §3.3. This plan does not reopen that.

### 1.4 Replication across disconnected sites (Nexus Peering) [V, marketing claim]

Palantir says Nexus Peering works "in low bandwidth conditions or disconnected environments",
queuing data until the link returns. It also says it combines "data enriched by different users
and teams without creating duplicate or conflicting copies".

**What transfers:** only the principle that each tenant's enrichment (annotations, attestations)
stays separate from the shared corpus and merges by rule. PLAN_18 §3 (tenancy, row-level
security) already fixes this. **Not needed:** multi-site replication. Nothing we sell runs
disconnected.

### 1.5 Humans decide; the system assembles [I, from the above]

Nothing in the public material describes Gotham reaching a decision on its own. It assembles
evidence for an analyst. That matches this repository's rule that a model may propose and never
decide (`CLAUDE.md`), and the MCP surface is read-only for the same reason (RT-10).

## 2. Where Gotham's model breaks for law

| Gotham assumption | Why it fails for Indian corporate law | Our replacement |
|---|---|---|
| Absence of a link is just absence | "No director edge" read as "not a director" is a fabricated fact | Tri-state queries: YES / NO / UNKNOWN. NO only under an explicit completeness assertion (`entity_graph.py:14-20`) [R] |
| One time axis | A lawyer asks both "what is true of 31 March?" and "what could we have known on 31 March?" | Valid time plus transaction time (`event_log.py` docstring) [R], with the store still to build |
| Ontology edited at will | A changed type changes the meaning of past findings | Types versioned in code, and a type change is a reviewed commit (03 §2) |
| Sources are fused | Fusing a news report with a Gazette notification blurs authority | Ring 2 observations never become Ring 0 facts (`checker/rings.py`) [R] |
| Analysts judge credibility | Our buyer needs the basis stated, not a credibility score | Evidence-state lattice with a named witness; no confidence percentages (AGENTS.md) |

## 3. The honest comparison, for an investor

Gotham is a general investigative workbench whose moat is the integration of many sources. Its
customers have lawful access to those sources.

In India, the sources that would make a *market-wide* legal Gotham either are not public or
forbid machine reuse:

- MCA21 has no API or delegation;
- NSE's terms prohibit scraping;
- DGCI&S withholds shipment-level data;
- NJDG's open API is limited to government.

That leaves two conclusions:

- **The integration moat cannot be built here by anyone at startup cost.** PLAN_08 §5 and
  PLAN_14 §3 already recorded this.
- **The discipline moat can be built:** every fact typed, dated, sourced, licensed and gated.
  That is what this plan builds.

## Sources

- US 7,962,495 B2: https://patents.google.com/patent/US7962495B2/en
- US 9,589,014 B2: https://patents.google.com/patent/US9589014B2/en
- US 12,386,803: https://patents.justia.com/patent/12386803
- US 2015/0261847 A1 (classification translation between nexuses): https://patents.google.com/patent/US20150261847
- Palantir, *Secure Collaboration* PDF: https://www.palantir.com/assets/xrfr7uokpv1b/4JWbqPQ8d6vYcNijOVqD0D/2857507783a328b6ddb6aef1ffc5fac4/Palantir_for_Secure_Collaboration__1_.pdf
- Object Explorer docs: https://www.palantir.com/docs/foundry/object-explorer/overview
- Ontology overview: https://www.palantir.com/docs/foundry/ontology/overview
- G-Cloud 14 Gotham service definition, **not fetched (egress-blocked)**: https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/92736/801146272055049-service-definition-document-2024-11-26-1253.pdf
- Denning, D. E., *A Lattice Model of Secure Information Flow*, CACM 19(5), 1976. Cited from knowledge and not re-checked today.

## Open-source analogue worth studying, not adopting

OCCRP's **Aleph** and its **FollowTheMoney** (FtM) model are an open-source investigative graph
built for journalists [V]:

- `ingest-file` turns documents into an FtM entity graph;
- `memorious` crawls;
- FtM is published as RDF/Turtle;
- OpenSanctions uses FtM, which matters because the sanctions overlay (PLAN_08 §5) would arrive
  in FtM shape.

**Take:** FtM's entity schema, as a mapping target for sanctions data. **Do not take:** Aleph as
a platform. It is built for leaked-document investigation, which `CLAUDE.md` forbids ("Do not
obtain private minutes or confidential company documents").

- https://docs.aleph.occrp.org/developers/followthemoney/
- https://www.opensanctions.org/docs/opensource/fincrime/
