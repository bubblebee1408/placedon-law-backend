"""The firewall: what the legal core is allowed to depend on.

PLAN_08 divides the system into rings. Ring 0 is the legal core -- statute,
obligations, the deciders, currency. Ring 1 is Bookmark. Ring 2 is observation
(telemetry, prices). Ring 3 is inference (estimates, model scoring).

    a module may import from INFRA, and from its own ring or lower.
    NO Ring 0 module may import, at ANY depth, from Ring 2 or Ring 3.

## Why this is code and not a convention

The product's value claim is that **a wrong model cannot make the product wrong**
(`CODING_CONVENTIONS.md:14-15`). A probability or a market observation reaching an
applicability decision destroys that property *silently*, because the output still
looks deterministic -- a number appears where a number always appeared, and
nothing in the response says its provenance changed.

That is not a failure a reviewer catches reliably, so it is checked by a machine,
the same way `api.py:644-654` asserts the API imports no model library.

It is installed while there is nothing to violate it. A firewall added after the
first breach is archaeology, not architecture.

## Transitive, because one hop is not the threat

Ring 0 importing Ring 3 directly is the obvious error and nobody makes it. The
real one is Ring 0 -> Ring 1 -> Ring 3, where each edge looks reasonable alone.
So the check walks the closure.

## Honest about coverage

113 modules exist and this classifies the ones whose ring is load-bearing.
Everything else is UNCLASSIFIED: permitted, reported, and counted -- so the
coverage cannot silently shrink while the check keeps passing. An invariant that
quietly stops covering things is worse than none, because it still reassures.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "checker"

# Cross-cutting mechanism, no domain data. Importable from any ring.
INFRA = frozenset({
    "lattice", "interval", "provenance", "release", "licence", "company_profile",
})

# Ring 0 -- the legal core. A wrong model must not be able to change any of these.
RING_0 = frozenset({
    "obligations", "applicability", "currency", "staleness", "as_of", "amendment",
    "prescribed_thresholds", "s188_threshold", "corpus_currency",
    "s185", "s186", "s188", "s180", "s184", "entity_graph", "admission",
    "jurisdiction", "derived_date",
})

RING_1 = frozenset({"event_log", "corporate_data", "mca_aggregator", "matter", "session"})

# Nothing here yet, deliberately. PLAN_08 designs OBSERVATION; LOOP_INTELLIGENCE_V0
# §1 excludes building it until a feature needs it.
RING_2: frozenset[str] = frozenset()

# Inference: anything that estimates, scores a model, or emits a probability.
RING_3 = frozenset({"calibration_contract", "shadow", "model_adapter", "reranker"})

_RINGS = {0: RING_0, 1: RING_1, 2: RING_2, 3: RING_3}
FORBIDDEN_TO_RING_0 = RING_2 | RING_3


class RingViolation(ValueError):
    """A dependency that would let a non-deterministic value reach a decider."""


def ring_of(module: str) -> int | None:
    for r, members in _RINGS.items():
        if module in members:
            return r
    return None


def local_imports(module: str) -> frozenset[str]:
    """`checker.*` modules imported by `module`, at any nesting depth.

    ast.walk descends into functions, so a deferred import inside a call is
    caught too -- which is the form this would most likely arrive in.
    """
    path = PKG / f"{module}.py"
    if not path.is_file():
        return frozenset()
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.ImportFrom):
            if node.module == "checker":
                found.update(a.name for a in node.names)      # from checker import x
            elif node.module and node.module.startswith("checker."):
                found.add(node.module.split(".", 1)[1])
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("checker."):
                    found.add(a.name.split(".", 1)[1])
    return frozenset(found)


def reachable(module: str, graph: dict[str, frozenset[str]] | None = None) -> frozenset[str]:
    """Transitive closure of a module's checker imports. One hop is not the threat."""
    seen: set[str] = set()
    stack = [module]
    while stack:
        cur = stack.pop()
        deps = graph[cur] if graph is not None and cur in graph else local_imports(cur)
        for d in deps:
            if d not in seen:
                seen.add(d)
                stack.append(d)
    return frozenset(seen)


