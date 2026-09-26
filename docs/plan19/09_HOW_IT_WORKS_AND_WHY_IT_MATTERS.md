# 09: Project Themis: how it is built, what matters, and how it could change legal work in India

*Written for the founder, 2026-09-26. Plain language first, technical names in brackets so you can
find the code. Nothing here is a measured market figure unless it says where it was measured.*

---

## Part 0: What Project Themis is

### The name, and what it stands for

**Themis** was adopted as the project name on your decision of 16 September 2026
(`docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §0). In Greek, Θέμις means *"that which is laid
down"*: established law, as distinct from argument. That is the project in one word:

- Themis serves only what is **laid down**: a provision, the instrument that changed it, and the
  date it took effect.
- Anything that is not established well enough is **refused, visibly**.

The motto in the README says the same thing in three sentences:

> **The model may propose. The system must verify. The reviewer decides.**

### Themis and Placedon: engine and product

| Name | What it is | Decided |
|---|---|---|
| **Themis** | **The engine.** The code that holds the law, reasons over it, checks every answer, and refuses when it cannot prove one. Everything in `checker/`, the Themis MCP tools (`themis.ask`, `themis.search_law`, `themis.get_obligations` and the rest) and scripts such as `scripts/themis_mcp.py` and `scripts/themis_slice.py` | Engine named 16 Sep 2026 |
| **Placedon** | **The product and brand** a customer buys and logs into. The website, the web app, pricing and the company | PLAN_16 decision 5, 24 Sep 2026 |

A useful comparison: Placedon is the car a customer drives, and Themis is the engine. Every plan
from PLAN_16 onward, the study guide (`docs/STUDY_GUIDE_THEMIS.md`) and the technical report
(`docs/THEMIS_TECHNICAL_REPORT_2026_09_17.md`) is about Themis.

### Where Themis came from

| When | What happened |
|---|---|
| 12 Aug 2026 | The repository starts on a different law: PoSH (workplace sexual harassment) tooling, e.g. District Officer letters. Retired since; only its refusal and `docs/RETIRED_POSH.md` remain |
| 20 Aug | Scope changes to Indian corporate law (`research/TASKS.md` R-011). The Companies Act corpus, scanner and date logic follow |
| 11 Sep (PLAN_08) | Two layers are proposed: **Bookmark** (a company and entity graph, "Bloomberg for Indian corporate law") and **God's Eye** (live data feeds). A source audit finds that most market-wide data in India cannot lawfully be reused |
| 16 Sep | **Themis** replaces both names as the project name |
| 17 Sep | The Themis technical report: deterministic core verified, and three weaknesses named (a broken PDF reader, an amendment corpus frozen since 2023, no lawyer review) |
| 23 Sep | **Themis V0 vertical slice** (`scripts/themis_slice.py`) runs end to end on live Gazette data: *Gazette event → affected obligation → watchlist → operation → tasks → human review* |
| 24 Sep | PLAN_16 (research), PLAN_17 (beta build) and PLAN_18 (technical design) written for Themis. Placedon confirmed as the product name, Themis as the engine |
| 25 Sep | The Themis MCP server ships 13 read-only tools. The gold set gives Themis its first honest measurement, which shows where it is wrong |
| 25–26 Sep | PLAN_19: the roadmap from Themis-the-engine to a Gotham-grade workbench for lawyers (parts 00–09) |

### The three things that make Themis Themis

1. **A deterministic core.** Code, not a model, decides what the law requires. Same question,
   same answer, every time.
2. **A record of the law over time.** Themis knows when each provision changed, so a question
   about 2021 is answered with 2021's law.
3. **A check on everything a model writes.** Every sentence must trace to its source exactly, or
   it is shown as refused.

And one gate that holds them together: the **admission gate** (`checker/admission.py`).
*"Existence is not admissibility."* A source can be downloaded, hashed and searchable and still
not be safe to state as law. Only material that has passed admission reaches an answer. This is
the literal meaning of the name: only what is *laid down* is served.

### A risk carried with the name

`Themis Solutions Inc.` is recorded as the registered name of Clio, a large legal
practice-management vendor, and other "Themis" businesses trade in legal and compliance services.
Trademark clearance is **UNVERIFIED and likely contested** (THEMIS_STATUS §0). Keeping Themis as
the *internal engine* name while customers see *Placedon* reduces that exposure. It does not
remove it if "Themis" is ever used in marketing. Get a trademark lawyer's view before it appears
on the website.

---

## Part 1: The idea in one page

### The problem, told as one real example

Indian company law has a category called a **small company**, and being one lightens the load:
fewer board meetings, a lighter annual return, no cash-flow statement, and more.

Whether a company is "small" depends on two numbers, **paid-up capital** and **turnover**. Those
numbers are not written in the Act. The government sets them by notification, and changes them:

| Instrument | Paid-up capital limit | Turnover limit | In force from |
|---|---|---|---|
| G.S.R. 700(E), 2022 | ₹4 crore | ₹40 crore | 2022 |
| G.S.R. 880(E) | **₹10 crore** | **₹100 crore** | **1 December 2025** |

A company with ₹7 crore capital was **not** small on 30 November 2025 and **was** small on
1 December 2025. Nothing in the Act's wording changed. Only a Gazette notification did.

What went wrong, measured in this repository (PLAN_00, FEATURES.md):

- **Our own engine** kept serving the ₹4 crore figure as current for months after it was replaced.
  When we built a check for this, it immediately found three more obligations with the same
  problem.
- **Four of the most-read Indian compliance websites** checked were still publishing the 2022
  figure. One published a figure that has never existed.
- **General AI tools** answer from whatever they read in training. A preregistered study of
  commercial legal AI research tools (Magesh et al., *Journal of Empirical Legal Studies*, 2025)
  found them hallucinating 17–33% of the time.

So a lawyer who asks "is this company a small company?" can get a confident, wrong answer from a
person, a website or an AI. **None of them tells you which notification the answer rests on, or
that it may be out of date.**

### What Themis does about it

Themis (the engine inside Placedon) answers only when it can show:

1. **the exact provision:** s.2(85), the definition of small company;
2. **the instrument that last changed it:** G.S.R. 880(E);
3. **the date it took effect:** 1 December 2025;
4. **how strong the evidence is:** for example, "corroborated from the Gazette copy";

and when it **cannot** show those, it **abstains** and says what is missing. It never guesses and
never stays silent.

**The one-line difference:** most legal tools help you *find* law. Themis *checks* whether the
law you are relying on is the right law, for the right company, on the right date, and proves it.

---

## Part 2: How Themis is built, explained as a building

Think of it as a building with six floors. **A floor may only rest on the floors below it, never
above.** This is enforced by code (`checker/rings.py`), not by good intentions. If an engineer
makes the legal core depend on a news feed, the build fails.

```
 FLOOR 5  OPERATIONS      tests, monitoring, the gold set, security reviews
 FLOOR 4  SURFACES        web app · terminal · CLI · MCP (inside Claude/Copilot/Harvey) · Word add-in
 FLOOR 3  PLATFORM        login, one customer's data kept from another's, document vault, job queue
 FLOOR 2  INTELLIGENCE    the question pipeline; AI models used only to phrase, never to decide
 FLOOR 1  EVIDENCE        feeds (Gazette, sanctions, insolvency), company graph, timeline of changes
 FLOOR 0  LEGAL CORE      the Companies Act text, obligations, date logic, currency — pure rules
```

### Floor 0: the legal core (the heart of Themis, and the most valuable part)

- **What it holds:** 529 sections of the Companies Act, 2013, each hash-stamped so any change to
  the text is detectable (`corpus/companies_act/`).
- **What it does:**
  - works out which version of a section was in force on any date (`checker/as_of.py`);
  - works out which duties apply to a company (`checker/obligations.py`, and deciders for s.180,
    s.184, s.185, s.186 and s.188);
  - works out whether a figure is still current (`checker/currency.py`).
- **The rule that makes it trustworthy:** no AI model is on this floor. Everything here is
  deterministic: same question, same answer, every time. You can re-run it next year and get the
  identical result.
- **Why this matters:** a court, an auditor or opposing counsel can ask "how did you reach this?"
  and the answer is a chain of rules and sources, not "the model said so".

### Floor 1: the evidence

- **Feeds** bring in facts from named public sources: the eGazette, the OFAC sanctions list, and
  IBBI insolvency data (`checker/feeds/`).
- The **company graph** records who directs whom, who controls whom, and who holds shares
  (`checker/entity_graph.py`).
  - **The key discipline:** if the graph has no record that X is a director, it answers
    **UNKNOWN**, not NO. It says NO only when it has been told the list is complete.
  - "We have no record" and "it isn't true" are different answers. Confusing them is how software
    invents facts.
- The **timeline** (`checker/event_log.py`) records two dates for every change:
  - when it took effect in law;
  - when *we* learned of it.

  A lawyer needs both. "What was the law on 31 March?" and "what could we have known on
  31 March?" are different questions, and only the second defends an opinion given on that day.

### Floor 2: intelligence (where AI is allowed, and how it is fenced)

AI models are used for language: understanding a question, reading an uploaded document, and
phrasing an answer. **They never decide a legal fact.**

Every sentence an AI writes is traced back, byte for byte, to a passage in a source
(`checker/lawyer_summary.py`). A sentence that cannot be traced is not shown as fact.

**Why this is the right design:** the failure of legal AI is not that models are stupid. It is
that they are fluent when they are wrong. Fencing the model so it can only *phrase what the rules
decided* removes the fluent-and-wrong failure at the root.

### Floor 3: the platform (being designed, PLAN_17/18)

This floor covers:

- login, through the customer's Microsoft account;
- **each customer's data sealed from every other customer's**, enforced by the database itself;
- a **Vault** for a customer's own documents, which nothing is ever trained on without that
  customer's explicit opt-in;
- a job queue for long checks.

### Floor 4: surfaces (how a lawyer reaches it)

One engine, several doors:

- **Web app:** the main screen for in-house teams.
- **Terminal:** a Bloomberg-style keyboard screen. Type `CO <CIN> OBL 2026-03-31` and see every
  obligation of that company on that date.
- **CLI:** the same commands, for engineers and power users.
- **MCP:** a standard that lets AI assistants call tools. Through it, a lawyer inside Claude,
  Microsoft Copilot or Harvey can ask Placedon to check a fact without leaving the tool they
  already use. Today it offers 13 read-only tools (`checker/mcp/`).
- **Word add-in:** checks a draft where it is written.

PLAN_19 generates all of these from **one list of Themis commands** (the "verb table"), so the web app,
the CLI and the AI connector can never give different answers to the same question.

### Floor 5: operations (how we know it works)

- **The gate:** every change must pass about 200 automated test suites before it can be saved
  (`scripts/verify_green.sh`).
- **The gold set** (`eval/goldset/`): a bank of test questions with known right answers. It
  measures two things separately:
  - of the questions it *should* answer, how many it got right;
  - of the questions it *should refuse*, how many it refused.

  One number would hide whichever failure you have.
- **Honest status today:** the gold set has **zero questions checked by a practising lawyer.**
  So Placedon has **no accuracy figure**, and we do not publish one. Getting that first
  human-checked set is the most important non-code task (H-001).

### The journey of one question through Themis, floor by floor

> A lawyer asks: *"Is ABC Pvt Ltd a small company as of 31 March 2026? Its capital is ₹7 crore
> and turnover ₹60 crore."*

1. **Floor 4:** the question arrives from the web app, the terminal or Claude.
2. **Floor 3:** checks who is asking and that they may see this matter.
3. **Floor 2:** the **scope gate** asks whether this is about law we hold. Yes: the Companies Act.
   Had it been about FEMA or data protection, it would refuse and name that law.
4. **Floor 0:**
   - finds s.2(85);
   - finds that on 31 March 2026 the limits are ₹10 crore / ₹100 crore under G.S.R. 880(E),
     in force from 1 Dec 2025;
   - checks the evidence state of that notification (it must be CORROBORATED or VERIFIED to be
     served);
   - decides: capital ₹7 crore ≤ ₹10 crore, and turnover ₹60 crore ≤ ₹100 crore, so the company
     qualifies, subject to the exclusions in s.2(85), for example not being a holding or
     subsidiary company.
5. **Floor 2:**
   - the exclusions are facts the lawyer did not supply, so the answer says **"qualifies on
     thresholds; exclusions UNKNOWN"**, not a flat yes;
   - an AI model may phrase this in plain English, and every phrase is traced to s.2(85) or
     G.S.R. 880(E).
6. **Floor 4:** the lawyer sees the answer, the section in mono type, the instrument, the date,
   the evidence state, and what is still unknown.

Ask the same question **as of 30 November 2025** and the answer flips: ₹7 crore is above the old
₹4 crore limit. **That flip, shown with its reason, is the product.**

### The journey of one law change (what the V0 slice started and PLAN_19 completes: "watching")

> The government publishes a new notification in the Gazette.

1. The Gazette feed picks it up (Floor 1). This part already runs: the Themis V0 slice
   (`scripts/themis_slice.py`) does it on live data. One honest limit it found: a Gazette listing
   does not name the instrument inside it, so the first task is always a human opening the PDF.
2. The engine finds which sections it changes, which obligations rest on those sections, which of
   a customer's companies those obligations apply to, and which matters those companies are in.
3. Each affected customer gets an **alert that states its reason as a chain**:
   *notification → s.2(85) → small-company status → ABC Pvt Ltd → Matter "FY26 compliance"*.
4. If we have not yet read and checked the notification, the alert says so
   (`BASIS_UNACQUIRED`). It never invents what the change means.
5. **Recall:** if a source we relied on is later found wrong and withdrawn, the engine can list
   every answer it gave that rested on it. PLAN_19 part 04 proves this works without re-running
   anything. For a law firm, that is the difference between "we think our advice was fine" and
   "here are exactly the four opinions to revisit".

---

## Part 3: What is important (the seven Themis rules that are the real asset)

Code can be copied. These rules, held in every line of Themis, are what make Placedon different. If any one
is broken to ship faster, the product loses the reason it exists.

| # | Rule | Why it matters to a lawyer |
|---|---|---|
| 1 | **Every fact carries its source, date and evidence state** | A statement without a basis is not usable in advice |
| 2 | **Abstain rather than guess**, and say what is missing | A wrong confident answer costs more than "I don't know" |
| 3 | **Never silent about law we don't hold.** Name the law and say it is not held | Silence reads as "no obligation found", which is the worst error |
| 4 | **UNKNOWN is not NO** | Missing records are not evidence of absence |
| 5 | **AI phrases; rules decide** | Removes fluent-but-wrong answers at the root |
| 6 | **Never repair a government source.** Flag it and keep it verbatim | Our record must match the official record, defects included |
| 7 | **No accuracy claim without a lawyer-checked benchmark** | The first false claim ends trust in a trust product |

These come from `CLAUDE.md`, and each one was learned from a mistake recorded in
`docs/RETRACTIONS.md` or `.claude/memory/LESSONS.md`.

---

## Part 4: What of Themis is built and what is not (honest, 26 Sep 2026)

| Part | Status |
|---|---|
| Companies Act corpus, 529 sections, hash-stamped | **Built.** Cross-checked against India Code, with two known source defects recorded |
| Date logic: which version was in force when | **Built.** Boundary behaviour proved on s.177, s.447 and s.35 |
| Obligation deciders (s.180, 184, 185, 186, 188) | **Built** |
| Currency checks (is this figure still current?) | **Built** |
| Scope refusals for the other 8 bodies of law | **Built, but leaky.** It refuses when the Act is named (7/7), and misses when a practitioner describes it without naming it (2/7 caught). Fixing this is PLAN_19 G0.3 |
| Gazette, OFAC and IBBI feeds | **Built** |
| MCP connector (13 read-only tools) | **Built.** Local use only; secure remote use is PLAN_17 M9 |
| Gold set | **Built**, with 0 lawyer-checked questions |
| Login, multi-customer separation, Vault | **Designed** (PLAN_18), not built |
| Web app for customers | **Designed**, not built |
| Themis V0 slice: Gazette → affected obligation → tasks → human review | **Built** (`scripts/themis_slice.py`); produces work, never a legal conclusion |
| Watching and alerts, replay, recall | **Designed** (PLAN_19 G1–G3) |
| Case-law checker ("has this judgment been overruled?") | **Designed** (PLAN_19 G5); needs counsel's view on the data licence |
| Continuous automated testing on GitHub (CI) | **Waiting on you:** add the workflow file through the GitHub website |

---

## Part 5: How Themis could change the market for lawyers

This part separates what is **observed** (with a source) from what is **reasoning** (marked [I]).
No market-size number is given, because none has been measured for this segment (R-011 in
`research/TASKS.md` is still open).

### 5.1 What legal work in India looks like today

- **The law moves by notification** (observed: the small-company example above; PLAN_00).
  Rules, thresholds and forms change through Gazette notifications that many practitioners learn
  about late, second-hand, from blogs and newsletters.
- **The secondary sources are wrong in a measurable way** (observed: four of the most-read
  compliance sites still showed the 2022 figure).
- **Templates drift** (observed, `CLAUDE.md`). ComplyRelax, a template tool free to ICSI members
  until 31 March 2029, says in its own instruction PDFs that customising a template stops its
  legal updates. So every real firm's documents are a private copy, slowly drifting from the law.
- **Legal AI answers without showing its basis** (observed: the 17–33% hallucination study,
  measured on US tools). No Indian-specific measurement was found.
- **Nobody checks a document's claims against the register** (observed for Harvey and Spellbook's
  public material, `docs/research/CONNECTORS_AND_THE_WHITE_SPACE_2026_09_25.md`). Indian KYB
  firms (Karza/Perfios, Probe42 and others) check registers, but have no drafting or legal-review
  surface. Verification exists and drafting exists; nothing joins them.

### 5.2 The shift Themis pushes: from "search" to "verify and watch"

| Today | With Themis inside Placedon [I] |
|---|---|
| Lawyer searches, reads, and hopes the source is current | The lawyer gets the provision **and proof it was current on the date that matters** |
| Checking a document's legal currency is manual, done by a senior person | A first-pass audit flags stale figures, wrong document types and missing information, **each with its source**, and the senior person reviews the flags rather than the whole document |
| Law changes are noticed when someone happens to read about them | Changes are **pushed**, with the chain of reasons showing which client and matter they touch |
| When a source turns out wrong, nobody knows which advice relied on it | **Recall:** list every answer that relied on it |
| AI answers are fluent and unverifiable | Answers are **traceable sentence by sentence**, and the tool abstains when it can't trace |

### 5.3 Who gains, and how

| Who | Gain [I, to be tested with real users] |
|---|---|
| **In-house counsel** (first customer, founder decision) | Review routine documents without sending everything to outside counsel, and show the board the basis for each answer |
| **Law-firm associates** | Faster first-pass work with citations a partner will accept, because each carries instrument and date |
| **Partners and General Counsel** (the buyers) | Lower risk of advice built on superseded law, and an audit trail if advice is challenged |
| **Company Secretaries** (secondary) | Filings and minutes checked against current thresholds |
| **Clients** | Fewer compliance defaults caused by stale figures |

### 5.4 Why this is hard for others to copy [I]

1. **The discipline lives in every line.** A competitor can add a "sources" button in a week.
   Making every fact carry date, instrument and evidence state, with refusals and UNKNOWN handled
   correctly, is a rebuild, not a feature.
2. **Big legal-AI vendors optimise for fluent answers across everything.** Placedon optimises for
   being provably right, or saying it can't be, in one domain. Those goals pull in opposite
   directions, and the incumbent's customers are used to the first.
3. **Distribution without a new seat.** Through MCP, Placedon can work *inside* the AI tools
   lawyers already pay for (Claude, Copilot, and Harvey through its "bring your own MCP
   server" feature). Harvey's own documentation leaves register-checking to others. We don't
   need to win a seat; we plug into theirs.
4. **Honesty compounds.** A tool that says "I don't know" when it doesn't earns trust that
   survives its first mistake. A tool that always answers does not.

### 5.5 What must be true for this to matter (the honest risks)

- **Lawyers must value the refusals.** If practitioners call abstentions useless ("just answer"),
  the thesis fails (PLAN_00 falsifier 1). **Only real conversations test this. H-001, one
  practising Company Secretary or lawyer reviewing real output, outranks every feature.**
- **Stale figures must actually cost someone.** If nobody is ever caught out by a superseded
  threshold, the currency engine is a curiosity (PLAN_00 falsifier 2).
- **An incumbent** (SCC Online, Manupatra) could ship dated-instrument tracking as one feature
  (PLAN_00 falsifier 3).
- **Legal:** whether an AI product's analysis counts as "commentary" under Copyright Act
  s.52(1)(q)(ii), on which the corpus rests, is a question for counsel.
- **The name:** see Part 0. "Themis" is likely contested as a trademark in legal software.
- **Scope:** only the Companies Act is held today. Listed companies also need SEBI law, which is
  not held. The product is narrow until more law is acquired, and it says so.

### 5.6 What we deliberately do not promise

- Predicting who wins a case: not reliable, not calibratable with available Indian data, and off
  our market (PLAN_19 part 04 §7).
- Live stock-market or shipment intelligence: the sources forbid machine reuse or have no
  provable origin (PLAN_19 part 02).
- An accuracy percentage: not until lawyers have checked a benchmark.

---

## Part 6: What you, the founder, should do next (in order)

1. **Talk to practising lawyers.** Show one Company Secretary and one in-house counsel a real
   answer, an abstention and an alert. Ask:
   - "Would you rely on this?"
   - "Is the refusal useful or annoying?"
   - "What would you pay to never be caught by a stale figure?"

   Record the answers (H-001; `docs/H001_OUTREACH.md` has the script).
2. **Get 30–60 questions checked by a lawyer** for the gold set. That produces the first real
   accuracy number, and nothing else can.
3. **Turn on CI** by adding the workflow file through the GitHub website. Then every change is
   tested on a clean machine, not only on the laptop.
4. **Two questions for counsel:** the s.52(1)(q) commentary question, and whether the Supreme
   Court dataset's CC-BY licence covers the judgments (this gates the case-law checker).
5. **Let the build loop continue** with PLAN_19 G0, fixing the scope gate and abbreviation
   search, before any new feature.

---

## Glossary

| Term | Meaning |
|---|---|
| **Themis** | The engine inside Placedon. Greek for "that which is laid down"; project name since 16 Sep 2026 |
| **Placedon** | The product and brand customers buy |
| **Admission gate** | The Themis check that decides whether a source is established enough to be served |
| **V0 slice** | The first end-to-end run of Themis on live Gazette data (`scripts/themis_slice.py`) |
| **Abstain** | Decline to answer, and say what is missing |
| **Instrument** | A notification, rule or amending Act that changes the law, e.g. G.S.R. 880(E) |
| **Evidence state** | How strongly a fact is supported: VERIFIED, CORROBORATED, INFERRED, UNRESOLVED or RETRACTED |
| **Currency** | Whether a legal figure or text is still the one in force |
| **As of** | The date a question is asked about |
| **Scope gate** | The check that refuses questions about law we do not hold |
| **Gold set** | Test questions with known right answers, used to measure accuracy |
| **MCP** | Model Context Protocol, the standard that lets AI assistants call outside tools |
| **Ring / floor** | A layer of the system; each may depend only on layers below it |
| **Deterministic** | Same input, same output, every time; no randomness and no model guess |
| **Recall (of advice)** | Listing every answer that relied on a source later found wrong |
