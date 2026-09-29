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
    """A price with its provenance. Every provenance field is required, and that is the point.

    A rate with no meter id is a rate nobody can re-check: Azure's meter names are
    abbreviated ("Llama 3.3 70B Inp glbl Tokens") and several look alike, so the id is what
    makes "this exact rate" a verifiable claim rather than a recollection.
    """
    usd_per_m_input: float
    usd_per_m_output: float
    meter_id_input: str
    meter_id_output: str
    sku_id_input: str
    sku_id_output: str
    currency: str
    source: str          # the exact query that returned it
    dated: str           # the day it was read

    def __post_init__(self) -> None:
        missing = [f for f in ("meter_id_input", "meter_id_output", "sku_id_input",
                               "sku_id_output", "currency", "source", "dated")
                   if not getattr(self, f)]
        if missing:
            raise CostError(
                f"a Priced entry is missing its provenance: {missing}. A rate without the "
                f"query that returned it, its meter id and the date it was read is a "
                f"recollection, and three documents later it is indistinguishable from a "
                f"measured figure.")
        if self.currency != "USD":
            raise CostError(
                f"currency is {self.currency!r}; the USD_INR conversion below assumes USD. "
                f"A non-USD rate needs its own conversion, not this one.")

    def inr(self, tokens_in: int, tokens_out: int) -> float:
        usd = (tokens_in * self.usd_per_m_input
               + tokens_out * self.usd_per_m_output) / 1_000_000
        return round(usd * USD_INR, 4)


@dataclass(frozen=True)
class Unpriced:
    """We do not know what this costs, and the reason is on the record."""
    reason: str


# ── Verified 2026-09-29 against the public Azure Retail Prices API (no auth) ──
#
#   https://prices.azure.com/api/retail/prices
#     ?$filter=armRegionName eq 'uaenorth' and contains(meterName,'Llama 3.3 70B')
#
# Two meters matched, one input and one output, after excluding the fine-tuning meters
# (which carry "FT" in the name and price differently). Two is what makes this
# unambiguous: had there been a regional AND a data-zone AND a global variant, the
# deployment type would decide between them and nothing in this repository records which
# we provisioned -- so it would have stayed UNPRICED.
RETAIL_API = "https://prices.azure.com/api/retail/prices"
LLAMA_QUERY = (f"{RETAIL_API}?$filter=armRegionName eq 'uaenorth' and "
               f"contains(meterName,'Llama 3.3 70B')")

