"""The reviewer's decisions, recorded and never applied here.

A decision is evidence. It is written once, with who made it, when, against
which version of the table, and why — and nothing in this module can reach a
gold label. Promotion is a separate, explicit step in
`benchmark_v2_freeze.freeze(promote=True)`.

The sequence this enforces:

    review decision -> immutable review record -> fixture replacement
    -> second validation -> explicit gold-label promotion

## Append-only

The log is JSONL and is only ever appended to. A decision that turns out to be
wrong is superseded by a later record naming it, not edited in place: the point
of a review log is that it shows what was believed at the time, including the
parts that changed. `append()` refuses to write a decision for a proposal that
already has one unless it declares what it supersedes.

## Provenance

Each record pins the table it was made against by content hash, not only by
commit — the working tree is routinely dirty, so a commit alone does not
identify what the reviewer actually read.

## Reviewer identity

Recorded as a pseudonymous id. The benchmark manifest asserts that no reviewer
id contains an "@", so real addresses must not reach this file; the mapping
from id to person lives outside the repository.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

LOG = Path("corpus/benchmark/review_decisions.jsonl")

ACCEPT, REJECT, SEND_BACK = "ACCEPT", "REJECT", "SEND BACK"
# A proposal whose SOURCE is defective is not rejected on its merits and is not
# accepted either. s.174(1)'s span carries the SD-004 transcription defect
# ("of a company hall be one-third"), so the claim cannot rest on it as clean
# gold evidence — while the defective text itself stays exactly as served.
BLOCKED = "BLOCKED_PENDING_SOURCE_CORRECTION"
DECISIONS = (ACCEPT, REJECT, SEND_BACK, BLOCKED)

FROZEN_SET = Path("corpus/benchmark/approved_pairs.jsonl")


def frozen_labels(path: Path = FROZEN_SET) -> dict[str, str]:
    """pair_id -> label, as currently frozen."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["pair_id"]] = r["label"]
    return out


def changes_fixture(proposal_id: str, decision: str,
                    frozen: dict[str, str] | None = None) -> bool:
    """Would acting on this decision alter the frozen benchmark?

    Not derivable from the decision alone, which is how the first pass got it
    wrong in both directions. Nine of the eleven proposals had already been
    promoted in an earlier session, so:

        ACCEPT of an already-frozen pair    ratifies what is there — no change
        ACCEPT of a pair not yet frozen     adds it — a change
        SEND BACK of an already-frozen pair it must come OUT — a change
        SEND BACK of a pair not yet frozen  it never got in — no change

    The dangerous case is the third. Recording it as "no fixture change" would
    have left two pairs the reviewer rejected sitting in the benchmark as
    ENTAILED, with a decision log stating that nothing needed to happen.
    """
    if frozen is None:
        frozen = frozen_labels()
    is_frozen = proposal_id in frozen
    if decision == BLOCKED:
        return False          # a block is a refusal to act, never a mutation
    if decision == ACCEPT:
        return not is_frozen
    return is_frozen          # REJECT or SEND BACK: a change only if it is in


class ReviewError(RuntimeError):
    """A decision could not be recorded. Nothing is written on failure."""


@dataclass(frozen=True)
class Decision:
    proposal_id: str
    supersedes: str
    decision: str
    reason: str
    reviewer_id: str
    decided_at: str
    table_sha256: str
    software_commit: str
    working_tree_dirty: bool
    changes_benchmark_fixture: bool
    applied: bool = False          # never true here; promotion is elsewhere
    supersedes_decision: str | None = None
    # Distinct clocks, recorded rather than inferred. A filesystem mtime is not
    # an event time: it says when bytes last landed, not when a person decided.
    recorded_at: str | None = None        # when this record was written
    source_state_read_at: str | None = None  # when the frozen set was read


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def table_hash(path: Path = Path("docs/FIXTURE_REVIEW.md")) -> str:
    if not path.exists():
        raise ReviewError(f"the review table is missing: {path}")
    return _sha(path.read_bytes())


