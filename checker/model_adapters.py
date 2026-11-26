"""Adapter: router → route_fn for cuad_extractor.

Bridges the router's (Task → Route) with the extractor's (prompt → str).
cuad_extractor never imports a model module; this is the only place that does.

Run: PYTHONPATH=. python3 checker/model_adapters.py --test
"""
from __future__ import annotations

from typing import Callable

from checker import router

__all__ = ["make_route_fn"]


def make_route_fn(
    task_name: str = "cuad_extract",
) -> tuple[Callable[[str], str] | None, str, str]:
    """Build a route_fn for cuad_extractor, or None if no model is available.

    Returns (route_fn | None, provider, model).
    """
    available = router.providers_available()
    task = router.Task(task_name, router.TEXT, router.HIGH, purpose=router.EXTRACTION)

    try:
        r = router.route(task, available=available)
    except router.NoRoute:
        return None, "", ""

    fn = _adapter_for(r)
    return fn, r.provider, r.model


def _adapter_for(r: router.Route) -> Callable[[str], str]:
    """Return a (prompt → str) closure for the given route."""
    if r.provider == router.AZURE:
        from checker import azure_model
        return azure_model.as_text_model(origin="cuad_extract", model=r.model)

    if r.provider == router.BEDROCK:
        from checker import bedrock_model
        return bedrock_model.as_text_model(origin="cuad_extract", model=r.model)

    if r.provider == router.ANTHROPIC:
        from checker import anthropic_model
        def _anthropic(prompt: str) -> str:
            return anthropic_model.extract(prompt, model=r.model)
        return _anthropic

    if r.provider == router.GEMINI:
        from checker import gemini_model
        return gemini_model.as_text_model(origin="cuad_extract", model=r.model)

    if r.provider == router.OLLAMA:
        from checker import ollama_runner
        def _ollama(prompt: str) -> str:
            return ollama_runner.generate(prompt, model=r.model)
        return _ollama

    raise ValueError(f"no adapter for provider {r.provider!r}")


# ── self-tests ────────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("model_adapters")

    # ── make_route_fn returns a 3-tuple ──────────────────────────────────
    result = make_route_fn()
    check(isinstance(result, tuple) and len(result) == 3, "returns 3-tuple")

    fn, provider, model = result

    # Either we got a function + provider/model, or None + empty strings.
    if fn is None:
        check(provider == "" and model == "", "NoRoute → empty strings")
        print("  (no model available — adapter-shape tests only)")
    else:
        check(callable(fn), "route_fn is callable")
        check(provider != "", f"provider is {provider!r}")
        check(model != "", f"model is {model!r}")

    # ── _adapter_for covers every known provider ─────────────────────────
    from checker.router import Route
    known_providers = (router.AZURE, router.BEDROCK, router.ANTHROPIC,
                       router.GEMINI, router.OLLAMA)
    for p in known_providers:
        # Build a synthetic route — we only need provider + model for dispatch.
        fake = Route(provider=p, model="test-model", why="test",
                     est_cost_inr=0.0)
        try:
            adapter = _adapter_for(fake)
            check(callable(adapter), f"adapter for {p} is callable")
        except Exception as e:
            # Import errors are expected when keys aren't set — that's fine,
            # the adapter code path itself is reachable.
            if "not configured" in str(e).lower() or "not available" in str(e).lower():
                check(True, f"adapter for {p} reachable (key not set: {e})")
            else:
                check(False, f"adapter for {p} raised {e}")

    # ── unknown provider raises ValueError ───────────────────────────────
    fake_unknown = Route(provider="unknown_provider", model="x", why="test",
                         est_cost_inr=0.0)
    try:
        _adapter_for(fake_unknown)
        check(False, "unknown provider should raise ValueError")
    except ValueError:
        check(True, "unknown provider raises ValueError")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
