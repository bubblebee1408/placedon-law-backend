# Handoff — acquire The Indian Contract Act, 1872

**Automation stopped safely (`HUMAN_RETRIEVAL_REQUIRED`). This needs a human with a browser. It is a ~10-minute task.**

Per `docs/policy/ACQUISITION_POLICY.md`, a **robots refusal is `BLOCKED`, and `BLOCKED` is never retried automatically** ("the server answered, and the answer was no … escalate to a human or a permitted alternative source; do not escalate to more requests"). Reaching this handoff is the success state, not a failure.

## Why automation cannot finish this

| Path | Result | Response |
|---|---|---|
| `indiacode.gov.in/robots.txt` | **HTTP 500 since 2026-09-28** | `checker.robots.fetch_rules` → `loaded=False`; `allowed(...)` → **False**. Fail-closed per RFC 9309. |
| any `indiacode.*` fetch through `checker.robots` | **refused (robots unusable)** | `BLOCKED` → **retry Never**. No `ingest_act.py` fetch, no enumerator — both only serve a blocked route. |
| `indiacode.gov.in` DSpace REST API, direct `curl` | 200 | **Went around `checker.robots`.** See the warning below — this is a bypass, not a permitted route. |

A browser session you drive yourself is not the automated fetch path the policy governs; a person opening the page and saving the PDF is exactly the permitted human-retrieval route.

## ⚠ The leads below came from an UNGATED read — treat them as leads, not facts

While diagnosing, section metadata was pulled from India Code's DSpace API with a direct `curl`, which **bypassed `checker.robots`** (the fail-closed gate) — the same mistake `ingest_act.py` records ("I measured the first with curl, which goes around the gate"). Therefore:

- **Nothing from those reads may enter the corpus or a fixture.** They are navigation leads only.
- **The act_id is a LEAD, to be checked against the downloaded file — not trusted.**
- These facts are read off the **human-retrieved PDF** at ingest, never carried over from the API read.

**Lead (check, do not trust):** act_id `AC_CEN_3_20_00035_187209_1523268996428` — the *Central* Act (not a State copy). Section s.10's Central text appeared to match the canonical "All agreements are contracts if they are made by the free consent …". Use these only to find and sanity-check the right file.

## What to get

**The principal, Central Act** — "The Indian Contract Act, 1872", **Act No. 9 of 1872**, enacted by Parliament (Legislative Department, Ministry of Law and Justice).

**Not** any of these look-alikes:
- ❌ a **State Government** reproduction — e.g. the **Chhattisgarh** copy (India Code handle `123456789/549122`, act_id `AC_CG_…`, `state_name: Chhattisgarh`). It out-ranks the Central Act in search and is the trap this handoff exists to avoid. The Central Act says `state_name: CENTRAL`, Ministry of Law and Justice.
- ❌ **The Indian Contract Act (1872) Amendment Act, 1886** (handle `123456789/489053`) or any later amendment. An amendment says "further to amend"; the principal Act is self-contained and opens with "short title … extent … commencement".

## Where

1. **India Code** (`indiacode.gov.in`) — in a browser, search "Indian Contract Act 1872" and open the **Central** result (Act 9 of 1872, Ministry of Law and Justice). Download the full Act PDF ("View PDF" / the bitstream).
2. **eGazette** (`egazette.gov.in`) — official archive fallback, if India Code's download misbehaves.

**Do not** download from `indiankanoon.org`, `taxguru.in`, `vlex.in`, `latestlaws.com`, `devgan.in`, or similar. They carry the text, but their fidelity to the gazetted version is unestablished, and at the point of use an unofficial copy is indistinguishable from the real one. India Code or eGazette only.

## Where to save it

```
corpus/raw/contract_act/indian_contract_act_1872.pdf
```

(Create `corpus/raw/contract_act/`. Keep the original filename too if you like, but the ingest will look for the Act PDF in this directory.)

## What to record (provenance — human retrieval, not a script)

Alongside the file, note down (you'll paste this to me, and it goes into the provenance record — **"retrieved by <person>", never "fetched by script"**):

- **URL** — the exact India Code page/bitstream you downloaded from.
- **Date** — when you downloaded it (e.g. 2026-10-12).
- **Who** — your name/handle.
- **What the PDF shows on its face** — title, **Act number (should read Act 9 of 1872)**, year, and whether an act_id/identifier is printed (if so, is it the `AC_CEN_3_20_…` lead above?).

## Then

Tell me the file is in `corpus/raw/contract_act/` with the four provenance facts. I take it from there (Step 2): ingest **from the file only** — assert the `%PDF` magic bytes, record the file's **sha256** and your human-retrieval provenance, split sections with `checker/pdf_pages`, keep footnotes verbatim, mark repealed/omitted chapters as such (never empty), and read the **Act number and year off the document itself**. Then I check section count/numbering against the Act's own arrangement-of-sections table, byte-compare a sample of sections page-by-page, hash-stamp every section, and report (not repair) any source defects.

## What stays true until you review

- This is **PR 1**: handoff + file-ingest + `corpus/contract_act/` only. **`checker/scope.py` is untouched; `CONTRACT1872` stays `DECLARED`.**
- A single PDF source has **no cross-render or corroboration**, so even after review the most it can become is **`CURRENT_ONLY`** (text held, no amendment history) — **never `IN_CORPUS`** on one source. That, the lookup plumbing, the picker, retrieval, and one byte-matched answer are **PR 2**, after you review PR 1.
