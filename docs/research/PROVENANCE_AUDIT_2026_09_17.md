# Provenance audit of the registration records — 17 September 2026

Job P-2, following P-1 (A-001). Every claim below was gathered by an agent and is labelled as such:
**no reviewer id was written, no human check field was touched, and nothing here is a human attestation.**
Evidence log with the raw commands, timings and hashes:
`~/.claude/jobs/c886fa96/tmp/p2/EVIDENCE.md`. Commits: `95cbb08`, `da334ce`, `c072b01`.

## What A-001 was, and why four more records were read

P-1 found that `scripts/register_gsr880e.py:is_attested()` checked two human checks and a status, and never
the source — while the record's own `attests_to[2]` said the download URL and date were recorded from the
Gazette or India Code, and both fields were null. The ₹10 crore / ₹100 crore figures were served on an
attestation the record did not support. The fix required a recorded or corroborated source on that host class,
plus the classifier's own `VERIFIED_INSTRUMENT` outcome.

The question for P-2 was whether the same shape existed in the other four records. It did, in three of them,
and in one of those the figures are served today.

The rule now lives once, in `checker/provenance.SourcePolicy`, and each script states its own host class,
publication floor and clause field. Shared with it: `source_conflict`, `split_source_flags`, `cli_exit`,
`EXIT_WORDING` and a pure `record_source` that returns the record to write rather than writing it.

---

## 1. `corpus/sources/gsr700e_registration.json` — G.S.R. 700(E) of 15-09-2022 (S-002)

**Question.** Does the guard check what the record claims, and can the held artifact be corroborated from an
official host? This is the record whose figures (₹4 crore / ₹40 crore, 15-09-2022 → 30-11-2025) are **served
today**, with a source URL printed beside them.

**Sources checked.**
- The record and `scripts/register_gsr700e.py` at `554e190`; `checker/prescribed_thresholds.py:_prescribed()`.
- The acquisition history: `corpus/sources/acquisition_gsr700e.json`, commits `61a6e5e` (registration) and
  `1f6bcf0` (attestation by NS, 04-09-2026).
- `https://egazette.gov.in/WriteReadData/2022/238857.pdf` — fetched 2026-09-17T09:26:48Z under
  `checker.robots` rules (robots.txt HTTP 404 = no rules published), TLS verified, chain completed with Let's
  Encrypt's own published intermediate. Address derived from the Gazette number `CG-DL-E-15092022-238857`
  printed on the held file.
- `https://indiacode.gov.in/robots.txt` — HTTP 502 on every probe (09:26Z, 15:20Z). Fails closed, so India
  Code was not fetched.
- `scripts/verify_document.py` on both files; `scripts/register_gsr700e.classify()` on both.

**Evidence found.**
- Guard defect, same class as A-001: `is_attested()` checked the two human checks and the status only — not
  the classifier's outcome, and not the source. The record has **no `downloaded_from` field at all** and
  `downloaded_at: null`, while the served figure carried `https://indiacode.gov.in/handle/123456789/508916`,
  a constant in `prescribed_thresholds`. That handle is where the instrument is *listed*; it is not a claim
  the record can support about where our file came from. The record's `attests_to` (two limbs) makes no source
  claim, so unlike 880(E) nothing in it was contradicted — what was unsupported was the address the engine
  printed.
- Corroboration: **text-identical**. eGazette served 733,961 bytes,
  sha256 `bb19f1b28fa3d1fad986a549d2f664ba052de684b7f1539a07f221441ea0fff3`, Last-Modified 15 Sep 2022.
  `classify()` on it returns `VERIFIED_INSTRUMENT` and an operative clause equal to the record's, character
  for character, including the extraction artefact `"[F ."`. The two text layers differ only by the held
  file's two `IndiaCode` stamp lines (same four non-blank lines otherwise).
- Bytes are **not** identical: held 746,519 vs Gazette 733,961, and the held file is not a prefix of it (the
  Gazette file carries two `startxref`/`%%EOF` — a signed incremental update — the held file one).
