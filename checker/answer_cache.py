#!/usr/bin/env python3
"""Serve an answer again only when the law it rests on has not moved.

O9. A cache for answers, in a product whose whole claim is that an answer cites the
provision it rests on and the date that provision came into force. So the only
interesting question here is not "have we seen this question before" -- it is **"is the
stored answer still true today"**, and that is settled by re-reading the corpus, not by a
timestamp.

## The key cannot be what the brief says, and here is why

PLAN_23 O9 gives the key as:

    (normalised question, task, as_of, sha256 of every cited provision, sources)

The cited provisions are known only AFTER the question has been answered. A lookup key
containing them could never be computed at lookup time, so a cache built on it would
never hit once. The brief describes an IDENTITY, not a lookup. Split in two, and both
halves are used:

    lookup_key   (normalised question, task, as_of, sources)   -- computable before
    content_key  lookup_key + the sorted provision hashes      -- the full identity

A read fetches by `lookup_key`, then the entry must survive **two** checks:

  1. its stored `content_key` still matches the hashes its citations carry now, and
  2. **every citation re-verifies against the corpus as it stands today.**

(2) is the one that matters and (1) is nearly free. (2) is injected (`verify`) so this
module stays pure and the gate runs it without a corpus read per case.

## A miss is cheaper than a wrong hit, always

Every refusal to serve returns a REASON. "Not found" and "found, and the section it cites
has changed since" are different facts about the law, and the second is the one a lawyer
would want to know. A cache that silently re-answered would hide a corpus change that is
itself the news.

## Tenant scope

An entry belongs to the tenant that created it. Full stop, in this version -- see
`gateway/migrations/014_answer_cache.sql`. PLAN_23 says "never across tenants for client
documents", which would permit sharing a purely statutory answer; this takes the stricter
reading, because the cost of being wrong once about which bucket an answer is in is a
client's contract shown to another firm. Sharing public answers is a later change that
needs its own proof, and the hit rate below will be lower until then. That is a price
worth naming rather than paying quietly.

Run: PYTHONPATH=. python3 checker/answer_cache.py --test
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

__all__ = ["normalise_question", "lookup_key", "content_key", "provision_hashes",
           "Entry", "servable", "Stats", "CacheError"]


class CacheError(ValueError):
    """A cache entry that cannot be formed. Never a silently skipped write."""


_WS = re.compile(r"\s+")
# Only the ends. Internal punctuation carries meaning in legal text -- "s.173(2)" and
# "s 1732" are different provisions, and a normaliser that stripped dots and brackets
# would collide them into one cache entry and serve the answer to the wrong one.
_TRIM = " \t\r\n.?!,;:"


def normalise_question(question: str) -> str:
    """Case and surrounding whitespace only. Deliberately timid.

    Every further normalisation is a chance to make two different questions share one
    answer, and the damage from that is an answer about the wrong provision, served with
    full confidence and a real citation attached to it.
    """
    return _WS.sub(" ", str(question or "")).strip(_TRIM).lower()


def _digest(parts) -> str:
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def lookup_key(*, question: str, task: str, as_of: str, sources=()) -> str:
    """What a read queries by. Computable BEFORE the question is answered."""
    q = normalise_question(question)
    if not q:
        raise CacheError("a cache key needs a question; an empty one would collide with "
                         "every other empty one")
    if not str(task or "").strip():
        raise CacheError("a cache key needs a task: the same words asked as a "
                         "RESEARCH_QUESTION and as a DRAFT are different requests")
    return _digest({"q": q, "task": str(task).strip(),
                    "as_of": str(as_of or "").strip(),
                    "sources": sorted({str(s) for s in (sources or ())})})


def provision_hashes(citations) -> tuple[str, ...]:
    """The sorted, de-duplicated sha256 of every cited provision.

    Sorted and de-duplicated because the SET of provisions an answer rests on is what
    identifies it; citing s.96 before s.173 is the same answer as the other way round.
    """
    return tuple(sorted({str((c or {}).get("sha256") or "")
                         for c in (citations or ())
                         if str((c or {}).get("sha256") or "")}))


def content_key(lookup: str, hashes) -> str:
    """The full identity from PLAN_23: the lookup key plus the law it rests on."""
    return _digest({"lookup": lookup, "provisions": list(hashes or ())})


@dataclass(frozen=True)
class Entry:
    lookup: str
    content: str
    question: str
    task: str
    as_of: str
    sources: tuple = ()
    citations: tuple = ()
    payload: dict = field(default_factory=dict)
    created_at: str = ""

    @staticmethod
    def build(*, question: str, task: str, as_of: str, sources=(), citations=(),
              payload: dict, created_at: str) -> "Entry":
        lk = lookup_key(question=question, task=task, as_of=as_of, sources=sources)
        hashes = provision_hashes(citations)
        if not str(created_at or "").strip():
            raise CacheError("an entry records when it was made; without that, nothing "
                             "can say how old a served answer is")
        return Entry(lookup=lk, content=content_key(lk, hashes), question=question,
                     task=str(task), as_of=str(as_of or ""),
                     sources=tuple(sorted({str(s) for s in (sources or ())})),
                     citations=tuple(dict(c) for c in (citations or ())),
                     payload=dict(payload or {}), created_at=str(created_at))

    def to_dict(self) -> dict:
        return {"lookup_key": self.lookup, "content_key": self.content,
                "question": self.question, "task": self.task, "as_of": self.as_of,
                "sources": list(self.sources), "citations": [dict(c) for c in self.citations],
                "payload": dict(self.payload), "created_at": self.created_at}


def servable(entry: Entry, *, verify) -> tuple[bool, str]:
    """(may we serve it, why not). `verify(citation) -> (ok, reason)`.

    An entry with NO citations is never served. An uncited answer has nothing to
    re-verify, so "still true" cannot be established about it at all -- and the whole
    reason this cache is allowed to exist is that the claim can be re-checked. Cheaper to
    answer again.
    """
    if entry is None:
        return False, "nothing is stored for this question, task, date and source set"
    if not entry.citations:
        return False, ("the stored answer cites nothing, so there is no way to check it "
                       "is still true. An answer that cannot be re-verified is answered "
                       "again, not served from a cache")
    if content_key(entry.lookup, provision_hashes(entry.citations)) != entry.content:
        return False, ("the stored answer's provision hashes no longer agree with its own "
                       "content key: the entry has been altered since it was written")
    for c in entry.citations:
        ok, why = verify(c)
        if not ok:
            return False, (f"the law moved: {str((c or {}).get('provision') or '?')} no "
                           f"longer re-verifies -- {why}")
    return True, (f"every one of {len(entry.citations)} citation(s) re-verifies against "
                  f"the corpus as it stands today")


@dataclass(frozen=True)
class Stats:
    hits: int = 0
    misses: int = 0
    stale: int = 0          # found, but the law moved -- the interesting kind of miss

    @property
    def looks(self) -> int:
        return self.hits + self.misses + self.stale

    def rate(self) -> float | None:
        """The hit rate, or None when nothing has been looked up.

        None, not 0.0: a cache nobody has queried has no hit rate, and printing 0% would
        read as "it never helps" rather than "we have not measured".
        """
        return None if self.looks == 0 else round(self.hits / self.looks, 4)

    def to_dict(self) -> dict:
        r = self.rate()
        return {"hits": self.hits, "misses": self.misses, "stale": self.stale,
                "lookups": self.looks, "hit_rate": r,
                "note": ("no lookup has been made, so there is no hit rate. This is not a "
                         "rate of zero." if r is None else
                         f"{self.hits} of {self.looks} lookups served from cache. "
                         f"{self.stale} entry(ies) were found and refused because a cited "
                         f"provision had changed, which is a corpus change and not a "
                         f"cache fault.")}


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("answer_cache")
    T0 = "2026-10-01T10:00:00+05:30"
    C1 = {"id": "c1", "provision": "s.96", "sha256": "a" * 64, "quote": "hold a meeting"}
    C2 = {"id": "c2", "provision": "s.173", "sha256": "b" * 64, "quote": "four meetings"}
    ENV = {"status": "ANSWERED", "task": "RESEARCH_QUESTION"}

    def made(**kw):
        base = dict(question="When must a company hold its AGM?", task="RESEARCH_QUESTION",
                    as_of="2026-10-01", sources=(), citations=(C1,), payload=ENV,
                    created_at=T0)
        base.update(kw)
        return Entry.build(**base)

    # ── normalisation is timid on purpose ──────────────────────────────────
    check(normalise_question("  When must a COMPANY hold its AGM? ")
          == normalise_question("when must a company hold its agm"),
          "case, surrounding space and a trailing ? do not make a different question")
    check(normalise_question("What does s.173(2) require?")
          != normalise_question("What does s 1732 require?"),
          "...but INTERNAL punctuation is kept: 's.173(2)' and 's 1732' are different "
          "provisions, and collapsing them would serve an answer about the wrong one")
    check(normalise_question("Is a gap of 120 days allowed?")
          != normalise_question("Is a gap of 90 days allowed?"),
          "...and two questions differing only in a number are different questions")
    check(normalise_question("   ") == "", "whitespace alone normalises to nothing")

    # ── the key, and what changes it ───────────────────────────────────────
    k = lookup_key(question="When must a company hold its AGM?", task="RESEARCH_QUESTION",
                   as_of="2026-10-01")
    check(k == lookup_key(question="  when must a company hold its agm  ",
                          task="RESEARCH_QUESTION", as_of="2026-10-01"),
          "the lookup key is stable across casing and spacing")
    _base = {"question": "When must a company hold its AGM?",
             "task": "RESEARCH_QUESTION", "as_of": "2026-10-01"}
    for label, kw in (("the task", {"task": "DRAFT"}),
                      ("the as_of date", {"as_of": "2026-09-01"}),
                      ("the source set", {"sources": ("sebi",)})):
        check(k != lookup_key(**{**_base, **kw}),
              f"...and changes when {label} changes")
    check(lookup_key(question="q", task="t", as_of="d", sources=("b", "a"))
          == lookup_key(question="q", task="t", as_of="d", sources=("a", "b")),
          "...while the ORDER of sources does not matter: it is a set")
    for bad, why in (({"question": "", "task": "t", "as_of": "d"}, "no question"),
                     ({"question": "q", "task": " ", "as_of": "d"}, "no task")):
        try:
            lookup_key(**bad)
            check(False, f"a key with {why} raises")
        except CacheError:
            check(True, f"a key with {why} is refused, never hashed to a collidable blank")

    check(provision_hashes([C1, C2]) == provision_hashes([C2, C1]),
          "the provision hashes are a SET: citing s.96 before s.173 is the same answer")
    check(provision_hashes([C1, C1]) == provision_hashes([C1]),
          "...de-duplicated, so citing one provision twice is not a different answer")
    check(provision_hashes([{"provision": "s.5"}]) == (),
          "...and a citation with no sha256 contributes nothing rather than an empty hash")
    e1, e2 = made(), made(citations=(C1, C2))
    check(e1.lookup == e2.lookup and e1.content != e2.content,
          "two answers to ONE question resting on DIFFERENT provisions share a lookup key "
          "and differ in content key -- which is the split the brief's key implies")

    # ── servable: the law moving is the whole point ────────────────────────
    def yes(c):
        return True, "re-read and the quote byte-matches"

    def no(c):
        return False, f"s.{c['provision']} has changed since this answer was given"

    good, why = servable(e2, verify=yes)
    check(good and "re-verifies" in why, f"an entry whose citations all re-verify IS "
                                         f"servable ({why[:40]})")
    bad, why2 = servable(e2, verify=no)
    check(not bad and "the law moved" in why2,
          f"...and one citation that no longer re-verifies refuses the whole entry "
          f"({why2[:46]})")
    check("s.96" in why2 or "s.173" in why2,
          "...naming the provision that moved, which is the news a lawyer wants")

    calls = []

    def once(c):
        calls.append(c["id"])
        return (False, "gone") if c["id"] == "c1" else (True, "fine")

    servable(e2, verify=once)
    check(calls == ["c1"],
          f"verification STOPS at the first failure: nothing is served, so re-reading the "
          f"rest would be work for an answer already refused ({calls})")

    check(servable(None, verify=yes)[0] is False,
          "a missing entry is not servable")
    check("nothing is stored" in servable(None, verify=yes)[1],
          "...and says so, distinctly from a stale one")
    uncited = made(citations=())
    check(not servable(uncited, verify=yes)[0]
          and "cites nothing" in servable(uncited, verify=yes)[1],
          "an answer that CITES NOTHING is never served: there is nothing to re-check, "
          "and re-checkability is the only reason this cache is allowed to exist")
    tampered = Entry(**{**e1.__dict__, "content": "0" * 64})
    check(not servable(tampered, verify=yes)[0],
          "an entry whose content key disagrees with its own citations is refused")

    try:
        made(created_at="")
        check(False, "an entry with no timestamp raises")
    except CacheError:
        check(True, "an entry with NO created_at is refused: nothing could then say how "
                    "old a served answer is")

    # ── the hit rate, and the honest zero ──────────────────────────────────
    check(Stats().rate() is None,
          "a cache nobody has queried has NO hit rate -- None, not 0.0, which would read "
          "as 'it never helps' rather than 'we have not measured'")
    check("not a rate of zero" in Stats().to_dict()["note"], "...and the note says so")
    check(Stats(hits=1, misses=3).rate() == 0.25, "the rate is hits over lookups")
    check(Stats(hits=1, misses=2, stale=1).looks == 4,
          "a STALE find counts as a lookup: it is a miss, and hiding it would flatter the "
          "rate")
    check("corpus change and not a cache fault" in Stats(hits=1, stale=1).to_dict()["note"],
          "...and the note says a stale entry means the law moved")
    check(Entry.build(question="q", task="t", as_of="d", citations=(C1,), payload=ENV,
                      created_at=T0).to_dict()["created_at"] == T0,
          "to_dict round-trips the timestamp")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
