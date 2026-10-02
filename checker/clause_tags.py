#!/usr/bin/env python3
"""Which clauses a document contains, each with the sentence it was found in.

V1. The CUAD categories a lawyer actually looks for, detected by rule, and **every tag
carries the quote it was found in**. `gateway/migrations/020_vault.sql` enforces that with
a CHECK: a tag with no span is an assertion about a document nobody can check against it,
which is the one thing this repository consistently refuses to ship.

## A tag is a POINTER, not a finding

`Governing Law` on a contract means "there is a sentence here about governing law, and
here it is". It does NOT mean the clause is valid, standard, or acceptable -- those are
`checker/playbook.py`'s job against a firm's own standard, and `agents/review_contract.py`
is careful to say its findings are against that standard and never statements of law.

So `tag()` returns spans, not verdicts, and nothing here has a pass/fail.

## Rules, word-anchored, and no tag without a sentence

Patterns are `\\b`-anchored for the reason `agents/intake.py` and
`checker/doc_classifier.py` both learned: substrings lie. A match yields the whole SENTENCE
it sits in, so a lawyer reading the tag sees what produced it -- and a match that cannot
be resolved to a sentence of at least `MIN_QUOTE` characters is DROPPED rather than tagged
with a fragment.

Run: PYTHONPATH=. python3 checker/clause_tags.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["TAGS", "MIN_QUOTE", "Tag", "tag", "patterns_for"]

# 020's CHECK. Named here so the detector and the database agree on the same number.
MIN_QUOTE = 8

# The CUAD categories this detects. A closed list: a clause type with no rule is simply
# not tagged, which is visible, rather than guessed at, which is not.
TAGS = (
    "Governing Law",
    "Term",
    "Termination for Convenience",
    "Confidentiality",
    "Indemnity",
    "Limitation of Liability",
    "Non-Compete",
    "Assignment",
    "Notice Period",
    "Renewal",
    "Audit Rights",
    "Insurance",
    "Dispute Resolution",
)

_RULES: tuple[tuple[str, str], ...] = (
    ("Governing Law", r"\bgoverned by the laws? of\b"),
    ("Governing Law", r"\bgoverning law\b"),
    ("Term", r"\bthis agreement (shall )?(commence|continue|remain in (force|effect))\b"),
    ("Term", r"\bterm of (this agreement|the agreement)\b"),
    ("Termination for Convenience", r"\bterminate .{0,40}\bfor convenience\b"),
    ("Termination for Convenience",
     r"\bmay terminate .{0,60}\bwithout (cause|assigning any reason)\b"),
    ("Confidentiality", r"\bconfidential information\b"),
    ("Confidentiality", r"\b(shall|will) (not )?(disclose|keep confidential)\b"),
    ("Indemnity", r"\bindemnif(y|ies|ied|ication)\b"),
    ("Indemnity", r"\bhold harmless\b"),
    ("Limitation of Liability", r"\b(aggregate )?liability .{0,40}\b(shall not exceed|"
                                r"is limited to)\b"),
    ("Limitation of Liability", r"\b(in no event|under no circumstances) shall\b"),
    ("Non-Compete", r"\b(non[- ]?compete|shall not (directly or indirectly )?compete)\b"),
    ("Assignment", r"\b(assign|novate) (this agreement|its rights)\b"),
    ("Notice Period", r"\b(\w+|\d+)[ -]days?('| )?( prior)? (written )?notice\b"),
    ("Renewal", r"\b(automatically renew|renewal term|renewed for)\b"),
    ("Audit Rights", r"\bright to audit\b"),
    ("Audit Rights", r"\b(audit|inspect) .{0,30}\brecords\b"),
    ("Insurance", r"\b(maintain|procure) .{0,30}\binsurance\b"),
    ("Dispute Resolution", r"\b(arbitration|arbitral tribunal|seat of arbitration)\b"),
    ("Dispute Resolution", r"\bexclusive jurisdiction\b"),
)

_COMPILED = tuple((name, re.compile(pat, re.IGNORECASE)) for name, pat in _RULES)
_SENTENCE = re.compile(r"[^.!?\n]*[.!?]|[^.!?\n]+")


@dataclass(frozen=True)
class Tag:
    tag: str
    quote: str
    span_start: int
    span_end: int

    def to_dict(self) -> dict:
        return {"tag": self.tag, "quote": self.quote, "span_start": self.span_start,
                "span_end": self.span_end}


def patterns_for(name: str) -> tuple[str, ...]:
    return tuple(p for n, p in _RULES if n == name)


def _sentence_at(text: str, pos: int) -> tuple[str, int, int]:
    for m in _SENTENCE.finditer(text):
        if m.start() <= pos < m.end():
            return m.group(0).strip(), m.start(), m.end()
    return "", -1, -1


def tag(text: str) -> list[Tag]:
    """Every clause tag found, each with the sentence it was found in.

    One tag per (name, quote): a category matched twice in one sentence is one tag, and
    the same category in two different sentences is two -- because a lawyer checking a
    tag wants every place it occurs, not a count.
    """
    body = str(text or "")
    out: list[Tag] = []
    seen: set[tuple[str, str]] = set()
    for name, pat in _COMPILED:
        for m in pat.finditer(body):
            quote, start, end = _sentence_at(body, m.start())
            if len(quote) < MIN_QUOTE:
                # A fragment is not a quote. 020 would refuse it; refusing here means the
                # caller never has to handle a tag the database will reject.
                continue
            key = (name, quote)
            if key in seen:
                continue
            seen.add(key)
            out.append(Tag(name, quote, start, end))
    out.sort(key=lambda t: (t.span_start, t.tag))
    return out


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

    print("clause_tags")
    CONTRACT = (
        "2. Term\n\nThis Agreement shall continue for five years. Either party may "
        "terminate on ninety days written notice.\n\n"
        "7. Indemnity\n\nThe supplier shall indemnify the customer. In no event shall "
        "liability exceed INR 10,00,000.\n\n"
        "9. Governing law\n\nThis Agreement is governed by the laws of India. Disputes "
        "are referred to arbitration in Mumbai.\n\n"
        "11. Confidentiality\n\nConfidential Information means anything disclosed.")

    found = tag(CONTRACT)
    names = {t.tag for t in found}
    for want in ("Term", "Notice Period", "Indemnity", "Limitation of Liability",
                 "Governing Law", "Dispute Resolution", "Confidentiality"):
        check(want in names, f"{want} is detected")

    # ── every tag carries the SENTENCE it was found in ─────────────────────
    check(all(len(t.quote) >= MIN_QUOTE for t in found),
          f"**every tag carries a quote of at least {MIN_QUOTE} characters** -- 020's "
          f"CHECK, enforced here so a caller never holds a tag the database will reject")
    check(all(t.quote in CONTRACT for t in found),
          "...and every quote is really IN the document, byte for byte")
    check(all(CONTRACT[t.span_start:t.span_end].strip() == t.quote for t in found),
          "...and the span points at it, so a reader can be shown the words around it")
    indemnity = [t for t in found if t.tag == "Indemnity"][0]
    check(indemnity.quote == "The supplier shall indemnify the customer.",
          f"a tag's quote is the whole SENTENCE, not the matched words "
          f"({indemnity.quote!r})")

    # ── a tag is a pointer, not a finding ──────────────────────────────────
    check(all(not hasattr(t, "verdict") and not hasattr(t, "status") for t in found),
          "a Tag has no verdict and no status: 'Governing Law' means there is a sentence "
          "about it HERE, never that the clause is valid or standard -- that is the "
          "playbook's job and it is careful to say so")
    check(set(TAGS) >= names,
          f"every tag produced is in the closed list ({sorted(names - set(TAGS))})")

    # ── the same category twice is two tags, in two places ─────────────────
    twice = tag("Governed by the laws of India. Also governed by the laws of Singapore.")
    gl = [t for t in twice if t.tag == "Governing Law"]
    check(len(gl) == 2 and gl[0].quote != gl[1].quote,
          f"the same category in TWO sentences is two tags: a lawyer checking it wants "
          f"every place it occurs, not a count ({len(gl)})")
    once = tag("This is governed by the laws of India and the governing law is Indian.")
    check(len([t for t in once if t.tag == "Governing Law"]) == 1,
          "...while two matches in ONE sentence is one tag")

    # ── word boundaries, and no tag from a fragment ────────────────────────
    unanchored = [p for _n, p in _RULES if not p.startswith(r"\b")]
    check(not unanchored, f"every pattern is \\b-anchored ({unanchored})")
    check(not tag(""), "no text is no tags")
    check(not tag("short"), "a document too short to hold a sentence yields nothing")
    check(all(t.span_start >= 0 for t in found), "every span is a real offset")
    check(patterns_for("Indemnity") and not (
        set(patterns_for("Indemnity")) & set(patterns_for("Insurance"))),
        "patterns_for returns one tag's patterns and none of another's")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
