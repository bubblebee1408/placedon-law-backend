"""
Seed admission records and the review queue from what the repo actually knows.

This is where the earlier findings stop being documentation and start being enforcement:

  SD-002 (s.16, s.124, s.76A, s.329) carry PRE-AMENDMENT text. They were admitted before anyone
  knew that, and the honest state for "admitted, then found defective" is SUSPENDED.

  SD-001 (s.1) carries a non-statutory editorial tail. The section is law; the tail is not. That
  is limited production with a restriction code, not suspension.

  The Board Powers Rules are parsed but unread, so every rule enters HUMAN_REVIEW_PENDING with a
  review item, and r.15 gets an extra FORM item because its body absorbs the Annexure.

The Act itself is admitted with an explicit, dated reason rather than silently: its standing rests
on the cross-render check and the 17 hand-verified MVP sections, which predate this machinery.
That reason is written into the audit trail so nobody later mistakes grandfathering for review.

Run: python3 scripts/seed_admission.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import admission as adm          # noqa: E402
from checker import review_queue as rq        # noqa: E402

AT = "2026-08-21T00:00:00Z"
ACTOR = "system"
ACT = "ACT:COMPANIES_ACT_2013"
RULES = "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014"

SD002 = ("16", "124", "76A", "329")


def walk(target_type: str, target_id: str, states: list[tuple[str, str, tuple[str, ...]]]):
    rec = adm.AdmissionRecord(target_type, target_id, adm.DISCOVERED)
    for state, reason, codes in states:
        rec = adm.transition(rec, state, actor=ACTOR, at=AT, reason=reason,
                             restriction_codes=codes)
    adm.save(rec)
    return rec


def main() -> None:
    ladder = [(adm.ACQUIRED, "ingested from India Code", ()),
              (adm.TECHNICALLY_VERIFIED, "hashed; cross-render check vs the full-Act PDF", ()),
              (adm.STRUCTURED, "section index built, 464/474 mapped", ()),
              (adm.HUMAN_REVIEW_PENDING, "awaiting review", ()),
              (adm.HUMAN_REVIEWED, "17 MVP sections read by hand against the source", ())]

    act = walk("INSTRUMENT", ACT, ladder + [
        (adm.PRODUCTION_USABLE,
         "ADMITTED ON PRE-EXISTING EVIDENCE, not on a review item: the cross-render check "
         "(median record coverage 1.0000) and 17 hand-verified MVP sections. This predates the "
         "review queue and is recorded as such so it is never mistaken for a reviewed decision.",
         ())])

    # Defect-driven states. These are the two findings from the cross-validation.
    suspended = []
    for num in SD002:
        base = walk("PROVISION", f"{ACT}:S{num}", ladder + [
            (adm.PRODUCTION_USABLE, "admitted with the Act", ())])
        rec = adm.transition(base, adm.SUSPENDED, actor=ACTOR, at=AT,
                             reason="SD-002: the JSON corpus carries PRE-AMENDMENT text for this "
                                    "section where the PDF carries the current consolidation. "
                                    "Serving it would state superseded law as current.")
        adm.save(rec)
        suspended.append(rec)

    s1 = walk("PROVISION", f"{ACT}:S1", ladder + [
        (adm.DEFECT_FLAGGED_PRODUCTION_LIMITED,
         "SD-001: the record ends with the editorial instruction 'To be deleted', which is not "
         "statutory text. The section is law; the tail is not.",
         ("NO_SERVE_EDITORIAL_TAIL",))])

    # The Rules: parsed, unread, and therefore not servable.
    rules_doc = json.loads((ROOT / "corpus/rules/board_powers_2014.json").read_text())
    rules_inst = walk("INSTRUMENT", RULES, [
        (adm.ACQUIRED, "downloaded from eGazette, content id 159201", ()),
        (adm.TECHNICALLY_VERIFIED, "VERIFIED_PRINCIPAL by scripts/acquire_rules.py", ()),
        (adm.STRUCTURED, "parsed into 15 rules with page provenance", ()),
        (adm.HUMAN_REVIEW_PENDING, "nobody has read this against the gazette", ())])

    specs = [{"scope": "INSTRUMENT", "target_id": RULES, "priority": "HIGH",
              "note": "Gazette G.S.R. 240(E) 31-03-2014; confirm principal, not amendment"}]
    for r in rules_doc["rules"]:
        rid = f"{RULES}:R{r['rule_number']}"
        specs.append({"scope": "RULE", "target_id": rid,
                      "priority": "HIGH" if r["warnings"] else "MEDIUM",
                      "page_start": r["page_start"], "page_end": r["page_end"],
                      "note": "; ".join(r["warnings"])[:160]})
        walk("RULE", rid, [
            (adm.ACQUIRED, "part of the acquired gazette", ()),
            (adm.TECHNICALLY_VERIFIED, "extracted with page provenance", ()),
            (adm.STRUCTURED, f"parsed, pages {r['page_start']}-{r['page_end']}", ()),
            (adm.HUMAN_REVIEW_PENDING, "unread", ())])
        if r["rule_number"] == "15":
            specs.append({"scope": "FORM", "target_id": rid, "priority": "HIGH",
                          "page_start": r["page_start"], "page_end": r["page_end"],
                          "note": "body runs to end-of-document and absorbs the Annexure/forms; "
                                  "the operative text ends earlier"})
    for link in rules_doc["made_under"]:
        specs.append({"scope": "LINK", "target_id": link["to_section"], "priority": "MEDIUM",
                      "note": f"MADE_UNDER from the Rules' preamble: {link['evidence_text'][:90]}"})

    items = rq.create_items("BOARD_RULES_2014", specs)
    rq.save_queue(items)

    rules_inst = rq.apply_to_admission(rules_inst, items, actor=ACTOR, at=AT)
    adm.save(rules_inst)

    print(f"Act instrument      : {act.state}  servable={act.production_usable}")
    print(f"s.1 (SD-001)        : {s1.state}  codes={s1.restriction_codes}")
    for r in suspended:
        print(f"{r.target_id:<34}: {r.state}  servable={r.production_usable}")
    print(f"Rules instrument    : {rules_inst.state}  servable={rules_inst.production_usable}")
    print(f"open review items   : {len(rq.open_items(items))}")
    print(f"  by scope          : " + ", ".join(
        f"{s}={sum(1 for i in items if i.scope == s)}" for s in sorted({i.scope for i in items})))
    print(f"written             : corpus/admission/ ({len(list((ROOT/'corpus/admission').glob('*.json')))} files)")


if __name__ == "__main__":
    main()
