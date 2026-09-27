#!/usr/bin/env python3
"""Every path an ACTIVE document cites must exist on disk.

## Why this exists

On 27-09-2026 a sweep found **78 referenced paths that did not exist** across this
repository's Markdown. The worst of them were not merely stale, they were instructions:

  * `/build`, `/fix`, `/loop` and `/start` each told an agent to run `python3
    scripts/verify.py`. That file had not existed for weeks. The oracle is
    `scripts/verify_green.sh`.
  * The same commands told an agent that when a bug escapes it must "add a check to
    `scripts/verify.py` with its story in `because=`". There is no such file and
    `because=` appears in **zero** `.py` files here, so an agent obeying that had to
    INVENT a central check file and a parameter convention to comply.
  * `docs/BUILD_CONTEXT.md` -- which opens "Constraints an agent must load before
    touching this repository" -- described a rule "enforced in three places", two of
    which were gone.
  * `.claude/agents/developer.md` told the agent to stop if a task had no `Track:`
    field. Nothing has ever produced that field, so it refused every real task.

A document listing those findings would rot the same way. **This is the invariant
version.** `docs/DOC_DEBT_2026_09_27.md` is its narrative; this file is what holds.

## The distinction that makes this checkable

Not every missing path is a defect. `docs/RETIRED_POSH.md` cites the script it retired.
`docs/RETRACTIONS.md` cites a withdrawn plan. `docs/CLAIMS_LEDGER.md` records what was
true on its own date and says in terms that its denominator "must not be quietly restated
later". **Those references are correct, and editing them would destroy this repository's
memory of its own corrections** -- a find-and-replace across `*.md` is the failure mode,
not the fix.

So the rule is not "no missing paths". It is: **a document that speaks in the present
tense must not cite something that does not exist.** HISTORY_FILES and HISTORY_PREFIXES
name the documents that speak in the past tense.

## Why an allow-list here cannot quietly become permissive

Three ratchets, because an allow-list that only ever grows is how a check dies:

  1. Every KNOWN_DEBT entry must STILL dangle. Fix the document and this test fails
     until you delete the entry, so the list cannot hold stale exemptions.
  2. Every KNOWN_DEBT and HISTORY_FILES entry must name a document that EXISTS. Delete
     the document and the dead exemption is reported.
  3. KNOWN_DEBT is keyed on (document, path) pairs, never on a document alone. Exempting
     `TODAY.md` for one bad path does not exempt its next one.

Run:  python3 scripts/check_doc_refs.py            # report
      python3 scripts/check_doc_refs.py --test     # self-tests + the live scan (the gate)
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories that are not this repository's documentation.
SKIP_DIRS = (".claude/worktrees", ".git", "node_modules", "__pycache__")

# Paths belonging to ANOTHER repository, a build output, or an illustrative shape.
# Resolving these against our filesystem would report a miss that means nothing.
NOT_OURS = (
    "http", "~",
    "Placedon-law-business-plan/", "bizplan/", "3300/",          # other repos
    "src/", "app/", "frontend/", "content/", "shared/",          # the frontend repo
    "backend/engine", "backend/routers", "backend/models", "backend/tests",
    "docs/specs/",                                               # frontend docs
    "fixtures/", "metadata/", "ux/", "scratchpad/", "feeds/", "memory/",
    "s185/", "register_gsr700e/",                                # illustrative globs
)

# Documents that speak in the PAST tense. A missing path here is the record working.
HISTORY_FILES = (
    "docs/RETIRED_POSH.md",        # names what it retired
    "docs/RETRACTIONS.md",         # names what was withdrawn
    "docs/CLAIMS_LEDGER.md",       # dated entries; its denominators are fixed
    "docs/SOURCE_DEFECTS.md",      # defects as found
    "docs/DOC_DEBT_2026_09_27.md", # the narrative this file replaces; cites the misses
    "docs/REPO_AUDIT_2026_09_27.md",
    ".claude/memory/LESSONS.md",   # cites the file each incident happened in
    ".claude/memory/SPEC_ERRATA.md",
    "research/TASKS.md",           # closed rows name what they touched
)

# Whole trees of dated artifacts: research passes, loop runbooks, phase reports.
HISTORY_PREFIXES = ("docs/research/", ".claude/plans/", ".claude/loops/")

# A filename carrying a date is a dated artifact wherever it lives.
DATED = re.compile(r"20\d\d[-_]\d\d[-_]\d\d")

KNOWN_DEBT = {
    # Known debt, 27-09-2026. **This list may only shrink.** Twelve entries were removed the
    # day it was written, because writing the check found and fixed them -- docs/BUILD_CONTEXT.md
    # went from six to zero. Each entry below is a real defect in a present-tense document,
    # left because fixing it means REWRITING the document rather than swapping a path, and a
    # rewrite is a judgement someone has to make.
    #
    # If you are naming a path in order to say it no longer exists, do not backtick it. A
    # backticked path is read here as a live reference. That is the escape hatch, and it is
    # better than an exemption because it cannot go stale.

    # Describes an architecture with a POSH corpus and an api/ entry point. POSH is a retired
    # product direction that checker/scope.py refuses by name. Needs rewriting, not repointing.
    (".claude/memory/ARCHITECTURE.md", "checker/app.py"),
    (".claude/memory/ARCHITECTURE.md", "api/index.py"),
    (".claude/memory/ARCHITECTURE.md", "scripts/ingest_posh.py"),
    (".claude/memory/ARCHITECTURE.md", "corpus/provisions/posh_act_2013.json"),

    # A stale daily note presenting itself as today -- the highest confusion-per-line in the
    # repository. Either regenerate it or delete it; there is nothing to repoint.
    (".claude/today/TODAY.md", "docs/PLAN.md"),
    (".claude/today/TODAY.md", "docs/LAWYER_BRIEF.md"),
    (".claude/today/TODAY.md", "docs/WHERE_WE_ARE.md"),
    (".claude/today/TODAY.md", "scripts/check_transcription.py"),
    (".claude/today/TODAY.md", "scripts/verify.py"),

    # Prose describing the retired verification ratchet, and a budget file, as current.
    (".claude/memory/FEATURES.md", "scripts/verify.py"),
    (".claude/memory/FEATURES.md", "scripts/review_pack.py"),
    (".claude/memory/API_BUDGET.md", "scripts/verify.py"),
    (".claude/memory/API_BUDGET.md", "backend/.budget.json"),
    (".claude/INDEX.md", "checker/ratelimit.py"),
    (".claude/memory/CODING_CONVENTIONS.md", "checker/rules.py"),
    ("docs/FAILURE_MODES.md", "api/index.py"),
    ("docs/FAILURE_MODES.md", "scripts/retry_blocked_sources.py"),
    ("docs/FAILURE_MODES.md", "corpus/.budget.json"),

    # Modules built under other names. checker/retrieval.py became checker/text_search.py and
    # checker/dense_index.py; the others need someone to confirm the mapping before it is written.
    ("docs/COMPETITOR_PATTERN_ANALYSIS.md", "checker/retrieval.py"),
    ("docs/COMPETITOR_PATTERN_ANALYSIS.md", "docs/CLAUDE.md"),
    ("docs/PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md", "checker/pages.py"),
    ("docs/PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md", "checker/intake.py"),
    ("docs/LOOP_INTELLIGENCE_V0.md", "checker/pending.py"),

    # PLAN 20 cites docs/BUSINESS_PLAN.md, which is in the PUBLIC repo, not this one. Fixing it
    # means editing PLAN 20's preamble, which is a live product document -- founder's call.
    ("docs/PLAN_20_INHOUSE_CORPORATE.md", "docs/BUSINESS_PLAN.md"),

    # PLAN 19 decision records annotating a spec that lives on origin/main, not this branch.
    # The fix is a merge, not an edit. See docs/REPO_AUDIT_2026_09_27.md.
    ("docs/plan19/decisions/G0_1_INSTRUMENT_REGISTRY.md", "corpus/sources/index.json"),
    ("docs/plan19/decisions/M13_DERIVATION.md", "scripts/revocation_report.py"),
    ("docs/plan19/decisions/M13_DERIVATION.md", "docs/plan19/04_MATHS_AND_ALGORITHMS.md"),
}

# A backticked path, and a shell-invoked script. The second matters most: it is the
# category that actually broke, and it is never inside backticks.
_QUOTED = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|sh|json|md|ts|tsx))`")
_INVOKED = re.compile(r"(?:python3 |bash |\./)((?:scripts|checker|backend|eval)/"
                      r"[A-Za-z0-9_/]+\.(?:py|sh))")


def is_history(doc: str) -> bool:
    """True when the document speaks in the past tense, so a missing path is correct."""
    return (doc in HISTORY_FILES
            or doc.startswith(HISTORY_PREFIXES)
            or bool(DATED.search(os.path.basename(doc))))


def references(text: str) -> set[str]:
    """Every repo-relative path a document cites, excluding what is not ours.

    A bare filename with no directory is skipped: `README.md` is ambiguous across a
    repository this size, and resolving it would produce misses that mean nothing.
    """
    found = set(_QUOTED.findall(text)) | set(_INVOKED.findall(text))
    return {m for m in found
            if "/" in m and not m.startswith(NOT_OURS)}


def markdown_files(root: str) -> list[str]:
    out = []
    for cur, dirs, files in os.walk(root):
        rel_cur = os.path.relpath(cur, root).replace(os.sep, "/")
        rel_cur = "" if rel_cur == "." else rel_cur
        dirs[:] = [d for d in dirs
                   if not ((rel_cur + "/" + d).lstrip("/")).startswith(SKIP_DIRS)]
        for fn in files:
            if fn.endswith(".md"):
                rel = os.path.join(rel_cur, fn).replace(os.sep, "/").lstrip("/")
                out.append(rel)
    return sorted(out)


def dangling(root: str = ROOT) -> set[tuple[str, str]]:
    """(document, path) for every path an ACTIVE document cites that does not exist."""
    bad = set()
    for doc in markdown_files(root):
        if is_history(doc):
            continue
        try:
            with open(os.path.join(root, doc), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for path in references(text):
            if not os.path.exists(os.path.join(root, path)):
                bad.add((doc, path))
    return bad


def report(root: str = ROOT) -> int:
    bad = dangling(root)
    new = sorted(bad - KNOWN_DEBT)
    fixed = sorted(KNOWN_DEBT - bad)
    # Written first as a set expression; `-` binds tighter than `|` in Python, so
    # `A | B - C` is `A | (B - C)` and the KNOWN_DEBT half went unfiltered. Existence on
    # disk is the only question here, so ask it directly.
    allow_listed = {d for d, _ in KNOWN_DEBT} | set(HISTORY_FILES)
    missing_docs = sorted(d for d in allow_listed
                          if not os.path.exists(os.path.join(root, d)))

    print(f"active documents scanned : {sum(1 for d in markdown_files(root) if not is_history(d))}")
    print(f"dangling references      : {len(bad)}  (known debt {len(KNOWN_DEBT)})")

    if new:
        print(f"\nNEW dangling references -- {len(new)}. An active document cites a path that")
        print("does not exist. Fix the path, or the document, or move the claim into the past tense.")
        for doc, path in new:
            print(f"  {doc}\n      -> {path}")
    if fixed:
        print(f"\n{len(fixed)} KNOWN_DEBT entries no longer dangle. **Delete them from KNOWN_DEBT**")
        print("in scripts/check_doc_refs.py -- a stale exemption is how this check stops working.")
        for doc, path in fixed:
            print(f"  {doc}\n      -> {path}")
    if missing_docs:
        print(f"\n{len(missing_docs)} allow-list entries name a document that no longer exists:")
        for d in missing_docs:
            print(f"  {d}")

    if not (new or fixed or missing_docs):
        print("\nOK -- no active document cites a path that does not exist.")
        return 0
    return 1


def _test() -> None:
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    # ── what counts as a reference ────────────────────────────────────────────
    check(references("see `docs/A.md` now") == {"docs/A.md"},
          "a backticked repo path is a reference")
    check(references("run `python3 scripts/verify.py` to check") == {"scripts/verify.py"},
          "a shell-invoked script is a reference -- the category that actually broke")
    check(references("run\n./scripts/verify_green.sh\n") == {"scripts/verify_green.sh"},
          "...and it is found OUTSIDE backticks, which is where it lived")
    check(references("`README.md`") == set(),
          "a bare filename is skipped: ambiguous in a repo this size")
    check(references("`src/app/page.tsx` and `3300/AGENTS.md`") == set(),
          "another repository's paths are not ours to resolve")
    check(references("`docs/A.md` §2 and `docs/B.md`") == {"docs/A.md", "docs/B.md"},
          "a section suffix after the closing backtick does not break the path")
    check("checker/x.py" in references("import from `checker/x.py` please"),
          "checker/ paths are in scope")

    # ── the active / history distinction ─────────────────────────────────────
    check(is_history("docs/RETIRED_POSH.md"), "an explicit history file is history")
    check(is_history("docs/research/ANYTHING.md"), "a dated research tree is history")
    check(is_history("docs/LOOP_THEMIS_20_MOVES_2026_09_17.md"),
          "a dated filename is history wherever it lives")
    check(not is_history("docs/BUILD_CONTEXT.md"),
          "a constraints file is ACTIVE -- it is read as a guarantee")
    check(not is_history(".claude/commands/build.md"),
          "a slash command is ACTIVE -- an agent executes it")
    check(not is_history(".claude/today/TODAY.md"),
          "a stale daily note is ACTIVE, not history: it presents itself as today")

    # ── the scan itself, on a synthetic tree ─────────────────────────────────
    # A real dangling reference must be FOUND, and the same reference inside a history
    # document must NOT be. Both halves, because either alone passes a broken scanner.
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "docs"))
        os.makedirs(os.path.join(tmp, "scripts"))
        with open(os.path.join(tmp, "scripts/real.py"), "w") as fh:
            fh.write("# exists\n")
        with open(os.path.join(tmp, "docs/ACTIVE.md"), "w") as fh:
            fh.write("run `scripts/real.py` and `scripts/ghost.py`\n")
        with open(os.path.join(tmp, "docs/RETIRED_POSH.md"), "w") as fh:
            fh.write("we deleted `scripts/ghost.py`\n")
        found = dangling(tmp)
        check(("docs/ACTIVE.md", "scripts/ghost.py") in found,
              "a dangling reference in an ACTIVE document is caught")
        check(("docs/ACTIVE.md", "scripts/real.py") not in found,
              "...and a path that exists is not reported")
        check(("docs/RETIRED_POSH.md", "scripts/ghost.py") not in found,
              "...while the SAME path in a history document is left alone")
        check(len(found) == 1, "nothing else is invented")

        # The check must go RED on a new reference. This is the mutation: if this
        # passed while the scanner was broken, the whole file would be decoration.
        with open(os.path.join(tmp, "docs/NEW.md"), "w") as fh:
            fh.write("see `docs/NEVER_WRITTEN.md`\n")
        check(("docs/NEW.md", "docs/NEVER_WRITTEN.md") in dangling(tmp),
              "a NEWLY added dangling reference is caught -- the ratchet bites")

    # ── the allow-list cannot quietly rot ───────────────────────────────────
    live = dangling()
    stale = sorted(KNOWN_DEBT - live)
    check(not stale,
          f"every KNOWN_DEBT entry still dangles (else delete it): {stale[:3]}")
    dead = sorted(d for d in ({d for d, _ in KNOWN_DEBT} | set(HISTORY_FILES))
                  if not os.path.exists(os.path.join(ROOT, d)))
    check(not dead, f"every allow-listed document still exists: {dead[:3]}")
    check(all("/" in p for _, p in KNOWN_DEBT),
          "no KNOWN_DEBT entry is a bare filename the scanner would never emit")

    # ── and the live invariant, which is the point of being in the gate ──────
    new = sorted(live - KNOWN_DEBT)
    check(not new,
          f"NO active document cites a path that does not exist ({len(new)} new: {new[:3]})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        raise SystemExit(report())
