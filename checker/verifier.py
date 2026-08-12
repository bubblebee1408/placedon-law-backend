"""
The gate. Nothing reaches a user without passing through here.

The spec's `should_abstain()` flags hedging words — "I believe", "I think", "probably". That
catches an anxious answer, not a wrong one: a confidently-worded fabricated deadline sails
straight past it. We keep the phrase list as a weak signal and make the real gate mechanical —

    **every number in the answer must appear verbatim in the retrieved source text.**

That check is the one that would have caught the fabricated s.4 quotation that three separate
generated specs propagated. It does not depend on the model being careful.

Pure functions, no I/O. Run: python3 checker/verifier.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Confidence = Literal["answer", "abstain"]

SUPPORTED_STATES = {"IN-KA", "IN-MH", "IN-DL", "IN-TG", "IN-TN", "IN-HR"}

# Weak signal, kept from the spec. Not the gate.
HEDGES = ("i believe", "i think", "probably", "might be", "i'd guess", "presumably")

# Second-person prescription. The system prompt forbids it and the model did it anyway on the
# very first real generation: "Action: You should constitute an Internal Complaints Committee."
#
# The distinction being drawn is not politeness. Relaying "section 4 requires every employer to
# constitute a Committee [s.4]" is reporting. Telling a specific company what it should do is
# advice, and this product's entire liability position is that it does not advise. A model will
# drift into it because being helpful is what it was trained for.
ADVICE = ("you should", "you must", "you need to", "you are required to", "you have to",
          "i recommend", "we recommend", "i advise", "we advise", "my advice", "our advice",
          "i suggest", "we suggest")

# An answer that asserts something must say where it came from. "No citation, no answer" is the
# spec's rule and it is right — but a model REFUSING has nothing to cite, and that refusal is
# the most valuable output this product produces. So refusals are exempt.
REFUSALS = ("i don't have verified information", "i do not have verified information",
            "not in the provided text", "the legal text does not", "cannot answer",
            "i don't know", "i do not know")

# Out of scope by design — arithmetic is where a wrong answer is instantly expensive,
# and `docs/03` puts the calculation agent last for exactly this reason.
CALCULATION = ("calculate", "how much pf", "gratuity amount", "salary breakup",
               "ctc breakup", "how much will i pay", "compute")

# Questions the statute does not settle, which must abstain EVEN ON A VERIFIED CORPUS.
#
# This gate exists because of a hole found by testing the post-verification state. Today every
# one of these abstains, but only incidentally — nothing is verified, so everything abstains.
# Simulate the corpus a lawyer has signed off and the product cheerfully answers "do interns
# count toward the ten?" from s.2(f), a definition that does not mention interns at all.
#
# The gate opening is precisely when this fires. That is the worst possible timing: the day the
# product becomes useful is the day it starts answering the questions it should refuse.
#
# Every entry is a question a practising lawyer would want to see the facts for. s.2(f) defines
# "employee" broadly — "whether for remuneration or not... whether the terms of employment are
# express or implied" — which is exactly the kind of breadth that makes confident answers about
# specific worker categories unsafe rather than easy.
# Patterns, anchored on word boundaries. Substring matching was the first implementation and it
# broke the flagship question: "Do I need an Internal Committee?" contains "intern", so the most
# important question the product answers would have abstained forever.
EDGE_CASES: tuple[tuple[str, str], ...] = (
    (r"\binterns?\b", "whether interns count toward the threshold"),
    (r"\btrainees?\b", "whether trainees count toward the threshold"),
    (r"\bapprentices?\b", "whether apprentices count — the Apprentices Act may govern instead"),
    (r"\bprobation(?:er|ers|ary)?\b", "how probationers are counted"),
    (r"\bpart[- ]time\b", "how part-time staff are counted"),
    (r"\bcontract(?:or|ors|\s+workers?|\s+staff)\b",
     "whether contract workers count toward the threshold"),
    (r"\bconsultants?\b", "whether consultants on contract count"),
    (r"\bfreelancers?\b", "whether freelancers count"),
    (r"\bgig\b", "whether gig workers count"),
    (r"\b(?:two|three|four|five|several|multiple|different|many|\d+)\s+states?\b",
     "which state's rules govern an employer operating in more than one state"),
    (r"\bmulti[- ]state\b",
     "which state's rules govern an employer operating in more than one state"),
    (r"\bremote(?:ly)?\b", "which workplace a remote employee attaches to"),
    (r"\bwork(?:ing)? from home\b", "whether a home counts as a workplace under s.2(o)"),
)

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CITE = re.compile(r"\bs\.\s?\d+[A-Za-z0-9()\/]*", re.I)
# Years and small ordinals appear in prose ("the 2013 Act", "three years") without being
# claims about quantities. Section numbers are checked separately, by resolution.
_BENIGN = {"2013", "1", "2", "3", "4"}


@dataclass(frozen=True)
class Verdict:
    confidence: Confidence
    reason: str
    unsupported_numbers: list[str]
    unresolved_citations: list[str]

    @property
    def abstained(self) -> bool:
        return self.confidence == "abstain"


def _source_text(provisions: list[dict]) -> str:
    """
    What a claim is checked against: statute only, not the editorial apparatus around it.

    `text_statutory` strips the PDF's footnotes — a section spanning a page break swallows the
    footnotes printed at the foot of that page. Leaving them in widened what counted as sourced:
    a model writing "6-5-2016" or "2016" against s.8 was ACCEPTED, because those digits sit in
    "Subs. by Act 23 of 2016 … (w.e.f. 6-5-2016)". That is a citation of an amendment, not a
    statement of law, and no answer should be able to lean on it.
    """
    return " ".join(
        (p.get("text_statutory") or p.get("text_display") or p.get("text", ""))
        for p in provisions
    )


# Consequences a reader would act on, which the Act may or may not actually provide. Asserting
# one that is absent from the source is the same class of error as inventing a figure, and until
# now nothing checked it: "Section 26 provides for imprisonment of the employer" passed clean
# through both the citation check (s.26 was retrieved) and the number check (no numbers), while
# "imprisonment" appears nowhere in the Act. Found by scripts/bench_safety.py.
_CONSEQUENCE = (
    "imprisonment", "imprisoned", "arrest", "arrested", "prosecution", "prosecuted",
    "criminal liability", "cancellation", "cancelled", "revoked", "revocation",
    "suspension", "suspended", "blacklist", "debarred", "injunction",
)


def check_hallucination(answer: str, provisions: list[dict]) -> list[str]:
    """
    Assertions in the answer the source does not support. Empty is the only pass.

    Two families, both exact: figures the source does not contain, and legal consequences the
    source does not provide. Neither uses similarity. A measured comparison against an
    embedding-similarity guard on twelve real cases is in scripts/bench_safety.py — the
    embedding guard flagged two verbatim-correct statements as fabrications, because quoting
    the statute exactly is not the same as resembling it.
    """
    src = _source_text(provisions)
    src_nums = {n.replace(",", "") for n in _NUM.findall(src)}
    out: list[str] = []
    for raw in _NUM.findall(answer):
        n = raw.replace(",", "")
        if n in _BENIGN or n in src_nums:
            continue
        # "fifty thousand" in the source, "50,000" in the answer is a real mismatch to surface —
        # we cannot confirm it from the text, so it does not get a free pass.
        out.append(raw)

    low_src, low_ans = src.lower(), answer.lower()
    for word in _CONSEQUENCE:
        if word in low_ans and word not in low_src:
            out.append(f"consequence not in source: {word!r}")
    return sorted(set(out))


def verify_citations(answer: str, provisions: list[dict]) -> list[str]:
    """
    Citations in the answer that do not resolve to a retrieved provision.

    Sub-clauses are checked against the provision's own text, not just the section number. The
    first version stopped at the base — so `s.26(9)(z)` and `s.4(99)`, sub-clauses that do not
    exist, resolved cleanly because s.26 and s.4 were in the packet. A fabricated sub-clause is
    exactly as misleading as a fabricated section, and harder to notice.
    """
    # base -> (parts the provision's own citation already covers, its verbatim text)
    # Keyed by the SECTION NUMBER as an integer, never by string prefix.
    #
    # Prefix matching failed open, catastrophically. `"s.27".startswith("s.2")` is True, so with
    # s.2 in the packet every one of s.21, s.22, s.26, s.27 and even s.199 resolved cleanly.
    # The citation enforcer — the component this product's trustworthiness rests on — passed
    # every fabricated section it was shown.
    def _section_of(cite: str) -> int | None:
        m = re.match(r"s\.?\s*(\d{1,3})", cite.strip().lower())
        return int(m.group(1)) if m else None

    held: dict[int, tuple[set[str], str]] = {}
    for p in provisions:
        cite = (p.get("citation") or "").lower().replace(" ", "")
        num = _section_of(cite)
        if num is None:
            continue
        own = set(re.findall(r"\(([^)]+)\)", cite))
        body = " ".join((p.get("text_display") or p.get("text", "")).split()).lower()
        prev_own, prev_body = held.get(num, (set(), ""))
        held[num] = (own | prev_own, body or prev_body)

    unresolved: list[str] = []
    for c in _CITE.findall(answer):
        norm = c.lower().replace(" ", "")
        num = _section_of(norm)
        if num is None or num not in held:
            unresolved.append(c)
            continue
        match = num
        own, body = held[match]
        # Only parts the answer adds BEYOND the provision's own citation need proving. When the
        # provision IS s.4(1), citing s.4(1) adds nothing and requiring "(1)" inside its own
        # text would reject a correct citation.
        for part in set(re.findall(r"\(([^)]+)\)", norm)) - own:
            if f"({part})" not in body:
                unresolved.append(c)
                break
    return sorted(set(unresolved))


def should_abstain(question: str, provisions: list[dict], answer: str | None,
                   *, state: str = "") -> Verdict:
    """
    Runs twice: once before the LLM (answer=None) and once on its output.

    The pre-LLM pass is what makes this cheap — an abstention decided before the call costs ₹0,
    which is why the engine currently spends nothing at all.
    """
    q = question.lower()

    for pattern, subject in EDGE_CASES:
        if re.search(pattern, q):
            # Show the tension rather than only refusing. s.2(f) expressly includes contract
            # workers, probationers, trainees and apprentices in "employee" — so a user who
            # reads the Act will think this is settled. It is not, because the ten-figure does
            # not come from s.2(f): it comes from s.2(p), which counts "WORKERS", a word the Act
            # never defines. Whether those two sets coincide is the whole question, and naming
            # it is more useful than a flat no.
            return Verdict("abstain",
                           f"We will not answer {subject}, and here is exactly why. Section 2(f) "
                           f"defines \"employee\" very widely — it expressly includes \"a "
                           f"co-worker, a contract worker, probationer, trainee, apprentice or "
                           f"called by any other such name\". But the ten-person figure does not "
                           f"come from that definition. It comes from section 2(p), which counts "
                           f"\"workers\" — a word this Act never defines. Whether those two sets "
                           f"are the same is the question, and we are not going to decide it for "
                           f"you. Ask your District Officer or a labour lawyer, and tell us what "
                           f"they say — we will add it.", [], [])

    if any(k in q for k in CALCULATION):
        return Verdict("abstain",
                       "We don't do payroll arithmetic. A wrong number there is instantly "
                       "expensive, so we'd rather send you to your CA than guess.", [], [])

    if state and state not in SUPPORTED_STATES:
        return Verdict("abstain",
                       f"We haven't ingested the rules for {state} yet. We only answer where "
                       f"we hold the text.", [], [])

    if not provisions:
        return Verdict("abstain",
                       "We don't have verified information on this yet. Every question we "
                       "can't answer tells us which part of the law to read next.", [], [])

    unverified = [p for p in provisions if not p.get("verified_by")]
    if unverified:
        cites = ", ".join(sorted({p.get("citation", "?") for p in unverified})[:4])
        return Verdict("abstain",
                       f"We hold the text for {cites}, but no lawyer has verified our reading "
                       f"of it yet — so we won't state it as an answer. This is the honest "
                       f"state of the corpus, not a bug.", [], [])

    if answer is None:                       # pre-flight passed; the caller may now spend
        return Verdict("answer", "evidence packet is verified and complete", [], [])

    bad_nums = check_hallucination(answer, provisions)
    bad_cites = verify_citations(answer, provisions)
    if bad_nums or bad_cites:
        return Verdict("abstain",
                       "Our own check rejected the drafted answer before you saw it.",
                       bad_nums, bad_cites)

    low = answer.lower()

    if any(h in low for h in HEDGES):
        return Verdict("abstain",
                       "The drafted answer hedged, which means it wasn't grounded in the text.",
                       [], [])

    if any(a in low for a in ADVICE):
        return Verdict("abstain",
                       "The drafted answer told you what to do rather than what the law says. "
                       "We relay cited text; we do not advise. Rejected before you saw it.",
                       [], [])

    # No citation, no answer — unless the model is refusing, which needs none.
    if not _CITE.search(answer) and not any(r in low for r in REFUSALS):
        return Verdict("abstain",
                       "The drafted answer cited nothing. Every claim we pass on names the "
                       "section it came from, so an uncited one is discarded.",
                       [], [])

    return Verdict("answer", "verified against source", [], [])


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    verified = [{"citation": "s.4(1)", "text_display":
                 "Every employer of a workplace shall, by an order in writing, constitute a "
                 "Committee to be known as the Internal Complaints Committee",
                 "verified_by": "Adv. Test"}]
    unverified = [{**verified[0], "verified_by": None}]

    cases = [
        ("no provisions → abstain",
         should_abstain("do I need an IC?", [], None).abstained, True),
        ("unverified corpus → abstain (this is us, today)",
         should_abstain("do I need an IC?", unverified, None).abstained, True),
        ("verified + no answer yet → clear to spend",
         should_abstain("do I need an IC?", verified, None).abstained, False),
        ("payroll arithmetic → abstain",
         should_abstain("calculate my PF liability", verified, None).abstained, True),
        ("unsupported state → abstain",
         should_abstain("do I need an IC?", verified, None, state="IN-XX").abstained, True),
        ("grounded answer passes",
         should_abstain("do I need an IC?", verified,
                        "Yes. Every employer of a workplace shall constitute a Committee "
                        "[s.4(1)].").abstained, False),
        ("fabricated number → abstain",
         should_abstain("do I need an IC?", verified,
                        "You need one at 10 or more employees [s.4(1)].").abstained, True),
        ("unresolvable citation → abstain",
         should_abstain("do I need an IC?", verified,
                        "You must display the notice [s.19].").abstained, True),
        ("advice language → abstain (a live model wrote 'Action: You should…')",
         should_abstain("do I need an IC?", verified,
                        "Every employer shall constitute a Committee [s.4(1)]. "
                        "Action: You should constitute one.").abstained, True),
        ("uncited answer → abstain",
         should_abstain("how many employees?", verified,
                        "The Act applies regardless of headcount.").abstained, True),
        ("honest refusal needs no citation",
         should_abstain("when is it due?", verified,
                        "I don't have verified information on this.").abstained, False),
        ("edge case: interns → abstain even when verified",
         should_abstain("do interns count toward the ten?", verified, None).abstained, True),
        ("edge case: multi-state → abstain",
         should_abstain("we operate in three states, which rules apply?",
                        verified, None).abstained, True),
        ("'Internal Committee' does NOT trip the intern rule",
         should_abstain("do I need an Internal Committee?", verified, None).abstained, False),
        ("hedging → abstain",
         should_abstain("do I need an IC?", verified,
                        "I think you probably need a Committee [s.4(1)].").abstained, True),
    ]

    failures = 0
    for name, got, want in cases:
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")

    v = should_abstain("do I need an IC?", verified,
                       "You need one at 10 or more employees by 31 January [s.4(1)].")
    caught = v.unsupported_numbers
    ok = "10" not in _BENIGN and set(caught) >= {"10", "31"}
    failures += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] names the fabricated figures: {caught}")

    total = len(cases) + 1
    print(f"\n{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)
