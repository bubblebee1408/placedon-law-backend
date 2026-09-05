#!/usr/bin/env python3
"""Render the fixture review table to markdown. Decides nothing, writes no label."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.review_table import build

OUT = Path("docs/FIXTURE_REVIEW.md")


def render() -> str:
    rows = build()
    L = ["# Fixture review — 11 proposals",
         "",
         "Candidate replacements for benchmark fixtures invalidated under the",
         "fail-closed convention. **Nothing here has been applied and no gold label",
         "has been changed.** Each row records what the original claimed, the premise",
         "it rests on, every qualifier the provision carries, which the replacement",
         "restores and which it still omits.",
         "",
         "The recommendation is a reading of the accounting beneath it, not a decision.",
         "",
         "| # | ID | Provision | Action | Qualifiers still missing | Near-duplicate |",
         "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        m = ", ".join(f"`{q.kind}`" for q in r.missing) or "—"
        d = ", ".join(f"`{x}`" for x in r.near_duplicates) or "—"
        L.append(f"| {i} | `{r.proposal_id}` | s.{r.section}({r.subsection}) | "
                 f"**{r.recommendation}** | {m} | {d} |")

    for i, r in enumerate(rows, 1):
        L += ["", "---", "",
              f"## {i}. `{r.proposal_id}` — s.{r.section}({r.subsection}) — {r.recommendation}",
              "",
              f"**Supersedes** `{r.supersedes}`  ",
              f"**Defect** {r.defect}", "",
              "**Original claim**", "", f"> {r.original_claim}", "",
              "**Proposed replacement**", "", f"> {r.replacement_claim}", "",
              "**Supporting premise** — served text, verbatim, not repaired", "",
              f"> {r.supporting_premise}", "",
              "**Qualifier accounting**", "",
              "| kind | trigger in source | status | note |", "|---|---|---|---|"]
        for q in r.qualifiers:
            L.append(f"| `{q.kind}` | {q.trigger} | **{q.status}** | {q.why} |")
        if r.near_duplicates:
            L += ["", f"**Near-duplicate of** {', '.join(r.near_duplicates)}."]
        if r.transcription_warnings:
            L += ["", "**Source transcription warnings**", ""]
            L += [f"- {w}" for w in r.transcription_warnings]
        L += ["", f"**Recommendation — {r.recommendation}.** {r.reason}"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT} ({len(render().splitlines())} lines)")
