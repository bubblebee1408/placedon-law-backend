"""Apply exactly the pairs a reviewer named, and nothing else.

`freeze(promote=True)` regenerates the benchmark from code state, so it cannot
express "remove these two". It expresses "make the file match the code", and
those are different operations: an authorisation to retract two pairs was
executed as four removals, because two unrelated pairs had drifted out of
eligibility when a qualifier inventory was corrected.

This module never regenerates. It reads the records on disk, drops the ones in
scope, and writes every other record back **byte-identically**. A change nobody
authorised cannot ride along, because nothing outside the scope is rewritten.

## The divergence this creates, and why it is recorded

After a scoped retraction the frozen file may knowingly disagree with what the
current code would produce — two s.174 pairs remain frozen that the corrected
inventory now treats as INVALID_FIXTURE. That is the point: the reviewer chose
not to apply that change yet. But a silent divergence becomes an unexplained one
within a week, so it is written to `deferred_drift.json` with what it is and why
it was deferred. `label_drift()` continues to report it, and the freeze
continues to refuse until someone decides.

## Nothing is deleted

The approval is superseded in the review store, which keeps the prior decision
in its history. If a retraction only removed lines from the frozen file, the
store would still say APPROVED and the next promotion would put the pairs back.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

DIR = Path("corpus/benchmark")
FROZEN = DIR / "approved_pairs.jsonl"
MANIFEST = DIR / "manifest.json"
REVIEWS = DIR / "entailment_reviews.json"
DEFERRED = DIR / "deferred_drift.json"

# Restored on rollback. Every file a scoped retraction can touch.
_TOUCHED = (str(FROZEN), str(MANIFEST), str(REVIEWS))


class RetractionError(RuntimeError):
    """The retraction did not match its authorisation. Nothing was left changed."""


@dataclass
class Plan:
    scope: list[str]
    in_scope_removals: list[dict] = field(default_factory=list)
    deferred: list[dict] = field(default_factory=list)
    count_before: int = 0
    count_after: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _records() -> list[dict]:
    return [json.loads(l) for l in FROZEN.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def plan(scope: list[str]) -> Plan:
    """What a scoped retraction would do, and what it would deliberately defer."""
    from checker.benchmark_v2_freeze import label_drift

    recs = _records()
    by_id = {r["pair_id"]: r for r in recs}
    p = Plan(scope=sorted(scope), count_before=len(recs))

    missing = [s for s in scope if s not in by_id]
    if missing:
        p.problems.append(f"not in the frozen set, so nothing to retract: {missing}")

    p.in_scope_removals = [
        {"pair_id": s, "label": by_id[s]["label"], "claim": by_id[s]["claim"]}
        for s in sorted(scope) if s in by_id]
    p.count_after = p.count_before - len(p.in_scope_removals)

    # Everything the freeze would also do, which this operation will not.
    drift = label_drift()
    for pid, lab in drift["removed"]:
        if pid not in scope:
            p.deferred.append({"pair_id": pid, "current_label": lab,
                               "would_become": "excluded (INVALID_FIXTURE)",
                               "deferred_because": "outside the authorised scope"})
    for pid in drift["added"]:
        if pid not in scope:
            p.deferred.append({"pair_id": pid, "current_label": None,
                               "would_become": "added",
                               "deferred_because": "outside the authorised scope"})
    for pid, old, new in drift["relabelled"]:
        if pid not in scope:
            p.deferred.append({"pair_id": pid, "current_label": old,
                               "would_become": new,
                               "deferred_because": "outside the authorised scope"})
    return p


def _rollback() -> None:
    subprocess.run(["git", "checkout", "HEAD", "--", *_TOUCHED], check=True)


def apply(scope: list[str], *, reviewer: str, reason: str,
          expected_after: int) -> dict:
    """Retract exactly `scope`. Verifies afterwards and rolls back on mismatch."""
    from checker.benchmark_v2_freeze import write_manifest
    from checker.reviews import record, REJECTED

    pl = plan(scope)
    if not pl.ok:
        raise RetractionError("; ".join(pl.problems))
    if pl.count_after != expected_after:
        raise RetractionError(
            f"scope yields {pl.count_after}, authorisation expects {expected_after}")

    before = _records()
    before_sha = _sha(FROZEN.read_bytes())
    scope_set = set(scope)

    # 1. Supersede the approval at its source, so the pairs do not return.
    record(sorted(scope_set), reviewer=reviewer, status=REJECTED, note=reason)

    # 2. Rewrite, preserving every out-of-scope record byte for byte. The lines
    #    are re-serialised from the objects they were parsed from, with the same
    #    sort and separators freeze() uses, so an untouched record's bytes are
    #    unchanged — asserted by the test, not assumed.
    kept = [r for r in before if r["pair_id"] not in scope_set]
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                   for r in kept)
    FROZEN.write_text(body, encoding="utf-8")

    try:
        man = json.loads(MANIFEST.read_text())
        write_manifest(kept, man.get("invalid_fixture_count", 0),
                       man.get("pending_review_count", 0),
                       man.get("rejected_count", 0))

        after = _records()
        removed = sorted({r["pair_id"] for r in before} - {r["pair_id"] for r in after})
        added = sorted({r["pair_id"] for r in after} - {r["pair_id"] for r in before})
        problems = []
        if removed != sorted(scope_set):
            problems.append(f"removed {removed}, authorised {sorted(scope_set)}")
        if added:
            problems.append(f"added {added}; a retraction adds nothing")
        if len(after) != expected_after:
            problems.append(f"count {len(after)}, authorised {expected_after}")

        # Every surviving record must be untouched, field for field.
        before_by = {r["pair_id"]: r for r in before}
        changed = [r["pair_id"] for r in after if before_by[r["pair_id"]] != r]
        if changed:
            problems.append(f"out-of-scope records were modified: {changed}")

        if problems:
            raise RetractionError("; ".join(problems))
    except Exception:
        _rollback()
        raise

    # 3. Record what was deliberately not applied.
    DEFERRED.write_text(json.dumps({
        "deferred": pl.deferred,
        "note": ("These changes are pending and were NOT applied. The frozen set "
                 "knowingly diverges from what the current code would produce; "
                 "label_drift() will keep reporting them and freeze() will keep "
                 "refusing until a reviewer decides."),
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    return {"removed": removed, "added": added,
            "count_before": len(before), "count_after": len(after),
            "deferred": pl.deferred,
            "approved_pairs_sha256_before": before_sha,
            "approved_pairs_sha256_after": _sha(FROZEN.read_bytes()),
            "manifest_sha256_after": _sha(MANIFEST.read_bytes())}


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

    print("scoped_retraction")
    before_bytes = FROZEN.read_bytes()

    # Scope is chosen from whatever is frozen right now, not hardcoded. A test
    # that named specific pair ids failed the moment a legitimate retraction
    # removed them — which pressures the next person to revert a correct change
    # to make the suite green. The mechanism is what is under test, not the
    # contents of the benchmark on any given day.
    from checker.benchmark_v2_freeze import label_drift
    drifting = {pid for pid, _ in label_drift()["removed"]}
    frozen_now = [r["pair_id"] for r in _records()]
    # Prefer pairs that carry a prior review entry, so the history-preservation
    # path is actually exercised. A constructed negative has no approval to
    # supersede, and picking one would leave that behaviour untested.
    from checker.reviews import load as load_reviews
    reviewed = set(load_reviews())
    eligible_ids = [p for p in frozen_now if p not in drifting]
    scope = ([p for p in eligible_ids if p in reviewed]
             + [p for p in eligible_ids if p not in reviewed])[:2]
    check(len(scope) == 2, f"two retractable pairs exist to test with ({scope})")
    # Drift is transient: it exists between a code correction and the freeze
    # that promotes it, and is empty the rest of the time. An earlier version
    # asserted drift EXISTS, which turned a resolved benchmark into a red suite.
    # What must hold is the deferral property, whichever state we are in.
    check(isinstance(drifting, set),
          f"pending drift is enumerable ({len(drifting)} pair(s) today)")

    pl = plan(scope)
    n = len(frozen_now)
    check(pl.ok, f"the plan is clean ({pl.problems})")
    check(pl.count_before == n, f"before matches disk ({pl.count_before})")
    check(pl.count_after == n - 2, f"after: exactly the scope ({pl.count_after})")
    check([r["pair_id"] for r in pl.in_scope_removals] == sorted(scope),
          "only the scoped pairs are removed")

    # The whole point: the drift the freeze would apply is deferred, not applied.
    deferred_ids = sorted(d["pair_id"] for d in pl.deferred)
    check(deferred_ids == sorted(drifting),
          f"every pending drift is deferred, not swept along "
          f"({deferred_ids or 'none pending'})")
    check(not (set(deferred_ids) & set(scope)),
          "nothing is both retracted and deferred")
    check(all(d["deferred_because"] for d in pl.deferred),
          "each deferral says why")

    # A pair that is not frozen cannot be retracted.
    bad = plan(["v2-does-not-exist"])
    check(not bad.ok and "nothing to retract" in bad.problems[0],
          "retracting a pair that is not frozen is refused")

    # A scope whose arithmetic disagrees with the authorisation is refused.
    try:
        apply(scope, reviewer="reviewer-01", reason="r", expected_after=n - 4)
        check(False, "a count mismatch is refused before writing")
    except RetractionError as e:
        check("authorisation expects" in str(e),
              "a count mismatch is refused before writing")
    check(FROZEN.read_bytes() == before_bytes,
          "...and nothing was written")

    # Serialisation must be byte-stable: re-serialising every record unchanged
    # must reproduce the file exactly, or "byte-identical" is a false claim.
    recs = _records()
    rebuilt = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                      for r in recs).encode("utf-8")
    check(rebuilt == before_bytes,
          "re-serialising every record reproduces the file byte for byte")

    # End-to-end: perform a real scoped retraction, verify it, then restore.
    # A mechanism whose write path is never exercised is not a verified
    # mechanism, and this is the operation that previously went wrong.
    import shutil, tempfile
    with tempfile.TemporaryDirectory() as td:
        keep = {f: shutil.copy2(f, Path(td) / Path(f).name) for f in _TOUCHED}
        deferred_existed = DEFERRED.exists()
        try:
            res = apply(scope, reviewer="reviewer-01",
                        reason="end-to-end verification of the scoped mechanism",
                        expected_after=n - 2)
            after = _records()
            check(len(after) == n - 2,
                  f"the write produced {n - 2} pairs ({len(after)})")
            check(res["removed"] == sorted(scope),
                  f"exactly the scope was removed ({res['removed']})")
            check(not res["added"], "nothing was added")
            check(all(p not in {r['pair_id'] for r in after} for p in scope),
                  "the scoped pairs are gone from the frozen set")
            check(drifting <= {r["pair_id"] for r in after},
                  "every deferred pair is STILL frozen — not swept along")

            # Out-of-scope records must be byte-identical to before.
            before_by = {r["pair_id"]: r for r in json.loads("[" + ",".join(
                Path(keep[str(FROZEN)]).read_text().splitlines()) + "]")}
            check(all(before_by[r["pair_id"]] == r for r in after),
                  "every surviving record is unchanged field for field")

            man = json.loads(MANIFEST.read_text())
            check(man["pair_count"] == n - 2,
                  f"the manifest was rebuilt to match ({man['pair_count']})")
            from checker.benchmark_v2_freeze import verify
            check(verify() == [], f"the manifest verifies against disk ({verify()[:2]})")

            from checker.reviews import status_of, history_of
            st, _, _ = status_of(scope[0])
            check(st == "REJECTED", f"the approval was superseded at source ({st})")
            had_prior = [s for s in scope if s in reviewed]
            check(bool(had_prior), f"the scope exercises the history path ({had_prior})")
            check(all(history_of(s) for s in had_prior),
                  "...and every prior decision is preserved in its history")
            check(DEFERRED.exists(), "the deferred drift was recorded")
        finally:
            for dest, src in keep.items():
                shutil.copy2(src, dest)
            if not deferred_existed:
                DEFERRED.unlink(missing_ok=True)

    check(FROZEN.read_bytes() == before_bytes,
          "the whole test left the frozen set untouched")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
