# Acquisition policy

How this repository is allowed to go and get a source, what it must record while doing so, and when
it must stop.

Implemented in `checker/acquisition_log.py` (attempt history) and `checker/provenance.py`
(accessibility states, retry rule). Companion to `docs/SOURCE_PROVENANCE_POLICY.md`, which governs
the *other* axis — see immediately below, because that distinction is the whole reason this file
exists.

## Two axes. They are not the same axis.

| Axis | Question it answers | Where it lives | Values |
|---|---|---|---|
| **Source attempt** | What happened when we asked a host for a document? | `provenance.ACCESSIBILITY_STATES` | `ACCESSIBLE` · `BLOCKED` · `UNREACHABLE` · `NOT_FOUND` |
| **Artifact classification** | How strongly is a claim we want to make actually backed? | `provenance.STATES` | `UNRESOLVED` · `INFERRED` · `UNFETCHED_CORROBORATION` · `CORROBORATED` · `VERIFIED` · `RETRACTED` |

An attempt state describes a *network event*. A classification state describes *evidence we hold*.
Neither one implies the other:

- `ACCESSIBLE` does not mean verified. `egazette.gov.in` answered 200 and we still have nothing:
  reachable is not the same as retrievable, and retrieved is not the same as reviewed.
- `BLOCKED` does not mean the claim is false, or the document absent. It means we were refused.
- `VERIFIED` says nothing about whether the URL still works. It is verified against a *hashed local
  artifact*, and it stays verified if the publisher takes the page down tomorrow.

### This repo already conflated them once

On 2026-08-21 a WAF `403` from India Code's dynamic endpoints was written up as an outage — the
request path in use timed out rather than surfacing the status, and a timeout reads as "the host is
having a bad day". The 403 was therefore recorded under the same state as a downed host, and the
downed-host state is retryable. The result was a scheduled automated retry pointed at a WAF: a
source that had explicitly refused us, queued to be asked again. Fixed in `fe5136c` by splitting the
two failures into separate `SourceRecord`s with opposite retry treatment.

The lesson generalises past that one bug. **Never infer an attempt state from a symptom that could
have more than one cause.** Record what the server actually said, and if nothing was heard, record
that instead. `append()` enforces the minimum: a state that means "the server answered" must carry
an HTTP status; a state that means "nothing answered" must carry the transport error.

## Attempt states and the retry policy

| State | Cause | Automated retry | Why |
|---|---|---|---|
| `ACCESSIBLE` | 2xx | n/a | Nothing to retry. Whether it was *useful* is a separate question. |
| `UNREACHABLE` | connection refused, timeout, DNS failure | **Permitted** | The host never answered. Hosts come back; the address may be perfectly good. This is the only retryable class. |
| `BLOCKED` | 403 / WAF / robots refusal | **Never** | The server answered, and the answer was no. Re-probing a source that has refused us is abusive regardless of intent, and it is exactly what the WAF exists to stop. Escalate to a human or a permitted alternative source; do not escalate to more requests. |
| `NOT_FOUND` | 404 at an address we believed exact | **Never** | The server answered, and the answer was "not here". A repeat of the same request cannot make a wrong address right. The fix is re-discovery or human retrieval. |

Encoded as `provenance.RETRYABLE` and `provenance.is_retryable()`; `RETRYABLE` is `(UNREACHABLE,)`
and the tests pin it there.

### What a 404 does and does not mean

A `404` means **the address is wrong**. It does not mean the instrument does not exist. India Code
reshuffles file paths between releases, so a URL that was exact last year 404s while the document
sits unchanged at a new path.

This matters more here than in an ordinary crawler, because the downstream consumer is a legal
audit. If "we could not find rule X" ever hardens into "rule X does not apply", the system produces
a confident wrong legal answer — the worst failure mode in this codebase. So:

> **Discovery failure never disproves existence.** `summary()` reports
> `instrument_existence: EXISTENCE_UNDETERMINED` for *any* history of failed attempts, and there is
> no code path that turns failed attempts into a finding of absence. Nothing downstream may treat
> absence-from-corpus as absence-from-law.

Disproving existence would require reading a source that *would* list the instrument if it existed
— a gazette index, an official rule list — and reading it successfully. That is a positive finding
from an accessible source, not the absence of one.