- Signature check, the finding worth more than the match:
  held `gsr700e_2022.pdf` → **VERIFICATION_FAILED** (signature INVALID, signed byte integrity INVALID,
  unsigned appended content FOUND); Gazette copy → INCOMPLETE_VERIFICATION with signature **VALID** over
  unaltered bytes, chain VALID (MANOJ KUMAR VERMA ← (n)Code Solutions ← CCA India), revocation NOT_REVOKED,
  validity-at-signing UNKNOWN. The held file is India Code's re-saved rendering of a signed Gazette file.
- Two smaller record defects: commit `61a6e5e` states the downloaded file was 733,961 bytes — that is the
  *Gazette* file's size, not the held file's; and `bitstream_id` names the TEXT bitstream from the 31-08
  handoff, not the ORIGINAL bitstream the same commit says was downloaded.

**Evidence quality.** Primary, machine-checked, reproducible: one official host, robots honoured, TLS verified
without weakening, hashes recorded, both files kept in-repo. It is **automated corroboration, not a human
check**, and it establishes the *clause*, not the *file's history*.

**Result.** Defect found and closed. The guard now requires classification, both human checks, the status and
a recorded-or-corroborated Gazette/India Code source. The record carries `corroborating_copy` (text-identical,
`matched_clause` = the held clause), `provenance_note` and `artifact_verification`; the Gazette copy is stored
as `corpus/sources/gsr700e_2022_egazette.pdf` with its SHA256SUMS line.
**Served state: before —** ₹4 crore / ₹40 crore served, `source_url` = the India Code handle, on an
attestation that said nothing about the source. **After —** the same figures served, carried by the
corroborating copy, `source_url` = `https://egazette.gov.in/WriteReadData/2022/238857.pdf`. Remove the copy
and the record is refused (asserted in the suite). Fixtures rebuilt byte-identical; no fixture carries a
700(E) figure.

**Unresolved issues.**
- Where the founder's own copy came from is still unrecorded, and only they can record it. The corroboration
  says what the Gazette says today; it does not say where the held file was obtained.
- The held artifact's signature does not verify. Nothing in the engine describes it as the signed Gazette,
  and `artifact_verification` now says so in the record, but any future "we hold the Gazette" claim about this
  file would be false.
- Whether the Gazette copy should *replace* the held artifact as the registered file is a founder decision:
  it would change `artifact_sha256`, and it would discard the file a human actually reviewed.

**Recommended next action.** Founder, one command, optional:
`python3 scripts/register_gsr700e.py --source --from <the https URL you used> --at <YYYY-MM-DD>`.
Then decide the artifact question above. S-002 in `research/TASKS.md` is updated to what is now true.

---

## 2. `corpus/sources/kmp_rules_registration.json` — G.S.R. 249(E) of 31-03-2014, principal KMP Rules

**Question.** Same two: does the guard check what the record claims, and can the artifact be corroborated?
This record governs s.203, which is refused today for an unrelated reason (the chain is traced, not resolved).

**Sources checked.** The record and `scripts/register_kmp_rules.py`; commits `fcb517a`, `5da7549`;
`checker/staleness.py:_acquisition_state`; India Code robots (502, three probes); eGazette notification-date
index for 31-Mar-2014 and for 25-Mar → 15-Apr-2014; eGazette full-text search; the artifact's own text layer
and PDF metadata; `scripts/provenance_census.py`.

**Evidence found.**
- Guard defect, same class: `is_attested()` checked the human checks and status only — no classification, no
  source. The record is `PENDING_HUMAN_REVIEW`, so nothing is served on it today, and `is_servable()`
  additionally requires `chain_resolved`, which no code sets.
- Provenance state: no `downloaded_from`, no `downloaded_at`. `acquisition_method` is
  `india_code_dspace_api` and `source_url` is a real bitstream address — but that field is a **constant in the
  script**, written at registration whatever happened, which is exactly the hole A-001 is about. It is not
  evidence of where these bytes came from.
- Corroboration: **not-found / blocked**. India Code is unreachable under our own robots gate (502, fails
  closed). eGazette's notification-date index for 31-Mar-2014 lists 14 gazettes — five of them MCA, including
  the Board Rules (159201) this repo already holds — and the Managerial Personnel Rules are **not among them**.
  Paging the wider range and the full-text search both failed on the site's own errors (recorded in the
  evidence log). The file predates CG-DL-E numbering, so P-1's address-from-the-number route does not exist.
  No captcha was seen and none was attempted.
