"""The human approval record for benchmark pairs.

Kept as data in `corpus/benchmark/entailment_reviews.json`, not as edits to the
fixture definitions, for three reasons: an approval can be revoked without
touching the claim it approved; the reviewer's identity and timestamp are visible
in one place rather than scattered through source; and a diff of who approved
what is readable by someone who does not read Python.

A pair with no entry is unapproved. Absence is never approval.

Reviewers are recorded by **pseudonymous ID** (`reviewer-01`), not by email. The
benchmark files are meant to be distributable, and a reviewer's address is not
part of the evidence that a claim was reviewed — only that an identified person
reviewed it and can be traced through a local map. `.reviewer_identities.json`
holds that map and is gitignored.
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
    if "@" in reviewer:
        raise ValueError(
            "record a pseudonymous reviewer ID, not an email address; the "
            "identity map in .reviewer_identities.json stays local")
    data = load(path)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for pid in pair_ids:
        prior = data.get(pid)
        entry = {"status": status, "reviewer": reviewer,
                 "reviewed_at": stamp, "note": note}
        if prior:
            # A decision that replaces another does not erase it. Retracting an
            # approval is exactly the case where someone later needs to see that
            # the pair WAS approved, by whom, and when — writing the new status
            # over the old left no trace of the thing being undone.
            history = list(prior.pop("history", []))
            history.append(prior)
            entry["history"] = history
        data[pid] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return data


def status_of(pair_id: str, path: Path = REVIEWS) -> tuple[str, str | None, str | None]:
    e = load(path).get(pair_id)
    if not e:
        return PENDING, None, None
    return e["status"], e.get("reviewer"), e.get("reviewed_at")


def history_of(pair_id: str, path: Path = REVIEWS) -> list[dict]:
    """Every superseded decision on this pair, oldest first."""
    return list(load(path).get(pair_id, {}).get("history", []))


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
        try:
            record(["a0"], reviewer="someone@example.com", path=p)
            check(False, "an email address is refused as a reviewer id")
        except ValueError:
            check(True, "an email address is refused as a reviewer id")
        record(["a1"], reviewer="reviewer-01", path=p)
        st, who, when = status_of("a1", p)
        check(st == APPROVED and who == "reviewer-01" and when,
              "an approval records status, reviewer and timestamp")
        try:
            record(["a2"], reviewer="reviewer-02", status=REJECTED, path=p)
            check(False, "a rejection without a reason is refused")
        except ValueError:
            check(True, "a rejection without a reason is refused")
        try:
            record(["a3"], reviewer="  ", path=p)
            check(False, "an unnamed reviewer is refused")
        except ValueError:
            check(True, "an unnamed reviewer is refused")
        record(["a1"], reviewer="reviewer-02", status=REJECTED, note="wrong", path=p)
        check(status_of("a1", p)[0] == REJECTED, "a decision can be revoked")
    # A replaced decision is kept, not overwritten.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "hist.json"
        record(["h"], reviewer="reviewer-01", status=APPROVED, path=hp)
        first = load(hp)["h"]["reviewed_at"]
        record(["h"], reviewer="reviewer-01", status=REJECTED,
               note="retracted", path=hp)
        e = load(hp)["h"]
        check(e["status"] == REJECTED, "the current status is the new one")
        hist = history_of("h", hp)
        check(len(hist) == 1 and hist[0]["status"] == APPROVED,
              f"the superseded approval is kept ({[x['status'] for x in hist]})")
        check(hist[0]["reviewed_at"] == first,
              "...with its original timestamp, not restamped")
        check("history" not in hist[0],
              "history does not nest inside itself")
        record(["h"], reviewer="reviewer-01", status=APPROVED, path=hp)
        check([x["status"] for x in history_of("h", hp)] == [APPROVED, REJECTED],
              "each further decision appends, oldest first")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
