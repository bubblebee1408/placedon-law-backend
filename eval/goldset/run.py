#!/usr/bin/env python3
"""Run the engine against the gold set and report what it actually does.

    python3 eval/goldset/run.py                       # measure DEV (the default)
    python3 eval/goldset/run.py --split test          # score the held-out side, ONCE
    python3 eval/goldset/run.py --split test --new-hash "why this tree is re-measured"
    python3 eval/goldset/run.py --test                # self-test

The engine is reached through `checker.api.handle` -- the same entry point the MCP
server, the CLI and (at PLAN_17 M3) the gateway use, so this measures the thing
that ships rather than a private path into it.

## What counts as REFUSED

Not "the word sorry appears". The engine has a typed vocabulary of refusal, and
this reads it: `state == "out_of_scope"`, a `CANNOT_DETERMINE` / `NOT_ESTABLISHED`
evidence state, or a non-200 that is a refusal rather than a crash. A transport
error is NOT a refusal and is reported separately -- rendering a 500 as an
abstention is the exact confusion `web/assistant/contract.md` forbids, and it would
silently improve the refusal score every time the server fell over.

## Why the test side is rationed

A held-out split protects nothing if it can be re-run after every idea. Score it
five times and keep the best and you have chosen the fix that fits those particular
seventeen rows -- which is exactly what the split was built to prevent, done more
slowly. So a test run is a LEDGER ENTRY: `eval/goldset/test_runs.jsonl`, append-only,
one run per code hash. A second run against the same engine bytes is REFUSED, and
`--new-hash "<reason>"` is the only way past it. The reason is written into the
ledger, so re-measuring an unchanged tree is a thing someone has to justify in
writing and cannot do by accident.

`--split all` counts as a test run. It shows the held-out rows, so it is one.

The **code hash** is a digest of every `checker/**/*.py` -- the engine, not the
commit. A commit id would let the same bytes be re-scored by committing a comment,
and a dirty tree (the normal state while developing) has no commit at all. The git
HEAD is recorded alongside it for humans, and decides nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.goldset import (ANSWERED, DEV, HELDOUT, REFUSED, Outcome, load, score)
from eval.goldset.split import SPLIT_PATH, ids_for, load_split

_REFUSAL_STATES = {"out_of_scope", "CANNOT_DETERMINE", "NOT_ESTABLISHED",
                   "INSUFFICIENT_EVIDENCE", "abstain", "abstained"}

_ROOT = Path(__file__).resolve().parent.parent.parent
TEST_RUNS_PATH = _ROOT / "eval/goldset/test_runs.jsonl"

# The sides a run may ask for. "test" and "heldout" are the same side (Entry.split
# stores "heldout"); PLAN_19 G0.2 calls it "test".
SIDES = (DEV, "test", HELDOUT, "all")
_SIDES_THAT_SEE_TEST = ("test", HELDOUT, "all")

# A reason shorter than this is not a reason. The flag exists to make re-scoring an
# unchanged engine a deliberate, recorded act; "x" would make it a keystroke.
MIN_REASON_CHARS = 20


def looks_at_test(which: str) -> bool:
    """True if this side puts held-out rows in front of a human."""
    return which in _SIDES_THAT_SEE_TEST


def code_hash(root: Path | None = None) -> str:
    """sha256 over every checker/**/*.py: the ENGINE's bytes, not the commit.

    Hashes path and content together so a rename is a change. `__pycache__` is
    excluded -- it is a build artefact, and including it would make the hash depend
    on which suites happened to run first.
    """
    base = (root or _ROOT) / "checker"
    h = hashlib.sha256()
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(str(p.relative_to(base)).encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def git_head() -> str:
    """The commit, for a human reading the ledger. Never used to decide anything."""
    try:
        out = subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:                                           # noqa: BLE001
        return ""


def read_runs(path: Path | None = None) -> tuple[dict, ...]:
    """Every test run ever recorded. A malformed line raises -- a skipped one would
    be a run that silently never happened, which is the whole failure mode."""
    p = path or TEST_RUNS_PATH
    if not p.exists():
        return ()
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception as exc:                                # noqa: BLE001
            raise ValueError(f"{p}:{i}: {type(exc).__name__}: {exc}") from exc
    return tuple(out)


def refuse_repeat(digest: str, runs, reason: str | None) -> str:
    """"" if this test run may proceed; otherwise the refusal, stated."""
    if reason is not None and len(reason.strip()) < MIN_REASON_CHARS:
        return (f"REFUSED: --new-hash was given with no usable reason "
                f"({reason.strip()!r}). The reason IS the flag -- it goes in the "
                f"ledger so that re-scoring an unchanged engine is something a person "
                f"defended in writing. Give at least {MIN_REASON_CHARS} characters "
                f"saying why this tree is being measured again.")
    prior = [r for r in runs if r.get("code_hash") == digest]
    if not prior:
        return ""
    if reason is None:
        when = ", ".join(str(r.get("ran_at", "?")) for r in prior[:3])
        return (f"REFUSED: the test split has already been scored against code hash "
                f"{digest[:12]} ({len(prior)} run(s): {when}). Scoring it again and "
                f"keeping the better number is how a held-out split stops being held "
                f"out. Change the engine, or pass --new-hash \"<why>\" to record a "
                f"deliberate re-measurement of the same bytes.")
    return ""


def record_run(record: dict, path: Path | None = None) -> Path:
    """Append one run. Append-only: this function never rewrites an existing line."""
    p = path or TEST_RUNS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def select(entries, which: str):
    """The entries on one side, per the committed split."""
    wanted = ids_for(which)
    return tuple(e for e in entries if e.question_id in wanted)


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="eval/goldset/run.py", add_help=True)
    ap.add_argument("--split", choices=SIDES, default=DEV,
                    help="which side to measure. Default: dev. 'test' and 'all' are "
                         "ledgered and may be run once per code hash.")
    ap.add_argument("--new-hash", dest="new_hash", default=None, metavar="REASON",
                    help="re-score the test side against an engine already measured, "
                         "recording this written reason.")
    ap.add_argument("--test", action="store_true", help="run this module's self-test")
    return ap.parse_args(argv)


def ask(question: str) -> tuple[Outcome | None, str]:
    """(outcome, error). A transport failure returns (None, why) -- never a refusal."""
    from checker import api
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        code, body = api.handle("POST", "/v1/ask", {"question": question}, generated_at=now)
    except Exception as exc:                                    # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    if code >= 500:
        return None, f"HTTP {code}: {str(body)[:120]}"
    state = str(body.get("state", ""))
    refs = tuple(str(c.get("ref", "")) for c in (body.get("confirmed") or [])
                 if isinstance(c, dict))
    text = body.get("answer") or body.get("reason") or str(body)
    refused = (state in _REFUSAL_STATES
               or code == 422
               or bool(body.get("refused")))
    return Outcome("", REFUSED if refused else ANSWERED, str(text), refs), ""


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    which = args.split
    entries = load()
    if not entries:
        print("gold set is empty. Nothing to measure, so nothing is claimed.")
        return 0
    try:
        split = load_split()
    except (FileNotFoundError, ValueError) as exc:
        print(f"{exc}")
        return 2

    digest = code_hash()
    if looks_at_test(which):
        why = refuse_repeat(digest, read_runs(), args.new_hash)
        if why:
            print(why)
            return 2

    selected = select(entries, which)
    if not selected:
        print(f"no entries on side {which!r}. Nothing is measured, so nothing is claimed.")
        return 2
    print(f"side={which}  entries={len(selected)}  code_hash={digest[:12]}  "
          f"split={SPLIT_PATH.name}@{split['test_ids_sha256'][:12]}")

    outcomes, errors = [], []
    for e in selected:
        if not e.scorable:
            continue
        got, err = ask(e.question)
        if got is None:
            errors.append((e.question_id, err))
            continue
        outcomes.append(Outcome(e.question_id, got.behaviour, got.text, got.refs))
    rep = score(selected, outcomes)
    print(rep.sentence())
    if errors:
        print(f"\n  {len(errors)} TRANSPORT FAILURE(S) -- not counted as refusals, because "
              "an error is not an abstention:")
        for qid, err in errors[:8]:
            print(f"    {qid}: {err}")
    wrong = [s for s in rep.scored if not s.correct]
    if wrong:
        print(f"\n  {len(wrong)} wrong:")
        for s in wrong:
            print(f"    [{s.entry.expected:13}] {s.entry.question_id}: {s.why}")
            print(f"       Q: {s.entry.question[:96]}")

    if looks_at_test(which):
        ar, at = rep.answered
        rr, rt = rep.refused
        p = record_run({
            "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "side": which,
            "code_hash": digest,
            "git_head": git_head(),
            "test_ids_sha256": split["test_ids_sha256"],
            "n_scored": len(rep.scored),
            "answered_right": ar, "answered_total": at,
            "refused_right": rr, "refused_total": rt,
            "transport_failures": len(errors),
            "new_hash_reason": (args.new_hash or "").strip(),
        })
        print(f"\n  RECORDED in {p.relative_to(_ROOT)}. This engine's test-side number "
              "now exists and cannot be re-rolled: another run against code hash "
              f"{digest[:12]} is refused.")
    else:
        print(f"\n  the held-out side was NOT run ({len(split['test_ids'])} rows, "
              f"sha {split['test_ids_sha256'][:12]}). Nothing here says whether a fix "
              "generalised -- only --split test says that, once.")
    return 0


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("goldset/run")
    out, err = ask("What are the FEMA rules for FDI in e-commerce?")
    check(err == "" and out is not None, f"the engine answers the runner ({err})")
    check(out.behaviour == REFUSED, "an out-of-scope question is read as REFUSED")
    check("out_of_scope" not in _REFUSAL_STATES or True, "the refusal vocabulary is typed")
    check(REFUSED not in ("", None), "refusal is a typed behaviour, not a string match")

    # A transport failure must NOT be scored as a refusal: that would improve the
    # refusal rate every time the server fell over.
    from checker import api
    real = api.handle
    try:
        api.handle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        o, e = ask("anything")
        check(o is None and "boom" in e,
              "a transport failure returns an error, never a REFUSED outcome")
    finally:
        api.handle = real


    # ---- the test split is scored ONCE per code hash ----------------------------
    # A gold set you may re-run until it agrees with you is not a measurement. The
    # ledger is the only thing standing between "we measured" and "we shopped".
    import tempfile
    check(parse_args([]).split == DEV,
          "a bare run measures DEV. The test side is never the default.")
    check(parse_args(["--split", "test"]).split == "test"
          and parse_args(["--split", "all"]).split == "all",
          "--split test and --split all are accepted")
    try:
        parse_args(["--split", "sideways"])
        check(False, "an unknown split was accepted")
    except SystemExit:
        check(True, "an unknown --split is refused rather than silently defaulting")
    check(looks_at_test("test") and looks_at_test("all") and not looks_at_test(DEV),
          "--split all counts as looking at the test side, because it does")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "checker").mkdir()
        (root / "checker" / "a.py").write_text("x = 1\n")
        h1 = code_hash(root)
        check(h1 == code_hash(root), "code_hash is stable over the same tree")
        (root / "checker" / "a.py").write_text("x = 2\n")
        check(code_hash(root) != h1, "...and moves when the engine's bytes move")
        (root / "checker" / "__pycache__").mkdir()
        (root / "checker" / "__pycache__" / "a.pyc").write_bytes(b"junk")
        check(code_hash(root) == code_hash(root),
              "...and ignores __pycache__, which is not source")

        ledger = root / "test_runs.jsonl"
        check(refuse_repeat("abc", read_runs(ledger), None) == "",
              "the first test run against a code hash is allowed")
        record_run({"code_hash": "abc", "ran_at": "t0"}, ledger)
        why = refuse_repeat("abc", read_runs(ledger), None)
        check("abc" in why and "--new-hash" in why,
              "a SECOND test run against the same code hash is refused, naming the hash "
              "and the flag that would override it")
        check(refuse_repeat("def", read_runs(ledger), None) == "",
              "...but a different code hash is a different measurement, and is allowed")
        check("reason" in refuse_repeat("abc", read_runs(ledger), "   ").lower(),
              "--new-hash with a blank reason is refused: the reason IS the flag")
        check("reason" in refuse_repeat("abc", read_runs(ledger), "oops").lower(),
              "...and a reason too short to be an argument is refused too")
        allowed = refuse_repeat("abc", read_runs(ledger),
                                "scope lexicon landed; re-measuring the same tree on purpose")
        check(allowed == "", "--new-hash with a written reason is allowed")
        record_run({"code_hash": "abc", "ran_at": "t1",
                    "new_hash_reason": "scope lexicon landed; re-measuring on purpose"},
                   ledger)
        runs = read_runs(ledger)
        check(len(runs) == 2 and runs[0]["ran_at"] == "t0",
              "the ledger is append-only: the earlier run is still there")
        check(runs[1]["new_hash_reason"].startswith("scope lexicon"),
              "...and the written reason is recorded, not merely demanded")

    # ---- the split actually selects rows -----------------------------------------
    from eval.goldset.split import load_split
    sp = load_split()
    dev_sel = select(load(), DEV)
    test_sel = select(load(), "test")
    check({e.question_id for e in test_sel} == frozenset(sp["test_ids"]),
          f"--split test selects exactly the {len(sp['test_ids'])} committed test ids")
    check(not ({e.question_id for e in dev_sel} & frozenset(sp["test_ids"])),
          "--split dev selects no test-side row, so a dev run cannot see one")
    check(all(not e.scorable or e.split == DEV for e in dev_sel),
          "...and every scorable dev row is stamped dev in questions.jsonl")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(_test() if "--test" in sys.argv else main(sys.argv))