def violations(graph: dict[str, frozenset[str]] | None = None,
               ring_0: frozenset[str] | None = None,
               forbidden: frozenset[str] | None = None) -> list[tuple[str, str, str]]:
    """(ring-0 module, forbidden module, the path that reaches it). Empty is the goal."""
    core = RING_0 if ring_0 is None else ring_0
    bad = FORBIDDEN_TO_RING_0 if forbidden is None else forbidden
    out: list[tuple[str, str, str]] = []
    for m in sorted(core):
        for dep in sorted(reachable(m, graph) & bad):
            direct = (graph[m] if graph is not None and m in graph else local_imports(m))
            how = "directly" if dep in direct else "transitively"
            out.append((m, dep, how))
    return out


def unclassified() -> frozenset[str]:
    """Modules carrying no declared ring. Permitted, but counted."""
    every = {p.stem for p in PKG.glob("*.py") if not p.stem.startswith("_")}
    return frozenset(every - INFRA - RING_0 - RING_1 - RING_2 - RING_3 - {"rings"})


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

    print("rings")

    # ── the real tree is clean ───────────────────────────────────────────────
    real = violations()
    check(not real, f"no Ring 0 module reaches Ring 2 or Ring 3 ({real or 'none'})")

    # ── a DIRECT violation is caught and named ──────────────────────────────
    g = {"s185": frozenset({"calibration_contract"}), "calibration_contract": frozenset()}
    v = violations(graph=g, ring_0=frozenset({"s185"}),
                   forbidden=frozenset({"calibration_contract"}))
    check(len(v) == 1, f"a Ring 0 module importing Ring 3 is caught ({len(v)})")
    check(v[0][0] == "s185" and v[0][1] == "calibration_contract",
          f"...naming both modules ({v[0][0]} -> {v[0][1]})")
    check(v[0][2] == "directly", f"...and how it reaches it ({v[0][2]})")

    # ── THE ONE THAT MATTERS: the transitive path nobody reviews ────────────
    g2 = {"s185": frozenset({"event_log"}),
          "event_log": frozenset({"shadow"}),
          "shadow": frozenset()}
    v2 = violations(graph=g2, ring_0=frozenset({"s185"}), forbidden=frozenset({"shadow"}))
    check(len(v2) == 1 and v2[0][2] == "transitively",
          f"Ring 0 -> Ring 1 -> Ring 3 is caught, where each edge looks fine alone ({v2})")

    # ── and a legitimate dependency is NOT flagged ──────────────────────────
    g3 = {"s185": frozenset({"entity_graph", "lattice"}),
          "entity_graph": frozenset(), "lattice": frozenset()}
    check(not violations(graph=g3, ring_0=frozenset({"s185"}),
                         forbidden=frozenset({"shadow"})),
          "importing INFRA and its own ring is not a violation")

    # ── the classification is real, not decorative ──────────────────────────
    check(ring_of("s185") == 0 and ring_of("event_log") == 1
          and ring_of("calibration_contract") == 3,
          "modules resolve to their declared ring")
    check(ring_of("not_a_module") is None, "an unknown module has no ring, and does not default to 0")
    check(RING_2 == frozenset(),
          "Ring 2 is deliberately empty until a feature needs it")

    # ── deferred imports are caught, because that is how this would arrive ──
    src = local_imports("staleness")
    check("currency" in src,
          f"`from checker import currency` is detected ({sorted(src)[:3]})")
    check("prescribed_thresholds" in local_imports("event_log"),
          "...and function-local imports are detected too, via ast.walk")

    # ── coverage cannot silently shrink ─────────────────────────────────────
    u = unclassified()
    classified = len(INFRA | RING_0 | RING_1 | RING_2 | RING_3)
    check(classified >= 30, f"at least 30 modules carry a declared ring ({classified})")
    check(len(u) < 90, f"the unclassified remainder is reported, not hidden ({len(u)})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
