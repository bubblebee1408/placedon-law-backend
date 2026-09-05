#!/usr/bin/env python3
"""What a benchmark re-freeze would change. Writes nothing; asks for a decision.

The release gate refuses to score, because 19 frozen pairs carry a source-span
hash that no longer matches the span the generator produces. Until that clears,
no accuracy figure may be quoted from this system at all — which is correct, and
is also a standstill.

This prints the case for clearing it, so a reviewer can answer yes or no rather
than reconstruct the history.

## Why the spans moved

Two deliberate corrections, both made and justified before the gate could see
them, because the gate was scoring the generator rather than the frozen file:

1. **s.96's premise was truncated at 400 characters**, and the cut landed inside
   the first proviso. The premise stopped before "nine months" while a pair
   labelled ENTAILED asserted exactly that — the premise did not contain the
   evidence for its own label. The fallback became the whole provision.

2. **s.174's "two-thirds" pairs were attributed to sub-section (1)**, whose
   qualifier is "whichever is higher". They are about s.174(3), the
   interested-director rule. `subsection_of()` reattributed them, and a precise
   s.174(3) span was added.

So the frozen file records the OLD spans, and the old spans were wrong. The
question is not whether the generator drifted from the truth; it is whether the
frozen file should be corrected to match a truth it never had.

Run: python3 scripts/benchmark_refreeze_request.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FROZEN = Path("corpus/benchmark/approved_pairs.jsonl")


def report() -> tuple[str, bool]:
    from checker.entail_pairs_v2 import all_pairs

    live = {p.id: p for p in all_pairs()}
    frozen = {}
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            frozen[r["pair_id"]] = r

    drifted, gone, label_moves = [], [], []
    for pid, rec in frozen.items():
        p = live.get(pid)
        if p is None:
            gone.append((pid, rec["label"]))
            continue
        got = "sha256:" + hashlib.sha256(p.source_span.encode()).hexdigest()
        if got != rec["source_span_hash"]:
            drifted.append((pid, rec["label"], p.section, p.subsection,
                            len(p.source_span)))
        if p.label != rec["label"]:
            label_moves.append((pid, rec["label"], p.label))

    added = sorted(set(live) - set(frozen))

    L = ["=" * 76,
         "BENCHMARK RE-FREEZE — REQUEST FOR AUTHORISATION",
         "=" * 76, "",
         f"  frozen pairs        : {len(frozen)}",
         f"  spans drifted       : {len(drifted)}",
         f"  frozen but now gone : {len(gone)}",
         f"  gold labels moved   : {len(label_moves)}",
         f"  in generator only   : {len(added)}", ""]

    if drifted:
        L += ["  SPANS THAT MOVED, and where they moved to", ""]
        by = Counter((d[2], d[3], d[4]) for d in drifted)
        for (sec, sub, ln), n in sorted(by.items()):
            L.append(f"    {n:>3} pair(s)  s.{sec}({sub})  premise now {ln} chars")
        L += ["",
              "  Both moves are corrections already made and justified:",
              "    s.96  — the 400-character truncation cut inside the first",
              "            proviso, so a premise did not contain the evidence",
              "            for its own ENTAILED label.",
              "    s.174 — the two-thirds pairs belong to sub-section (3), not",
              "            (1), and (3) now has a precise span.", ""]

    if label_moves:
        L += ["  GOLD LABELS THAT WOULD MOVE — read every one before deciding", ""]
        for pid, was, now in label_moves:
            L.append(f"    {pid:<24} {was}  ->  {now}")
        L.append("")

    if gone:
        L += ["  FROZEN PAIRS THE GENERATOR NO LONGER PRODUCES", ""]
        for pid, lab in gone:
            L.append(f"    {pid:<24} was {lab}")
        L.append("")

    if added:
        L += [f"  PAIRS THE GENERATOR HAS THAT THE FREEZE DOES NOT ({len(added)})", ""]
        for pid in added[:8]:
            L.append(f"    {pid}")
        if len(added) > 8:
            L.append(f"    …and {len(added) - 8} more")
        L.append("")

    safe = not label_moves and not gone
    L += ["-" * 76]
    if safe:
        L += ["  No gold label moves and no pair disappears. The change is to",
              "  source-span text only, in the direction of the corrections",
              "  already reviewed.", ""]
    else:
        L += ["  THIS IS NOT A SPAN-ONLY CHANGE. Labels move or pairs vanish, and",
              "  each one is a separate judgement that a claim's gold answer is",
              "  different from what was frozen. Do not authorise in bulk.", ""]

    L += ["  To authorise:",
          "    PYTHONPATH=. python3 -c \"from checker.benchmark_v2_freeze import "
          "freeze; freeze(promote=True)\"",
          "",
          "  Until then the gate reports BENCHMARK DRIFT and certifies nothing,",
          "  which is the correct behaviour and is also a standstill.",
          "=" * 76]
    return "\n".join(L), safe


def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("benchmark_refreeze_request")
    before = FROZEN.read_bytes()
    text, safe = report()

    check(FROZEN.read_bytes() == before, "the report writes nothing")
    check("REQUEST FOR AUTHORISATION" in text, "it asks rather than acts")
    check("spans drifted" in text, "it counts the drift")
    check("gold labels moved" in text, "it counts label movement separately")
    check("Do not authorise in bulk" in text or safe,
          "an unsafe change is called out")
    check("promote=True" in text, "it states the exact command to authorise")
    check("certifies nothing" in text, "it states what the standstill costs")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    text, _ = report()
    print(text)
