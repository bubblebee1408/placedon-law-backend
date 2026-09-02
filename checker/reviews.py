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

# How a recorded label got there. The distinction is the whole point of F4.
STATED = "STATED_BY_REVIEWER"          # the reviewer said what the label is
INFERRED = "INFERRED_FROM_APPROVAL"    # migrated: they approved a proposed label
LABEL_SOURCES = (STATED, INFERRED)


def load(path: Path = REVIEWS) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def record(pair_ids: list[str], *, reviewer: str, status: str = APPROVED,
           note: str = "", label: str | None = None,
           proposed_label: str | None = None,
           path: Path = REVIEWS) -> dict[str, dict]:
    """Write a decision. A rejection requires a reason; an approval does not.

    The asymmetry is deliberate and matches checker/review_queue.py: approving
    is the default outcome of a careful read, whereas restricting or rejecting
    is a judgement someone will later need explained.

    `label` is the reviewer's own legal judgement and is separate from `status`.
    Before F4 there was no such field: a reviewer recorded APPROVAL, approval was
    compiled to ENTAILED, and there was no code path by which a human-judged pair
    could ever carry NOT_ENTAILED. The paraphrase bucket's blindness to false
    accepts was therefore permanent by construction — more review could not fix
    it, because every additional human-judged pair the pipeline could produce was
    another positive.

    So the reviewer's question changes from "approve this proposed positive?" to
    "is this claim entailed by this span, yes or no?". `proposed_label` records
    what they were shown, so a reviewer who disagreed with the proposal is
    visible rather than merely absent.
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
        if label is not None:
            entry["label"] = label
            entry["label_source"] = STATED
        if proposed_label is not None:
            entry["proposed_label"] = proposed_label
            entry["reviewer_disagreed"] = (label is not None
                                           and label != proposed_label)
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


def label_of(pair_id: str, path: Path = REVIEWS) -> tuple[str | None, str | None]:
    """(the reviewer's label, how it got there). (None, None) if unrecorded.

    A caller must not fall back to a default when this returns None. An
    unrecorded label means nobody judged it, which is different from a judgement
    that happens to be positive.
    """
    e = load(path).get(pair_id)
    if not e or "label" not in e:
        return None, None
    return e["label"], e.get("label_source", INFERRED)


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

    # ── F4: a reviewer records a LABEL, not an approval ─────────────────────
    with tempfile.TemporaryDirectory() as td:
        fp = Path(td) / "f4.json"

        # The property that was structurally impossible before this repair.
        record(["neg"], reviewer="reviewer-01", status=APPROVED,
               label="NOT_ENTAILED", proposed_label="ENTAILED",
               note="the claim drops the proviso", path=fp)
        lab, src = label_of("neg", fp)
        check(lab == "NOT_ENTAILED",
              f"an APPROVED review can now carry NOT_ENTAILED ({lab})")
        check(src == STATED, f"...recorded as stated, not inferred ({src})")
        check(load(fp)["neg"]["reviewer_disagreed"] is True,
              "a reviewer who disagreed with the proposal is visible")

        # Agreement is visible too, and is not the same as silence.
        record(["pos"], reviewer="reviewer-01", status=APPROVED,
               label="ENTAILED", proposed_label="ENTAILED", path=fp)
        check(load(fp)["pos"]["reviewer_disagreed"] is False,
              "agreement is recorded as agreement")

        # Silence is neither.
        record(["quiet"], reviewer="reviewer-01", status=APPROVED, path=fp)
        check(label_of("quiet", fp) == (None, None),
              "an approval with no label yields no label, and no default")

        check(len({label_of(p, fp)[0] for p in ("neg", "pos")}) == 2,
              "the store can hold both classes from human review")

    # The migrated records must not masquerade as stated judgements.
    real = load()
    migrated = [k for k, v in real.items() if v.get("label_source") == INFERRED]
    check(bool(migrated), f"the pre-F4 records are marked inferred ({len(migrated)})")
    check(all("migration_note" in real[k] for k in migrated),
          "...each carrying why it is not an independent judgement")
    check(not any(v.get("label_source") == STATED for v in real.values()),
          "no pre-F4 record claims to be a stated label")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
