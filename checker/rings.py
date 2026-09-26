"""The one-way firewall between the legal core and the forecasting layers.

## The architecture this enforces

`docs/PLAN_08_BOOKMARK_AND_GODSEYE.md` §2 declares four rings:

    RING 0  LEGAL CORE      statute, obligations, deciders, currency, entailment
    RING 1  BOOKMARK        entity graph (CIN/DIN), public registers, event log
    RING 2  FEEDS           observations from named live sources
    RING 3  INFERENCE       ordinal assessments; numeric estimates only if calibrated

A module in ring N may import from rings below it. **No Ring 0 decider may
import, read, or receive any value originating in Ring 2 or Ring 3. Same for
Ring 1.** A forecast may never be an input to a deterministic legal decision.
Ring 2 and Ring 3 are currently EMPTY — no God's Eye or inference module has
been built yet (PLAN_08 §3: the release chokepoint has to land first) — so this
guard currently has nothing to catch. That is expected, and the guard has to
keep working (not error, not vacuously report "clean" for the wrong reason)
right up to the day a Ring 2 module is registered.

## Why structural, not conventional

The product's whole claim is that a wrong model cannot make the product wrong.
That property is what a probability leaking into an applicability decision
destroys — and it destroys it **silently**, because the output of a corrupted
Ring 0 decider still looks exactly like a deterministic legal answer. There is
no downstream symptom to notice. A code-review convention ("please don't
import checker.godseye in a decider") relies on every future diff being read
by someone who remembers the rule; an AST walk does not forget.

`checker/api.py:858-859` already does the structural version of this for a
narrower claim — it parses its own module with `ast` and asserts the parsed
import roots exclude `openai`/`anthropic`/`requests`/`httpx`, rather than
trusting a comment that says "no model calls here". This module is the same
technique pointed at the ring boundary instead of the network boundary.

## Why the walk covers nested imports, not just the top of the file

`ast.walk` descends into every function and method body, not just module
level. That is deliberate: an import deferred inside a function is the
**normal, legitimate** style already used all over this codebase for
lower-ring dependencies (`checker/cascade.py` imports `checker.entail_baseline`
inside a function, `checker/obligations.py` imports `checker.s185` inside a
function) to avoid import cycles. The same mechanism is exactly how an
upward leak would be hidden — an import at module level is what a reviewer's
eye catches; a `import checker.godseye.feed` on line 800 of a 60-line function
is not. A guard that only scanned top-level imports would miss precisely the
case it exists for.

## The negative control

A guard that has never been shown to fail is not evidence that it works — it
is evidence that nobody has tried. This repository has already lost real time
to exactly that shape of mistake, twice: `harness_regression.sh` exists
because a green check once turned out to be a check that could not turn red,
and `docs/D002_CLOSURE_REPORT_2026_09_17.md` §2.1 records that
`pdf_text.py`'s only wired-in test fixture was the one corpus document
structurally immune to the bug it was meant to catch — "a green check that
cannot fail... a test whose fixture cannot exhibit the defect is not
evidence, and the harness cannot tell the difference." `_test()` below does
not just assert the real codebase is clean; it first builds a synthetic
module that DOES import a (temporarily registered) Ring 2 module from inside
a function, and asserts `violations()`'s underlying scan catches it. Only
after the guard has been shown capable of failing does its clean run on the
real codebase count as evidence of anything.

## Classifying imports, not files

`ring_of` takes a module's **import name** (`"checker.currency"`, or
`"applicability"` for a root-level module, or the file-path spelling
`"checker/currency.py"` — both normalise to the same key) rather than a raw
file path, because the thing that can leak is an import statement, and
Python import statements name modules, not files. `from checker import
event_log` and `from checker.event_log import Answer` must both resolve to
the same registry key even though they parse to different AST shapes; see
`_imported_names` for how `ast.ImportFrom` is normalised to cover both.
"""
from __future__ import annotations

import ast
from pathlib import Path

RING_0 = 0   # LEGAL CORE — statute, obligations, deciders, currency, entailment
RING_1 = 1   # BOOKMARK — entity graph (CIN/DIN), public registers, event log
RING_2 = 2   # FEEDS — observations from named live sources
RING_3 = 3   # INFERENCE — ordinal assessments; numeric estimates only if calibrated

