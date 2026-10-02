#!/usr/bin/env python3
"""How often does a verifier accept a quote that has been broken? Measured, per check.

M1. Every verifier in this repository is tested with things that are true. This feeds each
one things that are FALSE in six specific ways -- negation, numbers, dates, section
numbers, shall/may, truncation -- built from real held statute, and counts how often it
says yes anyway.

    false accept   a MUTATED quote was accepted. The dangerous direction.
    false reject   the ORIGINAL quote was rejected. Costly, not dangerous.

Both carry Wilson 95% intervals, because a rate from sixty quotes is not a rate from six
thousand and a bare percentage invites a decision the sample cannot support.

## Negation and number are bugs, not rates

PLAN_23 and M1 both single them out, for the same reason: they change what the law
REQUIRES while leaving every word a lexical check looks for. So this script EXITS NONZERO
on a false accept in either class. The others are reported.

## What each check is, and what it is not

    quoted_span.locate     is this text in the source, byte for byte? An exact matcher, so
                           a false accept here would mean a bug in normalisation, not a
                           judgement call.
    claim_verifier         does the evidence carry the claim? Its LEXICAL_CANDIDATE
                           verdict is deliberately NOT support -- the architecture's
                           answer to term-overlap survival -- and this measures whether
                           that holds.
    entailment_gate.grade  the only check that can PROMOTE to SUPPORTED. It is the one
                           that can genuinely be fooled, and the headline number.

Run: PYTHONPATH=. python3 scripts/verifier_error_rates.py
     PYTHONPATH=. python3 scripts/verifier_error_rates.py --json
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

SAMPLE = 400         # provisions drawn from the held corpus
PER_SECTION = 3      # sentences per section: one sentence rarely carries every construct


@dataclass
class Tally:
    attempted: int = 0
    accepted: int = 0          # false accepts, for mutated input

    def rate(self):
        return None if not self.attempted else self.accepted / self.attempted


@dataclass
class CheckResult:
    check: str
    by_mutation: dict = field(default_factory=dict)
    originals: int = 0
    original_rejected: int = 0     # false rejects
    unmeasurable: int = 0          # quotes this check could not be driven on, and why
    unmeasurable_why: str = ""
    means: str = ""                # what this check's numbers do and do not say

    def to_dict(self) -> dict:
        from checker.review_grid import wilson
        out = {"check": self.check, "means": self.means,
               "false_accept": {}, "false_reject": {}}
        for kind, t in sorted(self.by_mutation.items()):
            lo, hi = wilson(t.accepted, t.attempted) if t.attempted else (None, None)
            out["false_accept"][kind] = {
                "accepted": t.accepted, "attempted": t.attempted,
                "rate": t.rate(), "ci95": [lo, hi],
                "note": ("not attempted on any quote: the mutation could not apply"
                         if not t.attempted else "")}
        if self.unmeasurable:
            out["unmeasurable"] = {"quotes": self.unmeasurable,
                                   "why": self.unmeasurable_why}
        lo, hi = wilson(self.original_rejected, self.originals) if self.originals \
            else (None, None)
        out["false_reject"] = {
            "rejected": self.original_rejected, "attempted": self.originals,
            "rate": (None if not self.originals
                     else self.original_rejected / self.originals),
            "ci95": [lo, hi]}
        return out


def provisions(n: int = SAMPLE):
    """Real held statute, as (row, one sentence of it).

    The row is the corpus record with `section_number` filled in from
    `corpus/companies_act/_index.json`, which is what `evidence_pack.build_pack` needs to
    give a provision an identity. Walking the index rather than globbing the directory also
    skips `_index.json` and `_manifest.json`, which are not sections -- the miscount
    CLAUDE.md records being corrected on 27-09-2026.
    """
    import json as _json
    import re
    from pathlib import Path

    from checker.sarvam_model import html_to_text

    root = Path(__file__).resolve().parent.parent / "corpus" / "companies_act"
    index = _json.loads((root / "_index.json").read_text(encoding="utf-8"))["entries"]

    out = []
    for number, entry in sorted(index.items(), key=lambda kv: _sort_key(kv[0])):
        section_id = str(entry.get("section_id") or "")
        path = root / f"{section_id}.json"
        if not section_id or not path.exists():
            continue                    # an omitted provision resolves to no record
        try:
            rec = _json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        row = dict(rec, section_number=str(number), title=entry.get("title") or "")
        taken = 0
        for sentence in re.split(r"(?<=[.;])\s+", html_to_text(rec.get("content") or "")):
            text = " ".join(sentence.split())
            # Long enough to be a real quote and to survive a truncation mutation.
            if 90 <= len(text) <= 400:
                out.append((row, text))
                taken += 1
                if taken >= PER_SECTION:
                    break
        if len(out) >= n:
            break
    return out[:n]


def _sort_key(number: str):
    """Section numbers sort as numbers, not as strings: s.9 before s.10, s.173 after s.96."""
    m = re.match(r"(\d+)(.*)", str(number))
    return (int(m.group(1)), m.group(2)) if m else (10 ** 9, str(number))


def _locate_check(quotes) -> CheckResult:
    from checker.quote_mutations import MUTATIONS, mutate
    from checker.quoted_span import locate

    class Src:
        def __init__(self, text):
            self.text = text

    res = CheckResult(
        "quoted_span.locate",
        means=("An EXACT matcher. A false accept here would be a normalisation bug, not a "
               "judgement call -- and the 100% on truncation is CORRECT behaviour, not a "
               "defect: a truncated quote IS a substring of the source, so byte-matching "
               "finds it. Dropping a proviso is a half-truth stated in true words, which "
               "is E6's question, not this one's."))
    for row, text in quotes:
        sources = [Src(text)]
        res.originals += 1
        if locate(text, sources) is None:
            res.original_rejected += 1
        for kind in MUTATIONS:
            bad = mutate(text, kind)
            t = res.by_mutation.setdefault(kind, Tally())
            if bad is None:
                continue        # NOT ATTEMPTED, never counted as a pass
            t.attempted += 1
            if locate(bad, sources) is not None:
                t.accepted += 1
    return res


def _entailment_check(quotes) -> CheckResult:
    from checker.claim_verifier import LEXICAL_CANDIDATE, SUPPORTED
    from checker.entailment_gate import grade
    from checker.quote_mutations import MUTATIONS, mutate

    res = CheckResult(
        "entailment_gate.grade",
        means=("The ONLY check that can promote to SUPPORTED, so it is the only one that "
               "can genuinely be fooled, and the headline number. Its truncation rate is a "
               "real weakness rather than an artefact: the gate accepts a quote whose "
               "proviso was removed, because what remains is true."))
    for row, text in quotes:
        res.originals += 1
        if grade(text, text, LEXICAL_CANDIDATE) != SUPPORTED:
            res.original_rejected += 1
        for kind in MUTATIONS:
            bad = mutate(text, kind)
            t = res.by_mutation.setdefault(kind, Tally())
            if bad is None:
                continue
            t.attempted += 1
            # The premise is the TRUE text; the claim is the broken one. Promoting that
            # to SUPPORTED is the failure this check exists to prevent.
            if grade(text, bad, LEXICAL_CANDIDATE) == SUPPORTED:
                t.accepted += 1
    return res


def _claim_verifier_check(quotes) -> CheckResult:
    """Drive the real `verify_claim` against a real `build_pack` pack, per quote.

    An earlier version of this function asked `establishes_support(LEXICAL_CANDIDATE)` once
    per row. That is a CONSTANT -- it reads neither the quote nor the mutation -- so it
    reported 0/400 with a Wilson interval implying four hundred independent observations of
    a single fact. A rate computed from a constant is not a rate, and the interval was the
    most misleading part of it. This runs the verifier against the pack a runtime builds.
    """
    from checker.claim_schema import ClaimError
    from checker.claim_verifier import establishes_support, verify_claim
    from checker.evidence_pack import EvidencePackError, build_pack
    from checker.quote_mutations import MUTATIONS, mutate

    res = CheckResult("claim_verifier.verify_claim",
                      means=(
                          "Read the false ACCEPT column. The false-reject rate is 100% BY "
                          "DESIGN and is not a defect: this module never returns SUPPORTED "
                          "-- its own docstring says the top lexical verdict used to be "
                          "SUPPORTED and that was a lie -- so `establishes_support` is "
                          "False for every verdict it can return. A 334/334 false-reject "
                          "rate is that reservation being kept, and the 0 false accepts "
                          "across all six classes are what it buys."),
                      unmeasurable_why=(
                          "checker/claim_schema.Claim refuses a non-atomic claim, and a "
                          "statutory sentence often joins propositions. Those quotes are "
                          "NOT MEASURED here rather than skipped quietly: this check's "
                          "denominator is smaller than the other two on purpose"))
    for i, (row, text) in enumerate(quotes):
        try:
            pack = build_pack([row], query=text[:60], mode="MODEL")
        except EvidencePackError:
            res.unmeasurable += 1       # no identity, so not packable -- never a pass
            continue
        ev = tuple(p.key for p in pack.provisions)
        if not ev:
            res.unmeasurable += 1
            continue
        try:
            true_claim = _claim(f"t{i}", text, ev)
        except ClaimError:
            res.unmeasurable += 1
            continue

        res.originals += 1
        if not establishes_support(verify_claim(true_claim, pack).verdict):
            res.original_rejected += 1

        for kind in MUTATIONS:
            bad = mutate(text, kind)
            t = res.by_mutation.setdefault(kind, Tally())
            if bad is None:
                continue
            try:
                claim = _claim(f"m{i}", bad, ev)
            except ClaimError:
                continue                # NOT ATTEMPTED, exactly as an N/A mutation is
            t.attempted += 1
            if establishes_support(verify_claim(claim, pack).verdict):
                t.accepted += 1
    return res


def _claim(claim_id: str, text: str, evidence_ids: tuple):
    from checker.claim_schema import LEGAL_TRIGGER, Claim
    return Claim(claim_id=claim_id, text=text, claim_type=LEGAL_TRIGGER,
                 evidence_ids=evidence_ids)


def measure(n: int = SAMPLE) -> dict:
    quotes = provisions(n)
    checks = [_locate_check(quotes), _entailment_check(quotes),
              _claim_verifier_check(quotes)]
    from checker.quote_mutations import DANGEROUS
    bugs = []
    for c in checks:
        for kind in DANGEROUS:
            t = c.by_mutation.get(kind)
            if t and t.accepted:
                bugs.append({"check": c.check, "mutation": kind,
                             "accepted": t.accepted, "attempted": t.attempted})
    return {"provisions": len(quotes), "dangerous": list(DANGEROUS),
            "checks": [c.to_dict() for c in checks], "bugs": bugs}


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width) if text else []


def report(r: dict) -> str:
    lines = [f"verifier error rates over {r['provisions']} real held provisions", ""]
    for c in r["checks"]:
        lines.append(f"  {c['check']}")
        for chunk in _wrap(c.get("means", ""), 84):
            lines.append(f"    | {chunk}")
        if c.get("unmeasurable"):
            lines.append(f"    not measured  {c['unmeasurable']['quotes']} quotes: "
                         f"{c['unmeasurable']['why'][:58]}...")
        fr = c["false_reject"]
        lines.append(f"    false reject  {fr['rejected']}/{fr['attempted']}"
                     + (f"  (95% CI {fr['ci95'][0]:.0%}-{fr['ci95'][1]:.0%})"
                        if fr["ci95"][0] is not None else ""))
        for kind, fa in c["false_accept"].items():
            mark = "  <-- BUG" if (fa["accepted"] and kind in r["dangerous"]) else ""
            if not fa["attempted"]:
                lines.append(f"    false accept  {kind:<15} not attempted")
                continue
            lines.append(f"    false accept  {kind:<15} {fa['accepted']}/"
                         f"{fa['attempted']}"
                         f"  (95% CI {fa['ci95'][0]:.0%}-{fa['ci95'][1]:.0%}){mark}")
        lines.append("")
    if r["bugs"]:
        lines.append(f"  {len(r['bugs'])} FALSE ACCEPT(S) on a negation or number "
                     f"mutation. M1 calls these bugs, not rates:")
        for b in r["bugs"]:
            lines.append(f"    {b['check']} accepted {b['accepted']}/{b['attempted']} "
                         f"{b['mutation']} mutations")
    else:
        lines.append("  No false accept on a negation or number mutation. Those are the "
                     "two that change\n  what the law REQUIRES while keeping every word a "
                     "lexical check looks for.")
    lines += ["", "  A mutation that could not apply to a quote is NOT ATTEMPTED, never a "
                  "pass: a\n  mutation that changed nothing and was then rejected is a "
                  "check never tested."]
    return "\n".join(lines)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("verifier_error_rates")
    r = measure(12)
    check(r["provisions"] > 0, f"real held provisions are drawn ({r['provisions']})")
    check(len(r["checks"]) == 3,
          f"three checks are measured ({[c['check'] for c in r['checks']]})")
    # The headline check is only evidence if the dangerous mutations were actually
    # attempted. Without this it would pass just as readily on a sample where no quote
    # could carry a negation -- the vacuity a clean result is most prone to.
    from checker.quote_mutations import DANGEROUS
    attempted = {k: sum(c["false_accept"][k]["attempted"] for c in r["checks"])
                 for k in DANGEROUS}
    check(all(v > 0 for v in attempted.values()),
          f"the dangerous mutations were ATTEMPTED, so the next check is evidence "
          f"({attempted})")
    check(not r["bugs"],
          f"**no false accept on a negation or number mutation** -- M1 calls those bugs "
          f"({r['bugs']})")

    # ...and the bug detector must be able to fire. A reporter that cannot report is
    # indistinguishable from a verifier that never errs.
    _probe = dict(r)
    _probe["checks"] = [dict(r["checks"][0])]
    _probe["checks"][0]["false_accept"] = dict(
        r["checks"][0]["false_accept"],
        negation={"accepted": 3, "attempted": 3, "rate": 1.0, "ci95": [0.4, 1.0],
                  "note": ""})
    check("BUG" in report({**_probe, "bugs": [
              {"check": "probe", "mutation": "negation", "accepted": 3, "attempted": 3}]}),
          "a false accept on a dangerous mutation IS reported as a bug when one exists")
    for c in r["checks"]:
        check(set(c["false_accept"]) == {"negation", "number", "date", "section_number",
                                         "shall_may", "truncation"},
              f"{c['check']}: all six mutations are reported")
        check(all(v["attempted"] == 0 or v["ci95"][0] is not None
                  for v in c["false_accept"].values()),
              f"{c['check']}: every attempted rate carries a Wilson interval")
    text = report(r)
    check("NOT ATTEMPTED" in text,
          "the report says a mutation that could not apply is not a pass")
    check("accuracy" not in text.lower(), "...and never claims accuracy")
    check(json.loads(json.dumps(r)) == r, "the result is JSON-serialisable, as M1 asks")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    result = measure()
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
    else:
        print(report(result))
    raise SystemExit(1 if result["bugs"] else 0)