## The attempt log

Every acquisition attempt is appended to a hash-chained log, successes and failures alike. An
unrecorded failure costs twice: the next run repeats a request whose answer is already known, and a
gap in the history later reads as "nobody tried".

- **Append-only structurally.** Records are frozen dataclasses in a tuple; `append()` returns a new
  tuple and leaves the old one alone.
- **Append-only verifiably.** Each record's digest commits to its own payload *and* to the previous
  record's digest, so altering any past field breaks every digest after it. `verify()` names the
  record that changed.
- **Tail truncation** leaves a chain that is still internally valid, so it is caught only by the
  declared length and head stored alongside the records. `load()` always checks against them and
  raises rather than returning a log whose chain does not check out.
- **No clock reads.** Timestamps are passed in. A function that reads the clock cannot be run twice
  on the same input, and the claim being tested is precisely that identical inputs produce identical
  digests. A test asserts the module contains no clock call.
- **Timestamps may be date-only.** Recording a minute that was never observed is inventing
  precision. Ordering is carried by `seq`.
- **`artifact_sha256` is set only for bytes of the target instrument.** A control probe, a redirect,
  or an error page leaves it `None`. Otherwise `ACQUIRED` stops meaning anything — and `ACQUIRED` is
  refused at construction unless some attempt can show the bytes.

The committed report (`reports/acquisition_board_rules_2014.json`) is checked against the recorded
history on every test run, so hand-editing the JSON fails the suite. Regenerate with
`python3 checker/acquisition_log.py --emit`.

### Log a control probe

When several endpoints on one host fail, probe something on that host that is known to work. The
Board Rules history includes a `200` on a static `/bitstream/*.pdf` path for exactly this reason: it
is what distinguishes "India Code is down" from "India Code is refusing us", and those two readings
lead to opposite retry decisions. Without the control, the entire host looks dead and gets a retry
schedule it must not have.

## Terminal states

| State | Meaning | Successful stop? |
|---|---|---|
| `IN_PROGRESS` | Routes remain untried. | No — unfinished |
| `ACQUIRED` | Bytes obtained; some attempt carries the artifact hash. | Yes |
| `HUMAN_RETRIEVAL_REQUIRED` | No permitted automated route remains. | **Yes** |

### HUMAN_RETRIEVAL_REQUIRED is a success

It is not a failure, an error, or a task to be retried until it passes. It is the automation
correctly establishing that every permitted route is exhausted and stopping, instead of grinding
against a WAF or inventing a workaround.

The failure modes it exists to prevent are all worse than stopping:

- bypassing the block (forbidden outright by `CLAUDE.md`);
- retry loops against a source that has refused us;
- substituting an unofficial copy — `taxguru.in`, `vlex.in`, and similar have the text, but their
  fidelity to the gazetted version is unestablished, and at the point of use an unofficial copy is
  indistinguishable from the real one;
- filling the gap with model recall, which is the same defect with no audit trail at all.

The correct behaviour on reaching it: write the handoff, name what is needed and where to look, and
stop. `docs/ACQUISITION_HANDOFF_board_rules_2014.md` is the worked example — a five-minute browser
task, because a browser session is not subject to the block that stopped the automation.

## Leads are not facts

An acquisition often turns up a third-party claim about the instrument — a notification number, a
date. Record it as a **lead to be checked against the acquired document**, never as a value.
`provenance.PRINCIPAL_RULES_LEAD` is the pattern: the claimed values sit in a dict labelled
`UNFETCHED_CORROBORATION` with an explicit instruction not to backfill them into any record.

Once the document is in hand, read the notification number and date **off the document** and record
those. If the lead disagrees with the document, the document wins and the lead is retracted.

## Standing constraints

From `CLAUDE.md`, restated here because acquisition is where they bite:

- Do not bypass the MCA/India Code WAF, robots restrictions, access controls, or source terms — to
  acquire a document or to raise an evidence state.
- Permitted sources only: official legislation, Gazette, public ICSI specimens, public
  listed-company disclosures, Indian Kanoon under its attribution terms.
- Never repair a defective government source. Flag it, preserve it verbatim.
- If evidence is incomplete, write `OPEN` or `UNVERIFIED`. Do not guess.
