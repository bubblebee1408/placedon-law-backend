# The loop — what to build next, one iteration at a time

Companion to `docs/TECHNICAL_PLAN.md` (why) and `docs/BUILD_CONTEXT.md` (constraints). This is the
queue. Each item is **one iteration**: one file, one check written first, one commit.

Read `docs/BUILD_CONTEXT.md` before starting any of them.

---

## The cycle

```
1. PICK     the lowest-numbered unblocked item. One file.
2. CHECK    write the verify.py check or module test FIRST. Run it. It must FAIL.
            If it passes before the code exists, it is asserting nothing — fix it now.
3. BUILD    the smallest thing that makes it pass.
4. VERIFY   python3 scripts/verify.py            must print GO
5. MUTATE   break the thing the check exists to catch. It must catch it.
            A check that survives its own mutation is decoration.
6. PROVE    corpus touched?  python3 scripts/check_transcription.py   30/30
            frontend touched? npx tsc --noEmit, and load it in a browser
7. RATCHET  a bug escaped? add a check with because= naming the incident.
8. COMMIT   the message says why, not what.
```

**Step 5 is the one people skip.** Every check in `verify.py` was mutation-tested; three of them
passed on deliberately broken input the first time and had to be rewritten. Assume yours will too.

---

## Queue

### 1 — Reply intake for Bengaluru Urban · BLOCKED on a reply
`scripts/build_register.py --record` already exists and is tested. Nothing to build. When the
reply lands, paste the officer's words verbatim and commit the register as a data change.

If nothing arrives by **2026-09-11** (30 days), mark it `NO_REPLY`. That is a publishable finding
about the district, not a failure — and it is the first thing in this project that will be true
and unavailable anywhere else.

### 2 — The public register page
The register is currently only visible inside the product. Its commercial value is as a *citable
public artifact* — the thing competitors have to link to.

- `GET /api/register` → the whole register as JSON, no auth
- A page: district · status · notified date · the officer's words · date asked
- Rows with no reply shown **as prominently** as rows with one. The non-answers are the proof
  that we asked rather than guessed.
- Check: the page must render every district in the register, and must not render a date
  without its quote.

### 3 — Widen the dev CORS origin
Found while browser-testing the district picker: the app works from exactly
`http://localhost:3000` and fails **silently** from any other port or from `127.0.0.1`. The
picker just comes back empty. Cost me one debugging cycle; it will cost the next person more.

- Allow `http://localhost:*` and `http://127.0.0.1:*` in dev only, never in production
- Check: production origins must remain an explicit allow-list, not a pattern

### 4 — `NO_REPLY` is currently unreachable from the CLI
`build_register.py` can mark `ASKED` and `--record` a reply, but nothing sets `NO_REPLY`. The
status exists in the schema, `register.py` describes it, `verify.py` validates it — and no code
path produces it. Dead branch.

- `--mark-no-reply CODE --on DATE`, refusing if `asked_on` is unset or less than 30 days ago
- Check: a status the schema permits must be reachable by some code path

### 5 — Gazette text for the four MCA provisions
All four came from `ibclaw.in`, a legal-news reproduction. Every Board's Report we generate
already discloses that it quotes a quotation. With AGM season live, this is the disclosure most
worth removing.

- Replace with Gazette text, set `source_quality` accordingly
- Check: `check_transcription.py` must cover them the way it covers the Act

### 6 — Companies Act s.96
We do not hold it, so we cannot state when a Board's Report is due. Until we do, the Board's
Report route has no timing hook and the relaunch plan's "Why Now" stays open.

### 7 — `placedon.com` front door
Currently serving Vercel's `DEPLOYMENT_NOT_FOUND`. Attach `api.placedon.com` to the backend
project and point the frontend at it. That decouples the frontend from the Vercel project name
**permanently** — which is why renaming those projects off "hr" is not on this list. It becomes
moot here rather than being done carefully.

### 8 — Golden set and the three numbers
Not one accuracy figure. Three:

| Metric | Target |
|---|---|
| Fabrication rate — claims not in source | **0**, not "low" |
| Coverage — answered rather than abstained | rises as `verified_by` fills |
| Wrong abstention — abstained when the corpus did support an answer | falls |

The third is the real cost of this design and nothing currently measures it.

---

## Blocked, and not by code

| | Unblocks | Who |
|---|---|---|
| Six clauses to a lawyer | Every answer the product could give. `verified_by` is null on all 30, so the Q&A path abstains on everything. | You |
| Ten customer conversations | Whether any of this is a business. Zero logged. | You |
| District Officer replies | The register's whole value. 1 asked, 0 answered. | Them |

No item in the queue above changes any of these. That is the point of listing them separately.

---

## Not on this list, deliberately

**Vector search / ChromaDB / sentence-transformers.** 30 sections. Revisit at ~500, when the
labour codes land. `checker/retrieval.py` carries the arithmetic.

**LoRA or any fine-tuning.** No labelled data, no training set, and the corpus solves the problem
for nothing.

**Re-typing statutory text into Python.** See below. This is the one that would do real damage.

---

## Why hand-typed statute is barred

A proposed Step 1.5 would have seeded the vector store with hand-typed sections. Checked against
the byte-verified corpus, all three provisions it typed were corrupted:

| Provision | What the typed version dropped |
|---|---|
| s.4(2)(b) | *"preferably committed to the cause of women or who have had experience in social work or have legal knowledge"* — the entire qualification for who may sit on an IC |
| s.4(2)(c) | *"committed to the cause of women or a person familiar with the issues…"*, **and the proviso: "at least one-half of the total Members so nominated shall be women"** |
| s.19(b) | *"penal consequences"* became *"penalities"*; *"and the order constituting, the Internal Committee under sub-section (1) of section 4"* deleted — a separate display obligation |

The second row is the one that matters. **A hard compliance requirement — half the nominated
members must be women — vanishes.** `ic_order.py` checks committee composition against s.4(2);
against the typed text it would approve an all-male committee and print a compliance statement
saying so.

And the damage is silent. `verifier.py` checks every claim against the stored source text. If the
stored text is a paraphrase, the verifier certifies paraphrases with full confidence. The one
mechanism that has caught every fabrication in this project would become the mechanism that
launders them.

**Statutory text enters this repository through `scripts/ingest_*.py` from a primary source, or it
does not enter.** `check_transcription.py` re-fetches the India Code PDF and re-proves 30/30 on
demand. Nothing typed by a human or a model is admissible.
