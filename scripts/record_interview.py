"""
Record one practitioner interview into research/interviews.csv.

Instrumentation, not analysis. It captures what was observed and refuses to capture a conclusion:
there is no "was this validated" field, because the decision rule reads the recorded facts and a
free-text verdict would quietly become the finding.

It also will not invent a participant. Every field is entered by the interviewer or left blank, and
blank means unobserved -- distinct from "no", which is why the observation fields accept y / n / ?
rather than a checkbox.

    python3 scripts/record_interview.py --new         # walk one session interactively
    python3 scripts/record_interview.py --summary     # what the five sessions show so far
    python3 scripts/record_interview.py --test

Run --summary after each interview, not at the end. If three participants have already answered the
question the study exists to ask, the remaining sessions can go deeper instead of repeating it.
"""
from __future__ import annotations

import csv
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "research/interviews.csv"

# The correct answer to the baseline task. Held here so the tool can classify an answer without the
# interviewer having to decide in the moment -- and so "they got it wrong" is a recorded fact rather
# than a recollection.
CORRECT = "2026-08-10"          # fifteen-month limb binds
PLAUSIBLE_MISS = "2026-09-30"   # six-month limb only


@dataclass
class Interview:
    participant_id: str = ""
    profession: str = ""              # company_secretary | corporate_lawyer | ca | junior | other
    years_experience: str = ""
    firm_type: str = ""               # solo | cs_firm | law_firm | in_house | ca_firm
    city_or_region: str = ""
    interview_date: str = ""
    consent_recorded: str = ""        # y/n

    # Stage 1 — what they actually do. These test CLAIMS_TO_TEST.md Tier 1: money, counts and
    # specific past events. Everything else a practitioner says is softer than these.
    redo_due_to_rule_change: str = ""      # y/n/? — T4
    redo_last_instance: str = ""           # when, and what it cost
    past_date_question_asked: str = ""     # y/n/? — B2
    past_date_what_they_did: str = ""
    past_date_time_taken: str = ""
    pays_for_alerts: str = ""              # y/n/? — T2
    pays_for_alerts_amount: str = ""
    pays_for_historical_research: str = ""  # y/n/? — T3, the claim most likely to be invented
    pays_for_historical_amount: str = ""
    current_research_tool: str = ""        # T1
    current_research_spend: str = ""
    research_tool_approver: str = ""
    filings_last_quarter: str = ""         # T5/T6 — a count, not an impression
    who_drafts: str = ""                   # B3
    fy_2018_19_outcome: str = ""           # could_not | from_memory | opened_source

    # Stage 2 — baseline task
    baseline_answer: str = ""
    baseline_seconds: str = ""
    sources_used: str = ""            # pipe-separated
    checked_six_month: str = ""       # y/n/?
    checked_fifteen_month: str = ""
    mentioned_extension: str = ""
    would_verify_before_sending: str = ""
    historical_year_method: str = ""  # how they'd answer for FY 2018-19
    reported_outdated_guidance: str = ""
    outdated_guidance_story: str = ""

    # Stage 2 — after the demo
    read_provenance_panel: str = ""
    opened_source_text: str = ""
    noticed_two_limbs: str = ""
    trust_without_checking: str = ""  # y/n/? — y is a SAFETY finding
    blocking_reaction: str = ""       # helpful | annoying | neutral
    useful_parts: str = ""
    noise_parts: str = ""

    # Stage 3 — commitment, not opinion
    version_questions_frequency: str = ""
    conflict_resolution_practice: str = ""
    commitment: str = ""              # none | will_test | gave_document | named_date | pilot_talk
    blockers_to_use: str = ""
    verbatim_quote: str = ""

    def baseline_verdict(self) -> str:
        a = (self.baseline_answer or "").strip()
        if not a:
            return "not recorded"
        if CORRECT in a:
            return "correct (fifteen-month limb)"
        if PLAUSIBLE_MISS in a:
            return "MISSED the fifteen-month limb"
        return "other / unclear"


def load() -> list[dict]:
    if not CSV_PATH.is_file():
        return []
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(exist_ok=True)
    names = [f.name for f in fields(Interview)]
    tmp = CSV_PATH.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=names)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(CSV_PATH)          # atomic: an interrupted write must not truncate the record


