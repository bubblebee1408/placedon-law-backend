# Lessons

Things that cost something to learn. Each one names the incident, because a lesson without its
incident degrades into a slogan within a month and gets ignored.

Rules for this file: only write a lesson **after** it has cost you something. Never write one
that was merely predicted. Delete one only when it is proven wrong, not when it becomes
uncomfortable.

---

## L-1 — Generated plans repeat each other's fabrications with total confidence

**Incident.** *"Every employer employing 10 or more employees shall constitute an Internal
Committee"* is not in the PoSH Act. That sentence appeared in the master spec §2.2, the
scaffold's `applicability.py`, the scaffold's `seed_provisions.py`, and — after all of that — in
a code comment in our own shipped `checker/rules.py`. Four documents, one fabrication, zero
sources. The ten-worker figure is actually in s.2 and s.6(1).

**What caught it.** Only the ingested verbatim corpus. Not review, not cross-checking the plan
against itself, not any amount of care while reading. A second generated document agreeing with
the first is not corroboration — it is the same error twice.

**Apply.** Ingest the primary text before writing rules that cite it. If a claim cannot be traced
to a `text_display` field, it is not a claim yet.

---

## L-2 — Unit tests cannot see the browser, and the browser is where users are

**Incident.** Three bugs shipped past a fully green Python suite: CORS not exposing
`X-Blocking-Issues` (so the unlawful-committee banner never fired cross-origin), "Change the
details" unmounting the form and discarding every committee member typed, and the "Before you
sign this" panel rendering *below* the signature line while marked `no-print`.

Each was invisible from Python because each lived in the gap between the layers — the CORS
policy, React's mount lifecycle, the print stylesheet.

**Apply.** Drive the real flow in a real browser before claiming a feature works. `scripts/
verify.py` now holds a permanent check for each of the three.

---

## L-3 — Rehearse a process end to end before asking a human to run it

**Incident.** The lawyer review pack asked for **six** sections and told the reviewer that
verifying them unlocked the product. Rehearsing the whole cycle against a stub reviewer disproved
it in about a minute: with all six verified, *"Do I need an Internal Committee?"* still abstained,
because `verifier.should_abstain` rejects a packet if **any** provision in it is unverified — and
that question also retrieves s.7. Six sections bought one answer out of twelve. The real closure
is twelve sections.

Had that not been rehearsed, a lawyer would have spent an evening on the wrong six sections and
the product would still have abstained at the end of it. That is a favour you get to ask once.

**Apply.** Any process that ends at a human — a lawyer, a customer, a filing — gets rehearsed
with a stub first. Tier 1 is now computed from the retrieval closure so it cannot drift again.

---

## L-4 — The unit of verification is the retrieved packet, not the cited section

**Incident.** The generalisation of L-3, and worth stating separately because it is a property of
the architecture rather than a mistake in a document. Verifying the section a claim cites is not
enough; everything retrieval pulls alongside it must also be verified, or the answer still
abstains.

**Apply.** Anywhere the corpus grows, compute what a question actually retrieves rather than what
it appears to cite.

---

## L-5 — Numbers in specs are usually asserted, not derived, and the arithmetic often fails

**Incident.** The spec paired "₹150–250/day" with a "₹3,500/month" cap. ₹150 × 30 = ₹4,500 and
₹250 × 30 = ₹7,500 — both breach the cap, so every daily check would have passed while the month
blew out. `DAILY_CAP_INR` is now `MONTHLY_CAP_INR / 30`, derived. The autonomous-agent-system
document later reintroduced the identical bug as "₹155/day".

Same pattern elsewhere: "₹3–5 per call" priced a mid-tier model at Opus rates (measured: **₹0.97**
on Haiku 4.5); the 0–100 risk score and HIGH/MEDIUM confidence tiers had no derivation at all; the
₹539 Cr TAM is not reproducible from Udyam data because India does not classify enterprises by
headcount.

**Apply.** Derive every number in code from a constant, and multiply it out before believing it.
If a figure cannot be derived, it does not go in front of a customer or an investor.

---

## L-6 — A checklist that is not executable is a record of intentions

**Incident.** The agent-system document proposed a verification checklist as a markdown file. Its
own best idea — *"if the Verify Agent misses a bug, that check is added permanently"* — only
works if the checklist runs. `scripts/verify.py` is therefore the checklist: every check carries
`because=`, the incident that bought it.

**And on its first run it failed two of its own checks, both false positives.** It flagged
`citation-badge.tsx` and `trust-footer.tsx` for the false verification badge — where the phrase
appears only in comments explaining why we refused it. A check that cannot tell an assertion from
an explanation of a refusal punishes the exact discipline it exists to protect, and would have
trained us to delete the reasoning. The other was a ten-paisa rounding artefact.

**Apply.** New checks get calibrated against the current tree before being trusted. A check that
fires on correct code is worse than no check, because it teaches people to ignore the suite.

---

## L-7 — Research the enforcement route, not just the obligation

