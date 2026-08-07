# Errata — MASTER_SPEC.md

Ten defects found on ingest. Three would break the build or re-introduce a bug we had already
fixed. Each entry states the evidence, because "the spec says X" is going to come up again and
this file has to win that argument on facts.

**Where the spec and this file disagree, this file wins.**

---

## E-1 — CRITICAL: the spec fabricates a quotation from s.4 of the PoSH Act

**Spec, §2.2 (p5) and by implication throughout:**
```python
"rule": "Section 4(1), PoSH Act, 2013",
"text": "Every employer employing 10 or more employees shall constitute an IC",
```

**That sentence is not in the Act.** From our ingested corpus (`corpus/provisions/posh_act_2013.json`,
source sha256 `e59776d9…`), s.4(1) reads, verbatim:

> *"Every employer of a workplace shall, by an order in writing, constitute a Committee to be
> known as the 'Internal Complaints Committee'"*

The word "ten" does not appear in s.4 at all. The ten-worker figure is an **inference from s.6(1)**,
which provides a Local Committee for establishments that have not constituted an IC *"due to
having less than ten workers"*.

We shipped this exact error, caught it on 2026-08-07 by grepping the ingested text, and corrected
it. **Copying the spec's snippet would put it straight back into a live compliance product.**
See `RESEARCH_LOG.md` 2026-08-07 and `checker/rules.py`, which now cites s.6(1) and labels the
threshold an inference.

---

## E-2 — CRITICAL: the specified model was retired nine months ago

**Spec, §3.3 (p8) and `ARCHITECTURE.md` template (p19):** `claude-3-5-sonnet-20241022`

That model **retired 28 October 2025** and returns HTTP 404. Any code built on it fails on the
first call.

Current models: `claude-opus-5` ($5/$25 per MTok), `claude-sonnet-5` ($3/$15, introductory $2/$10
through 2026-08-31), `claude-haiku-4-5` ($1/$5).

Our routing (`DECISIONS.md` D-3) is **Haiku 4.5 for serving**, Opus 5 via the Batch API for the
100-question proof artifact. That is not a downgrade — it is safe *because* applicability is
decided in deterministic Python and every number is verified verbatim afterward, so model choice
is a cost lever rather than a correctness lever.

---

## E-3 — CRITICAL: the daily budget overspends the monthly cap

**Spec, §4.1 (p8):** "Daily Budget: Rs 150-250 (50 LLM calls max)"
**Spec, §4.3 (p9):** `MONTHLY_BUDGET_RUPEES = 3500`

```
₹150/day × 30 = ₹4,500/month   →  29% over the cap
₹250/day × 30 = ₹7,500/month   → 114% over the cap
```

Both daily figures breach the monthly limit. `BudgetTracker.can_make_call()` would pass every
daily check and then hit the monthly wall somewhere around **day 14–23**, with no warning, mid-month.

**Correct figures.** ₹3,500/month ÷ 30 = **₹116/day**. At Haiku 4.5 (~₹0.97 per answered question,
measured at ~6,700 input / ~700 output tokens) that is **~120 answers/day, ~3,600/month** — not the
50/day the spec allows. The spec's cap is simultaneously too generous in rupees and far too strict
in calls, because it prices a mid-tier model at Opus rates.

---

## E-4 — The per-call cost estimate is 3–5× too high

**Spec:** ₹3–5 per call. **Measured:** ~₹0.97 on Haiku 4.5, ~₹4.86 on Opus 5.

The spec's figure is roughly Opus pricing applied to a model it names as Sonnet. Every derived
number in §4 — daily limits, call counts, tier maths — inherits the error.

---

## E-5 — The response cache is a no-op, and wouldn't work in production anyway

**Spec, §4.2 Strategy 2 (p9):**
```python
@lru_cache(maxsize=1000)
def cached_answer(question_hash: str, company_state: str) -> str:
    pass
```

