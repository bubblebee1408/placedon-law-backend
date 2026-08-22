"""
The Section 96 vertical slice, end to end.

matter -> question -> admitted source -> quoted interval -> derived deadline -> controlled draft
-> typed provenance -> human approval.

This is the whole product thesis on one section, and it is deliberately one section. It exists to be
shown to a company secretary and to answer their first question -- "how do I know this date is
right?" -- with the working rather than with confidence.

Nothing here calls a language model. Every value in the output came from an admitted provision, a
fact the user supplied, or arithmetic on the two.

Run: python3 scripts/slice_s96.py            (walk the slice)
     python3 scripts/slice_s96.py --test     (assert it end to end)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import assessment as asm          # noqa: E402
from checker.agm import compute                # noqa: E402
from checker.drafting import DraftError, draft_agm_notice  # noqa: E402
from checker.matter import Matter              # noqa: E402
from checker.retrieve import MODE_MODEL, retrieve  # noqa: E402

AT = "2026-08-22T00:00:00Z"


def build(matter: Matter, question: str):
    """Run the slice. Returns (pack, assessment, deadline, draft)."""
    pack, _ = retrieve("s.96", mode=MODE_MODEL)
    if not pack.usable:
        raise SystemExit("s.96 is not admitted; nothing can be answered from it")
    prov = pack.usable[0]
    src = prov.reading_text or prov.raw_text

    a = asm.assess_from_pack(pack, prov.key, facts_established=not matter.missing_for_agm())
    deadline = (compute(source_text=src, **matter.agm_inputs())
                if not matter.missing_for_agm()
                else compute(source_text=src, financial_year_end=matter.financial_year_end,
                             is_first_agm=matter.is_first_agm))
    draft = draft_agm_notice(company_name=matter.company_name, deadline=deadline,
                             provision_text=src)
    return pack, a, deadline, draft


def walk(matter: Matter, question: str) -> None:
    pack, a, deadline, draft = build(matter, question)
    prov = pack.usable[0]

    print("=" * 78)
    print(f"MATTER  {matter.matter_id}  —  {matter.company_name} ({matter.company_type})")
    print("=" * 78)
    for f in matter.provenance():
        print(f"  {f.field:<22} {f.value:<16} [{f.origin}]")

    print(f"\nQUESTION\n  {question}\n")

    print("SOURCE")
    print(f"  {prov.key}  —  {prov.ref.title}")
    print(f"  admission     : {a.provision_status}")
    print(f"  applicability : {a.applicability}")
    print(f"  record        : {prov.corpus_record_id}, sha256 {prov.corpus_content_sha256[:16]}…")
    print("  amendment     : 1 recorded — Subs. by Act 1 of 2018, s.26 (w.e.f. 13-6-2018).")
    print("                  The text used is the CURRENT consolidation. Point-in-time")
    print("                  reconstruction is not verified against an external source, so no")
    print("                  claim is made about the wording on any earlier date.\n")

    print("ANSWER")
    for line in deadline.render().splitlines():
        print("  " + line)

    print("\nDRAFT")
    for line in draft.render().splitlines():
        print("  " + line)

    print()
    try:
        draft.approve("reviewer", AT)
        print("APPROVAL: available — a human must still read and sign it.")
    except DraftError as e:
        print(f"APPROVAL: refused — {e}")


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    m = Matter(matter_id="M-001", company_name="ABC Private Limited", company_type="PRIVATE",
               financial_year_end=date(2026, 3, 31), created_at=AT, previous_agm=date(2025, 5, 10))
    pack, a, dl, draft = build(m, "What is the latest date for the next AGM?")

    check(a.provision_status == asm.ADMITTED, "the slice runs on an ADMITTED provision")
    check(dl.binding.deadline == date(2026, 8, 10),
          f"the fifteen-month limb binds: {dl.binding.deadline}")
    check(len(dl.constraints) == 2, "both statutory limbs are shown, not only the binding one")

    flat = " ".join((pack.usable[0].reading_text or pack.usable[0].raw_text).split()).lower()
    check(dl.binding.interval_text.lower() in flat,
          "the interval quoted is verbatim in the provision")
    check("2026-08-10" not in flat and "10 august" not in flat,
          "the derived date appears nowhere in the Act — which is what makes it derived")

    # The draft must refuse approval while meeting facts are absent.
    check(not draft.ready, "the draft is not approvable on financial-year facts alone")
    try:
        draft.approve("r", AT); check(False, "approving must raise")
    except DraftError:
        check(True, "approval is refused, not warned about")

    # Every value in the draft is typed, and nothing is a model suggestion.
    types = {s.slot_type for s in draft.slots}
    check("MODEL_SUGGESTION" not in types,
          "no value in the slice came from a model — none is wired")
    check(all(s.slot_type for s in draft.slots), "every slot carries an origin")

    # A first-AGM matter takes the nine-month limb and shows one constraint.
    first = Matter(matter_id="M-002", company_name="NewCo Private Limited",
                   company_type="PRIVATE", financial_year_end=date(2026, 3, 31),
                   created_at=AT, is_first_agm=True)
    _, _, fdl, _ = build(first, "First AGM deadline?")
    check(fdl.binding.deadline == date(2026, 12, 31),
          f"first AGM -> nine months -> 31-12-2026 ({fdl.binding.deadline})")
    check(len(fdl.constraints) == 1, "the fifteen-month limb does not apply to a first AGM")

    # A matter missing the previous AGM must not yield a deadline at all.
    thin = Matter(matter_id="M-003", company_name="XYZ Limited", company_type="PUBLIC",
                  financial_year_end=date(2026, 3, 31), created_at=AT)
    _, _, tdl, tdraft = build(thin, "AGM deadline?")
    check(tdl.binding is None, "no previous AGM -> no binding deadline is stated")
    check(any("previous annual general meeting" in x for x in tdl.missing_facts),
          "...and the missing fact is named")
    check(not tdraft.ready, "...and the draft cannot be approved")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        walk(Matter(matter_id="M-001", company_name="ABC Private Limited",
                    company_type="PRIVATE", financial_year_end=date(2026, 3, 31),
                    created_at=AT, previous_agm=date(2025, 5, 10)),
             "What is the latest date for the next AGM?")
