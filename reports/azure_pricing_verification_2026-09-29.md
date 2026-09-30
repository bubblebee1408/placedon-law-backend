# Azure prices, verified — 2026-09-29

Queried the public Azure Retail Prices API (no auth) for the two deployments this gateway
serves in **UAE North**.

## llama-3-3-70b — PRICED

    https://prices.azure.com/api/retail/prices
      ?$filter=armRegionName eq 'uaenorth' and contains(meterName,'Llama 3.3 70B')

| direction | meterName | meterId | skuId | retail |
|---|---|---|---|---|
| input | `Llama 3.3 70B Inp glbl Tokens` | `1a90d107-2527-5fe4-bced-37776297dcec` | `DZH318Z0T9X1/016Q` | 0.00071 USD / 1K |
| output | `Llama 3.3 70B Outp glbl Tokens` | `27268bdf-1d66-5f0a-9454-d1218d8924c0` | `DZH318Z0T9X1/012R` | 0.00071 USD / 1K |

= **0.71 USD per 1M, input and output**, effectiveStartDate 2026-01-01, currency USD,
converted at the repo's own `USD_INR = 95.23` (dated 2026-08-06 in `backend/budget.py`).

**Why this is unambiguous.** Ten `Llama` meters exist in uaenorth. Excluding the
fine-tuning meters (`FT` in the name, priced differently at 0.0045 USD/1K) and Llama 4
Maverick, exactly **two** remain — one input, one output. Had there been regional AND
data-zone AND global variants, the deployment type would decide between them, and nothing
in this repository records which we provisioned, so it would have stayed UNPRICED.

**Independently confirmed against real billing.** `az consumption usage list` returns usage
records for this subscription carrying meterIds `1a90d107-...` and `27268bdf-...` — the same
two — against `Microsoft.CognitiveServices/accounts/placedon-law-eval`. The table is keyed
to the meters this account is actually billed on, not to a plausible-looking row.

A live call now records a real figure: **INR 0.0735** for 852 input + 235 output tokens.

## gpt-5-mini — UNPRICED (ambiguous match)

`contains(meterName,'gpt-5-mini')` returns **0 results anywhere in the API**. uaenorth has
18 `Azure OpenAI GPT5` meters containing "mini" — `5 mini pp Inp Gl` (0.45 USD/1M),
`5.4 mini pp cd Inp Gl` (0.15), `5.1 codex mini inp Gl` (0.25), `5.1 codex mini cd inp Gl`
(0.025) and others spanning GPT-5, 5.1, 5.4 and 5.6. Nothing in this repository records
which of those the deployment named `gpt-5-mini` maps to, and picking the plausible one is
guessing with extra steps. Left UNPRICED with that exact reason.

## Reasoning tokens — ANSWERED, and not the blocker

Microsoft Learn, read 2026-09-29:
https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reasoning

> "Reasoning tokens never appear in the message content, but they occupy space in the
> context window and **are billed as output tokens**. To see how many reasoning tokens a
> request consumed, check `completion_tokens_details.reasoning_tokens` in a Chat
> Completions API response."

Its sample response shows `completion_tokens: 1843` with
`completion_tokens_details.reasoning_tokens: 448` **inside** it — so `completion_tokens`
already includes reasoning tokens, and pricing output against it would be correct. The
earlier note guessing this "needs checking" is resolved; the blocker is meter identity alone.

## Month-to-date spend — NOT READ

`az account show` succeeds (subscription **Azure for Students**).

- `az costmanagement` — extension not installed. Installing one is a side effect beyond the
  ask, so it was not installed.
- Cost Management REST via `az rest` — **RBACAccessDenied**, and the CLI asks for an
  interactive `az login`. Not run: an interactive login is the operator's to perform.
- `az consumption usage list` — returns **22 usage records**, and they are how the meter ids
  above were confirmed. But every `pretaxCost` and `quantity` is **null**, and `currency`
  is empty.

**Month-to-date spend is therefore UNREADABLE, which is not the same as zero**, and it is
not reported as 0.00 for exactly the reason this whole change exists. To obtain it, run
`az login` yourself and re-run the Cost Management query.

Subscription and tenant identifiers are deliberately not reproduced here.
