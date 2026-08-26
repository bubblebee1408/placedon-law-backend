"""The human approval record for benchmark pairs.

Kept as data in `corpus/benchmark/entailment_reviews.json`, not as edits to the
fixture definitions, for three reasons: an approval can be revoked without
touching the claim it approved; the reviewer's identity and timestamp are visible
in one place rather than scattered through source; and a diff of who approved
what is readable by someone who does not read Python.

A pair with no entry is unapproved. Absence is never approval.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REVIEWS = Path("corpus/benchmark/entailment_reviews.json")

APPROVED = "APPROVED"
REJECTED = "REJECTED"
PENDING = "PENDING_REVIEW"


def load(path: Path = REVIEWS) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def record(pair_ids: list[str], *, reviewer: str, status: str = APPROVED,
           note: str = "", path: Path = REVIEWS) -> dict[str, dict]:
    """Write a decision. A rejection requires a reason; an approval does not.

    The asymmetry is deliberate and matches checker/review_queue.py: approving
    is the default outcome of a careful read, whereas restricting or rejecting
    is a judgement someone will later need explained.
    """
    if status == REJECTED and not note.strip():
        raise ValueError("a rejection requires a written reason")
    if not reviewer.strip():
        raise ValueError("a decision requires a named reviewer")
    data = load(path)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for pid in pair_ids:
        data[pid] = {"status": status, "reviewer": reviewer,
                     "reviewed_at": stamp, "note": note}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return data


def status_of(pair_id: str, path: Path = REVIEWS) -> tuple[str, str | None, str | None]:
    e = load(path).get(pair_id)
    if not e:
        return PENDING, None, None
    return e["status"], e.get("reviewer"), e.get("reviewed_at")


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

    print("reviews")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.json"
        check(status_of("nope", p)[0] == PENDING,
              "an unrecorded pair is PENDING — absence is never approval")
        record(["a1"], reviewer="someone@example.com", path=p)
        st, who, when = status_of("a1", p)
        check(st == APPROVED and who == "someone@example.com" and when,
              "an approval records status, reviewer and timestamp")
        try:
            record(["a2"], reviewer="x@y.z", status=REJECTED, path=p)
            check(False, "a rejection without a reason is refused")
        except ValueError:
            check(True, "a rejection without a reason is refused")
        try:
            record(["a3"], reviewer="  ", path=p)
            check(False, "an unnamed reviewer is refused")
        except ValueError:
            check(True, "an unnamed reviewer is refused")
        record(["a1"], reviewer="x@y.z", status=REJECTED, note="wrong", path=p)
        check(status_of("a1", p)[0] == REJECTED, "a decision can be revoked")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