- `provenance_census.py` grades the held file **UNSIGNED_RENDERING** — no signature at all.
- A claim the record contradicts: `attests_to[2]` asks a reviewer to attest that "five later amendments to
  these Rules are unacquired". All five have been held, hashed and traced since `5da7549`, and the record says
  so (`chain_traced: true`, five artifacts with hashes). `attest()` printed the same stale sentence.

**Evidence quality.** The guard reading is direct from code. The corroboration outcome is a fact about two
hosts on one day — **a failure to find is not evidence that the instrument is absent from either**.

**Result.** Defect found and closed for the guard: classification and a recorded-or-corroborated
Gazette/India Code source are now required, `--source --from --at [--replace]` exists, and `--attest` reports
its gaps instead of implying usability. **Served state: unchanged — nothing was served before and nothing is
now**, because the record is unattested and the chain is unresolved. No corroborating copy was obtained, so
the record now also carries a source gap; that is the fail-closed outcome and it costs nothing today.

**Unresolved issues.**
- `attests_to[2]` is stale and, as written, a reviewer would be signing something the record disproves. I did
  not rewrite it: it is the text of a human attestation, and its wording is the founder's call. The printed
  note in `attest()` was left alongside it for the same reason.
- No copy of G.S.R. 249(E) from an official host. The route is India Code's REST API once its robots.txt
  answers again, or eGazette once its search returns.