PROMPTS = {
    "participant_id": "participant id (P01…)",
    "profession": "profession [company_secretary/corporate_lawyer/ca/junior/other]",
    "years_experience": "years of experience",
    "firm_type": "firm type [solo/cs_firm/law_firm/in_house/ca_firm]",
    "city_or_region": "city or region",
    "interview_date": "interview date (YYYY-MM-DD)",
    "consent_recorded": "consent recorded? [y/n]",
    "redo_due_to_rule_change": "STAGE 1 — ever redone a document because a rule changed? [y/n/?]",
    "redo_last_instance": "  ...when, and what it cost (blank if none recalled)",
    "past_date_question_asked": "  ever asked what the law was on a PAST date? [y/n/?]",
    "past_date_what_they_did": "  ...what they actually did",
    "past_date_time_taken": "  ...how long it took",
    "pays_for_alerts": "  pays for rule-change alerts? [y/n/?]",
    "pays_for_alerts_amount": "  ...how much",
    "pays_for_historical_research": "  pays anyone for HISTORICAL legal research? [y/n/?]",
    "pays_for_historical_amount": "  ...how much",
    "current_research_tool": "  current research tool",
    "current_research_spend": "  ...annual spend",
    "research_tool_approver": "  ...who signs it off",
    "filings_last_quarter": "  filings/minutes done personally LAST QUARTER (a number)",
    "who_drafts": "  who drafts in their office, and why",
    "fy_2018_19_outcome": "  FY 2018-19 question [could_not/from_memory/opened_source]",
    "baseline_answer": "STAGE 2 — their answer (a date, or what they said)",
    "baseline_seconds": "  seconds taken",
    "sources_used": "  sources opened (pipe-separated; blank = none)",
    "checked_six_month": "  checked six-month limb? [y/n/?]",
    "checked_fifteen_month": "  checked fifteen-month limb? [y/n/?]",
    "mentioned_extension": "  mentioned Registrar extension? [y/n/?]",
    "would_verify_before_sending": "  would verify before sending to client? [y/n/?]",
    "historical_year_method": "  how they'd answer for FY 2018-19",
    "reported_outdated_guidance": "  ever hit outdated/superseded guidance? [y/n/?]",
    "outdated_guidance_story": "  ...what happened (their words)",
    "read_provenance_panel": "STAGE 2 — read the provenance panel? [y/n/?]",
    "opened_source_text": "  opened/asked for the source text? [y/n/?]",
    "noticed_two_limbs": "  noticed the two limbs? [y/n/?]",
    "trust_without_checking": "  would trust WITHOUT opening the section? [y/n/?]",
    "blocking_reaction": "  blocked approval [helpful/annoying/neutral]",
    "useful_parts": "  what they called useful",
    "noise_parts": "  what they called noise",
    "version_questions_frequency": "STAGE 3 — how often does the version of the law matter",
    "conflict_resolution_practice": "  what they do when sources disagree",
    "commitment": "  commitment [none/will_test/gave_document/named_date/pilot_talk]",
    "blockers_to_use": "  what would stop them using it",
    "verbatim_quote": "  one verbatim quote worth keeping",
}


def new_session() -> int:
    if not sys.stdin.isatty():
        print("This records a live interview and will not run unattended.\n"
              "There is no way to fill it in without a participant in the room.")
        return 2
    print("Recording one interview. Enter blank for anything you did not observe —\n"
          "blank means UNOBSERVED, which is not the same as 'no'.\n")
    data = {}
    for name, prompt in PROMPTS.items():
        data[name] = input(f"{prompt}: ").strip()
    iv = Interview(**data)
    rows = load()
    if any(r.get("participant_id") == iv.participant_id for r in rows):
        print(f"\nrefused: {iv.participant_id} already recorded. Use a new id.")
        return 1
    rows.append(asdict(iv))
    save(rows)
    print(f"\nrecorded {iv.participant_id}. Baseline: {iv.baseline_verdict()}")
    if iv.trust_without_checking.lower().startswith("y"):
        print("NOTE: they would trust it without checking. That is a SAFETY finding, "
              "not a product success — it belongs in the findings as a risk.")
    return 0