RING_NAMES = {
    RING_0: "RING 0 LEGAL CORE",
    RING_1: "RING 1 BOOKMARK",
    RING_2: "RING 2 FEEDS",
    RING_3: "RING 3 INFERENCE",
}

REPO_ROOT = Path(__file__).resolve().parent.parent

# Declared, not inferred. Registry keys are import names, exactly as they would
# appear on the right-hand side of `import` / `from ... import` in this
# codebase's own style (`checker.currency`, or bare `applicability` for a
# root-level module such as `applicability.py`).
REGISTRY: dict[str, int] = {
    # ── RING 0 — statute, obligations, deciders, currency, entailment ──────
    "applicability": RING_0,
    "checker.obligations": RING_0,
    "checker.instrument_registry": RING_0,  # pointers to the register scripts; PLAN_19 G0.1
    "checker.s180": RING_0,             # borrowing-limit decider, same family as s185/6/8
    "checker.s184": RING_0,             # director-interest decider, same family as s185/6/8
    "checker.s185": RING_0,
    "checker.s186": RING_0,
    "checker.s188": RING_0,
    "checker.s188_threshold": RING_0,
    "checker.currency": RING_0,
    "checker.cascade": RING_0,
    "checker.ground_span": RING_0,
    "checker.as_of": RING_0,
    "checker.amendment": RING_0,
    "checker.prescribed_thresholds": RING_0,
    "checker.entail_baseline": RING_0,
    "checker.entail_binding": RING_0,
    "checker.entail_mine": RING_0,
    "checker.entail_pairs_v2": RING_0,
    "checker.entail_paraphrase": RING_0,
    "checker.entail_qualifier": RING_0,
    "checker.entail_role": RING_0,
    "checker.admission": RING_0,
    "checker.provenance": RING_0,

    # ── RING 1 — entity graph, public registers, event log ─────────────────
    "checker.entity_graph": RING_1,
    "checker.ontology": RING_1,          # typed objects; PLAN_19 G1.1
    "checker.observation_store": RING_1, # append-only bitemporal store; PLAN_19 G1.2
    "checker.derivation": RING_1,        # evidence semiring; PLAN_19 G2.1
    "checker.event_log": RING_1,
    "checker.corporate_data": RING_1,
    "checker.mca_aggregator": RING_1,
    "checker.mca_snapshot": RING_1,

    # ── RING 2 — the Operation Model: reads observations and the register,
    #    produces work, decides nothing. THEMIS V0 milestone 6.
    "checker.operations": RING_2,
    # ── RING 2 — persistence for the Operation Model, plus evidence submission.
    #    THEMIS V0 milestones 5 and 6. Reads operations and writes local state
    #    under corpus/.operations/; decides nothing about the law.
    "checker.operation_store": RING_2,

    # ── RING 2 — FEEDS. Classified by PACKAGE below, not listed here. ──────
    # ── RING 3 — INFERENCE. Deliberately empty; see the module docstring. ──
}

# Whole packages whose every module belongs to one ring, by construction.
#
# Why a package rule and not more REGISTRY lines: REGISTRY matches exactly. When
# `checker/feeds/` landed (2026-09-17), an exact-match-only guard had a hole — the
# day someone adds `checker/feeds/mca_defaulters.py` and forgets to register it, a
# Ring 0 decider could import it and `ring_of()` would return None, which this guard
# deliberately never flags. A forgotten registry line would silently disable the
# firewall for exactly the modules it exists to fence. So a feed is Ring 2 because
# of WHERE it lives, and cannot escape by being forgotten.
#
# The same applies to importing the package itself: `from checker.feeds import
# Observation` names `checker.feeds`, which no submodule entry would match.
PACKAGE_RINGS: dict[str, int] = {
    "checker.feeds": RING_2,
    # The MCP surface: read-only tools over the engine, reachable by an agent.
    # Ring 2 for the same reason feeds are -- a Ring 0 decider must never import it.
    "checker.mcp": RING_2,
}


def _normalise(module_path: str) -> str:
    """`"checker/currency.py"` and `"checker.currency"` are the same module."""
    dotted = module_path[:-3] if module_path.endswith(".py") else module_path
    return dotted.replace("/", ".").replace("\\", ".")


