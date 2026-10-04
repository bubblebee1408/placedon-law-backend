# Handoff — acquire the Meetings of Board Rules 2014

**Automation stopped safely. This needs a human with a browser. It is a 5-minute task.**

## Why automation cannot finish this

| Path | Result | Response |
|---|---|---|
| `upload.indiacode.nic.in` (direct file) | ECONNREFUSED — host down | Retry later; may recover |
| `indiacode.nic.in` dynamic search/browse | **HTTP 403 — blocked** | Will not be retried automatically |
| `indiacode.nic.in` `/bitstream/*.pdf` | 200 — works | But the Rules' address is unknown |
| `mca.gov.in` | 403 | — |
| `egazette.gov.in` | 200 — reachable | Stateful search form |

India Code serves the file from a static address, but the address is *discovered* through the
dynamic pages, and those return 403 to us. So: the document is almost certainly still published;
we cannot look up where. A browser session is not subject to the same block.

## What to get

**The principal Rules** — "The Companies (Meetings of Board and its Powers) Rules, 2014".

**Not** an amendment. Titles are nearly identical and the difference is one word:

- ✅ `Companies (Meetings of Board and its Powers) Rules, 2014`
- ❌ `Companies (Meetings of Board and its Powers) **Amendment** Rules, 2014`
- ❌ `... **Second Amendment** Rules, 2014`

An amendment says "further to amend" and consists of substitutions and insertions. The principal
Rules are self-contained and begin with "short title and commencement".

## Where

1. **India Code** — search rules for the Companies Act 2013, filter to the 2014 Board Rules.
2. **eGazette** (`egazette.gov.in`) — official archive, search by notification number/date.

**Unverified lead, to check rather than trust:** third-party sources say the principal Rules were
notified by **G.S.R. 240(E) dated 31-03-2014**. We have not read that off an official document.
Use it to find the file, then read the real number and date off the PDF itself. Do not assume it.

**Do not** download from `ca2013.com`, `vlex.in`, `taxguru.in`, `webtel.in`, or `thc.nic.in`. They
have the text; their fidelity to the gazetted version is unestablished, and at the point of use an
unofficial copy is indistinguishable from the real one.

## Then run

```bash
python3 scripts/acquire_rules.py ~/Downloads/<whatever-it-saved-as>.pdf
```

It will read the document's own title and notification, refuse it if it is an amendment or if
identity cannot be confirmed, hash and store it, and print the provenance record to paste into
`checker/provenance.py`. Then:

```bash
./scripts/run_tests.sh
```

## What stays false until a human reads it

`human_reviewed=False` until someone has actually read the document. `can_promote()` will refuse
`VERIFIED` until then — the script handles custody, not review.
