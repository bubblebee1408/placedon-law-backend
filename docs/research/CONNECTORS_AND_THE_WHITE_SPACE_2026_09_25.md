# How Harvey and Spellbook connect to other systems — and the gap neither fills

25 Sep 2026. Desk research. Tags: **[V]** vendor's own words · **[I]** independently reported ·
**[M]** forced by a technical mechanism · **[U]** unconfirmed.

## 1. The strategic finding, first

**Neither Harvey nor Spellbook verifies a document's factual assertions against a government
registry.** Exhaustive search of both vendors' sites, help centres, integration pages and press as
of today found **no** company-registry lookup, no charge or security-interest search, no
filing-status check, no director/shareholder/UBO verification, no sanctions screening — and no
assertion-level "does this recital match the register" check anywhere. **[V] as an absence**; an
undocumented enterprise capability remains **[U]**.

Both retrieve **law** and cite it. Both include filing repositories — EDGAR, SEDAR — but as
**research corpora you can read**, not as **registers you check a claim against**.

> **Retrieval is not verification. Nothing in either product closes the loop from "the contract
> asserts X about this party" to "the register says Y".**

And in India the verification capability **does** exist — as a **fintech KYB** category, not a legal
one: Karza (acquired by Perfios ~$80M, 2022) aggregates MCA records, GST, ITR, court databases,
EPFO, property and vehicle data behind APIs; Probe42, Tofler, Signzy, Surepass compete. **[I]** None
of them has a drafting, redlining or clause-analysis surface.

**Verification exists. Drafting exists. Nothing joins them. That disjunction is the white space, and
it is the business this repository has been accidentally building toward.**

## 2. Harvey's connector model — precisely what the founder described

Connector Library, early access from **mid-June 2026** **[V]**:

- **Native API connectors:** Gmail, Google Drive, Outlook, SharePoint.
- **MCP connectors:** iManage, NetDocuments, Box, PitchBook, SS&C Intralinks DealCentre AI, Datasite.
- **How it connects:** a workspace **administrator must enable** the connector before any user may
  use it; the user then authenticates and "Harvey handles the authentication handshake, stores the
  user's token securely"; partner servers must implement **OAuth 2.1 with PKCE, S256 required**.
- **BYOMCP, verbatim:** *"Bring Your Own MCP Server (BYOMCP) allows a workspace administrator to
  connect a custom MCP server to Harvey for use within their Harvey workspace."* **[V]**

**Harvey is also an MCP server** — usable from Claude, Gemini and Microsoft 365 Copilot, remote MCP
over Streamable HTTP, OAuth. Five tools: `ask_harvey`, `ask_with_knowledge_source`,
`list_knowledge_sources`, `list_vault_projects`, `ask_about_vault`. Each call is stateless and scoped
to the authenticated user's permissions. **[V]**

**Harvey's own governance disclaimers, worth quoting to anyone who assumes connectors are safe [V]:**
- *"Harvey's controls apply up to the point where a request leaves Harvey."*
- *"Harvey may not prompt users before a connected tool executes certain types of write actions."*
- *"Harvey does not continuously monitor custom MCP servers."*

## 3. Spellbook is architecturally the opposite

- **Spellbook does not author tracked changes — Word does.** Its help centre says clauses inserted
  from the Draft tab *"will not automatically redline"* and tells the user to turn on Track Changes
  **in Microsoft Word**. It writes text at the cursor through an Office.js add-in; Word records that
  as a tracked change attributed to the signed-in user. No public diff engine. **[V][M]**
- **Harvey does have a real diff pipeline**, and describes it in engineering terms: edits applied
  *"through the Word JavaScript object model"*, LLM reasoning done in natural language then
  *"deterministically translate[d] back into precise OOXML mutations"*, tracked changes produced
  *"via a word-level diff"*. **[V]** This is the sharpest technical divergence between them.
- **Spellbook has no public API, no webhooks, no MCP and no BYO mechanism.** A customer cannot add
  the missing capability at all. Harvey at least provides a socket.
- Its own coverage claim is **internally inconsistent**: "1,000+ public legal databases" on two
  pages, "100+" on two others, unreconciled. **[V]** Mechanism claim: *"we query the source of
  record directly, so the currency of our results reflects what the publishing authority has
  posted."* **[V]**

## 4. What this means for us

**The opportunity is not to be Harvey. It is to be the thing Harvey explicitly leaves to someone
else — and Harvey has already built the socket to plug it into.**

`checker/mcp/` already exposes **thirteen read-only tools over the engine**, refusal-preserving,
with `_policy` and `_boundary` on every response and **no write of any kind**. That is, structurally,
a BYOMCP-compatible server. The gap between what exists and "PlacedOn verification inside a Harvey
workspace" is OAuth 2.1 + PKCE (S256) and a remote transport — **not** a new product.

Three consequences for the plan:

1. **Our MCP surface is a distribution channel, not just an internal tool.** It reaches Harvey via
   BYOMCP, and Claude / Gemini / Copilot directly. This is the cheapest route to being used by
   lawyers who will never buy a second seat.
2. **Read-only is a feature here, not a limitation.** Harvey's own disclaimer is that it "may not
   prompt users before a connected tool executes certain types of write actions". A server that
   *cannot* write is the safe thing to hand an agent, and ours already refuses `submit_evidence`.
3. **The verification loop is the product.** Not drafting — Harvey does that better and has the
   OOXML pipeline to prove it. The loop is: *this document asserts X about this company on this
   date → the register and the law then in force say Y*. Nobody ships that, in any jurisdiction.

**What it needs that we do not have:** company-register data. Which returns to the MCA finding —
no OAuth, no delegation, no API, and no sanctioned aggregator licence to buy. The lawful inbound
route today is customer-in-the-loop upload, plus data.gov.in's GODL-licensed Company Master Data.

## 5. Corroboration to chase, not to cite
arXiv:2512.18658, *"Does It Tie Out? Towards Autonomous Legal Agents in Venture Capital"* (Dec 2025)
reportedly frames capitalisation diligence — reconciling documents against ownership records — as a
manual, error-prone, capped-fee bottleneck AI has not automated. **[U] — abstract only, not read.**
If it holds up, it is third-party evidence for exactly this white space. Read it before citing it.
