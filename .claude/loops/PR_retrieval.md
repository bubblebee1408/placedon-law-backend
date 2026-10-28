# PR draft (not opened): document excerpts — BM25 ranking, relative cut-off, follow-up history

## Why
Document excerpts were ranked by shared-word count / sqrt(length) with no term weighting and no
cut-off: "What notice period does the termination clause require?" returned 8 of 8 pages of a
synthetic contract because filler pages share "period". Follow-ups without content words
("And how long is that?") returned NO_MATCH.

## What (phase 1 only: deterministic, model-free, stdlib)
- `gateway/english_stem.py` (new): Snowball English (Porter2). 9,001/9,002 CUAD-dev words equal
  NLTK's SnowballStemmer; "realization" differs (realiz vs realize), unresolved.
- `gateway/document_evidence.py`: BM25 (K1 1.2, B 0.4) over this call's passages, two streaming
  passes; keep passages scoring ≥ 0.6 × the top score; Porter2 on ASCII words, NFC on tokens only
  (offsets untouched); `previous_query` expansion at weight 0.5 on a follow-up cue, an empty
  question, no match, or common-only matches; `history_query` + a limitation line when used.
- `gateway/verbs.py`: passes the previous USER message (never an assistant reply), one turn back.
- Frontend (separate repo, fe-simfix): shows "Read together with your previous question: …".

## Evidence (CUAD, CC BY 4.0; tuned on contracts 0–50, verdict on 51–101 run once)
| held-out 51–101, long query | before | after |
|---|---|---|
| Recall@1 | 0.220 | 0.383 |
| MRR | 0.334 | 0.459 |
| Recall@8 | 0.576 | 0.598 |
| precision of shown | 0.108 | 0.268 |
| passages shown | 6.38 | 3.88 |
| empty (short query) | 0.079 | 0.038 |

## Tests
- tests/test_document_evidence.py: 36 OK (15 new: filler pages, stemming, general≠generate,
  two strong clauses kept, common-only not NO_MATCH, NO_MATCH kept honest, NFC nukta offsets,
  no score key, follow-up expansion, topic change ignores history, bounded memory, determinism,
  verbs wiring uses the previous user message).
- gateway/english_stem.py --test: 130/130. Gate: HARNESS_RESULT suites=342 failed=0 GREEN.
- Browser (isolated harness, synthetic 8-page contract): fee → p3; termination → p6 only;
  "And how long is that?" → p6 with visible disclosure.

## Known limitations
- Wording gaps remain ("brought to an end" vs "terminate"): synthetic semantic-gap-2 still returns
  a filler page containing "end". Phase 2 (dense leg + RRF) is the planned answer, under the
  residency rules.
- Follow-up history is one turn back (followup-chain-3 fails by design).
- Parties questions got worse (dev MRR 0.10 → 0.05): the cut removes lucky low-ranked hits.
  Phase 1b (preamble rule) is designed but not built.
- 2 contracts over MAX_DOCUMENT_CHARS (200,000) are never searched (6–8% of questions).
- ALPHA 0.6 was a judged tie-break inside the 0.01 MRR noise band, not the literal sweep rule.
- CUAD is US contracts; query templates are ours; overlap-based relevance is generous.
- Dev wall time ~15.7 s vs ~7 s before (two passes + stemming).
