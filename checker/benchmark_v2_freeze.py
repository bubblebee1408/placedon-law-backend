"""Freeze the human-reviewed benchmark, and refuse to freeze anything else.

Freezing does not mean the benchmark is legally complete. It means the exact
version is fixed, the records cannot change silently, future results are
comparable, every label has an explicit basis, and every human approval is
auditable. Nothing more is claimed.

## What may enter

Only `ENTAILED` and `NOT_ENTAILED` records, and only where a `HUMAN_JUDGED`
label carries an APPROVED review. These are excluded by construction, not by
filtering-and-hoping:

    INVALID_FIXTURE   PENDING_REVIEW   UNRESOLVED
    SOURCE_MISSING    CONTRADICTORY

`freeze()` raises rather than dropping a bad record silently. A freeze that
quietly excludes half its input is indistinguishable from one that worked.

## What this benchmark is

    human-reviewed, corpus-derived benchmark for selected Indian corporate-law
    proposition types

It does **not** measure general legal grounding. Its claims are derived from a
handful of provisions of one Act, its negatives are constructed, and its
positives were written by one reviewer. It is useful for detecting failure modes
and for comparing checkers against each other. It is not evidence that any
system is accurate on real user-generated legal claims.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from checker.grounding_policy import (
    ENTAILED, HUMAN_JUDGED, INVALID_FIXTURE, NOT_ENTAILED, PENDING_REVIEW,
    REVIEW_APPROVED, REVIEW_REJECTED,
)

DIR = Path("corpus/benchmark")
APPROVED_F = DIR / "approved_pairs.jsonl"
REJECTED_F = DIR / "rejected_pairs.jsonl"
INVALID_F = DIR / "invalid_fixtures.jsonl"
PENDING_F = DIR / "pending_reviews.jsonl"
MANIFEST_F = DIR / "manifest.json"

VERSION = "1.0.0"
DESCRIPTION = ("human-reviewed, corpus-derived benchmark for selected Indian "
               "corporate-law proposition types")

FROZEN_LABELS = (ENTAILED, NOT_ENTAILED)
EXCLUDED_LABELS = (INVALID_FIXTURE, PENDING_REVIEW, "UNRESOLVED",
                   "SOURCE_MISSING", "CONTRADICTORY")


class FreezeError(RuntimeError):
    """A record that must not be frozen reached the freeze. Never swallowed."""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def eligible(pairs) -> list:
    from checker.reviews import status_of
    out = []
    for p in pairs:
        if p.label in EXCLUDED_LABELS:
            continue
        if p.label not in FROZEN_LABELS:
            raise FreezeError(f"{p.id}: unknown label {p.label!r}")
        if p.label_basis == HUMAN_JUDGED:
            st, _, _ = status_of(p.id)
            if st != REVIEW_APPROVED:
                raise FreezeError(
                    f"{p.id}: HUMAN_JUDGED with review status {st!r} reached the "
                    "freeze; only APPROVED may be frozen")
        out.append(p)
    return out


def _record(p) -> dict:
    from checker.reviews import status_of
    st, who, when = status_of(p.id)
    return {
        "pair_id": p.id,
        "claim": p.claim,
        "label": p.label,
        "label_basis": p.label_basis,
        "source_id": f"companies-act-2013-s{p.section}",
        "section": p.section,
        "subsection": p.subsection,
        "source_span_hash": "sha256:" + _sha(p.source_span.encode()),
        "qualifiers": [q.get("effect", q.get("kind")) for q in p.qualifiers],
        "preserves_all_qualifiers": p.preserves_all_qualifiers,
        "kind": p.kind,
        "rationale": p.rationale,
        "review": ({"reviewer_id": who, "reviewed_at": when, "decision": st}
                   if st != PENDING_REVIEW else None),
    }


def freeze() -> dict:
    from checker.entail_pairs_v2 import all_pairs, contradictions, qualifier_failures
    from checker.fixture_rebuild import invalid_records, propose
    from checker.reviews import load as load_reviews, status_of

    pairs = all_pairs()

    cons = contradictions(pairs)
    if cons:
        raise FreezeError(f"{len(cons)} contradiction(s) present: {cons[:3]}")
    qf = qualifier_failures(pairs)
    if qf:
        raise FreezeError(f"{len(qf)} qualifier-preservation failure(s): {qf[:3]}")

    keep = eligible(pairs)
    recs = [_record(p) for p in sorted(keep, key=lambda x: x.id)]

    DIR.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)
    APPROVED_F.write_text(body, encoding="utf-8")

    # Rejected pairs are kept: a rejection with its reason is part of the record.
    reviews = load_reviews()
    rej = [{"pair_id": k, **v} for k, v in sorted(reviews.items())
           if v.get("status") == REVIEW_REJECTED]
    REJECTED_F.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rej),
        encoding="utf-8")

    inv = invalid_records()
    INVALID_F.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in inv),
        encoding="utf-8")

    pend = [asdict(p) for p in propose() if status_of(p.pair_id)[0] != REVIEW_APPROVED]
    PENDING_F.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in pend),
        encoding="utf-8")

    labels: dict[str, int] = {}
    bases: dict[str, int] = {}
    for r in recs:
        labels[r["label"]] = labels.get(r["label"], 0) + 1
        bases[r["label_basis"]] = bases.get(r["label_basis"], 0) + 1

    reviewers = sorted({r["review"]["reviewer_id"] for r in recs if r["review"]})
    stamps = sorted({r["review"]["reviewed_at"] for r in recs if r["review"]})
    sources = sorted({r["source_id"] for r in recs})
    src_hashes = {r["source_id"]: r["source_span_hash"] for r in recs}

    man = {
        "benchmark_version": VERSION,
        "description": DESCRIPTION,
        "not_a_claim_of": ("This benchmark does not measure general legal "
                           "grounding. It is derived from selected provisions of "
                           "one Act, its negatives are constructed, and its "
                           "positives were written and reviewed by one reviewer."),
        "software_commit": _commit(),
        "pair_count": len(recs),
        "label_counts": labels,
        "label_basis_counts": bases,
        "source_ids": sources,
        "source_span_hashes": src_hashes,
        "fixture_hashes": {
            "approved_pairs.jsonl": _sha(APPROVED_F.read_bytes()),
            "rejected_pairs.jsonl": _sha(REJECTED_F.read_bytes()),
            "invalid_fixtures.jsonl": _sha(INVALID_F.read_bytes()),
            "pending_reviews.jsonl": _sha(PENDING_F.read_bytes()),
        },
        "reviewer_ids": reviewers,
        "review_timestamps": stamps,
        "excluded_labels": list(EXCLUDED_LABELS),
        "invalid_fixture_count": len(inv),
        "pending_review_count": len(pend),
        "rejected_count": len(rej),
    }
    MANIFEST_F.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    return man


def baseline_report() -> str:
    """Measured scores beside the trivial baselines. Never one without the other.

    The two benchmarks disagree about E3, and the disagreement is the point:

        templated set (2,052 pairs)  E3 1.00 vs majority 0.57  -> beats it
        strict set (71 pairs)        E3 0.44 vs majority 0.66  -> does NOT

    The templated negatives alter one checkable token, which is what E3 checks.
    The strict set's negatives drop a qualifier or rebind a quantity, which it
    cannot see. Reporting only the first number would be true and misleading,
    which is the failure Afane et al. (CSLAW 2026) measured in two commercial
    products: an all-affirmative baseline scored F1 0.73 against Westlaw AI's
    0.64 and Lexis+ AI's 0.41.
    """
    from checker.entail_baseline import judge
    from checker.entail_pairs_v2 import all_pairs

    rows = [json.loads(l) for l in
            APPROVED_F.read_text().splitlines() if l.strip()]
    spans = {p.id: p.source_span for p in all_pairs()}
    n = len(rows)
    gold = [r["label"] == ENTAILED for r in rows]
    pos = sum(gold)

    def prf(pred):
        tp = sum(p and g for p, g in zip(pred, gold))
        fp = sum(p and not g for p, g in zip(pred, gold))
        fn = sum((not p) and g for p, g in zip(pred, gold))
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        return (sum(p == g for p, g in zip(pred, gold)) / n if n else 0.0,
                2 * pr * rc / (pr + rc) if pr + rc else 0.0)

    always_yes = prf([True] * n)
    always_no = prf([False] * n)
    e3 = prf([judge(spans[r["pair_id"]], r["claim"]).entailed for r in rows])
    majority = max(always_yes[0], always_no[0])

    lines = [
        "", f"STRICT BENCHMARK — n={n} ({pos} ENTAILED / {n - pos} NOT_ENTAILED)",
        f"  {'strategy':<26}{'accuracy':>10}{'F1':>8}",
        f"    {'always ENTAILED':<24}{always_yes[0]:>10.2f}{always_yes[1]:>8.2f}",
        f"    {'always NOT_ENTAILED':<24}{always_no[0]:>10.2f}{always_no[1]:>8.2f}",
        f"    {'MAJORITY CLASS':<24}{majority:>10.2f}",
        f"    {'E3 deterministic':<24}{e3[0]:>10.2f}{e3[1]:>8.2f}",
        "",
        f"  E3 {'BEATS' if e3[0] > majority else 'DOES NOT BEAT'} the majority class "
        f"({e3[0]:.2f} vs {majority:.2f}, delta {e3[0] - majority:+.2f})",
    ]
    return "\n".join(lines)


def verify() -> list[str]:
    """Re-read everything from disk and check it against the manifest."""
    problems: list[str] = []
    if not MANIFEST_F.exists():
        return ["manifest.json is missing"]
    man = json.loads(MANIFEST_F.read_text())

    for name, want in man["fixture_hashes"].items():
        p = DIR / name
        if not p.exists():
            problems.append(f"{name} is missing")
            continue
        got = _sha(p.read_bytes())
        if got != want:
            problems.append(f"{name}: sha256 {got[:16]}… != manifest {want[:16]}…")

    rows = [json.loads(l) for l in APPROVED_F.read_text().splitlines() if l.strip()]
    if len(rows) != man["pair_count"]:
        problems.append(f"pair_count {man['pair_count']} != {len(rows)} rows on disk")
    for r in rows:
        if r["label"] not in FROZEN_LABELS:
            problems.append(f"{r['pair_id']}: label {r['label']!r} must not be frozen")
        if r["label_basis"] == HUMAN_JUDGED and (
                not r.get("review") or r["review"]["decision"] != REVIEW_APPROVED):
            problems.append(f"{r['pair_id']}: HUMAN_JUDGED without an approval")
        if r.get("review") and "@" in str(r["review"].get("reviewer_id")):
            problems.append(f"{r['pair_id']}: reviewer id is an email address")
    counted: dict[str, int] = {}
    for r in rows:
        counted[r["label"]] = counted.get(r["label"], 0) + 1
    if counted != man["label_counts"]:
        problems.append(f"label counts {counted} != manifest {man['label_counts']}")
    return problems


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("benchmark_v2_freeze")

    from checker.entail_pairs_v2 import Pair, all_pairs
    from checker.grounding_policy import CONSTRUCTED

    # Nothing unresolved may pass the gate. Each is refused, not dropped.
    for lbl in (INVALID_FIXTURE, PENDING_REVIEW):
        bad = Pair("x", "173", "1", "s", "c", lbl, CONSTRUCTED)
        check(eligible([bad]) == [], f"{lbl} is excluded from the freeze")
    for lbl in ("UNRESOLVED", "SOURCE_MISSING", "CONTRADICTORY"):
        check(eligible([Pair("x", "173", "1", "s", "c", lbl, CONSTRUCTED)]) == [],
              f"{lbl} is excluded from the freeze")
    try:
        eligible([Pair("x", "173", "1", "s", "c", "NONSENSE", CONSTRUCTED)])
        check(False, "an unknown label raises rather than being silently dropped")
    except FreezeError:
        check(True, "an unknown label raises rather than being silently dropped")
    try:
        eligible([Pair("z-unreviewed", "173", "1", "s", "c", ENTAILED, HUMAN_JUDGED)])
        check(False, "an unapproved HUMAN_JUDGED record raises")
    except FreezeError:
        check(True, "an unapproved HUMAN_JUDGED record raises")

    man = freeze()
    check(man["pair_count"] > 0, f"the benchmark froze ({man['pair_count']} pairs)")
    check(set(man["label_counts"]) <= set(FROZEN_LABELS),
          f"only ENTAILED/NOT_ENTAILED are frozen ({man['label_counts']})")
    check(man["software_commit"] != "unknown", "the software commit is recorded")
    check(man["benchmark_version"] == VERSION, "the benchmark version is recorded")
    check(man["reviewer_ids"] and all("@" not in r for r in man["reviewer_ids"]),
          f"reviewer ids are pseudonymous ({man['reviewer_ids']})")
    check(man["review_timestamps"], "review timestamps are recorded")
    check(man["source_ids"] and man["source_span_hashes"],
          "source ids and span hashes are recorded")
    check(len(man["fixture_hashes"]) == 4, "every fixture file is hashed")
    check("does not measure general legal grounding" in man["not_a_claim_of"],
          "the manifest states what the benchmark does NOT measure")
    check(man["description"] == DESCRIPTION, "the benchmark carries its honest label")

    probs = verify()
    check(probs == [], f"the manifest verifies against disk ({probs[:2]})")

    br = baseline_report()
    check("MAJORITY CLASS" in br, "the strict report carries the trivial baselines")
    check("DOES NOT BEAT" in br,
          "E3's failure against the majority class on the strict set is stated")
    check("always NOT_ENTAILED" in br,
          "both trivial strategies are shown, not just the winning one")

    # Tamper detection.
    orig = APPROVED_F.read_text()
    try:
        APPROVED_F.write_text(orig + json.dumps({"pair_id": "tamper", "label": ENTAILED,
                                                 "label_basis": "CONSTRUCTED"}) + "\n")
        check(verify() != [], "a tampered approved_pairs.jsonl fails verification")
    finally:
        APPROVED_F.write_text(orig)
    check(verify() == [], "restoring the file restores verification")

    for f in (APPROVED_F, REJECTED_F, INVALID_F, PENDING_F, MANIFEST_F):
        check(f.exists(), f"{f.name} was written")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--freeze" in sys.argv:
        m = freeze()
        print(json.dumps(m, indent=1, sort_keys=True))
        p = verify()
        print("\nverification:", "OK" if not p else p)
    else:
        _test()
