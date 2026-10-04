# 07: What Harvey is, and why it appeared in the architecture diagram

You asked: "what's the use of Harvey?" Harvey is **not a part of Themis.** It appeared in
the diagram for one reason: it is an AI assistant that lawyers already use, and it can
connect to outside tools the way Claude can. Here is the full picture.

**Evidence:** `.claude/loops/…_B_HARVEY_FUNNEL.md`. Mostly [S], with two [V]: the claude.com connector page, and BigLaw Bench's GitHub repo, which the agent fetched.

## 1. What Harvey is

| | |
|---|---|
| Business | Legal-AI software for law firms and in-house teams, founded 2022 |
| Size | $550M raised at a $15.5B valuation in September 2026 (Bloomberg says $15.6B). Revenue estimates range from $300M to $400M+ a year. "142,000+ lawyers, 1,500+ customers, 60+ countries" [S; vendor- or press-reported, not disclosed accounts] |
| India | AZB & Partners and Shardul Amarchand Mangaldas have firm-wide rollouts; S&A is reported as a customer. Bengaluru office. SCC Online content since January 2026 [S] |
| Price | About $1,200 per seat per month, 20–50 seat minimums [S]. Not published by Harvey |
| Products | Assistant (Q&A and drafting), Vault (up to 100k documents), Workflows, Knowledge, Word add-in |
| Under the hood | Rented models (OpenAI, then Anthropic and Google). Custom Voyage embeddings trained on US case law plus annotations from its own lawyers. Its own post-trained model, "Tenet", on Kimi K3 [S, vendor-reported] |

**The lesson in the last row, already recorded in PLAN_22:** Harvey switched models twice.
Its advantage is **retrieval, workflows and lawyer-labelled data**, not a model. That is why
file 05, the lawyer funnel, sits on Themis's critical path.

## 2. Why it matters to Placedon: three roles, in order of importance

1. **The incumbent at India's top firms.** Themis will not displace Harvey at AZB or SAM, and
   this plan does not try. Harvey's public material does **not** claim point-in-time Indian
   statutory answers or a recall register. That is an *unverified absence* [I], not proof.
   It is the space PLAN_20 targets: in-house teams, below Harvey's price.
2. **A possible distribution channel, the reason it was in the diagram.** Harvey is also an
   **MCP client**. Its "Bring Your Own MCP Server" feature [S] lets a firm's administrator
   connect an outside MCP server, and each lawyer then signs in with OAuth. So a firm that
   already pays for Harvey could use Themis's currency and recall tools **inside Harvey**.
   - **The condition:** Themis needs a *hosted* MCP server with OAuth 2.1 (file 04 §5).
     That is not built. Today's MCP server is local-only.
   - Separately, Harvey runs its own MCP server [V: claude.com/connectors/harvey], so the
     two can connect in either direction.
3. **The market's measuring stick.** Buyers will expect evaluations built by lawyers, because
   that is what Harvey publishes (BigLaw Bench [V]). Themis's answer is the gold set plus the
   funnel, and the honest number it can publish first is "n = 59, zero errors".

## 3. What to say if an investor asks "why not just use Harvey?"

Say it without claiming anything unmeasured:

- *"Harvey answers from law it retrieves. Themis answers from the law **as it stood on a
  date**, shows the notification it rests on, and when that notification changes it lists
  every earlier answer that relied on it. Harvey's public material does not describe that.
  We have not tested Harvey directly."*
- *"Harvey's price is set for 20+ seat law firms. Our first buyer is an in-house team of
  three or four."*