def ring_of(module_path: str) -> int | None:
    """The ring a module belongs to, or None if it is unclassified.

    None is not an error. Most of this repository — `scripts/`, `eval/`,
    third-party packages — is neither Ring 0 nor Ring 1 and has no business
    being forced into this vocabulary; only the modules PLAN_08 §2 actually
    names are classified, plus the same-family deciders noted above.

    An exact REGISTRY entry wins. Otherwise the longest PACKAGE_RINGS prefix
    decides, matched on whole dotted segments -- so `checker.feeds.ofac_sdn`
    is Ring 2, while a hypothetical `checker.feedsX` is not.
    """
    name = _normalise(module_path)
    if name in REGISTRY:
        return REGISTRY[name]
    best, best_len = None, -1
    for pkg, ring in PACKAGE_RINGS.items():
        if (name == pkg or name.startswith(pkg + ".")) and len(pkg) > best_len:
            best, best_len = ring, len(pkg)
    return best


def _imported_names(tree: ast.AST, importer: str) -> list[tuple[str, int]]:
    """Every dotted module name imported anywhere in `tree`, with its line.

    Walks the WHOLE tree via `ast.walk`, so an import nested inside a function
    or method is found exactly as reliably as one at module level — that is
    exactly how a leak would be hidden (see the module docstring).

    `from checker import event_log` and `from checker.event_log import X` are
    both normalised to the module name `checker.event_log`, by combining the
    `from`-clause with each imported name as well as recording the bare
    `from`-clause itself; a relative import (`from . import x`) is resolved
    against `importer`'s own package rather than skipped, so switching an
    absolute import to a relative one cannot dodge the check.
    """
    found: list[tuple[str, int]] = []
    importer_parts = importer.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                pkg_parts = importer_parts[:-node.level] if node.level <= len(importer_parts) else []
                base = ".".join(pkg_parts)
                module = f"{base}.{node.module}" if node.module else base
            else:
                if node.module is None:
                    continue
                module = node.module
            found.append((module, node.lineno))
            for alias in node.names:
                found.append((f"{module}.{alias.name}", node.lineno))
    return found


def _leaks_upward(tree: ast.AST, importer: str, ring: int) -> list[tuple[str, int, int]]:
    """`(imported module, its ring, line)` for every FORBIDDEN import in `tree`.

    Only Ring 0 and Ring 1 importers are constrained at all — imports flowing
    downward or sideways within the allowed direction are never flagged. An
    import target that is not registered (`ring_of` returns None) is never
    flagged either: this guard enforces one declared rule, it does not invent
    opinions about the rest of the codebase.
    """
    if ring not in (RING_0, RING_1):
        return []
    out: list[tuple[str, int, int]] = []
    for imported, lineno in _imported_names(tree, importer):
        target = ring_of(imported)
        if target in (RING_2, RING_3):
            out.append((imported, target, lineno))
    return out


def _file_for(dotted: str) -> Path:
    return REPO_ROOT / (dotted.replace(".", "/") + ".py")


# Dynamic-import machinery. The AST walk sees `ast.Import`/`ast.ImportFrom` and
# nothing else, so `importlib.import_module("checker.feeds.ofac_sdn")`,
# `__import__(name)`, `sys.modules[...]` and `exec()` all reach Ring 2 with no
# import node at all (red team RT-01). Their ARGUMENT is often computed, so no
# static check can resolve where they lead. What a checker CAN do is refuse to
# certify a decider that carries the machinery: in a Ring 0 or Ring 1 module these
# have no legitimate use, and the repo has none today (asserted by _test()).
_DYNAMIC_CALLS = {"__import__", "eval", "exec", "import_module"}