def summary() -> int:
    rows = load()
    if not rows:
        print(f"no interviews recorded yet ({CSV_PATH.relative_to(ROOT)} is empty)")
        return 0
    n = len(rows)
    def count(field: str, value: str = "y") -> int:
        return sum(1 for r in rows if (r.get(field) or "").lower().startswith(value))

    print(f"interviews recorded: {n}\n")
    print("  BASELINE TASK")
    for r in rows:
        iv = Interview(**{k: r.get(k, "") for k in (f.name for f in fields(Interview))})
        print(f"    {r['participant_id']:<5} {r.get('profession',''):<20} "
              f"{r.get('baseline_seconds','?'):>5}s  {iv.baseline_verdict()}")
    missed = sum(1 for r in rows
                 if PLAUSIBLE_MISS in (r.get("baseline_answer") or ""))
    print(f"\n    missed the fifteen-month limb: {missed}/{n}")
    print(f"    checked it unprompted        : {count('checked_fifteen_month')}/{n}")

    print("\n  TIER-1 CLAIMS — the checkable ones (see research/CLAIMS_TO_TEST.md)")
    for field, label, claim in (
            ("pays_for_historical_research", "pays for historical research", "T3"),
            ("pays_for_alerts", "pays for change alerts", "T2"),
            ("redo_due_to_rule_change", "redid work after a rule change", "T4"),
            ("past_date_question_asked", "was asked a past-date question", "B2")):
        yes = count(field); no = count(field, "n")
        verdict = ("SUPPORTED" if yes >= 3 else
                   "REFUTED" if no >= 3 else "not settled")
        print(f"    {claim} {label:<34} y={yes} n={no} of {n}   {verdict}")
    could_not = sum(1 for r in rows if (r.get("fy_2018_19_outcome") or "") == "could_not")
    if n:
        print(f"    B2 could NOT answer the FY 2018-19 question: {could_not}/{n}"
              + ("   <- the strongest signal available" if could_not >= 3 else ""))

    print("\n  DECISION RULE (3 of 5 needed, and commitment is what counts)")
    hist = count("reported_outdated_guidance")
    commit = sum(1 for r in rows
                 if (r.get("commitment") or "none") not in ("", "none"))
    docs = sum(1 for r in rows if (r.get("commitment") or "") == "gave_document")
    print(f"    reported outdated guidance   : {hist}/{n}   (need 3)")
    print(f"    agreed to test something     : {commit}/{n}   (need 2)")
    print(f"    provided a concrete example  : {docs}/{n}   (need 1)")
    ready = hist >= 3 and commit >= 2 and docs >= 1
    print(f"\n    threshold for building amendment reconstruction: "
          f"{'MET' if ready else 'NOT met'}")

    trust = count("trust_without_checking")
    if trust:
        print(f"\n  SAFETY: {trust}/{n} would trust the output without checking the source.")
        print("    Treat as a risk finding. More visible friction, not less.")
    return 0


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    iv = Interview(participant_id="P01", baseline_answer="30 September 2026 (2026-09-30)")
    check("MISSED" in iv.baseline_verdict(), "a six-month-only answer is recorded as a miss")
    check("correct" in Interview(baseline_answer="2026-08-10").baseline_verdict(),
          "the fifteen-month answer is recorded as correct")
    check(Interview().baseline_verdict() == "not recorded",
          "an unrecorded answer is 'not recorded', never assumed wrong")

    names = [f.name for f in fields(Interview)]
    for banned in ("validated", "verdict", "conclusion", "score", "recommendation"):
        check(not any(banned in n for n in names),
              f"no field invites a conclusion ({banned!r}) — the decision rule reads facts")
    check("trust_without_checking" in names,
          "the safety question is a recorded field, not left to memory")
    check(all(p in PROMPTS for p in names if p != "participant_id" or True),
          "every field has an interviewer prompt")

    check(len(names) == len(set(names)), "no duplicate fields")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--summary"
    raise SystemExit({"--new": new_session, "--summary": summary,
                      "--test": lambda: (_test(), 0)[1]}.get(arg, summary)())
