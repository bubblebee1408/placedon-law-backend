"""
Assemble the evidence a reviewer needs, for every queued item, in one document.

This does NOT decide anything. It gathers the objective facts a human would otherwise have to dig
out of five files per item -- the artifact hash, the page range, the extraction's condition, whether
the rule number is where it should be, which Act sections the rule names -- and lays them beside the
questions. The decision column is deliberately blank.

Why it exists: 30 items each needing eight checks is 240 lookups. A reviewer who has to perform
those lookups by hand will start trusting the parser instead, which defeats the review. Assembling
evidence is assistance; supplying a conclusion is not, and this script does only the former.

Run: python3 scripts/review_brief.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import admission as adm          # noqa: E402
from checker import review_queue as rq        # noqa: E402

RULES_DOC = ROOT / "corpus/rules/board_powers_2014.json"
PDF = ROOT / "corpus/sources/companies_meetings_board_powers_rules_2014.pdf"
OUT = ROOT / "reports/review_brief.md"

# The gazette states its own notification. Recorded as read FROM the document, not as an assumption.
GAZETTE = "G.S.R. 240 (E)"
GAZETTE_DATE = "31st March, 2014"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rule_by_id(target_id: str, doc: dict) -> dict | None:
    n = target_id.rsplit(":R", 1)[-1] if ":R" in target_id else None
    return next((r for r in doc["rules"] if r["rule_number"] == n), None) if n else None


def evidence_for(item: rq.ReviewItem, doc: dict) -> list[tuple[str, str]]:
    """Objective facts for this item. No judgements, no recommendations."""
    rec = adm.load(item.scope if item.scope in ("RULE", "INSTRUMENT") else "RULE", item.target_id)
    rows: list[tuple[str, str]] = [
        ("admission state", rec.state if rec else "no record"),
        ("servable now", str(bool(rec and rec.production_usable)) if rec else "n/a"),
    ]
    if item.scope == "INSTRUMENT":
        rows += [
            ("artifact", f"`{PDF.relative_to(ROOT)}`"),
            ("sha256", f"`{sha256(PDF)[:32]}…`" if PDF.is_file() else "**FILE MISSING**"),
            ("pages", str(doc["pages"])),
            ("rules parsed", f"{len(doc['rules'])} (r.1–r.{doc['rules'][-1]['rule_number']})"),
            ("gazette, per the document", f"{GAZETTE} dated {GAZETTE_DATE}"),
            ("made under, per the preamble",
             ", ".join(l["to_section"].split(":S")[-1] for l in doc["made_under"])),
            ("principal or amendment?",
             "classified VERIFIED_PRINCIPAL by scripts/acquire_rules.py — "
             "'Short title and commencement' present, no amending language"),
        ]
        return rows

    r = rule_by_id(item.target_id, doc)
    if r is None:
        rows.append(("parsed rule", "**not found in the parsed corpus**"))
        return rows
    body = r.get("text_raw", "")
    splits = len(re.findall(r"\b[A-Za-z]{2,}\s+[a-z]{1,3}\b(?=[\s.,;:)])", body))
    rows += [
        ("heading", r["heading"]),
        ("pages", f"{r['page_start']}–{r['page_end']} of {doc['pages']}"),
        ("body length", f"{len(body):,} chars"),
        ("sub-rules detected", ", ".join(r.get("sub_rules", [])) or "none"),
        ("sections it names", ", ".join(sorted({l["to_section"].split(":S")[-1]
                                                for l in r.get("act_links", [])})) or "none"),
        ("extraction split words", f"{splits}" + ("  ← read text_raw closely" if splits > 20 else "")),
        ("parser warnings", "; ".join(r.get("warnings", [])) or "none"),
    ]
    return rows


def main() -> None:
    items = rq.load_queue()
    if not items:
        print("no queue; run scripts/seed_admission.py"); raise SystemExit(1)
    doc = json.loads(RULES_DOC.read_text())

    out = [
        "# Reviewer brief — 30 queued items", "",
        "Assembled evidence only. **Every decision column is blank and stays blank until you fill "
        "it.** Nothing here recommends an outcome.", "",
        f"- Source: `{PDF.relative_to(ROOT)}` ({doc['pages']} pages)",
        f"- Parsed: {len(doc['rules'])} rules, instrument status `{doc['status']}`, "
        f"`production_usable: {doc['production_usable']}`",
        f"- Queue: {len(items)} items, {sum(1 for i in items if i.is_open)} open", "",
        "## How to record a decision", "",
        "```bash", "python3 scripts/review.py --next        # shows extraction beside the gazette",
        "```", "",
        "`ADMITTED` · `LIMITED` (needs restriction codes + note) · `SUSPENDED` · `REJECTED`", "",
        "A `LIMITED` or `REJECTED` decision requires a written reason — the tool enforces it.", "",
    ]

    by_scope: dict[str, list[rq.ReviewItem]] = {}
    for i in items:
        by_scope.setdefault(i.scope, []).append(i)

    for scope in ("INSTRUMENT", "RULE", "FORM", "LINK"):
        group = by_scope.get(scope, [])
        if not group:
            continue
        out += [f"## {scope} — {len(group)} item(s)", ""]
        if scope == "LINK":
            # 13 near-identical items; a table serves the reviewer better than 13 sections.
            out += ["Each asserts the Rules are MADE_UNDER an Act section, quoted from the "
                    "preamble. Check the section exists and its subject matter matches.", "",
                    "| item | Act section | decision |", "|---|---|---|"]
            for i in group:
                out.append(f"| `{i.review_item_id}` | {i.target_id.split(':S')[-1]} | |")
            out.append("")
            continue
        for i in group:
            out += [f"### `{i.review_item_id}` — {i.target_id}", "",
                    f"*{i.priority} priority*" + (f" · {i.note}" if i.note else ""), "",
                    "| fact | value |", "|---|---|"]
            out += [f"| {k} | {v} |" for k, v in evidence_for(i, doc)]
            out += ["", "**Questions**", ""]
            out += [f"{n}. {q}" for n, q in enumerate(i.questions, 1)]
            out += ["", "**Decision:** ______   **Reason:** ______", ""]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(out) + "\n")
    print(f"items briefed : {len(items)}")
    for s in sorted(by_scope):
        print(f"  {s:<12} {len(by_scope[s])}")
    print(f"written       : {OUT.relative_to(ROOT)}")
    print("\nNothing was decided. All 30 remain PENDING.")


def _check() -> None:
    """Guard the one property that matters: this script decides nothing."""
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    before = rq.load_queue()
    states_before = [(i.review_item_id, i.status) for i in before]
    main()
    after = rq.load_queue()
    check([(i.review_item_id, i.status) for i in after] == states_before,
          "running the brief changes no item's status -- it assembles, it does not decide")
    check(all(i.status == "PENDING" for i in after),
          f"all {len(after)} items remain PENDING")

    text = OUT.read_text()
    check("**Decision:** ______" in text, "every decision field is left blank")

    # Scan the ITEM sections, not the preamble. The preamble's job is to say "nothing here
    # recommends an outcome", and scanning it flagged that very sentence -- a false positive that
    # would have been silenced by rewording the one line the reader most needs to see.
    body = text.split("## INSTRUMENT", 1)[-1]
    for word in ("recommend", "should be admitted", "looks correct", "appears valid",
                 "safe to admit", "no issues found"):
        check(word not in body.lower(),
              f"no item section steers toward an outcome ({word!r})")
    check("Nothing here recommends an outcome" in text,
          "...and says so explicitly to the reader")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        _check()
    else:
        main()
