---
description: Research only. No code.
argument-hint: [topic]
---

# /research $ARGUMENTS

No code will be written. The output is a finding in `RESEARCH_LOG.md`.

## 1. Ask ourselves first

```bash
python3 scripts/search_memory.py --memory "$ARGUMENTS"
```

## 2. Then the world — primary sources only

Order matters: **the bare Act or the Gazette** → an official portal → everything else. A legal
news site reproducing a notification is a secondary source and must be recorded as one
(`corpus/provisions/companies_accounts_rules_2014.json` shows the shape).

Spawn **`market-researcher`** or **`hr-ops-researcher`** by track.

## 3. Write it up honestly

Required sections: **Verdict / Confidence / Evidence / Contradictions found / What this means for
the product / Open questions.**

Rules that are not negotiable:

- **A failed search is a finding.** Record it as INCONCLUSIVE. Do not pad with vendor content
  marketing — that is what a company selling HRMS says its product fixes, not evidence of demand.
- **Never invent a number.** If it cannot be derived, say it cannot be derived and say why.
- **Consistency across secondary sources is not truth.** Every source states the PoSH ten-employee
  threshold as though s.4 contained it. It does not. Agreement usually means a shared upstream.
- **Tag the track** — `[TRACK: compliance]`, `[TRACK: operations]`, `[TRACK: market]`. `/loop`
  refuses to build on a track with no tagged evidence.
- **Record findings that contradict the plan at least as carefully as findings that support it.**

## 4. Recommend, do not build

End with what this changes and what it costs. If it changes nothing, say that.