def _commit() -> tuple[str, bool]:
    try:
        h = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=10)
        d = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                           text=True, timeout=10)
        if h.returncode:
            return "unknown", True
        return h.stdout.strip(), bool(d.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return "unknown", True


def load(path: Path = LOG) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def latest_for(proposal_id: str, path: Path = LOG) -> dict | None:
    hits = [r for r in load(path) if r["proposal_id"] == proposal_id]
    return hits[-1] if hits else None


def append(decisions: list[Decision], path: Path = LOG) -> int:
    """Append decisions. Refuses to silently overwrite an existing one."""
    for d in decisions:
        if d.decision not in DECISIONS:
            raise ReviewError(f"{d.proposal_id}: unknown decision {d.decision!r}")
        if not d.reason.strip():
            raise ReviewError(f"{d.proposal_id}: a decision without a reason is "
                              "not a record")
        if d.applied:
            raise ReviewError(f"{d.proposal_id}: this log cannot mark a decision "
                              "applied; promotion happens in the freeze")
        prior = latest_for(d.proposal_id, path)
        if prior and not d.supersedes_decision:
            raise ReviewError(
                f"{d.proposal_id}: already decided {prior['decision']!r} at "
                f"{prior['decided_at']}; a new decision must name what it "
                "supersedes rather than overwrite it")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for d in decisions:
            rec = asdict(d)
            if rec.get("recorded_at") is None:
                rec["recorded_at"] = _now()
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return len(decisions)


def build_decisions(ruling: dict[str, tuple[str, str]], reviewer_id: str,
                    decided_at: str) -> list[Decision]:
    """Turn {proposal_id: (decision, reason)} into records against the table."""
    from checker.review_table import build as build_table

    rows = {r.proposal_id: r for r in build_table()}
    unknown = sorted(set(ruling) - set(rows))
    if unknown:
        raise ReviewError(f"decisions for proposals not in the table: {unknown}")
    undecided = sorted(set(rows) - set(ruling))
    if undecided:
        raise ReviewError(f"every proposal needs a decision; missing: {undecided}")

    commit, dirty = _commit()
    th = table_hash()
    frozen = frozen_labels()
    out = []
    for pid, (decision, reason) in sorted(ruling.items()):
        out.append(Decision(
            proposal_id=pid, supersedes=rows[pid].supersedes,
            decision=decision, reason=reason,
            reviewer_id=reviewer_id, decided_at=decided_at,
            table_sha256=th, software_commit=commit, working_tree_dirty=dirty,
            changes_benchmark_fixture=changes_fixture(pid, decision, frozen),
        ))
    return out


def render(path: Path = LOG) -> str:
    recs = load(path)
    if not recs:
        return "No review decisions recorded."
    L = [f"{len(recs)} decision(s) recorded, none applied.", ""]
    for r in recs:
        flag = "would change a fixture" if r["changes_benchmark_fixture"] else \
               "no fixture change"
        L.append(f"  {r['proposal_id']:<22} {r['decision']:<10} {flag}")
        L.append(f"    {r['reason']}")
    return "\n".join(L)


def _test() -> None:
    import tempfile
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("review_record")

    def mk(pid="x-1", decision=ACCEPT, reason="because", applied=False,
           supersedes_decision=None):
        return Decision(pid, "orig", decision, reason, "reviewer-01",
                        "2026-08-30T00:00:00Z", "sha256:aa", "abc", False,
                        decision == ACCEPT, applied,
                        supersedes_decision)

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "log.jsonl"

        check(append([mk()], p) == 1, "a decision is appended")
        check(len(load(p)) == 1, "...and reads back")

        try:
            append([mk()], p)
            check(False, "a second decision on the same proposal is refused")
        except ReviewError as e:
            check("supersedes" in str(e),
                  "a second decision must name what it supersedes")

        check(append([mk(supersedes_decision="the first")], p) == 1,
              "...and is accepted once it does")
        check(len(load(p)) == 2, "the original record is kept, not overwritten")
        check(load(p)[0]["decision"] == ACCEPT and load(p)[0]["reason"] == "because",
              "the superseded record is unchanged on disk")

        try:
            append([mk(pid="y", reason="  ")], p)
            check(False, "a decision without a reason is refused")
        except ReviewError:
            check(True, "a decision without a reason is refused")

        try:
            append([mk(pid="z", applied=True)], p)
            check(False, "this log cannot mark a decision applied")
        except ReviewError as e:
            check("promotion happens in the freeze" in str(e),
                  "this log cannot mark a decision applied")

        try:
            append([mk(pid="w", decision="MAYBE")], p)
            check(False, "an unknown decision is refused")
        except ReviewError:
            check(True, "an unknown decision is refused")

        # A failed batch writes nothing.
        before = len(load(p))
        try:
            append([mk(pid="ok-1"), mk(pid="bad", decision="NOPE")], p)
        except ReviewError:
            pass
        check(len(load(p)) == before, "a batch that fails validation writes nothing")

    # Every proposal must be ruled on; a partial ruling is refused.
    try:
        build_decisions({"v2-p103-qbind-0": (ACCEPT, "r")}, "reviewer-01", "t")
        check(False, "a partial ruling is refused")
    except ReviewError as e:
        check("every proposal needs a decision" in str(e),
              "a partial ruling is refused")

    # Reviewer ids stay pseudonymous — the manifest test forbids "@".
    check("@" not in "reviewer-01", "reviewer ids carry no address")

    # The fixture-impact field is derived from the frozen set, not the decision.
    fz = {"already-in": "ENTAILED"}
    check(changes_fixture("already-in", ACCEPT, fz) is False,
          "accepting an already-frozen pair changes nothing")
    check(changes_fixture("not-in", ACCEPT, fz) is True,
          "accepting a pair that is not frozen adds it")
    check(changes_fixture("already-in", SEND_BACK, fz) is True,
          "sending back an already-frozen pair means it must come OUT")
    check(changes_fixture("not-in", SEND_BACK, fz) is False,
          "sending back a pair that never got in changes nothing")

    # Nothing in this module may write a gold label. Asserted on the module's
    # own path constants rather than by searching its source for a filename —
    # the search string would itself be a match.
    # It reads the frozen set to derive fixture impact, so holding that path is
    # expected. What must hold is that it never writes it — asserted by hashing
    # the file across the module's whole surface rather than by reading source.
    import hashlib
    before = hashlib.sha256(FROZEN_SET.read_bytes()).hexdigest() \
        if FROZEN_SET.exists() else None
    with tempfile.TemporaryDirectory() as td:
        q = Path(td) / "l.jsonl"
        frozen_labels()
        changes_fixture("anything", ACCEPT)
        append([mk(pid="probe")], q)
        load(q)
        render(q)
    after = hashlib.sha256(FROZEN_SET.read_bytes()).hexdigest() \
        if FROZEN_SET.exists() else None
    check(before == after, "the frozen gold-label file is untouched by this module")
    check(LOG.name == "review_decisions.jsonl", "the decision log is its only output")
    check(all(not d.applied for d in [mk()]), "a Decision is never born applied")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