def _dynamic_import_uses(tree: ast.AST) -> list[tuple[str, int]]:
    """`(construct, line)` for every dynamic-import CALL in a module's AST.

    Detected from the syntax tree, never from the text: a line-based scan flagged
    the prose "Pure function, no I/O, no eval()" in `applicability.py`'s docstring
    and would have taught everyone to ignore this check.

    A module's own `_test()` is exempt. `checker/entail_binding.py` reads its own
    source with `__import__("pathlib")` inside its test, which is a self-check, not
    a decision path -- and a rule that fires on tests is a rule people route around.
    """
    out: list[tuple[str, int]] = []
    test_spans = [(n.lineno, getattr(n, "end_lineno", n.lineno))
                  for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_test"]

    def in_test(lineno: int) -> bool:
        return any(a <= lineno <= b for a, b in test_spans)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = (f.id if isinstance(f, ast.Name)
                    else f.attr if isinstance(f, ast.Attribute) else "")
            if name in _DYNAMIC_CALLS and not in_test(node.lineno):
                out.append((f"{name}()", node.lineno))
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            v = node.value
            if v.attr == "modules" and isinstance(v.value, ast.Name) and v.value.id == "sys" \
                    and not in_test(node.lineno):
                out.append(("sys.modules[...]", node.lineno))
    return out


def _reachable_unregistered(dotted: str, seen: set[str] | None = None) -> set[str]:
    """Local, UNREGISTERED modules a module imports, transitively.

    RT-02: `violations()` checked only direct imports, so any unregistered helper
    was an invisible laundering hop -- a decider imports `helpers`, `helpers`
    imports a feed, and the guard saw nothing. The closure is walked through
    unregistered local modules only; a registered one is judged on its own ring,
    which is the whole point of registering it.
    """
    seen = set() if seen is None else seen
    path = _file_for(dotted)
    if not path.is_file():
        return seen
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return seen
    for imported, _lineno in _imported_names(tree, dotted):
        if ring_of(imported) is not None or imported in seen:
            continue
        if not _file_for(imported).is_file():
            continue                      # stdlib or third party: not ours to walk
        seen.add(imported)
        _reachable_unregistered(imported, seen)
    return seen


def violations() -> list[str]:
    """Every real Ring 0/1 module that imports Ring 2 or 3, named with a witness.

    A verdict with no witness is unusable: each entry names the offending
    module, the exact import, and the line it appears on, so the fix is
    "delete this line" rather than "go audit everything". Returns `[]` when
    the firewall holds — which, with Ring 2 and Ring 3 currently empty, is
    the only possible outcome, and this function still walks every declared
    Ring 0/1 module's real AST to say so rather than asserting it by
    construction.
    """
    out: list[str] = []
    for dotted, ring in sorted(REGISTRY.items()):
        if ring not in (RING_0, RING_1):
            continue
        path = _file_for(dotted)
        if not path.is_file():
            out.append(f"{dotted}: registered at ring {ring} but no source file at {path}")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(REPO_ROOT)
        for imported, target, lineno in _leaks_upward(tree, dotted, ring):
            out.append(
                f"{rel}:{lineno} — {dotted} ({RING_NAMES[ring]}) imports "
                f"{imported} ({RING_NAMES[target]})"
            )
        # RT-01: machinery whose target a static walk cannot resolve.
        for token, lineno in _dynamic_import_uses(tree):
            out.append(
                f"{rel}:{lineno} — {dotted} ({RING_NAMES[ring]}) uses {token!r}: a "
                "dynamic import the ring check cannot follow. Not permitted in a "
                "decider; import statically so the firewall can see it."
            )
        # RT-02: the laundering hop.
        for helper in sorted(_reachable_unregistered(dotted)):
            htree = ast.parse(_file_for(helper).read_text(encoding="utf-8"))
            for imported, target, lineno in _leaks_upward(htree, helper, ring):
                out.append(
                    f"{_file_for(helper).relative_to(REPO_ROOT)}:{lineno} — {dotted} "
                    f"({RING_NAMES[ring]}) reaches {imported} ({RING_NAMES[target]}) "
                    f"through the unregistered module {helper}"
                )
    return out


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("rings")

    # ---- ring_of: both spellings, both real rings, and the unclassified case ----
    check(ring_of("checker.currency") == RING_0, "checker.currency is Ring 0")
    check(ring_of("checker/currency.py") == RING_0, "...and the file-path spelling agrees")
    check(ring_of("applicability") == RING_0, "root-level applicability.py is Ring 0")
    check(ring_of("checker.entity_graph") == RING_1, "checker.entity_graph is Ring 1")
    check(ring_of("checker.lattice") is None, "an unregistered module is unclassified, not defaulted")
    check(ring_of("checker.godseye.no_such_feed") is None,
          "a module that does not exist yet is unclassified, not an error")

    # ---- the task-mandated Ring 0 roster is actually present ---------------------
    required_ring0 = [
        "applicability", "checker.obligations", "checker.s185", "checker.s186",
        "checker.s188", "checker.s188_threshold", "checker.currency", "checker.cascade",
        "checker.ground_span", "checker.as_of", "checker.amendment",
        "checker.prescribed_thresholds", "checker.admission", "checker.provenance",
    ]
    missing = [m for m in required_ring0 if REGISTRY.get(m) != RING_0]
    check(not missing, f"every task-mandated Ring 0 module is registered (missing: {missing})")

    entail_mods = sorted(m for m in REGISTRY if m.startswith("checker.entail_"))
    check(len(entail_mods) >= 6 and all(REGISTRY[m] == RING_0 for m in entail_mods),
          f"the entail_*.py family is registered as Ring 0 ({entail_mods})")

    required_ring1 = [
        "checker.entity_graph", "checker.event_log", "checker.corporate_data",
        "checker.mca_aggregator", "checker.mca_snapshot",
    ]
    missing1 = [m for m in required_ring1 if REGISTRY.get(m) != RING_1]
    check(not missing1, f"every task-mandated Ring 1 module is registered (missing: {missing1})")

    # ---- Ring 2 is now populated, by PACKAGE; Ring 3 is still empty -------------
    # This assertion used to read "Ring 2 and Ring 3 are empty". It changed on
    # 2026-09-17 when checker/feeds/ landed -- updated to the new truth, not
    # deleted, so the file still records what each ring is supposed to hold.
    check(PACKAGE_RINGS.get("checker.feeds") == RING_2, "checker.feeds is Ring 2 as a package")
    check(ring_of("checker.feeds") == RING_2, "importing the feeds PACKAGE itself resolves to Ring 2")
    check(ring_of("checker.feeds.ofac_sdn") == RING_2, "a registered-by-location feed resolves to Ring 2")
    check(ring_of("checker.feeds.not_written_yet") == RING_2,
          "a FUTURE feed nobody remembered to register is still Ring 2 -- the hole this closes")
    check(ring_of("checker/feeds/common/fetch.py") == RING_2, "...in the file-path spelling too")
    check(ring_of("checker.feedsX") is None, "prefix matching is on whole segments, not characters")
    check(not any(r == RING_3 for r in list(REGISTRY.values()) + list(PACKAGE_RINGS.values())),
          "Ring 3 is still empty, as PLAN_08 §2 records")

    # The hole, demonstrated: a Ring 0 decider importing an UNREGISTERED feed.
    sneaky = ast.parse("def decide(c):\n    from checker.feeds.mca_defaulters import hit\n    return hit(c)\n")
    caught = _leaks_upward(sneaky, "checker.s185", RING_0)
    check(bool(caught) and caught[0][1] == RING_2,
          f"a decider importing a never-registered feed is CAUGHT ({caught[:1]})")
    pkg_import = ast.parse("from checker.feeds import Observation\n")
    check(bool(_leaks_upward(pkg_import, "checker.obligations", RING_0)),
          "a decider importing the feeds package itself is CAUGHT")
    empty_upper = violations()
    check(isinstance(empty_upper, list),
          "violations() runs cleanly with both upper rings empty, and does not raise")

    # ---- downward and sideways imports are never flagged -------------------------
    ok_tree = ast.parse(
        "from checker.entity_graph import EntityGraph\n"
        "from checker import provenance\n"
    )
    check(_leaks_upward(ok_tree, "checker.obligations", RING_0) == [],
          "a Ring 0 module importing Ring 1 and Ring 0 is not flagged")

    unclassified_tree = ast.parse("import checker.lattice\n")
    check(_leaks_upward(unclassified_tree, "checker.obligations", RING_0) == [],
          "importing an unclassified module raises no false positive")

    # ---- NEGATIVE CONTROL: prove the guard can actually fail ---------------------
    # A guard never observed to catch anything is not evidence it works — this
    # repo already paid for that mistake once (docs/D002_CLOSURE_REPORT_2026_09_17.md
    # §2.1: a test fixture structurally immune to the bug it guarded). Register a
    # throwaway Ring 2 module, hide the import inside a function exactly the way a
    # real leak would be hidden, and assert the scan finds it.
    synthetic_src = (
        "from __future__ import annotations\n"
        "\n"
        "def compute_applicability(company):\n"
        "    # a forecast smuggled into a decider, one call down\n"
        "    import godseye.fake_feed\n"
        "    return godseye.fake_feed.risk_score(company)\n"
    )
    saved = REGISTRY.get("godseye.fake_feed")
    REGISTRY["godseye.fake_feed"] = RING_2
    try:
        leaks = _leaks_upward(ast.parse(synthetic_src), "checker.fake_decider", RING_0)
    finally:
        if saved is None:
            del REGISTRY["godseye.fake_feed"]
        else:
            REGISTRY["godseye.fake_feed"] = saved
    check(len(leaks) == 1, f"a synthetic Ring 2 import nested inside a function is caught ({leaks})")
    check(bool(leaks) and leaks[0][0] == "godseye.fake_feed" and leaks[0][1] == RING_2,
          "...naming the exact module and its ring")
    check(bool(leaks) and leaks[0][2] == 5,
          f"...and the line it appears on, not just that a leak exists (line {leaks[0][2] if leaks else None})")
    check("godseye.fake_feed" not in REGISTRY,
          "the negative control cleans up after itself — no residue in REGISTRY")

    # ---- a Ring 1 importer is checked with the same rule --------------------------
    saved1 = REGISTRY.get("godseye.fake_feed")
    REGISTRY["godseye.fake_feed"] = RING_2
    try:
        leaks1 = _leaks_upward(ast.parse("import godseye.fake_feed\n"),
                               "checker.entity_graph", RING_1)
    finally:
        if saved1 is None:
            del REGISTRY["godseye.fake_feed"]
        else:
            REGISTRY["godseye.fake_feed"] = saved1
    check(len(leaks1) == 1, f"Ring 1 importing Ring 2 is caught the same way ({leaks1})")

    # ---- a missing source file is reported, not silently skipped -----------------
    REGISTRY["checker.__no_such_ring0_module__"] = RING_0
    try:
        v = violations()
    finally:
        del REGISTRY["checker.__no_such_ring0_module__"]
    check(any("no_such_ring0_module" in x and "no source file" in x for x in v),
          "a registered module whose file is missing is reported, not skipped")

    # ---- the real codebase: run the guard for real, and report what it finds -----
    real = violations()
    check(real == [], f"no Ring 0/1 module in the real codebase imports Ring 2 or 3 ({real})")
    for line in real:
        print(f"  !! VIOLATION: {line}")

    # ---- RT-01: dynamic imports the AST walk cannot follow -------------------
    dyn = ast.parse("import importlib\n"
                    "def decide(c):\n"
                    "    m = importlib.import_module('checker.feeds.ofac_sdn')\n"
                    "    return m.screen(c)\n")
    hits = _dynamic_import_uses(dyn)
    check(any(t == "import_module()" for t, _ in hits),
          f"importlib.import_module in a decider is flagged ({hits})")
    check(_dynamic_import_uses(ast.parse("def f():\n    return __import__('x')\n")),
          "__import__ is flagged too")
    check(_dynamic_import_uses(ast.parse("import sys\ndef f():\n    return sys.modules['checker.feeds']\n")),
          "sys.modules[...] is flagged")
    check(not _dynamic_import_uses(ast.parse('"""prose mentioning eval() and __import__()."""\n')),
          "prose in a docstring is NOT flagged -- the check reads syntax, not text")
    check(not _dynamic_import_uses(ast.parse("def _test():\n    return __import__('pathlib')\n")),
          "a module's own _test() is exempt -- a self-check is not a decision path")

    # ---- RT-02: the laundering hop through an unregistered helper ------------
    helper = REPO_ROOT / "checker" / "_rt02_probe_helper.py"
    decider = REPO_ROOT / "checker" / "_rt02_probe_decider.py"
    try:
        helper.write_text("from checker.feeds import Observation\n")
        decider.write_text("from checker import _rt02_probe_helper\n")
        REGISTRY["checker._rt02_probe_decider"] = RING_0
        found = [v for v in violations() if "_rt02_probe" in v]
        check(bool(found), f"a Ring 0 module reaching a feed THROUGH a helper is caught ({found[:1]})")
        check(found and "through the unregistered module" in found[0],
              "...and the witness names the hop, so the fix is obvious")
    finally:
        REGISTRY.pop("checker._rt02_probe_decider", None)
        helper.unlink(missing_ok=True); decider.unlink(missing_ok=True)
    check(not [v for v in violations() if "_rt02_probe" in v],
          "the probe cleans up after itself -- no residue in the registry or on disk")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