TABLE: dict[str, Priced | Unpriced] = {
    # 0.00071 USD per 1K tokens on both meters = 0.71 USD per 1M. Input and output are the
    # SAME rate here, which is unusual enough to state: it is what both meters return.
    "llama-3-3-70b": Priced(
        usd_per_m_input=0.71,
        usd_per_m_output=0.71,
        meter_id_input="1a90d107-2527-5fe4-bced-37776297dcec",
        meter_id_output="27268bdf-1d66-5f0a-9454-d1218d8924c0",
        sku_id_input="DZH318Z0T9X1/016Q",
        sku_id_output="DZH318Z0T9X1/012R",
        currency="USD",
        source=LLAMA_QUERY,
        dated="2026-09-29"),

    # UNPRICED, and NOT for the reason it was before. How reasoning tokens bill is now
    # ESTABLISHED from Microsoft's own documentation --
    # https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reasoning, read
    # 2026-09-29: "Reasoning tokens never appear in the message content, but they occupy
    # space in the context window and are billed as output tokens", and the sample response
    # shows completion_tokens 1843 WITH completion_tokens_details.reasoning_tokens 448
    # inside it. So `completion_tokens` already includes them and pricing output against it
    # would be correct. That question is answered.
    #
    # What blocks it is meter IDENTITY. The retail API has no meter named 'gpt-5-mini'
    # anywhere (0 results for contains(meterName,'gpt-5-mini')). uaenorth has 18 meters
    # whose names contain 'mini' -- "5 mini pp Inp Gl", "5.4 mini pp cd Inp Gl", "5.1 codex
    # mini inp Gl" and others -- spanning GPT-5, 5.1, 5.4 and 5.6 at input rates from 0.025
    # to 0.45 USD per 1M. Nothing in this repository records which of those our deployment
    # named "gpt-5-mini" actually is, and picking the plausible one is guessing with extra
    # steps.
    "gpt-5-mini": Unpriced(
        "no Azure retail meter is named 'gpt-5-mini' (0 results), and the 18 'mini' meters "
        "in uaenorth span GPT-5, 5.1, 5.4 and 5.6 at input rates from 0.025 to 0.45 USD "
        "per 1M -- an AMBIGUOUS match, so no rate is recorded. Reasoning-token billing is "
        "NOT the blocker: Microsoft Learn (read 2026-09-29) states reasoning tokens 'are "
        "billed as output tokens' and are already counted inside completion_tokens. What "
        "is missing is which meter this deployment maps to."),
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

    # ── llama-3-3-70b: PRICED, verified against the retail API on 2026-09-29 ─
    llama = TABLE["llama-3-3-70b"]
    check(isinstance(llama, Priced), "llama-3-3-70b carries a verified price")
    check(llama.usd_per_m_input == 0.71 and llama.usd_per_m_output == 0.71,
          f"...0.71 USD per 1M in and out ({llama.usd_per_m_input}/"
          f"{llama.usd_per_m_output}), which is 0.00071 USD per 1K as the meters return it")
    check(llama.source.startswith("https://prices.azure.com/api/retail/prices")
          and "uaenorth" in llama.source and "Llama 3.3 70B" in llama.source,
          "...sourced to the EXACT query that returned it, region included")
    check(llama.meter_id_input == "1a90d107-2527-5fe4-bced-37776297dcec"
          and llama.meter_id_output == "27268bdf-1d66-5f0a-9454-d1218d8924c0",
          "...with the meter id for each direction, so the rate can be re-checked")
    check(llama.sku_id_input.startswith("DZH318Z0T9X1/")
          and llama.sku_id_output.startswith("DZH318Z0T9X1/"),
          f"...and the sku ids ({llama.sku_id_input}, {llama.sku_id_output})")
    check(llama.currency == "USD" and llama.dated == "2026-09-29",
          f"...the currency and the day it was read ({llama.currency}, {llama.dated})")

    cost, note = price_inr("llama-3-3-70b", tokens_in=1_000_000, tokens_out=1_000_000)
    check(cost == round(1.42 * USD_INR, 4),
          f"a million tokens each way costs 1.42 USD converted at the repo's own rate "
          f"({cost} INR)")
    check(cost > 0, "...which is not zero, because the call is not free")
    real, _ = price_inr("llama-3-3-70b", tokens_in=1200, tokens_out=300)
    check(0 < real < 1.0,
          f"a realistic call prices to a small non-zero rupee figure ({real})")

    # ── gpt-5-mini: UNPRICED, and the reason is meter identity ──────────────
    cost, note = price_inr("gpt-5-mini", tokens_in=1000, tokens_out=500)
    check(cost is UNPRICED and note.startswith("UNPRICED:"),
          "gpt-5-mini is UNPRICED, and the note says why")
    check("AMBIGUOUS" in note and "0 results" in note,
          "...the reason being that NO meter is named gpt-5-mini and the 18 'mini' meters "
          "are an ambiguous match, not that we forgot to look")
    check("billed as output tokens" in note and "completion_tokens" in note,
          "...and it records that reasoning-token billing is ANSWERED and is not the "
          "blocker, so nobody re-investigates the wrong question")
    check(len(note) > 200, "...at length, so the next reader knows what to go and find")
    cost, note = price_inr("some-future-deployment", tokens_in=10, tokens_out=10)
    check(cost is UNPRICED and "not in the price table" in note,
          "a deployment nobody listed is UNPRICED, not free")

    # ── and prices correctly the moment one is on record ────────────────────
    probe = dict(TABLE)
    probe["priced-demo"] = Priced(usd_per_m_input=0.50, usd_per_m_output=1.50,
                                  meter_id_input="m-in", meter_id_output="m-out",
                                  sku_id_input="s-in", sku_id_output="s-out",
                                  currency="USD",
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
    for missing in ({"source": ""}, {"dated": ""}, {"meter_id_input": ""},
                    {"currency": ""}):
        kw = dict(usd_per_m_input=1.0, usd_per_m_output=1.0, meter_id_input="a",
                  meter_id_output="b", sku_id_input="c", sku_id_output="d",
                  currency="USD", source="s", dated="d")
        kw.update(missing)
        try:
            Priced(**kw)
            check(False, f"a Priced missing {list(missing)[0]} is refused")
        except CostError:
            check(True, f"a Priced missing {list(missing)[0]} is REFUSED at construction: "
                        f"a rate nobody can re-check is a recollection")
    try:
        Priced(usd_per_m_input=1.0, usd_per_m_output=1.0, meter_id_input="a",
               meter_id_output="b", sku_id_input="c", sku_id_output="d",
               currency="INR", source="s", dated="d")
        check(False, "a non-USD rate is refused")
    except CostError:
        check(True, "...and a non-USD rate is refused, because USD_INR is the only "
                    "conversion here and applying it to rupees would double-convert")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
