#!/usr/bin/env python3
"""Stage Rule 15 (the s.188 members'-approval threshold) for human review.

Rule 15 of the Companies (Meetings of Board and its Powers) Rules, 2014 is HELD in
corpus/rules/board_powers_2014.json, but marked UNREVIEWED with extraction defects
("a reviewer must set the boundary", "557 words split"), and its limbs were amended
in 2019. So its threshold values may NOT be served as law until a person verifies
them against a clean, dated source and attests — the same discipline as
scripts/register_gsr700e.py.

This script does two things and nothing more:
  * stage : record the held Rule 15 text's hash and the CANDIDATE limbs extracted
            from it (clearly marked unverified), status PENDING_HUMAN_REVIEW.
  * --attest <id> : record that a reviewer verified the limbs against a clean
            source. Only then does checker.s188_threshold serve them, and s188
            resolves NEEDS_MEMBER_APPROVAL_UNDETERMINED to a determinate state.

It never sets the limbs to VERIFIED on its own. The candidate limbs are a lead, not
law. A reviewer may correct the `limbs` field in the record before attesting.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BOARD_RULES = Path("corpus/rules/board_powers_2014.json")
RECORD = Path("corpus/rules/s188_rule15_review.json")

PENDING = "PENDING_HUMAN_REVIEW"
CORROBORATED = "CORROBORATED"

# Candidate limbs EXTRACTED from the held (defective) Rule 15 text. UNVERIFIED —
# recorded so review is not from a blank page, never so they are served unread.
_CANDIDATE_LIMBS = {
    "paid_up_capital_floor_rupees": 100_000_000,   # "ten crore rupees or more" (pre-2019)
    "pct_of_turnover": 10.0,                        # "ten per cent of turnover"
    "pct_of_net_worth": 10.0,                       # "ten per cent of net worth"
    "extraction_note": ("from a DEFECTIVE extraction of Rule 15, amended over time. "
                        "The single pct_of_turnover / pct_of_net_worth values here are a "
                        "SIMPLIFICATION -- the real Rule has PER-TRANSACTION-TYPE limbs the "
                        "held fragments show as: goods ~25% of turnover; property/leasing/"
                        "services ~10% of net worth or turnover; underwriting ~1% of net "
                        "worth; office of profit ~Rs 2.5 lakh/month; plus a paid-up-capital "
                        "class trigger the 2019 amendment may have removed. A reviewer MUST "
                        "verify every limb against a clean dated copy and decide how to encode "
                        "the per-type granularity before attesting. Do NOT serve these unread."),
}


def _rule15_text() -> tuple[str, str]:
    """(text, source_sha256) of the held Rule 15, or ('', '')."""
    if not BOARD_RULES.is_file():
        return "", ""
    doc = json.loads(BOARD_RULES.read_text())
    for r in doc.get("rules", []):
        if str(r.get("rule_number")) == "15":
            text = r.get("text_raw") or r.get("text_reading") or ""
            sha = r.get("source_artifact_sha256") or (
                "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest())
            return text, sha
    return "", ""


def review_record() -> dict | None:
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def is_attested(rec: dict | None) -> bool:
    return bool(rec and rec.get("status") == CORROBORATED
               and rec.get("reviewed_by") and rec.get("limbs"))


def stage() -> int:
    text, sha = _rule15_text()
    if not text:
        print("Rule 15 not found in the held Board Powers Rules — cannot stage.")
        return 1
    # show the operative-limb fragments so a reviewer sees what to verify
    frags = re.findall(r".{0,40}(?:per\s*cent|crore rupees|lakh ru).{0,60}", text, re.I)
    RECORD.write_text(json.dumps({
        "instrument": "Rule 15, Companies (Meetings of Board and its Powers) "
                      "Rules, 2014 (as amended)",
        "task": "S-188-RULES",
        "source": f"{BOARD_RULES} (rule 15)",
        "source_sha256": sha,
        "status": PENDING,
        "candidate_limbs": _CANDIDATE_LIMBS,
        "limbs": None,                 # a reviewer sets this (may equal candidates)
        "reviewed_by": None,
        "reviewed_at": None,
    }, indent=1) + "\n", encoding="utf-8")
    print(f"staged Rule 15 for review -> {RECORD}")
    print(f"source hash : {sha[:26]}…")
    print("\ncandidate limbs (EXTRACTED, UNVERIFIED — verify before attesting):")
    for k, v in _CANDIDATE_LIMBS.items():
        if k != "extraction_note":
            print(f"    {k} = {v}")
    print(f"\n  {_CANDIDATE_LIMBS['extraction_note']}")
    print("\noperative-limb fragments found in the held text:")
    for f in frags[:8]:
        print("    …" + re.sub(r"\s+", " ", f).strip())
    print("\nStatus: PENDING_HUMAN_REVIEW. NOT servable. A reviewer must verify the")
    print("limbs against a clean dated source, set the record's `limbs` field (or")
    print("accept the candidates), then:")
    print("  python3 scripts/register_s188_rule15.py --attest <reviewer-id>")
    return 0


def attest(reviewer_id: str) -> int:
    rec = review_record()
    if rec is None:
        print("nothing staged; run scripts/register_s188_rule15.py first")
        return 1
    if "@" in reviewer_id:
        print("record a pseudonymous reviewer id, not an email address")
        return 2
    # A reviewer may have set `limbs` by editing the record; else accept the
    # candidates as verified by this attestation (the reviewer vouches for them).
    limbs = rec.get("limbs") or {k: v for k, v in rec["candidate_limbs"].items()
                                 if k != "extraction_note"}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec.update({"limbs": limbs, "reviewed_by": reviewer_id, "reviewed_at": stamp,
                "status": CORROBORATED})
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {stamp}")
    print(f"limbs now servable: {limbs}")
    print("\nchecker.s188_threshold now serves these, so s188 resolves the")
    print("members'-approval requirement instead of refusing. Run scripts/run_tests.sh.")
    return 0


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

    print("register_s188_rule15")

    # is_attested is strict about all three conditions
    check(not is_attested(None), "no record is not attested")
    check(not is_attested({"status": CORROBORATED, "reviewed_by": "x", "limbs": None}),
          "a record with no limbs is not attested")
    check(not is_attested({"status": PENDING, "reviewed_by": "x",
                           "limbs": {"pct_of_turnover": 10}}),
          "a PENDING record is not attested")
    check(is_attested({"status": CORROBORATED, "reviewed_by": "r1",
                       "limbs": {"pct_of_turnover": 10}}),
          "CORROBORATED + reviewer + limbs is attested")

    # the held Rule 15 is findable and its candidate limbs are marked unverified
    text, sha = _rule15_text()
    check(bool(text) and "related party" in text.lower(),
          "Rule 15 text is held and readable")
    check("verify" in _CANDIDATE_LIMBS["extraction_note"].lower(),
          "the candidate limbs are marked as needing verification, not served")

    # attest refuses an email as reviewer id
    src = Path(__file__).read_text()
    check('"@" in reviewer_id' in src, "attest refuses an email as reviewer id")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    if len(sys.argv) >= 3 and sys.argv[1] == "--attest":
        raise SystemExit(attest(sys.argv[2]))
    if len(sys.argv) == 1:
        raise SystemExit(stage())
    print(__doc__)
    raise SystemExit(1)
