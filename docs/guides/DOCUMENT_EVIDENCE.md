# Selected-document evidence in conversations

`conversation.send` can search the extracted text of selected vault documents when the
request is classified as `RESEARCH_QUESTION`. Explicit review and review-table requests
retain their existing workflow. A plain summary request receives a limited opening-text
preview, with an explicit warning that it is not a complete summary.

## Contract

Send `file_ids`, the matching conversation `matter_id` (or leave both unfiled), and
`sources: ["vault"]`. Omitted source selection allows selected-file reading. An explicit
selection excluding `vault` performs no file-byte reads and returns `NOT_SEARCHED`.

The frozen legal envelope stays unchanged. `metadata.document_evidence` and the immediate
response sibling `document_evidence` carry `document_evidence.v1`. The result identifies:

- Each selected document and whether it was searched, unavailable, over the limit, or not searched.
- Exact quotes, extracted-text SHA-256, document identity and half-open Unicode code-point offsets.
- `EXCERPTS_FOUND`, `NO_MATCH`, `UNAVAILABLE`, or `NOT_SEARCHED`.
- The limits of local keyword matching and of the saved evidence snapshot.

The envelope uses `PARTIAL` with no statutory citations or answered legal bodies. This is
not a legal conclusion, full-document summary, semantic entailment check, or proof that a
term is absent. It makes no model or public-web call. It does not claim original PDF pages,
OCR quality, handwriting support or verification against an official record.

## Bounds and persistence

The path accepts at most 20 files, 200,000 Unicode code points per file and 500,000 per
turn; the pre-read byte limits are 800,000 and 2,000,000 respectively. It retains at most
eight candidate excerpts of 1,200 code points each. Ranking is a deterministic lexical
overlap baseline, not a confidence score or a new trained retrieval model.

The saved metadata survives request replay and conversation reopening without recomputing
the result. It is a historical snapshot: deleting a vault file does **not** erase quotes
already stored in conversations. Purging those snapshots requires a separate retention
workflow. The UI must not call them freshly reverified after reopening.

Tenant isolation and matching document/conversation matter scope are enforced by existing
store/resolver checks. Individual lawyer-to-matter membership is **not implemented**.
Use synthetic data for shared-passcode/team evaluation until authorization covers every
document, conversation, run and artifact route. Exact quote integrity does not close that gap.

## Verification

```bash
PYTHONPATH=. python3 -m unittest tests.test_document_evidence -v
PYTHONPATH=. python3 scripts/conversation_regression_checks.py --test
bash scripts/run_tests.sh
```

`tests/test_document_evidence_postgres.py` is opt-in, using the explicit throwaway database
URLs documented in `tests/test_conversation_postgres.py`. It verifies new-connection
persistence, replay, exact Unicode spans and cross-tenant denial with a non-superuser,
non-BYPASSRLS application role. It does not assert per-actor matter authorization.