Two problems. The body is `pass`, so it returns `None` — it is a stub presented as a strategy.
And `lru_cache` is **per-process**: on Vercel or Render each invocation may be a fresh process, so
it caches nothing across requests.

**The real lever** is Anthropic's server-side prompt caching — cache reads at ~0.1× input cost,
minimum cacheable prefix 4,096 tokens on Haiku 4.5 (512 on Opus 5). Our system prompt and
generation rules are stable and belong behind a `cache_control` breakpoint. Verify with
`usage.cache_read_input_tokens`; if it's zero across repeated calls, something in the prefix is
varying.

---

## E-6 — Vector search re-embeds the entire corpus on every query

**Spec, §3.2 (p7):**
```python
for provision in provisions:
    prov_embedding = embed_text(provision.text[:500])
```

The provision embeddings are recomputed inside the query loop — N embeddings per question, every
question. They should be precomputed once at ingest and stored. Also `np.dot` on un-normalised
vectors is a dot product, not cosine similarity, so ranking will be biased toward longer text.

**Bigger point:** we do not need vector search yet. Thirty PoSH sections retrieve fine by topic and
citation in SQL. This is V1.5 (`architect` standing position).

---

## E-7 — The hallucination check is weaker than the one we already have

**Spec, §12 (p19):** flag answers containing "I believe", "I think", "probably", "might be".

That catches hedging, not fabrication. A confidently-worded wrong deadline sails through.

**Ours is mechanical:** extract every numeral from the generated answer and assert set-membership
in the retrieved verbatim source text. Hallucinated-number rate must be **exactly 0**
(`qa-reviewer` gate). Keep the spec's phrase list as an additional signal, not as the gate.

---

## E-8 — `state_override TEXT` cannot express a district-level obligation

**Spec, §5.1 (p10):** the `provisions` table has `state_override TEXT`.

The PoSH annual-return deadline is set by the **District Officer** — Gurugram notified 28 February
where most districts use 31 January. A state-level column cannot hold that, and a lookup that
falls back to the state record will confidently answer 31 January to a Bengaluru company.

Already solved in `jurisdiction.py`: district > state > national, with a `district_scoped` flag
that makes the fallback **refusable** rather than automatic.

---

## E-9 — `gazette_url TEXT NOT NULL` would block ingestion today

**Spec, §5.1 (p10).** We ingested the PoSH Act from India Code, not from an e-Gazette URL. There is
no gazette URL for these provisions, so a NOT NULL constraint rejects the entire corpus.

Make it nullable, and store `source_url` + `source_sha256` (which we already record) as the
provenance of record.

---

## E-10 — The frontend spec asks us to rebuild something that already works

**Spec, §2.1 (p2–4):** Next.js 14, TypeScript strict, shadcn/ui, a component-per-file convention.

The checker is **live at https://placedon-hr.vercel.app** as server-rendered HTML with inline CSS
and no build step. It loads in ~0.6s, has no dependencies beyond FastAPI, and shipped in one
session.

This is a genuine decision, not an obvious one — Next.js buys SEO for the 420-page state × obligation
matrix later. But adopting it *now* means rebuilding a working thing before anyone has used it.
Route it through `architect` when SEO actually becomes the constraint; don't do it because a
document says to.

---

## What the spec gets right, and we should adopt

- **`BudgetTracker` as runtime enforcement.** We have `cost-governor` as a design-time agent but
  nothing stopping a call at runtime. This is the spec's best idea — implemented, with corrected
  numbers, in `backend/budget.py`.
- **The engine/services split.** Engine layer makes no external calls; all LLM traffic goes through
  one file. That is the right shape and it matches our deterministic-first rule.
- **The API fallback chain** (§6.4). Sensible, and cheap to add.
- **Structured logging convention** (§9.3). Adopt verbatim.
- **`.env` discipline and rate limiting** (§8). Adopt verbatim.
