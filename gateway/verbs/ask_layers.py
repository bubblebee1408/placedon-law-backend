"""Layers around ask: the critic (layer 7) and the answer cache (O9)."""
from __future__ import annotations

from gateway.verbs import model_access
from gateway.verbs.answers import verify_citation
from gateway.verbs.core import Context, _now, _today


# ── layer 7: the critic ──────────────────────────────────────────────────────

_CRITIC_PROMPT = (
    "Below are the sentences of an answer about Indian company law. Each was already "
    "traced to a verbatim statutory span by a verifier.\n\n"
    "Your ONLY job is to object. You may:\n"
    "  REMOVE <id> -- the sentence is not supported by the span it rests on\n"
    "  FLAG   <id> -- the sentence is supported but reads more broadly than the span\n"
    "You may NOT rewrite, add, or suggest better wording. There is nowhere to put it.\n"
    "Reply with one line per objection: ACTION id: reason (at least 10 characters).\n"
    "Reply with nothing at all if you have no objection. Do not invent an objection to "
    "appear useful.\n\n")


def _critic_for(ctx: Context):
    """`critique(claims) -> [dict]` from the routed model, or one that raises.

    Raising is the designed failure: `critic.review` turns it into "the critic did not
    run" and the answer stands exactly as the verifier left it. This layer only ever
    subtracts, so not running it is always the safe direction.
    """
    from checker import public_only, router
    from checker.prompt_safety import UNTRUSTED_CLAUSE, wrap_untrusted

    def critique(claims):
        origins = tuple(public_only.clear_file(str(c.get("source")))
                        for c in (getattr(critique, "sources", ()) or ())
                        if str(c.get("source") or ""))
        if not origins:
            raise RuntimeError("no citation names the file it was read from, so the "
                               "answer's own sentences cannot be cleared")
        served, refusal = model_access._served_or_refusal(origins, name="critic",
                                             purpose=router.NARRATION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            raise RuntimeError(f"no model to criticise with: {refusal['code']}")
        body = "".join(f"{c['id']}:\n{wrap_untrusted(c['text'], 'an answer sentence')}\n"
                       for c in claims)
        raw = str(served.call(UNTRUSTED_CLAUSE + "\n\n" + _CRITIC_PROMPT + body) or "")
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            head, reason = line.split(":", 1)
            bits = head.split()
            if len(bits) != 2:
                continue
            out.append({"action": bits[0].strip().upper(), "claim_id": bits[1].strip(),
                        "reason": reason.strip()})
        return out

    return critique


def _critic_enabled() -> bool:
    """The one setting, default OFF. Job 6b.

    The critic can only subtract, and until a model is actually served live (B1) turning
    it on everywhere would mean every answer in the product quietly depends on a layer
    nobody has watched work. So it is off, and `ask`'s per-call `critic` flag stays the
    way to exercise it.
    """
    from checker import critic as cr
    return cr.enabled()                       # one answer, in checker/critic.py


def _apply_critic(d: dict, summary, ctx: Context, *, cite_index=None) -> dict:
    """Run the critic over the answer's own sentences and narrow the answer, or not.

    The claims are the VERIFIER'S OUTPUT -- sentences already traced to a verbatim span --
    which is what makes this an external check rather than the self-correction §1.4 rules
    out: the critic is shown what the verifier admitted, not what a model wanted to say.
    """
    from checker import critic as cr
    cite_index = dict(cite_index or {})
    claims = [{"id": f"s{i}", "text": str(getattr(sent, "text", "") or ""),
               "source": None, "citation_ids": list(cite_index.get(i, []))}
              for i, sent in enumerate(getattr(summary, "sentences", ()) or (), 1)]
    if not claims:
        return d
    critique = _critic_for(ctx)
    # The citations carry the corpus paths the sentences were traced to; the critic's
    # prompt is cleared against those files.
    critique.sources = list(d.get("citations") or ())
    try:
        verdict = cr.review(claims, critique=critique)
    except cr.CriticError:
        return d
    out = dict(d)
    out["critic"] = verdict.to_dict()
    if verdict.removed:
        kept_text = [c["text"] for c in verdict.kept if c["text"].strip()]
        out["answer"] = "\n".join(kept_text)
        # Job 6b: a citation that only the removed sentence used dies with it. Leaving it
        # in `citations[]` would show a provision as supporting an answer that no longer
        # says anything about it -- a source panel listing law the text does not rest on.
        # A citation a KEPT sentence also uses survives, which is why the index records
        # every sentence that cites a span and not just the first.
        still_used = {cid for c in verdict.kept for cid in (c.get("citation_ids") or ())}
        before = [dict(c) for c in (out.get("citations") or ())]
        kept_cites = [c for c in before if str(c.get("id") or "") in still_used]
        orphans = [str(c.get("id")) for c in before if str(c.get("id") or "")
                   not in still_used]
        if orphans:
            out["citations"] = kept_cites
            out["critic"] = dict(out["critic"], dropped_citations=orphans,
                                 trace=list(out["critic"]["trace"])
                                 + [f"DROPPED CITATIONS {orphans}: no remaining sentence "
                                    f"cites them"])
        out["critic_note"] = (
            f"The critic removed {len(verdict.removed)} sentence(s) from this answer, "
            f"with the reason recorded in critic.trace. It may remove at most one per run "
            f"(PLAN_23 §1.4) and may never rewrite or add.")
        if not kept_text:
            # The whole answer went. ANSWERED with an empty body would read as "nothing
            # applies" -- a finding of no obligation, produced by a critic rather than by
            # the law. It is an abstention, and it says whose objection caused it.
            out["status"] = "NEEDS_LAWYER"
            out["critic_note"] = (
                "The critic objected to EVERY sentence of this answer, so nothing is "
                "served. This is not a finding that no obligation exists: it is an "
                "answer withdrawn, and the objection is in critic.trace for a person to "
                "agree or disagree with.")
    return out


# ── O9: the answer cache ─────────────────────────────────────────────────────
#
# `checker/answer_cache.py` holds the rules and 014_answer_cache.sql holds the rows. These
# two functions are the whole of the wiring, and both fail SOFT: a cache that errors must
# never stop an answer being given, because every entry in it is derived and the fallback
# is simply to do the work.

def _cache_lookup(question: str, task: str, sources, ctx: Context):
    """(a servable result | None, the lookup key | None).

    The gate is `verify_citation` -- the same re-read `citation.get` uses -- run over every
    citation the stored answer carries. A stored answer whose provision has changed is NOT
    served, and that is counted apart from a miss: it means the law moved, which is itself
    the news.
    """
    from checker import answer_cache as ac
    partition = _cache_partition(ctx)
    if not partition:
        return None, None
    try:
        key = ac.lookup_key(question=question, task=task, as_of=_today(ctx),
                            sources=sources or (), partition=partition)
    except ac.CacheError:
        return None, None
    try:
        row = ctx.store.read_cache_entry(key)
        entry = None if row is None else ac.Entry(
            lookup=row["lookup_key"], content=row["content_key"],
            question=row.get("question") or "", task=row.get("task") or "",
            as_of=row.get("as_of") or "", sources=tuple(row.get("sources") or ()),
            citations=tuple(row.get("citations") or ()),
            payload=dict(row.get("payload") or {}),
            created_at=row.get("created_at") or "")
        ok, why = ac.servable(entry, verify=lambda c: verify_citation(c))
        kind = "hits" if ok else ("misses" if entry is None else "stale")
        ctx.store.bump_cache_stat(kind, day=_today(ctx))
        if not ok:
            return None, key
        out = {k: v for k, v in entry.payload.items() if k not in _CACHE_PRIVATE}
        # Older cache rows advertised a vault search that never grounded the answer.
        # Reuse the reverified statutory answer, never that obsolete retrieval claim.
        report = out.get("sources")
        if isinstance(report, dict):
            report = dict(report, searched=[sid for sid in report.get("searched", []) if sid != "vault"],
                          report=[dict(row, outcome="NOT_SEARCHED", hits=0,
                                       reason="Vault grounding is not connected to legal research.")
                                  if row.get("id") == "vault" else dict(row)
                                  for row in report.get("report", [])])
            report["note"] = "Retrieval report from the cached answer; no new search ran. " + str(report.get("note") or "")
            out["sources"] = report
        out["cached"] = True
        out["cache_note"] = (f"served from the answer cache, stored {entry.created_at}. "
                             f"{why}")
        return out, key
    except Exception:                                            # noqa: BLE001
        # Derived rows only. A broken cache costs a re-answer and must never cost an
        # answer, so nothing here is allowed to propagate.
        return None, None


# Never stored, never served: the asker's own run, and the cache's own annotations.
_CACHE_PRIVATE = frozenset({"run_id", "sub_run_ids", "cached", "cache_note"})


def _cache_partition(ctx: Context) -> str:
    """Who may reuse a cached answer (028): the matter it was asked in, else the one actor
    who asked it. No actor, no cache -- an anonymous entry would be reusable by anyone."""
    if getattr(ctx, "matter_id", None):
        return f"matter:{ctx.matter_id}"
    actor = str(getattr(ctx, "actor", "") or "")
    return f"actor:{actor}" if actor and actor != "unknown" else ""


def _cache_store(key, question: str, task: str, sources, result: dict,
                 ctx: Context) -> None:
    """Keep an answer only if it is the kind that can later be shown to be still true."""
    from checker import answer_cache as ac
    if not key or ctx.store is None or not isinstance(result, dict):
        return
    # ANSWERED only, and only with citations. A refusal may be a model that was briefly
    # unavailable, and caching it would make a transient outage permanent; an uncited
    # answer can never be re-verified, so `servable` would refuse it on every read.
    if result.get("status") != "ANSWERED" or not (result.get("citations") or []):
        return
    partition = _cache_partition(ctx)
    if not partition:
        return
    try:
        entry = ac.Entry.build(question=question, task=task, as_of=_today(ctx),
                               sources=sources or (),
                               citations=result.get("citations") or (),
                               payload={k: v for k, v in result.items()
                                        if k not in _CACHE_PRIVATE},
                               created_at=_now(ctx), partition=partition)
        ctx.store.write_cache_entry(dict(entry.to_dict(), matter_id=ctx.matter_id))
    except Exception:                                            # noqa: BLE001
        return


def cache_stats(ctx: Context) -> dict:
    """The hit rate, and what it does not include.

    Deliberately NOT a verb. Every read-only verb is exported as an MCP tool -- there is no
    opt-out, by design -- and a cache hit rate is an operator's number, not a capability an
    agent should hold. Adding it would also have meant editing the MCP policy allowlist in
    three files, one of them Project Themis's. `scripts/cache_report.py` prints it.
    """
    from checker.answer_cache import Stats
    if ctx.store is None:
        return {"error": "no store is configured, so there is no cache"}
    raw = ctx.store.read_cache_stats()
    return Stats(hits=int(raw.get("hits") or 0), misses=int(raw.get("misses") or 0),
                 stale=int(raw.get("stale") or 0)).to_dict()