**Recommended next action.** Founder: decide the `attests_to[2]` wording (suggested shape — "the reviewer
understands that attesting this does not make s.203 servable: the chain is traced but not resolved, and rule
8A has moved"). Then, when India Code answers, corroborate the bitstream and record it.

---

## 3. `corpus/sources/pas_rules_registration.json` — Companies (Prospectus and Allotment of Securities) Rules, 2014, rule 12

**Question.** Same two, plus: is the held file what the record says it is? Attesting this record bounds
`paid_up_capital` in `checker/mca_snapshot.py`, which is what turns `capital_headroom` from a refusal into an
answer.

**Sources checked.** The record and `scripts/register_pas_rules.py`; commits `9009988`, `7987dd6`;
`checker/mca_snapshot.py:_delegated_window`; the artifact's PDF metadata and text layer;
`scripts/provenance_census.py`; India Code robots (502); eGazette (as above).

**Evidence found.**
- Guard defect, same class: no classification check, no source check. (It did already require
  `window_days` — the one record-specific gap that was there before this audit.)
- `downloaded_from` is recorded as **`"India Code DSpace REST (open API), item c1199089-a010-44fe-b270-1aaec2e39ac6"`** — prose, not an address — with `downloaded_at: "2026-09-13"`, while
  `acquisition_method` says `human_browser` and commit `9009988` says the file came from India Code's REST
  API. The record disagrees with itself about how it was obtained, and what it stores as the source cannot be
  fetched, checked or shown to anyone.
- The artifact is **not the as-notified principal Rules**: PDF metadata says Microsoft Word 2013, author
  `ITD_OPRT28 BABITA`, created 2017-04-12, and the text carries footnote *"1. Inserted by the Companies
  (Prospectus and Allotment of Securities) Amendment Rules, 2014, w.e.f. 30-6-2014"* with the corresponding
  `1 [ Provided also ...` insertion in rule 14. It is a rendering that incorporates at least one amendment.
  `attests_to[0]` — "this file is the principal ... Rules, 2014, and not one of the Amendment Rules" — is true
  in the sense the classifier tests (it is not an amending instrument) and misleading in the sense a reviewer
  would read it (it is not the text as notified either). The record's own `artifact_verification` already
  records the file as an unsigned rendering; `provenance_census` grades it UNSIGNED_RENDERING.
- Corroboration: **blocked** (India Code robots 502). Not attempted on eGazette: the file is an India Code
  rendering with no Gazette number in its text, and the 31-Mar-2014 index does not list these Rules either.

**Evidence quality.** Direct reading of the artifact and the record; the amendment-incorporation finding is
from the file's own footnote, quoted verbatim, not inferred.

**Result.** Defect found and closed for the guard. **Served state: unchanged — `paid_up_capital` was
UNBOUNDED_BLIND before and still is**, because the record is unattested. After this change, attesting alone
will no longer bound it: the recorded prose "source" is refused (a recorded source that fails is refused
whatever any corroboration says), so someone must record a real address with
`--source --replace --from <URL> --at <DATE>` first. That is the correct fail-closed result and the suite
asserts it.

**Unresolved issues.**
- Nobody has recorded, in a checkable form, where this file came from. I did not rewrite `downloaded_from` to
  the record's `source_url`: that would be inventing a download the founder did not make.
- The reviewer should be told, before attesting, that the file is a 2017 rendering incorporating the 2014
  amendment. `attests_to[0]` as worded does not tell them.
- The rule-12 chain verdict remains `WINDOW_PROBABLY_SURVIVES_ON_SECONDARY_REPORTING`: G.S.R. 642(E) is a
  scan, and a person must read it (unchanged by this audit).

**Recommended next action.** Founder: record the address the file actually came from
(`python3 scripts/register_pas_rules.py --source --replace --from <URL> --at <YYYY-MM-DD>`), and decide
whether `attests_to[0]` should name the rendering. Only then attest.

---

## 4. `corpus/sources/sebi_lodr_registration.json` — SEBI LODR 2015 (consolidation)

**Question.** Same two, plus whether the shared guard can be applied at all.

**Sources checked.** The record and `scripts/register_sebi_lodr.py`; commit `b72a279`; a repo-wide grep for
readers of the record (`checker/`, `scripts/`, `eval/`); `checker/scope.py`; `scripts/provenance_census.py`.

**Evidence found.**
- Guard gaps, unchanged by this job: `is_attested()` checks `identity_checked_by`,
  `consolidation_understood_by` and the status. It does **not** check `identity_checked_at`, does not check a
  classification (the record has no `classification` field at all — `register()` never writes one), and does
  not check any source.
- Provenance: no `downloaded_from`, no `downloaded_at`; `source_url` and `landing_page` are sebi.gov.in
  addresses recorded as constants; `acquisition_method: sebi_gov_in_direct`.
- **Nothing reads this record.** No module outside the script imports it, so no obligation, figure or refusal
  depends on it today. `scope.py` carries SEBI_LODR as a DECLARED body.
- `provenance_census` grades the artifact UNSIGNED_RENDERING, attributed to "SEBI (issuing regulator)".
- The shared policy cannot express this record's source: `sebi.gov.in` is not in `OFFICIAL_SOURCE_HOSTS`, and
  `official_source_url()` raises rather than letting a caller widen that set — by design, so a guard cannot
  quietly bless a new host.

**Evidence quality.** Direct reading of code and record; the "nothing reads it" claim is a grep across the
three source trees, reproduced in the evidence log.

**Result.** **No change made, deliberately.** Applying the guard would require adding sebi.gov.in to the
official host set, which is a policy decision about what this system will cite — the founder's, not a change
to slip into a guard while nothing depends on it. **Served state: unchanged (nothing served, before or
after).**

**Unresolved issues.** Three named gaps stay open: the missing `identity_checked_at` check, the absent
classification field, and the unchecked source. If LODR is ever wired to an answer, all three become live.

**Recommended next action.** Founder: decide whether sebi.gov.in belongs in `OFFICIAL_SOURCE_HOSTS` (it is
the issuing regulator's own site, and CLAUDE.md's permitted sources include official legislation). Once
decided, this record takes the same `SourcePolicy` as the others in one small change — and that should happen
*before* anything reads it, not after.

---

## 5. The two findings carried from P-1's verifier

**Question.** Are they real, and where do they belong?

**Evidence found and result.**
1. **Whitespace around a URL.** Real. `urlsplit` strips leading/trailing spaces and control characters and
   removes tab, CR and LF from *anywhere* in an address, so `" https://egazette.gov.in/x "` passed
   `official_source_url()` and was then stored, and served, with the spaces — a different address from the one
   checked. Fixed at the shared helper: `official_source_url()` and `parse_when()` now **refuse** any
   whitespace or control character rather than trimming it, because a checker that edits its input is checking
   something the caller never passed it. Applies to every register script at once, and to the date as well as
   the address.
2. **`NO_RECORD` exit code vs usage wording.** Real. It exited 1 while the usage line called 1 "recorded but
   not usable", when nothing had been recorded. Every outcome that writes nothing — `NO_RECORD`,
   `SOURCE_REFUSED`, `SOURCE_CONFLICT` — now exits **2**, and one shared `EXIT_WORDING` string says so and is
   asserted in the suites. The same sentence also now covers `register`'s own 0/2/3/4, which the old wording
   contradicted.

**Unresolved issues.** None. Both are tested in `checker/provenance.py` and in the 880(E) suite.

---

## Fix round 1 (18-09-2026): what the verifier and the main session found

Six findings against the P-2 commits, all fixed in one follow-up commit. The first is the one that
mattered.

**1. `--attest --from <URL> --at <DATE>` discarded the source on KMP and on the Allotment Rules
(MEDIUM, reproduced by the main session).** `split_source_flags` lifted the flags out of the
argument list and `attest(rest[1])` then ignored them: the human check fields were written, the
provenance the operator supplied was dropped, the exit was 1 and nothing said so. Recording an
attestation while silently discarding its provenance is the worst combination available — it is
A-001 again, created by the fix for A-001. Both scripts now take `--from/--at/--replace` on
`--attest` exactly as 880(E) and 700(E) do: the source is recorded FIRST, a bad or conflicting one
refuses with exit 2 before anything is stamped, and attesting without a source stamps the checks,
prints the remaining gap and exits 1.

**2–3. CLI contract (LOW).** The Allotment Rules script exited 1 on no arguments while printing the
shared wording that reserves 1 for "recorded but not usable"; it now exits 2, like its sibling.
Both scripts gained the `--replace applies only to --source or --attest` guard, so `--replace
file.pdf` no longer registers with the flag quietly ignored.

**4. A stored corroborating copy is now re-hashed (LOW, applies to 700(E) and 880(E)).**
`corroborating_copy.local_copy` was recorded and never read again, so renaming or replacing
`corpus/sources/gsr700e_2022_egazette.pdf` left the record corroborating on a file that was no
longer there or no longer those bytes. The rule now, in `SourcePolicy`:
- **present and hashing to the recorded value** → corroborates, silently, as before;
- **present and different** → the corroboration is REFUSED (`attestation_gaps` names it), because a
  file that is not the bytes that were fetched is not evidence of what was fetched;
- **absent** → the corroboration **stands**. The evidence is the address and the sha256 recorded at
  fetch time, and deleting a local file does not unsay them. But the record is then claiming a file
  this repository does not hold, so `local_copy_note()` says so and `prescribed_thresholds` appends
  it to the **operator** note beside the served figure (never to the reader note, which is about the
  law and not about our filesystem).
Live records at the time of writing: both copies present, both hashing to their recorded values, no
note.

**5. The census matched a stored copy by file name (LOW).** `provenance_census._copy_source`
compared base names, so two records naming different files that share a name would cross-attribute
and one record's Gazette copy could vouch for another record's file. It now compares the recorded
path, resolved against the repository root.

**6. Invisible characters in an address (INFO).** `_unspaced` refused whitespace and C0 controls but
not U+200B, U+FEFF or the bidi marks — none of which `str.isspace()` calls whitespace, all of which
survive a copy-and-paste out of a PDF, and all of which are invisible in the record they would be
stored in. It now refuses any character in Unicode categories Cc, Cf, Zs, Zl or Zp. The test label
that read "a non-breaking space" beside what looked like a plain space was a literal U+00A0 pasted
into the source; the cases are now spelled as escapes (`\u00a0`, `\u200b`, `\ufeff`, `\u200e`) so
the next reader can see what is being tested.

Nothing in §§1–5 above changed as a result: no served figure, no record content, and no evidence
outcome. The fixes are to the guard and to two CLIs.

## What this audit did not do

- It did not attest anything, and did not write or alter a human check field, a reviewer id or a timestamp.
- It did not rewrite any `downloaded_from` to an address the founder did not use.
- It did not repair a source: the 700(E) rendering's `[F .`, its stamp lines and its broken signature are all
  preserved and recorded as found.
- It did not touch `corpus/sources/SHA256SUMS`'s pre-existing stale entry for `pas_rules_2014.txt` (the file
  lives in `corpus/rules/`, so `shasum -c` reports it unreadable). Recorded here; not this job's change.
- It read `scripts/register_s188_rule15.py` only far enough to confirm it registers a *review record* of text
  already held, not a downloaded artifact, so the download-provenance question does not arise there. Its
  guard has not been audited.
