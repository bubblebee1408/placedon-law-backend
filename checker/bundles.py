"""Tool bundles: capabilities the system declares, and refuses to fake.

The modular "tool bundle" shape -- self-contained units, each owning its own
instructions, that a manager layer selects between -- is reported of Harvey's
architecture in secondary write-ups. The value of the shape is decoupling: a team
can add a bundle without touching the ones already shipped, and that holds
whoever first described it.

**Provenance note.** The attribution is SECONDARY. Harvey's own blog and research
listings were checked and carry no post describing tool bundles or the
leave-one-out gate below; the nearest is a LangChain-co-authored post on
cost-efficient rubric scoring, which describes neither. So the ideas here are
adopted on their merits and on the measured evidence cited below -- not on
"Harvey does it", which could not be verified.

The shape transfers. One part of the reported design must not.

## The adaptation, and why it is not optional

In the reported design a **manager agent** -- an LLM -- decides which tool to
use. Routing a *task type* is a fair job for a model: "is this a document check
or a research question" is not a legal question. But a model that picks a bundle
is one design slip from a model that picks an answer, and this system's whole
claim is that no model decides whether a law applies.

So the router here is deterministic and, more importantly, **incapable of
substitution**. It returns exactly one declared bundle or it refuses. There is no
nearest-match, no fallback to a neighbouring capability, no "closest available
tool". A model may later propose an intent string; it can never widen what the
registry will serve.

## Leave-one-out, made executable

Withdraw a tool and check the system says "I cannot do that" rather than guessing.
This is the abstention discipline applied to orchestration, and the failure it
catches -- a system hallucinating a capability it does not have -- is the
orchestration-layer form of serving law we never read.

It is not adopted on anyone's say-so. It is adopted because the failure is
measured and common:

  * ToolEmu (arXiv 2309.15817), 36 tools over 144 scenarios: **even the safest
    agent tested failed 23.9% of the time**, and 68.8% of flagged failures were
    validated as plausible in the real world.
  * Gorilla (arXiv 2305.15334): LLMs hallucinate API calls to functions that do
    not exist; retrieval-augmented finetuning mitigates but does not solve it.
  * CAR-bench (arXiv 2601.22027): agents "frequently violate policies or fabricate
    information to satisfy user requests" under real-world uncertainty.
  * Large Legal Fictions (arXiv 2401.01301): models "cannot always predict when
    they are producing legal hallucinations" -- poor self-knowledge of error.

A router that substitutes a neighbouring capability is that failure, in our
system, with a real tool's output attached to lend it credibility.

`missing_capability_refuses()` implements the gate: withdraw each bundle in turn
and assert the router refuses rather than substituting. It runs in the suite.

## Honesty about models

Every bundle declares `uses_model`. Today every one of them is False, and that is
a fact about the product worth being able to state precisely rather than
approximately.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Callable


class NoSuchCapability(LookupError):
    """The router was asked for something no bundle declares. It refuses."""


@dataclass(frozen=True)
class Bundle:
    """One declared capability. What it answers, what it needs, what it uses."""
    name: str
    answers: str                       # the question, in a sentence
    requires: tuple[str, ...]          # inputs without which it cannot run
    uses_model: bool                   # does this bundle call an LLM?
    handler: Callable

    def missing(self, payload: dict) -> tuple[str, ...]:
        return tuple(k for k in self.requires if payload.get(k) is None)


# ── handlers ──────────────────────────────────────────────────────────────────
# Thin adapters onto modules that already exist and are already tested. A bundle
# adds no logic; it declares what an existing capability is for.

def _document_check(payload: dict, *, generated_at: str) -> dict:
    from checker.api import document_check
    return document_check(payload, generated_at=generated_at)


def _compliance_pack(payload: dict, *, generated_at: str) -> dict:
    from checker.api import compliance_pack
    return compliance_pack(payload, generated_at=generated_at)


def _law_changes(payload: dict, *, generated_at: str) -> dict:
    from checker.event_log import events_for
    as_of = date.fromisoformat(payload["as_of"])
    since = date.fromisoformat(payload["since"]) if payload.get("since") else None
    evs = events_for(as_of, since=since)
    return {"as_of": as_of.isoformat(), "count": len(evs),
            "events": [{"id": e.id, "at": e.at.isoformat(), "subtype": e.subtype,
                        "title": e.title, "output_class": e.output_class,
                        "instrument": e.source.instrument} for e in evs]}


def _acquisition_exposure(payload: dict, *, generated_at: str) -> dict:
    from checker.staleness import assess
    as_of = date.fromisoformat(payload["as_of"])
    return {"as_of": as_of.isoformat(),
            "findings": [{"rule_id": f.rule_id, "acquisition": f.acquisition,
                          "exposure": f.exposure, "governs": list(f.governs),
                          "detail": f.detail} for f in assess(as_of)]}


def _ground_extraction(payload: dict, *, generated_at: str) -> dict:
    from checker.document_extract import ground
    g = ground(payload["document_text"], payload["proposed"],
               source_id=payload.get("source_id"))
    return {"admissible": g.admissible, "refusal_reason": g.refusal_reason(),
            "payload": g.to_payload(),
            "fields": [{"name": f.name, "verdict": f.verdict, "reason": f.reason}
                       for f in g.fields]}


# ── the registry ──────────────────────────────────────────────────────────────
_REGISTRY: dict[str, Bundle] = {b.name: b for b in (
    Bundle("document.currency_check",
           "has the law this document rests on moved since it was made?",
           ("document_date", "company_class", "incorporation_date"),
           False, _document_check),
    Bundle("company.compliance_matrix",
           "which Companies Act obligations attach to this company, and are they met?",
           ("company_class", "incorporation_date", "as_of"),
           False, _compliance_pack),
    Bundle("law.changes",
           "what changed in the law, dated and sourced?",
           ("as_of",), False, _law_changes),
    Bundle("law.acquisition_exposure",
           "which instruments do our answers depend on, and is anyone watching them?",
           ("as_of",), False, _acquisition_exposure),
    Bundle("document.ground_extraction",
           "of what an extractor claimed to read, what is demonstrably in the document?",
           ("document_text", "proposed"), False, _ground_extraction),
)}


def registry() -> dict[str, Bundle]:
    return dict(_REGISTRY)


def capabilities() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


@contextmanager
def without(name: str):
    """Withdraw a bundle for the duration of a block. Test support for leave-one-out."""
    if name not in _REGISTRY:
        raise NoSuchCapability(name)
    held = _REGISTRY.pop(name)
    try:
        yield
    finally:
        _REGISTRY[name] = held


# ── the router ────────────────────────────────────────────────────────────────
def route(intent: str) -> Bundle:
    """Exactly the declared bundle, or a refusal naming what IS available.

    No nearest-match, no prefix match, no fallback. A router that helpfully
    substitutes a neighbouring capability is how a system answers a question it
    was never built to answer -- and does it confidently, because a real tool ran.
    """
    b = _REGISTRY.get(intent)
    if b is None:
        raise NoSuchCapability(
            f"no bundle declares {intent!r}. Available: {', '.join(capabilities())}. "
            "This system does not substitute a nearby capability for a missing one.")
    return b


def dispatch(intent: str, payload: dict, *, generated_at: str) -> dict:
    """Route and run. Fails closed on a missing capability or a missing input."""
    b = route(intent)
    gaps = b.missing(payload)
    if gaps:
        raise NoSuchCapability(
            f"{b.name} requires {', '.join(b.requires)}; missing: {', '.join(gaps)}")
    out = b.handler(payload, generated_at=generated_at)
    return {"bundle": b.name, "uses_model": b.uses_model, "result": out}


def missing_capability_refuses() -> list[tuple[str, bool, str]]:
    """Leave-one-out: withdraw each bundle and confirm the router refuses.

    Returns (name, refused_correctly, detail). The failure this catches is a
    router that answers with a neighbouring bundle when the right one is gone --
    the orchestration-layer form of serving law we never read.
    """
    out: list[tuple[str, bool, str]] = []
    for name in capabilities():
        with without(name):
            try:
                got = route(name)
                out.append((name, False,
                            f"substituted {got.name} for the withdrawn {name}"))
            except NoSuchCapability as e:
                ok = name in str(e) or "no bundle declares" in str(e)
                out.append((name, ok, "refused and named what is available"
                            if ok else f"refused without saying what is missing: {e}"))
    return out


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

    print("bundles")
    GEN = "2026-09-10T00:00:00Z"

    check(len(capabilities()) == 5, f"five bundles are declared ({len(capabilities())})")
    check(all(not b.uses_model for b in registry().values()),
          "no bundle currently calls a model, and each says so")

    # ── the router does not substitute ───────────────────────────────────────
    try:
        route("document.currency_chek")           # a typo, one character out
        check(False, "a near-miss intent is refused, not helpfully matched")
    except NoSuchCapability as e:
        check("does not substitute" in str(e),
              "a near-miss intent is refused, not helpfully matched")
        check("document.currency_check" in str(e),
              "...and the refusal lists what IS available")

    try:
        route("document")                          # a prefix of a real bundle
        check(False, "a prefix of a real intent is refused")
    except NoSuchCapability:
        check(True, "a prefix of a real intent is refused")

    # ── LEAVE-ONE-OUT ────────────────────────────────────────────────────────
    results = missing_capability_refuses()
    bad = [(n, d) for n, okk, d in results if not okk]
    check(not bad, f"withdrawing any bundle makes the router refuse, not substitute ({bad})")
    check(len(results) == len(capabilities()), "...checked for every bundle")

    # and the registry is restored afterwards
    check(len(capabilities()) == 5, "withdrawal is scoped -- the registry is restored")

    # ── dispatch fails closed on missing inputs ──────────────────────────────
    try:
        dispatch("document.currency_check", {"company_class": "private"}, generated_at=GEN)
        check(False, "dispatch refuses when a required input is absent")
    except NoSuchCapability as e:
        check("missing" in str(e) and "document_date" in str(e),
              f"dispatch refuses when a required input is absent, naming it")

    # ── a bundle actually runs ───────────────────────────────────────────────
    got = dispatch("document.currency_check",
                   {"document_date": "2024-06-01", "as_of": "2026-09-10",
                    "company_class": "private", "incorporation_date": "2015-04-01",
                    "is_listed": False, "paid_up_capital_rupees": 60000000,
                    "turnover_rupees": 550000000, "financial_year": "2024-25",
                    "director_count": 2},
                   generated_at=GEN)
    check(got["bundle"] == "document.currency_check", "a declared bundle dispatches")
    check(got["uses_model"] is False, "...and the response states no model was used")
    check(got["result"]["summary"]["superseded"] == 1,
          "...and returns the real result, not a stub")

    got2 = dispatch("law.acquisition_exposure", {"as_of": "2026-09-10"}, generated_at=GEN)
    check(any(f["rule_id"] == "S-003" for f in got2["result"]["findings"]),
          "a second, unrelated bundle dispatches independently")

    # ── every bundle declares what it answers ────────────────────────────────
    check(all(b.answers.strip().endswith("?") for b in registry().values()),
          "every bundle states the question it answers, as a question")
    check(all(b.requires for b in registry().values()),
          "every bundle declares its required inputs")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