**Incident.** Two months of work aimed at PoSH s.26 — ₹50,000, enforced by a District Officer who
may never call. One afternoon of research found that Rule 8(5)(x) of the Companies (Accounts)
Rules has, since **14 July 2025**, required the Board's Report to carry three complaint counts,
with **₹3,00,000** under s.134(8) — assessed off a document the company files itself, annually, in
a standard form. A self-reported machine-readable annual filing is a far higher-probability
enforcement path than an inspection.

The same pass found the research cut *against* our stated ICP: Rule 8(6) exempts Small Companies
and OPCs, so the disclosure bites above the micro-SME segment `docs/03` targets.

**Apply.** For any obligation, ask separately: who checks, how often, and off what document. The
answer changes the product more than the obligation does. Record findings that contradict the
plan at least as carefully as findings that support it.

---

## L-8 — Secondary sources agree with each other and are still wrong together

**Incident.** Every secondary source states the PoSH ten-employee threshold as though s.4
contained it. It does not. Separately, two sources assert that Rule 8A requires an IC statement
from small companies; the full text of Rule 8A shows no such clause. That second one is still
**unresolved** — it is Question 6 in the lawyer pack — and it has exactly the shape of the first.

**Apply.** Consistency across secondary sources is evidence of a shared upstream, not of truth.
Record the disagreement rather than picking a side, and mark the provenance in the corpus itself
(`source_quality`, `PROVENANCE_WARNING`) so downstream documents can disclose their own weakness.

---

## L-9 — Build speed has never been the constraint

**Incident.** Two months produced ~2,500 lines of tested code, 30 sections ingested verbatim,
three working document generators, and a checker that refuses to state what it cannot source.
Over the same period: **0 of 30 sections lawyer-verified, 0 customer conversations, 0 LLM calls
ever made.**

Everything of value shipped so far is deterministic. The AI layer has never been switched on
because the corpus is unverified.

**Apply.** Before adopting any system that makes building faster, check whether building is what
is blocked. Here it never has been. Both real gates — an evening with a lawyer (H-2), ten phone
calls (H-1) — are human, and no amount of tooling moves either.

---

## L-10 — A case-insensitive filesystem turns `ln -sf` into a file shredder

**Incident.** To make the spec's uppercase command names resolve, I ran
`ln -sf start.md .claude/commands/START.md` for four files. macOS APFS is case-insensitive, so
`START.md` **is** `start.md` — each link pointed at itself. All four command files, written
minutes earlier, became `too many levels of symbolic links`. They were recoverable only because
they had been committed.

The aliases were never needed: a case-insensitive filesystem already resolves `/START` to
`start.md`. The work destroyed the files it was trying to make more accessible.

**Apply.** On macOS, never create a symlink whose name differs from its target only by case.
Before any `ln -sf`, `mv`, or `rm` over existing files, check what is there — and commit first,
because git was the entire recovery path here. `scripts/verify.py` now checks that every command
file is readable and non-empty.

---

## L-11 — A check that skips when its input is missing reports PASS for a bug it never looked at

**Incident.** An adversarial review of `scripts/verify.py` — the file whose entire job is to be
trusted — found three checks that could pass while the bug they were named for was live.

- Two index checks began `if not idx_path.exists(): return True`. `.claude/index.json` is
  gitignored, so on **every fresh clone and in CI** they asserted nothing and printed PASS.
- `_cors_expose` searched all of `app.py` for `"X-Blocking-Issues"`. That string also appears
  where the response header is set, so deleting it from `expose_headers` — the original
  incident — left the check green.
- `_no_s4_threshold` grepped `rules.py` and the corpus but never touched `checker/assess.py`,
  the only file that emits the citation. Flipping `CITE_THRESHOLD` to `CITE_S4` there passed.

Each was proven with a working bypass, not argued.

**Apply.** Two rules, both now enforced in `verify.py`:

1. **Never skip a check because its input is missing.** Build the input, or fail. A skipped
   check that prints PASS is worse than no check, because it is trusted.
2. **String presence is not a proxy for behaviour.** Read the actual configuration
   (`app.user_middleware`), run the actual function (`assess()`), rebuild the actual artifact.
   A grep passes for reasons that have nothing to do with what you meant.

And the meta-lesson: **the ratchet needs its own adversary.** It found none of this itself.

---

## L-12 — Test the state the product will be in, not the state it is in

**Incident.** A build plan proposed an edge-case abstention list — *"intern, contractor,
multi-state always abstain."* Checked against the live product, every one of those questions
already abstained, so the gate looked redundant.

It was not. They abstained **incidentally**, because 0 of 30 sections are verified and therefore
*everything* abstains. Simulating the corpus a lawyer has signed off — the state the product is
one evening away from — showed it answering *"do interns count toward the ten?"* from s.2(f), a
definition that never mentions interns.

**The gate opening is exactly when the hole appears.** The day the product becomes useful is the
day it starts answering the questions it must refuse. Every test we had was run against a state
that hid the bug.

Then the first fix broke the flagship question: substring matching meant **"Internal Committee"
contains "intern"**, so *"Do I need an Internal Committee?"* abstained. Word boundaries fixed it.

**Apply.** When a system has a gate, test both sides of it. `checker/test_unlock.py` already
simulates verification for the happy path; that simulation is now also where refusals get
checked. And match on word boundaries, never substrings, when the trigger words are common
fragments of legitimate terms.
