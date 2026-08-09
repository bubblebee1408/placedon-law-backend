# placedon-law-backend

PoSH Act compliance checking for Indian SMEs. FastAPI, deterministic Python, no model in the
decision path.

Part of a three-repo split:

| Repo | Holds |
|---|---|
| **placedon-law-backend** | this one — the API, the corpus, the verification suite |
| placedon-law-frontend | the Next.js app |
| placedon-law-research | plans, decisions, research notes |

## The one design decision everything else follows from

**The model never decides whether a law applies.** `applicability.py` decides, deterministically,
from the company's answers. The model — when one is used at all — only explains a decision that
has already been made, and `checker/verifier.py` rejects any citation or number that does not
appear in the source text.

That inversion makes model choice a **cost lever, not a correctness lever**. A cheaper model
produces a worse explanation, never a wrong obligation.

It is also the reason for the corpus. *"Every employer employing 10 or more employees shall
constitute an Internal Committee"* is a sentence that appears in a great deal of Indian HR
writing. It is **not in the PoSH Act**. It reached five generated documents and one of our own
code comments before the verbatim corpus caught it.

## State

```
corpus/provisions/posh_act_2013.json   30 sections, byte-verified against India Code
corpus/rules/                          14 PoSH Rules provisions, cross-verified 9/9
corpus/reference/                      31 District Officers
verified_by                            null on every single one
inference spend, all time              Rs 0.00
```

`verified_by` means *a lawyer has checked our reading of this section*. Nothing this repository
can do sets it. `scripts/check_transcription.py` proves the text is a faithful transcription and
deliberately does not touch that field — transcription and interpretation are different claims,
and conflating them is the failure this project has refused eight times.

Because it is null everywhere, **the Q&A path abstains on every question it is asked.** That is
the designed state, not an outage.

## Run it

```bash
pip install -r requirements.txt
uvicorn checker.app:app --reload        # http://localhost:8000
python3 scripts/verify.py               # 39 checks, GO/NO-GO
python3 scripts/verify.py --fast        # skip the per-module suites (~2s)
```

## The verification ratchet

`scripts/verify.py` is the checklist — not a markdown file beside the code, which drifts from
what runs within about two weeks and becomes a record of intentions.

Every check carries `because=`: the specific incident that bought it. Some of what is in there:

- A citation enforcer that failed open, because `"s.27".startswith("s.2")` is `True`, so every
  fabricated citation passed.
- Sub-sections added to the corpus that **nothing read** — the lawyer pack still printed the
  full 5,570-character s.2. Dead data reports a win it did not deliver.
- Two checks of my own that passed while asserting nothing, found by a review agent.
- A stylesheet whose seven-state epistemic ramp was hue-coded green/amber/red, collapsing an
  ordinal ladder into three categories.

Do not delete a check because it has never fired. A check that never fires is a bug that never
came back.

The frontend half of the suite lives in `placedon-law-frontend`, because a check belongs in the
repo containing its subject. A check that cannot see its subject either crashes or — worse —
skips quietly. The `--fast` run here asserts on its own registry size for that reason.

## Layout

```
checker/          the API, the epistemic lattice, document generators, the citation enforcer
corpus/           statutory text. Read by 21 files; it is a runtime dependency, not reference
scripts/          ingestion, transcription checks, the review pack, verify.py
applicability.py  the deterministic decision. Not a model call
jurisdiction.py   district > state > national resolution, with a refusable state fallback
backend/          budget guard
api/              Vercel entry point
```

## What this deliberately does not do

No risk scores, no confidence percentages, no "verified against India Code" badge. Each has been
proposed and refused — a displayed confidence number needs a labelled validation set, and there
is none. Abstention is a designed state with its own rendering, not an error path.
