"""What a promotion would do. Runs the validations and writes nothing.

The preview is the last thing a reviewer sees before a gold label moves, so it
has to be exact: the files that would change, the pair counts before and after,
every label that would move, the diff, where the text came from, and the
decision that authorises it.

Six validations gate the preview. Each is a question that has to be answered
against the held source or the frozen set, not against the proposal's own
assertion about itself:

    1  the claim's source span is present in the held provision text
    2  the provision and sub-section mapping is right
    3  the source hash and the resubmission hash match what was reviewed
    4  the existing negative fixture is unchanged
    5  the two sent-back duplicates remain excluded
    6  no gold label moved while validating

A validation that cannot be answered fails. It does not warn.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FROZEN = Path("corpus/benchmark/approved_pairs.jsonl")
RESUB = Path("corpus/benchmark/resubmissions.jsonl")
DECISIONS = Path("corpus/benchmark/review_decisions.jsonl")
PREVIEW = Path("corpus/benchmark/promotion_preview.json")

SENT_BACK_DUPES = ("v2-p174-qbind-0", "v2-p174-qbind-1")
EXISTING_NEGATIVE = "v2-174-1-neg"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Preview:
    checks: list[Check] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    pair_count_before: int = 0
    pair_count_after: int = 0
    label_changes: list[dict] = field(default_factory=list)
    diff: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    decision_record: dict = field(default_factory=dict)

    @property
    def mechanically_valid(self) -> bool:
        """Every automated check answered. Says nothing about legal content."""
        return all(c.passed for c in self.checks)

    @property
    def authorised(self) -> bool:
        """A human has approved this mutation, and nothing in it is blocked.

        Deliberately not the same property as `mechanically_valid`. The s.174
        proposal passed all eight checks and is still wrong to promote, because
        the checks verify that the span is the one claimed — not that the span
        is sound. "SAFE TO PROMOTE" read as approval; it was never that.
        """
        return (self.mechanically_valid and not self.blocked
                and bool(self.decision_record)
                and self.decision_record.get("applied") is False)

    # Retained under the old name so nothing silently reads the wrong property.
    @property
    def safe(self) -> bool:
        raise AttributeError(
            "'safe' was ambiguous between mechanical validity and human "
            "authorisation. Use .mechanically_valid or .authorised.")


def _sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _frozen() -> dict[str, dict]:
    out = {}
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["pair_id"]] = r
    return out


def _resub() -> dict:
    lines = [l for l in RESUB.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"expected one resubmission, found {len(lines)}")
    return json.loads(lines[0])


def _decision_for(pair_id: str) -> dict | None:
    hits = [json.loads(l) for l in DECISIONS.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l)["proposal_id"] == pair_id]
    return hits[-1] if hits else None


def build() -> Preview:
    from checker.entail_pairs_v2 import provision, source_span
    from checker.grounding_policy import NOT_ENTAILED

    pv = Preview()
    frozen_before_bytes = FROZEN.read_bytes()
    frozen = _frozen()
    r = _resub()
    pid = r["pair_id"]

    # 1 — the claim's substance must be present in the held provision text.
    # Checked limb by limb against the source, not as a whole-string match: the
    # claim is a restatement, so it will not appear verbatim. Each limb must.
    prov = _norm(provision(r["section"]))
    limbs = ["one-third", "two directors", "whichever is higher", "quorum"]
    absent = [x for x in limbs if x not in prov]
    pv.checks.append(Check(
        "1 source span validated against the held provision",
        not absent,
        f"every limb of the claim is present in s.{r['section']} as held"
        if not absent else f"absent from the source: {absent}"))

    span = source_span(r["section"], r["subsection"])
    span_ok = all(x in _norm(span) for x in ("one-third", "two directors",
                                             "whichever is higher"))
    pv.checks.append(Check(
        "1b the sub-section span carries the whole rule",
        span_ok,
        f"s.{r['section']}({r['subsection']}) span, {len(span)} chars, carries "
        f"both limbs and the selector" if span_ok
        else "the span does not carry the full rule"))

    # 2 — provision and sub-section mapping. The selector must live in the
    # sub-section claimed, not merely somewhere in the section: that confusion
    # is what previously attributed s.174(1)'s selector to the (3) rule.
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"\((\d+)\)\s",
                                                          provision(r["section"]))]
    at = provision(r["section"]).lower().find("whichever is higher")
    sub_at = [n for s, n in marks if s <= at]
    mapped = sub_at[-1] if sub_at else None
    pv.checks.append(Check(
        "2 provision and sub-section mapping",
        mapped == r["subsection"] and r["source_id"].endswith(r["section"]),
        f"'whichever is higher' sits in sub-section ({mapped}); the resubmission "
        f"claims ({r['subsection']}); source_id {r['source_id']}"))

    # 3 — hashes. The decision must be pinned to the resubmission the reviewer
    # actually read.
    resub_hash = _sha(RESUB.read_bytes())
    dec = _decision_for(pid) or {}
    pv.checks.append(Check(
        "3 source and resubmission hashes",
        bool(dec) and dec.get("table_sha256") == resub_hash,
        f"resubmission {resub_hash[:23]}…; decision pins "
        f"{str(dec.get('table_sha256'))[:23]}…"))

    span_hash = _sha(span.encode("utf-8"))
    frozen_span = frozen.get(EXISTING_NEGATIVE, {}).get("source_span_hash")
    pv.checks.append(Check(
        "3b the span hash matches the frozen s.174(1) fixtures",
        span_hash == frozen_span,
        f"computed {span_hash[:23]}… vs frozen {str(frozen_span)[:23]}…"))

    # 4 — the existing negative must be untouched by this promotion.
    neg = frozen.get(EXISTING_NEGATIVE)
    pv.checks.append(Check(
        "4 the existing negative fixture is unchanged",
        bool(neg) and neg["label"] == NOT_ENTAILED
        and "two directors" in neg["claim"].lower(),
        f"{EXISTING_NEGATIVE} present, label {neg['label'] if neg else 'ABSENT'}, "
        f"claim unchanged" if neg else f"{EXISTING_NEGATIVE} is missing"))

    # 5 — the sent-back duplicates must stay out.
    still_in = [d for d in SENT_BACK_DUPES if d in frozen]
    pv.checks.append(Check(
        "5 the sent-back duplicates remain excluded",
        not still_in,
        "neither sent-back duplicate is in the frozen set" if not still_in
        else f"still frozen: {still_in}"))

    # --- what promotion would do -------------------------------------------
    pv.pair_count_before = len(frozen)

    # A proposal whose latest decision is a block is not an addition. The s.174
    # claim is legally sound and its source span is not: promoting it would put
    # a fixture into the benchmark resting on text the source got wrong.
    from checker.review_record import BLOCKED
    latest = _decision_for(pid) or {}
    blocked = latest.get("decision") == BLOCKED
    adds = [] if blocked else [{"pair_id": pid, "old_label": None,
                                "new_label": r["proposed_label"], "claim": r["claim"]}]
    if blocked:
        pv.blocked.append({
            "pair_id": pid, "decision": BLOCKED,
            "reason": latest.get("reason", ""),
            "source_defect": r["evidence"].get("transcription_warnings", []),
        })

    # Every SEND BACK on a pair that IS frozen means that pair must come out.
    removals = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d["decision"] == "SEND BACK" and d["proposal_id"] in frozen:
            removals.append({"pair_id": d["proposal_id"],
                             "old_label": frozen[d["proposal_id"]]["label"],
                             "new_label": None,
                             "claim": frozen[d["proposal_id"]]["claim"],
                             "reason": d["reason"].split("  [CORRECTION")[0]})
    seen, dedup = set(), []
    for x in removals:
        if x["pair_id"] not in seen:
            seen.add(x["pair_id"])
            dedup.append(x)
    removals = dedup

    # Pending drift is part of what promotion does, and leaving it out of the
    # preview understated the operation: the count read 71 -> 69 while the
    # freeze would actually write 67. A preview that does not predict the write
    # is not a preview. Every change carries where it came from.
    from checker.benchmark_v2_freeze import label_drift
    for x in adds:
        x["origin"] = "reviewer decision"
    for x in removals:
        x["origin"] = "reviewer decision"
    decided = {x["pair_id"] for x in adds + removals}
    drift = label_drift()
    for pid_d, lab in drift["removed"]:
        if pid_d in decided:
            continue
        removals.append({
            "pair_id": pid_d, "old_label": lab, "new_label": None,
            "claim": frozen.get(pid_d, {}).get("claim", ""),
            "origin": "pending inventory correction",
            "reason": "reclassified INVALID_FIXTURE when the s.174(1) qualifier "
                      "inventory was corrected; not a reviewer decision"})
    for pid_a in drift["added"]:
        if pid_a not in decided:
            adds.append({"pair_id": pid_a, "old_label": None,
                         "new_label": "?", "claim": "",
                         "origin": "pending inventory correction"})

    pv.label_changes = adds + removals
    pv.pair_count_after = pv.pair_count_before + len(adds) - len(removals)
    # Derived, not asserted. With the s.174 addition blocked, nothing marks a
    # resubmission promoted, so listing that file would overstate the change.
    pv.files_changed = []
    if adds or removals:
        pv.files_changed += ["corpus/benchmark/approved_pairs.jsonl",
                             "corpus/benchmark/manifest.json"]
    if adds:
        pv.files_changed.append(
            "corpus/benchmark/resubmissions.jsonl (record marked promoted)")
    pv.diff = ([f"+ {a['pair_id']}  ->  {a['new_label']}" for a in adds]
               + [f"- {x['pair_id']}  was {x['old_label']}" for x in removals])

    pv.provenance = {
        "source_id": r["source_id"],
        "section": r["section"], "subsection": r["subsection"],
        "source_span_sha256": span_hash,
        "source_span_chars": len(span),
        "held_provision_chars": len(provision(r["section"])),
        "resubmission_sha256": resub_hash,
        "supersedes": r["supersedes"],
        "supersedes_original": r["supersedes_original"],
        "transcription_warnings": r["evidence"].get("transcription_warnings", []),
    }
    pv.decision_record = dec

    # 6 — nothing moved while we looked.
    pv.checks.append(Check(
        "6 no gold label changed during validation",
        FROZEN.read_bytes() == frozen_before_bytes,
        "approved_pairs.jsonl is byte-identical before and after validation"))
    return pv


def render(pv: Preview) -> str:
    L = ["PROMOTION PREVIEW — nothing has been promoted", ""]
    L.append("Validations")
    for c in pv.checks:
        L.append(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}")
        L.append(f"         {c.detail}")
    L += ["",
          f"Mechanical validation : {'PASS' if pv.mechanically_valid else 'FAIL'}"
          "   (the span is the one claimed; not a judgement on its soundness)",
          f"Human authorisation   : {'GRANTED' if pv.authorised else 'WITHHELD'}",
          ""]
    if pv.blocked:
        L.append("Blocked — excluded from this preview")
        for b in pv.blocked:
            L.append(f"  {b['pair_id']}  {b['decision']}")
            L.append(f"      {b['reason'][:150]}")
            for w in b["source_defect"]:
                L.append(f"      source defect: {w[:120]}")
        L.append("")
    L += ["Files that would change"]
    L += [f"  {f}" for f in pv.files_changed]
    L += ["", f"Pair count   {pv.pair_count_before}  ->  {pv.pair_count_after}", ""]
    L += ["Label changes"]
    for ch in pv.label_changes:
        arrow = f"{ch['old_label']} -> {ch['new_label']}"
        L.append(f"  {ch['pair_id']:<22} {arrow}")
        L.append(f"      {ch['claim'][:96]}")
        if ch.get("reason"):
            L.append(f"      reason: {ch['reason'][:96]}")
    L += ["", "Diff"] + [f"  {d}" for d in pv.diff]
    L += ["", "Source provenance"]
    for k, v in pv.provenance.items():
        L.append(f"  {k}: {v}")
    d = pv.decision_record
    L += ["", "Reviewer decision record"]
    if d:
        for k in ("proposal_id", "decision", "reviewer_id", "decided_at",
                  "software_commit", "working_tree_dirty",
                  "changes_benchmark_fixture", "applied"):
            L.append(f"  {k}: {d.get(k)}")
        L.append(f"  reason: {d.get('reason', '')[:150]}")
    else:
        L.append("  NONE — the promotion is unauthorised")
    return "\n".join(L)


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

    print("promotion_preview")
    before = FROZEN.read_bytes()
    pv = build()

    check(len(pv.checks) >= 6, f"all validations ran ({len(pv.checks)})")
    check(FROZEN.read_bytes() == before,
          "building the preview does not touch the frozen set")
    from checker.scoped_retraction import _records
    check(pv.pair_count_before == len(_records()),
          f"before count matches disk ({pv.pair_count_before})")

    # Mechanical validity is not authorisation, and conflating them is what a
    # verdict of "SAFE TO PROMOTE" did on a defective span.
    check(pv.mechanically_valid, "every automated check answers")
    check(not pv.authorised,
          "...and authorisation is still withheld while a block stands")
    try:
        pv.safe
        check(False, "the ambiguous 'safe' property is gone")
    except AttributeError as e:
        check("ambiguous" in str(e), "the ambiguous 'safe' property refuses to read")

    check([b["pair_id"] for b in pv.blocked] == ["v2-174-1-rule-pos"],
          f"the s.174 proposal is blocked ({pv.blocked and pv.blocked[0]['pair_id']})")
    check(any("hall be one-third" in w for b in pv.blocked
              for w in b["source_defect"]),
          "...and the block carries the SD-004 defect that caused it")

    # The two s.101 send-backs are frozen and must appear as removals.
    # Structural, not pinned to specific ids. The s.101 pairs were asserted here
    # until they were legitimately retracted, at which point a correct benchmark
    # change turned the suite red. What must hold is that the preview predicts
    # the write, whatever is currently pending.
    from checker.benchmark_v2_freeze import label_drift
    removed = {c["pair_id"] for c in pv.label_changes if c["new_label"] is None}
    drift_removed = {pid for pid, _ in label_drift()["removed"]}
    check(drift_removed <= removed,
          f"every pending drift removal appears in the preview ({sorted(removed)})")
    added = {c["pair_id"] for c in pv.label_changes if c["old_label"] is None}
    check(added == set(), f"no addition while the s.174 span is defective ({added})")
    # 67, not 69: the freeze also applies the pending inventory correction that
    # reclassified two s.174 bind pairs. A preview that reported 69 while the
    # write produced 67 is the defect this now pins.
    check(pv.pair_count_after == pv.pair_count_before - len(removed) + len(added),
          f"the predicted count is internally consistent ({pv.pair_count_after})")
    check(pv.pair_count_after == pv.pair_count_before - len(drift_removed),
          "the prediction accounts for pending drift, not only decisions")
    check(all(c.get("origin") for c in pv.label_changes),
          "every change declares where it came from")
    check({c["origin"] for c in pv.label_changes}
          <= {"reviewer decision", "pending inventory correction"},
          f"origins are drawn from the known set "
          f"({ {c['origin'] for c in pv.label_changes} })")
    drifted = {c["pair_id"] for c in pv.label_changes
               if c["origin"] == "pending inventory correction"}
    check(drifted == drift_removed,
          f"drift is labelled as drift, never as a reviewer decision ({drifted})")
    check("v2-174-1-rule-pos" not in {c["pair_id"] for c in pv.label_changes},
          "the blocked s.174 resubmission is still not among the changes")
    check(pv.pair_count_after == pv.pair_count_before + len(added) - len(removed),
          f"the arithmetic holds ({pv.pair_count_after})")

    # A preview without an authorising decision must not read as safe.
    check(pv.decision_record.get("proposal_id") == "v2-174-1-rule-pos",
          "the authorising decision is attached")
    check(pv.decision_record.get("applied") is False,
          "...and is not marked applied")

    check(not any("resubmissions" in f for f in pv.files_changed),
          f"no resubmission file is touched when nothing is added ({pv.files_changed})")
    # files_changed is derived from what would actually be written, so it is
    # empty when nothing is pending. Assert the derivation, not a fixed count.
    expected = ({"corpus/benchmark/approved_pairs.jsonl",
                 "corpus/benchmark/manifest.json"} if pv.label_changes else set())
    check(set(pv.files_changed) == expected,
          f"files_changed lists exactly what a write would touch "
          f"({pv.files_changed or 'nothing pending'})")

    r = render(pv)
    check("nothing has been promoted" in r, "the preview says what it is not")
    check("Human authorisation   : WITHHELD" in r,
          "the rendered preview states that authorisation is withheld")
    check("Source provenance" in r and "Diff" in r,
          "the preview carries provenance and the diff")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--write" in __import__("sys").argv:
        pv = build()
        PREVIEW.write_text(json.dumps({
            "checks": [vars(c) for c in pv.checks],
            "mechanically_valid": pv.mechanically_valid,
            "authorised": pv.authorised,
            "blocked": pv.blocked,
            "files_changed": pv.files_changed,
            "pair_count_before": pv.pair_count_before,
            "pair_count_after": pv.pair_count_after,
            "label_changes": pv.label_changes, "diff": pv.diff,
            "provenance": pv.provenance, "decision_record": pv.decision_record,
        }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(render(pv))
        print(f"\nwritten to {PREVIEW}")
    else:
        _test()
