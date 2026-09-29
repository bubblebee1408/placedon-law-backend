"""What an Azure call actually costs, or an honest admission that we do not know.

`router.estimate_inr` returns 0.0 for Azure and says in its own comment that this is "zero
against MONTHLY_CAP_INR, NOT a claim that the call is free". That estimate then reached a
run step as `cost_inr=0.0`, and a recorded 0.0 IS a claim the call was free. It was not:
these deployments bill Azure for Students credit, a pot with its own exhaustion date.

So a cost is now derived from the TOKENS a call actually used, against a table that records
where each number came from and when it was read. And when no such number exists, the cost
is **UNPRICED** -- null, with a reason -- because a zero that means "unknown" is the same
mistake in different clothes.

## The table is empty today, and that is the honest state

No price here is invented. Azure for Students pricing for `llama-3-3-70b` and `gpt-5-mini`
in UAE North is not on record in this repository, and a plausible-looking number written
from memory would be indistinguishable from a measured one three documents later -- the
exact failure PLAN_22 §2 exists to prevent about vendor figures. So both deployments are
listed as UNPRICED with the reason, and every run step on them records null.

**Adding a price is a two-line change and a citation.** Put a `Priced` in TABLE with its
`source` and `dated`, and every step from then on carries rupees derived from real token
counts. Nothing else has to change.

Run: PYTHONPATH=. python3 backend/azure_pricing.py
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.budget import USD_INR

# Providers whose calls are BILLED to someone. A recorded cost of exactly 0.0 from one of
# these is a falsehood: either the call cost something, or we do not know what it cost.
# `gemini` is absent because its free tier bills nothing, and `ollama` because it runs on
# the operator's own machine -- both are genuinely zero MARGINAL cost, which is a different
# claim from "we have no idea".
BILLED_PROVIDERS = frozenset({"azure", "anthropic"})

UNPRICED = None


@dataclass(frozen=True)
class Priced:
    """A price with its provenance. Both fields are required, and that is the point."""
    usd_per_m_input: float
    usd_per_m_output: float
    source: str
    dated: str

    def inr(self, tokens_in: int, tokens_out: int) -> float:
        usd = (tokens_in * self.usd_per_m_input
               + tokens_out * self.usd_per_m_output) / 1_000_000
        return round(usd * USD_INR, 4)


@dataclass(frozen=True)
class Unpriced:
    """We do not know what this costs, and the reason is on the record."""
    reason: str


TABLE: dict[str, Priced | Unpriced] = {
    "llama-3-3-70b": Unpriced(
        "no verified price on record for this deployment. Azure for Students pricing for "
        "Llama-3.3-70B in UAE North has not been read from a source and written down here, "
        "and a number from memory would be indistinguishable from a measured one later."),
    "gpt-5-mini": Unpriced(
        "no verified price on record for this deployment. Reasoning models also bill hidden "
        "reasoning tokens, which the chat-completions `usage` object reports inside "
        "completion_tokens on some APIs and separately on others -- so even with a list "
        "price, which side of that line these counts fall on needs checking, not assuming."),
}


class CostError(ValueError):
    """A cost that cannot be true. Raised rather than recorded."""


def price_inr(deployment: str, *, tokens_in: int | None,
              tokens_out: int | None) -> tuple[float | None, str]:
    """(rupees, note). Rupees is None whenever the number would be a guess.

    Four ways to be unpriced, and each says which: no entry, an explicit Unpriced, no token
    counts at all, or a call that reported zero tokens (which no real call does).
    """
    entry = TABLE.get(deployment)
    if entry is None:
        return UNPRICED, (f"UNPRICED: {deployment!r} is not in the price table. Add a "
                          f"Priced entry with its source and date.")
    if isinstance(entry, Unpriced):
        return UNPRICED, f"UNPRICED: {entry.reason}"
    if tokens_in is None or tokens_out is None:
        return UNPRICED, ("UNPRICED: the provider reported no token usage for this call, "
                          "so there is nothing to price. An unmeasured cost is not a zero "
                          "cost.")
    if tokens_in <= 0 and tokens_out <= 0:
        return UNPRICED, ("UNPRICED: the reported usage was zero tokens, which no served "
                          "call is. Treating it as free would record a number nobody "
                          "measured.")
    return entry.inr(tokens_in, tokens_out), (
        f"priced from {tokens_in}+{tokens_out} tokens at {entry.source} ({entry.dated})")


def check_recordable(provider: str, cost_inr: float | None) -> None:
    """Refuse a cost that cannot be true before it reaches a run step or a database.

    The invariant: a BILLED provider never records exactly 0.0. It either costs something,
    or we do not know -- and "we do not know" is None with a reason, never zero.
    """
    if cost_inr is None:
        return
    if cost_inr < 0:
        raise CostError(f"a negative cost ({cost_inr}) is not a cost")
    if provider in BILLED_PROVIDERS and cost_inr == 0.0:
        raise CostError(
            f"{provider!r} is a BILLED provider and cannot record a cost of exactly 0.0. "
            f"Either the call cost something and the price table says how much, or the "
            f"cost is UNPRICED -- null with a reason. A recorded zero is a claim the call "
            f"was free, and these calls are billed to Azure for Students credit.")


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

    # ── the invariant the whole file exists for ─────────────────────────────
    for provider in sorted(BILLED_PROVIDERS):
        try:
            check_recordable(provider, 0.0)
            check(False, f"{provider} cannot record 0.0")
        except CostError as e:
            check("claim the call was free" in str(e),
                  f"a BILLED provider ({provider}) cannot record a cost of exactly 0.0")
    check_recordable("azure", None)
    check(True, "...while None is fine: that is UNPRICED, which is an honest answer")
    check_recordable("azure", 0.0001)
    check(True, "...and so is any real cost, however small")
    for free in ("gemini", "ollama"):
        check_recordable(free, 0.0)
        check(free not in BILLED_PROVIDERS,
              f"{free} MAY record 0.0: its marginal cost genuinely is zero, which is a "
              f"different claim from 'we have no idea'")
    try:
        check_recordable("azure", -1.0)
        check(False, "a negative cost is refused")
    except CostError:
        check(True, "a negative cost is refused as not being a cost")

    # ── the table admits what it does not know ──────────────────────────────
    check(set(TABLE) == {"llama-3-3-70b", "gpt-5-mini"},
          f"both served deployments are in the table ({sorted(TABLE)})")
    for dep in sorted(TABLE):
        cost, note = price_inr(dep, tokens_in=1000, tokens_out=500)
        check(cost is UNPRICED and note.startswith("UNPRICED:"),
              f"{dep} is UNPRICED today, and the note says why")
        check(len(note) > 60, f"...at length, so the next reader knows what to go and find")
    cost, note = price_inr("some-future-deployment", tokens_in=10, tokens_out=10)
    check(cost is UNPRICED and "not in the price table" in note,
          "a deployment nobody listed is UNPRICED, not free")

    # ── and prices correctly the moment one is on record ────────────────────
    probe = dict(TABLE)
    probe["priced-demo"] = Priced(usd_per_m_input=0.50, usd_per_m_output=1.50,
                                  source="a vendor page", dated="2026-09-29")
    saved = dict(TABLE)
    TABLE.update(probe)
    try:
        cost, note = price_inr("priced-demo", tokens_in=1_000_000, tokens_out=1_000_000)
        check(cost == round(2.0 * USD_INR, 4),
              f"a priced deployment costs tokens x rate x USD_INR ({cost})")
        check(cost > 0, "...which is never zero for a real call")
        check("a vendor page" in note and "2026-09-29" in note,
              f"...and the note carries the SOURCE and the DATE ({note})")
        small, _ = price_inr("priced-demo", tokens_in=1, tokens_out=1)
        check(small >= 0.0, "a tiny call still prices")
        check_recordable("azure", cost)
        check(True, "...and a priced cost passes the recordability check")

        none_cost, none_note = price_inr("priced-demo", tokens_in=None, tokens_out=None)
        check(none_cost is UNPRICED and "no token usage" in none_note,
              "a call that reported no usage is UNPRICED: an unmeasured cost is not zero")
        zero_cost, zero_note = price_inr("priced-demo", tokens_in=0, tokens_out=0)
        check(zero_cost is UNPRICED and "zero tokens" in zero_note,
              "...and a call reporting ZERO tokens is UNPRICED too, because no served call "
              "is zero tokens -- pricing it would record a number nobody measured")
    finally:
        TABLE.clear()
        TABLE.update(saved)
    check("priced-demo" not in TABLE, "the probe left the table as it found it")

    # ── a Priced cannot exist without its provenance ────────────────────────
    import dataclasses
    fields = {f.name for f in dataclasses.fields(Priced)}
    check({"source", "dated"} <= fields,
          f"a Priced carries its source and the date it was read ({sorted(fields)})")
    check(all(not isinstance(v, Priced) or (v.source and v.dated) for v in TABLE.values()),
          "...and no entry in the table has an empty one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
