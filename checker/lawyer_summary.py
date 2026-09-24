"""The lawyer summary: a sentence is traced to a span, or it is refused and shown as refused.

D4. A checked document produces a `placedon.ask/0` turn (scripts/serve_ask.py) and that
turn is not what a lawyer reads. Somebody has to say, in sentences, what the document is
and what the check found. The moment a model writes those sentences, the product's whole
claim is at risk: fluent prose is exactly the shape an invented fact arrives in, and it
arrives wearing the authority of the sentences around it.

So this module does not produce a summary. It produces a summary **in which every
sentence is either traced to a span of admitted evidence or visibly refused**.

## What "traced" means here, and what it does not mean

Opus is called with `citations: {enabled: true}`, so every text block comes back carrying
`char_location` citations: a document index and exact start/end character offsets. A
sentence is TRACED when, independently of anything the model said about itself:

  1. it carries at least one citation;
  2. the citation names a source we actually sent;
  3. the offsets lie inside that source;
  4. `source.text[start:end]` is **byte-identical** to the text the model said it read;
  5. the cited span is neither vacuous (" of the ", which could sit under any
     sentence) nor overbroad (the whole document, which contains every word any
     sentence could need);
  6. the sentence introduces no date, no figure and no provision citation that is absent
     from the cited span, and asserts no legal conclusion absent from it
     (`reasoning.review()`, run with the cited span as the verified material);
  7. the sentence's distinctive vocabulary overlaps the cited span's (less the words
     of a reporting frame, which by construction cannot be in the span);
  8. if it states what the law requires, it is cited to the ENGINE, not to the document.

TRACED IS NOT ENTAILMENT. A sentence can quote a real span, at real offsets, share its
vocabulary, and still assert something the span does not say. `ENTAILED` is declared below
and **never returned**, for the same reason `claim_verifier.SUPPORTED` never is: naming a
weaker check after a stronger one is the overclaim this repository exists to prevent. A
reader of `establishes_entailment()` gets False for every verdict this module can produce.

What the checks above do have is teeth in the other direction: each of them FAILING is
decisive. They do not close every route, and the first draft of this file claimed they did.

## What still gets through, stated rather than implied

A verifier broke the earlier version of this module four ways, and two of those holes were
holes in the IDEA, not in the code. What remains after the fixes:

  * **A clause on a conjunction the splitter does not know.** Coverage is a fraction, so a
    true clause can pay for a false one. That is why coverage is now measured per clause as
    well as per sentence -- but `_CLAUSE_SPLIT` is a pattern, and a fabrication joined by
    something it does not list still rides on the sentence's own coverage.
  * **A law assertion phrased in a way `_LAW_ASSERTION` does not recognise**, which then
    never has to face the engine-only test. Same limit `reasoning._CONCLUSIONS` states
    about itself.
  * **A false statement of law wearing a reporting frame.** "The document states that a
    small company must ..." is a faithful report of a document and is allowed to cite the
    document. A reader skimming may still take the clause for law. Mitigation today is
    presentational -- the frame plus the anchor -- and not mechanical.
  * **Entailment itself.** Nothing here decides it. See below.

None of these is a reason to trust the traced sentences less than the checks warrant; they
are the reason the headline of this file says "traced", and not "supported".

## (8) is the wedge, not a nicety

The document's own recital of the law is the thing this product exists to distrust: an
AGM notice reciting the small-company limits of G.S.R. 700(E) in 2026 is reciting
superseded law, correctly quoted. A summary sentence that restates a legal requirement
and cites the document has laundered the document's stale recital into our voice. So a
law assertion must cite the ENGINE -- the deterministic check's own output -- or it is
refused. A sentence that merely REPORTS what the document says ("the notice states that
the meeting shall be held on ...") is a fact about the document, and is allowed.

That distinction is drawn by a pattern, which is narrower than the rule it serves, and a
novel phrasing can evade it -- the same honest limit `reasoning._CONCLUSIONS` states about
itself. It is not the only gate; (4) and (6) do not depend on phrasing at all.

## What happens to a sentence that does not trace

**It is kept, verbatim, and quarantined.** Not deleted, not summarised into a count, and it
does not make the whole summary refuse. The alternatives were considered and are worse:

  * *Delete it silently, show a count.* CLAUDE.md: preserve uncertainty, never silently
    drop an unresolved marker. A count tells a reviewer that something was refused and
    withholds the one thing they need to judge it -- what the model actually asserted. It
    also destroys the audit trail for the model's behaviour on this document.
  * *Refuse the whole summary on any refusal.* One ungrounded sentence would discard a
    dozen traced ones, and the pressure that creates is to loosen the checks until the
    summary survives. A gate that is expensive to trip gets tuned until it stops tripping.

So the readable summary carries ONLY traced sentences, each printed with its anchor; the
refused ones are printed below it, verbatim, under a heading that says they are shown
because they were written and not because they are true; and the summary body carries a
banner naming how many were refused, so a reader who reads nothing else still learns that
the model wrote things that did not trace.

The one case where the whole thing refuses is when NOTHING traces. An empty summary would
read as "there was nothing to say about this document", which is a different and false
statement -- the same reason `evidence_pack` refuses to let a withheld provision look like
a provision that does not exist.

## Not wrapped

The sources go to Anthropic as document content blocks, byte-identical.
`prompt_safety.wrap_untrusted()` must NOT touch this path: a prefix shifts every
`char_location` offset, and the tracing above is offsets. `UNTRUSTED_CLAUSE` travels in the
system prompt instead, which is the half of CLAUDE.md's two-halves rule that IS universal.

Run: python3 checker/lawyer_summary.py      # stubs only: no network, no key, no spend
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker import reasoning
from checker.anthropic_model import (EXTRACT, Call, ModelUnavailable, available,
                                     cost_inr)
from checker.claim_verifier import distinctive_terms
from checker.prompt_safety import UNTRUSTED_CLAUSE
from checker.reasoning import (CITATION_OUTSIDE_PACK, CONCLUSION_ASSERTED, DATE_INVENTED,
                               FIGURE_INVENTED, Proposal)

__all__ = ["Source", "Citation", "Sentence", "Summary", "DOCUMENT", "ENGINE",
           "TRACED", "ENTAILED", "VERDICTS", "establishes_entailment",
           "document_source", "engine_source", "check_blocks", "blocks_from_response",
           "sentences_of", "clauses_of", "verify_sentence", "summarise", "SUMMARISE"]

# The founder's decision for D4 (plan, DEMO PLAN): Opus for lawyer summaries. Note the
# tension with anthropic_model's tiering, which puts narration on Sonnet because narration
# cannot introduce a fact. This path is narration-shaped but it also SELECTS what matters
# out of a long filing, which is a reading task, and it is the reading that Opus buys.
SUMMARISE = EXTRACT

DOCUMENT = "DOCUMENT"      # the checked document: evidence of what the document says
ENGINE = "ENGINE"          # the deterministic turn: evidence of what the check found
KINDS = (DOCUMENT, ENGINE)

TRACED = "TRACED"
ENTAILED = "ENTAILED"                        # reserved; never returned. See the docstring.
NO_CITATION = "NO_CITATION"
CITATION_NOT_IN_EVIDENCE = "CITATION_NOT_IN_EVIDENCE"
SPAN_OUT_OF_RANGE = "SPAN_OUT_OF_RANGE"
SPAN_MISQUOTED = "SPAN_MISQUOTED"
SPAN_VACUOUS = "SPAN_VACUOUS"
TERMS_NOT_IN_SPAN = "TERMS_NOT_IN_SPAN"
LAW_FROM_DOCUMENT = "LAW_FROM_DOCUMENT"
SPAN_OVERBROAD = "SPAN_OVERBROAD"
# The four content failures are `reasoning`'s own names, not new ones. They are the same
# failures it already refuses narration for -- an invented date, an invented figure, a
# citation to something outside the verified material, a legal conclusion nobody reached --
# and the only thing this module changes is WHAT counts as verified material: here it is the
# span this sentence cited, which is a far narrower bar than the whole document. A second
# vocabulary for one failure is how two names for one thing start disagreeing.
VERDICTS = (TRACED, ENTAILED, NO_CITATION, CITATION_NOT_IN_EVIDENCE, SPAN_OUT_OF_RANGE,
            SPAN_MISQUOTED, SPAN_VACUOUS, SPAN_OVERBROAD, TERMS_NOT_IN_SPAN,
            LAW_FROM_DOCUMENT,
            DATE_INVENTED, FIGURE_INVENTED, CITATION_OUTSIDE_PACK, CONCLUSION_ASSERTED)


def establishes_entailment(verdict: str) -> bool:
    """Whether this verdict means the cited span ENTAILS the sentence.

    False for everything this module returns, TRACED included. A caller that treats
    tracing as entailment is the failure the module exists to prevent, so the question has
    to be asked out loud rather than inferred from a verdict's name.
    """
    return verdict == ENTAILED


# THE VOCABULARY BAR, and the two lessons that set it.
#
# It is a FRACTION, and a fraction dilutes. A verifier demonstrated the failure on this
# module's own fixture: "the auditors have resigned" refuses on its own, and the SAME
# fabrication conjoined to a supported clause -- "...will be held on Thursday, 14 August
# 2025 and that the auditors have resigned" -- reached 0.77 and TRACED, then printed in the
# readable body with an anchor and no banner. Ten true terms had paid for three false ones.
# So coverage is measured on each CLAUSE that is substantial enough to be a claim, as well
# as on the whole sentence, and any one of them failing refuses the sentence.
#
# And it was too low. The same verifier showed UNDER-refusal at both thresholds, against a
# prediction that over-refusal was the likelier failure -- that prediction was wrong, and
# 0.5 was the number it was wrong about. At 0.7, and on clauses, a sentence has to be
# mostly about what it cited. It is a judgement, not a derivation, and the kill-test
# harness below is what stops it from becoming a number nothing depends on.
_MIN_COVERAGE = 0.7
# A fragment with fewer distinctive words than this is not a claim of its own -- it is a
# noun phrase the splitter cut ("books and papers"), and holding it to a coverage bar would
# refuse ordinary legal prose.
_MIN_CLAUSE_TERMS = 2
# The conjunctions a fabricated clause actually arrives on. This is a pattern, so it is
# narrower than the rule it serves: a conjunction not listed here still carries its clause
# on the whole sentence's coverage. That residue is stated in the docstring rather than
# hidden.
_CLAUSE_SPLIT = re.compile(
    r"(?:;|\b(?:and|but|while|whereas|although|though|however|also|moreover|furthermore)"
    r"\b)(?:\s+that\b)?", re.I)

# THE SPAN SIZE BARS. Both are absolute. The first version of this check scaled the budget
# with the SENTENCE's own length (20x, floor 600), and a verifier broke it twice over: a
# 387-character sentence bought a 7,740-character budget and swallowed the whole fixture,
# and the 600 floor sat above the 412-character fixture, so citing an entire short source
# was never refused at all -- the exact defect the commit was named for, still reachable.
# A bar a model can widen by writing more is not a bar. So: a span may not exceed
# _MAX_SPAN_CHARS characters, and the text cited out of any one source may not exceed
# _MAX_SOURCE_FRACTION of it, whatever the sentence looks like.
_MAX_SPAN_CHARS = 1000
_MAX_SOURCE_FRACTION = 0.6

# A sentence that says what the law requires, rather than what this document says.
_LAW_ASSERTION = re.compile(
    r"\b(?:shall|must|is required to|are required to|requires|required under|mandates|"
    r"prescribes|prescribed under|is obliged to|obligation to)\b", re.I)
# ...reporting the document's own words is a fact ABOUT the document, not a statement of
# law, and is allowed to cite the document.
_REPORTING = re.compile(
    r"\bthe (?:document|notice|minutes|resolution|filing|letter|circular|report|"
    r"intimation|extract|specimen)\b[^.]{0,40}?\b(?:states|stated|records|recites|says|"
    r"sets out|gives|shows|bears|names|lists|declares|is dated)\b", re.I)

# ...and the frame's OWN words are not part of what the sentence claims. The prompt asks
# for "The notice records that ...", and those words can never appear in the document span
# by construction, so counting them against the span's coverage charges a sentence for
# obeying our own instruction. Stripped from the vocabulary check ONLY when the sentence is
# a reporting frame, and only the frame words themselves -- never a span of text between
# them, which would be a hole a model could put a claim in. The date, figure, citation and
# conclusion checks still run over the FULL sentence, so nothing material hides here.
_FRAME_WORDS = re.compile(
    r"\b(?:document|notice|minutes|resolution|filing|letter|circular|report|intimation|"
    r"extract|specimen|states|stated|records|recites|says|sets out|gives|shows|bears|"
    r"names|lists|declares|dated)\b", re.I)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'“])")


@dataclass(frozen=True)
class Source:
    """One block of admitted evidence, exactly as it was sent to the model."""
    source_id: str
    kind: str
    text: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.kind!r} is not an evidence kind; one of {KINDS}")


@dataclass(frozen=True)
class Citation:
    """A `char_location` as it came back, before anything is believed about it."""
    source_index: int
    start: int
    end: int
    quoted: str                     # what the model SAID it read there

    def to_dict(self) -> dict:
        return dict(source_index=self.source_index, start=self.start, end=self.end,
                    quoted=self.quoted)


@dataclass(frozen=True)
class Sentence:
    text: str
    verdict: str
    citations: tuple[Citation, ...] = ()
    reasons: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()       # "<source_id> [start:end]", for a human to check
    shares_citation: bool = False       # it rode in on a block that held other sentences

    @property
    def traced(self) -> bool:
        return self.verdict == TRACED

    def to_dict(self) -> dict:
        return dict(text=self.text, verdict=self.verdict, reasons=list(self.reasons),
                    anchors=list(self.anchors), shares_citation=self.shares_citation,
                    citations=[c.to_dict() for c in self.citations])


@dataclass(frozen=True)
class Summary:
    sentences: tuple[Sentence, ...]
    sources: tuple[Source, ...]
    call: Call | None = None

    @property
    def traced(self) -> tuple[Sentence, ...]:
        return tuple(s for s in self.sentences if s.traced)

    @property
    def refused(self) -> tuple[Sentence, ...]:
        return tuple(s for s in self.sentences if not s.traced)

    @property
    def refused_entirely(self) -> bool:
        """Nothing traced. An empty summary would read as 'nothing to report'."""
        return not self.traced

    def refusal_reason(self) -> str | None:
        if not self.refused_entirely:
            return None
        if not self.sentences:
            return ("the model returned nothing that could be read as a sentence, so "
                    "there is no summary -- which is not the same as a document with "
                    "nothing in it")
        return (f"nothing traced: all {len(self.sentences)} sentence(s) the model wrote "
                f"failed to trace to admitted evidence, so there is no summary. The "
                f"sentences are preserved below as a record of what was written")

    def prose(self) -> str:
        """What a lawyer reads. Traced sentences only -- and never silently so."""
        if self.refused_entirely:
            return f"NO SUMMARY — {self.refusal_reason()}"
        out = []
        if self.refused:
            # The count rides in the summary body itself. A reader who reads nothing
            # else still learns that the model wrote sentences that did not trace.
            out.append(f"[{len(self.refused)} of {len(self.sentences)} sentence(s) the "
                       f"model wrote did not trace to admitted evidence and are not "
                       f"part of this summary. They are preserved in full below.]")
            out.append("")
        for i, s in enumerate(self.traced, start=1):
            out.append(f"{i}. {s.text}")
            out.append(f"   — {'; '.join(s.anchors)}")
        return "\n".join(out)

    def render(self) -> str:
        out = [self.prose()]
        if self.refused:
            out += ["", f"NOT TRACED ({len(self.refused)})",
                    "These sentences are shown because they were written, not because "
                    "they are true. Nothing here was traced to admitted evidence and "
                    "nothing here is a finding.", ""]
            for s in self.refused:
                out.append(f"  ✗ {s.text}")
                out.append(f"    {s.verdict}: {'; '.join(s.reasons)}")
        return "\n".join(out)

    def to_dict(self) -> dict:
        return dict(
            sentences=[s.to_dict() for s in self.sentences],
            traced_count=len(self.traced), refused_count=len(self.refused),
            refused_entirely=self.refused_entirely,
            refusal_reason=self.refusal_reason(),
            sources=[dict(source_id=s.source_id, kind=s.kind, chars=len(s.text))
                     for s in self.sources],
            call=(None if self.call is None else
                  dict(model=self.call.model, tokens_in=self.call.tokens_in,
                       tokens_out=self.call.tokens_out, cost_inr=self.call.cost_inr)),
            prose=self.prose())


def document_source(doc_id: str, text: str) -> Source:
    """The checked document, exactly as it will be sent. Never wrapped, never trimmed."""
    return Source(doc_id, DOCUMENT, text)


def engine_source(turn: dict) -> Source:
    """The check's own output as text, so a sentence about the CHECK can cite a span.

    Every value here is a string the turn already contains, copied verbatim. The labels
    around them are this function's, and they are fixed: the same turn must render to the
    same bytes twice or an offset into it means nothing.
    """
    def rows(key: str, fields: tuple[str, ...]) -> list[str]:
        out = []
        for row in turn.get(key) or ():
            if not isinstance(row, dict):
                continue
            parts = [f"{f}: {row[f]}" for f in fields
                     if isinstance(row.get(f), str) and row[f]]
            if parts:
                out.append("  - " + "; ".join(parts))
        return out

    lines = ["WHAT THE CHECK FOUND",
             f"result state: {turn.get('state', '(none recorded)')}"]
    for key, sub in (("scope", "sentence"), ("scope_frame", "sentence"),
                     ("law_version", "statement")):
        block = turn.get(key)
        if isinstance(block, dict) and isinstance(block.get(sub), str) and block[sub]:
            lines.append(f"{key}: {block[sub]}")
    sup = rows("superseded", ("duty", "provision", "governed_then", "governs_now",
                              "detail"))
    if sup:
        lines += ["the law moved under this document:"] + sup
    con = rows("confirmed", ("duty", "provision", "state", "basis"))
    if con:
        lines += ["confirmed:"] + con
    nc = rows("not_confirmed", ("kind", "duty", "provision", "detail"))
    if nc:
        lines += ["not confirmed:"] + nc
    for note in turn.get("what_it_is_not") or ():
        if isinstance(note, str) and note:
            lines.append(f"what this is not: {note}")
    return Source(f"engine:{turn.get('turn_id', 'turn')}", ENGINE, "\n".join(lines) + "\n")


def sentences_of(text: str) -> tuple[str, ...]:
    """One block of model text -> its sentences, whitespace collapsed, nothing dropped."""
    flat = " ".join(text.split())
    if not flat:
        return ()
    return tuple(p.strip() for p in _SENTENCE_SPLIT.split(flat) if p.strip())


def clauses_of(text: str) -> tuple[str, ...]:
    """The parts of a sentence that could each be a claim, split on plain conjunctions."""
    return tuple(p.strip() for p in _CLAUSE_SPLIT.split(text) if p and p.strip())


def verify_sentence(text: str, citations, sources, *, shares_citation: bool = False
                    ) -> Sentence:
    """One sentence, checked against the spans it cited. Refuses; never repairs."""
    text = " ".join(text.split())
    cits = tuple(citations)
    srcs = tuple(sources)

    def no(verdict: str, *reasons: str, anchors: tuple[str, ...] = ()) -> Sentence:
        return Sentence(text, verdict, cits, tuple(reasons), anchors, shares_citation)

    if not cits:
        return no(NO_CITATION,
                  "the model wrote this sentence without citing anything; there is no "
                  "span to trace it to")

    anchors: list[str] = []
    spans: list[tuple[Source, str]] = []
    for c in cits:
        if not 0 <= c.source_index < len(srcs):
            return no(CITATION_NOT_IN_EVIDENCE,
                      f"cites source {c.source_index}, and only {len(srcs)} source(s) "
                      f"were admitted")
        src = srcs[c.source_index]
        if not 0 <= c.start < c.end <= len(src.text):
            return no(SPAN_OUT_OF_RANGE,
                      f"the offsets [{c.start}:{c.end}] do not lie inside "
                      f"{src.source_id} ({len(src.text)} characters). Refused, not "
                      f"clamped: a clamped span is a span nobody chose")
        actual = src.text[c.start:c.end]
        if actual != c.quoted:
            return no(SPAN_MISQUOTED,
                      f"what the model said it read is not what sits at those offsets, "
                      f"byte for byte: {src.source_id}[{c.start}:{c.end}] is "
                      f"{actual[:60]!r}, the model quoted {c.quoted[:60]!r}")
        anchors.append(f"{src.source_id} [{c.start}:{c.end}]")
        spans.append((src, actual))

    span_text = "\n".join(a for _, a in spans)
    span_terms = distinctive_terms(span_text)
    if not span_terms:
        return no(SPAN_VACUOUS,
                  "the cited span carries no distinctive words, so it could stand under "
                  "any sentence at all", anchors=tuple(anchors))

    if len(span_text) > _MAX_SPAN_CHARS:
        return no(SPAN_OVERBROAD,
                  f"{len(span_text)} characters were cited for one sentence. A span that "
                  f"size contains every word the sentence could need and shows nothing "
                  f"about where it was read; cite the passage, not the document",
                  anchors=tuple(anchors))
    per_source: dict[str, int] = {}
    for src, actual in spans:
        per_source[src.source_id] = per_source.get(src.source_id, 0) + len(actual)
    for src, _ in spans:
        cited, whole = per_source[src.source_id], len(src.text)
        if whole and cited > _MAX_SOURCE_FRACTION * whole:
            return no(SPAN_OVERBROAD,
                      f"{cited} of {src.source_id}'s {whole} characters were cited for "
                      f"one sentence. Citing most of a source is gesturing at it, not "
                      f"quoting it, and it defeats every vocabulary test at once",
                      anchors=tuple(anchors))

    # The wedge. A statement of what the law requires may not rest on the document's own
    # recital of it: that recital is exactly what this product exists to distrust.
    #
    # The first version asked whether the sentence cited ONLY the document, which is not
    # the same rule and a verifier walked through the gap: add one engine citation beside
    # the document one and the bare statement of law passes, carried by the document's
    # stale recital. So a law assertion is now checked against the ENGINE spans ALONE. A
    # document span sitting next to one lends it nothing.
    if _LAW_ASSERTION.search(text) and not _REPORTING.search(text):
        engine_spans = [a for s, a in spans if s.kind == ENGINE]
        if not engine_spans:
            return no(LAW_FROM_DOCUMENT,
                      "this states what the law requires and cites no result of the "
                      "check. The document is not the law — its recital of the law may "
                      "be the superseded one, which is the defect this check looks for. "
                      "A legal position must cite the engine's own result",
                      anchors=tuple(anchors))
        span_text = "\n".join(engine_spans)
        span_terms = distinctive_terms(span_text)
        if not span_terms:
            return no(SPAN_VACUOUS,
                      "this states what the law requires, so only the engine's own "
                      "result can support it, and the engine span cited carries no "
                      "distinctive words", anchors=tuple(anchors))

    # `reasoning.review()`, with the CITED SPAN as the verified material.
    rev = reasoning.review(Proposal(narration=text), declared_intents=(),
                           verified_text=span_text)
    if rev.refusals:
        r = rev.refusals[0]
        return no(r.violation, *[x.detail for x in rev.refusals],
                  anchors=tuple(anchors))

    claimed = _FRAME_WORDS.sub(" ", text) if _REPORTING.search(text) else text
    if not distinctive_terms(claimed):
        return no(TERMS_NOT_IN_SPAN,
                  "the sentence carries no distinctive words of its own, so there is "
                  "nothing in it that the span could be said to support",
                  anchors=tuple(anchors))
    # The whole sentence AND every clause substantial enough to be a claim. A true clause
    # may not buy a false one a passing fraction.
    for part in (claimed,) + clauses_of(claimed):
        want = distinctive_terms(part)
        if part is not claimed and len(want) < _MIN_CLAUSE_TERMS:
            continue
        shared = want & span_terms
        coverage = len(shared) / len(want) if want else 0.0
        if coverage < _MIN_COVERAGE:
            where = "this sentence" if part is claimed else f"the clause {part.strip()!r}"
            return no(TERMS_NOT_IN_SPAN,
                      f"the cited span does not carry what {where} is about "
                      f"(coverage {coverage:.2f}; absent: "
                      f"{', '.join(sorted(want - shared)[:6])})",
                      anchors=tuple(anchors))

    return Sentence(text, TRACED, cits, (), tuple(anchors), shares_citation)


def check_blocks(blocks, sources, *, call: Call | None = None) -> Summary:
    """Every sentence of every returned block, each checked on its own.

    A block's citations attach to the BLOCK, so two sentences in one block share them.
    Checking them jointly would let the second ride in on the first's span, so each is
    checked alone and both are marked `shares_citation` -- the reviewer is told that the
    attribution is the block's, not the sentence's.
    """
    srcs = tuple(sources)
    out: list[Sentence] = []
    for text, cits in blocks:
        parts = sentences_of(text)
        shared = len(parts) > 1
        for part in parts:
            out.append(verify_sentence(part, cits, srcs, shares_citation=shared))
    return Summary(tuple(out), srcs, call)


def blocks_from_response(resp) -> tuple[tuple[str, tuple[Citation, ...]], ...]:
    """(text, citations) per returned block. Reads the SDK shape and the dict shape."""
    def field(obj, name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    blocks = []
    for b in field(resp, "content", ()) or ():
        if field(b, "type") != "text":
            continue
        cits = []
        for c in field(b, "citations") or ():
            if field(c, "type") != "char_location":
                # A citation shape we cannot check offsets in is not a citation here.
                continue
            cits.append(Citation(int(field(c, "document_index", -1) or 0),
                                 int(field(c, "start_char_index", -1) or 0),
                                 int(field(c, "end_char_index", -1) or 0),
                                 str(field(c, "cited_text", "") or "")))
        blocks.append((str(field(b, "text", "") or ""), tuple(cits)))
    return tuple(blocks)


_SUMMARY_SYSTEM = UNTRUSTED_CLAUSE + """

You write a short summary, for an Indian corporate lawyer, of ONE document that has
already been checked. You are given two sources: the document itself, and the result of
the check that was run on it.

Rules, and a sentence that breaks one is thrown away rather than corrected:

- Every sentence must be drawn from, and cite, the exact text you read it from.
- One proposition per sentence. Keep sentences short.
- When you say what the DOCUMENT says, say so: "The document states ...",
  "The notice records ...".
- Do NOT state what the law requires from the document's own recital of the law. A
  statement about the law must come from the result of the check. The document may be
  reciting law that has since been superseded; that is what the check is for.
- Introduce no date, no rupee figure and no provision number that is absent from the text
  you cite for that sentence.
- Do not say whether anybody complied, and do not advise.

Write between five and ten sentences. If you cannot support a sentence from the sources,
do not write it."""


def summarise(sources, *, question: str = "", client=None, model: str = SUMMARISE,
              budget=None) -> Summary:
    """Call the model and return the CHECKED summary. Nothing here trusts the output."""
    srcs = tuple(sources)
    if client is None:
        if not available():
            raise ModelUnavailable(
                "ANTHROPIC_API_KEY is not set, or the anthropic SDK is not installed. "
                "This refuses rather than returning an empty summary, because a summary "
                "with no sentences in it reads as a document with nothing to report.")
        import anthropic
        client = anthropic.Anthropic()
    if budget is not None and not budget.can_make_call():
        raise ModelUnavailable("budget exhausted; no call was made")

    content = [{"type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": s.text},
                "title": s.source_id,
                "citations": {"enabled": True}} for s in srcs]
    content.append({"type": "text",
                    "text": question or "Summarise this document and the result of the "
                                        "check on it, for a lawyer."})
    resp = client.messages.create(model=model, max_tokens=2048, system=_SUMMARY_SYSTEM,
                                  messages=[{"role": "user", "content": content}])
    blocks = blocks_from_response(resp)
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    raw = "".join(t for t, _ in blocks)
    call = Call(model, tin, tout, cost_inr(model, tin, tout), raw)
    return check_blocks(blocks, srcs, call=call)


# ── tests: stubs only. No network, no key, no spend. ──────────────────────────
DOC_TEXT = """NOTICE OF ANNUAL GENERAL MEETING

Notice is hereby given that the Twelfth Annual General Meeting of Vaidya Industries
Limited will be held on Thursday, 14 August 2025 at 11:00 a.m. at the registered
office of the Company at Pune.

The Company is a small company within the meaning of section 2(85) of the Companies
Act, 2013, the paid-up share capital of the Company being Rs. 3,50,00,000.

Date: 14 August 2025
"""

TURN = {
    "schema": "placedon.ask/0",
    "state": "partial",
    "question": "Is the law this document relies on still current?",
    "as_of": "2026-09-23",
    "context": {"kind": "document", "document_date": "2025-08-14"},
    "scope": {"held": ["Companies Act, 2013"],
              "sentence": "1 of 9 in-scope bodies of law are held"},
    "law_version": {"statement": "The law is read as India Code renders it today."},
    "superseded": [{
        "duty": "Establish whether the company is a small company",
        "provision": "Companies Act 2013, s.2(85)",
        "governed_then": "G.S.R. 700(E), dated 15-09-2022",
        "governs_now": "G.S.R. 880(E), dated 01-12-2025",
        "detail": "the prescribed small-company limits were raised by G.S.R. 880(E)",
    }],
    "not_confirmed": [{"kind": "cannot_determine",
                       "duty": "Hold an annual general meeting, and within the "
                               "statutory gap",
                       "provision": "Companies Act 2013, s.96",
                       "detail": "no company facts were supplied with this check"}],
    "what_it_is_not": ["This is not advice on whether anybody complied."],
}


def mixed_prose_probe(sentence: Sentence, sources) -> str:
    """The readable body of a summary holding just this sentence. Used by the tests to
    assert that a refused sentence cannot reach a reader through prose()."""
    return Summary((sentence,), tuple(sources)).prose()


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

    print("lawyer_summary")

    doc = document_source("agm_notices/vaidya_2025", DOC_TEXT)
    eng = engine_source(TURN)
    sources = (doc, eng)

    def at(src: Source, needle: str) -> tuple[int, int]:
        i = src.text.index(needle)
        return i, i + len(needle)

    def cite(idx: int, needle: str, *, quoted: str | None = None,
             start: int | None = None, end: int | None = None) -> Citation:
        s, e = at(sources[idx], needle)
        return Citation(idx, start if start is not None else s,
                        end if end is not None else e,
                        quoted if quoted is not None else needle)

    # ── the engine source is the turn's own words, not a paraphrase ──────────
    check(eng.kind == ENGINE and doc.kind == DOCUMENT,
          "the two admitted evidence kinds are the document and the engine")
    check("G.S.R. 880(E), dated 01-12-2025" in eng.text,
          "the engine source carries the turn's strings verbatim")
    check(engine_source(TURN).text == eng.text,
          "...and renders identically twice, so an offset into it is stable")
    check(engine_source({"state": "abstained"}).text.strip() != "",
          "a thin turn still renders something rather than an empty source")

    # ── 1. a sentence that traces ────────────────────────────────────────────
    s_ok = verify_sentence(
        "The notice records that the Annual General Meeting will be held on "
        "Thursday, 14 August 2025.",
        (cite(0, "Annual General Meeting of Vaidya Industries\nLimited will be held on "
                 "Thursday, 14 August 2025"),), sources)
    check(s_ok.verdict == TRACED, f"a quoted, in-range, on-topic sentence is TRACED "
                                  f"({s_ok.verdict}: {'; '.join(s_ok.reasons)})")
    check(s_ok.anchors and "agm_notices/vaidya_2025" in s_ok.anchors[0],
          f"...and carries an anchor a human can check ({s_ok.anchors})")
    check(not establishes_entailment(s_ok.verdict),
          "...and TRACED does NOT establish entailment -- tracing is not grounding")
    check(not any(establishes_entailment(v) for v in VERDICTS if v != ENTAILED),
          "no verdict this module returns establishes entailment")

    # ── 2. no citation at all ────────────────────────────────────────────────
    s_none = verify_sentence("The company appears to be in good standing.", (), sources)
    check(s_none.verdict == NO_CITATION, "an uncited sentence is refused")

    # ── 3. offsets outside the source ────────────────────────────────────────
    s_range = verify_sentence(
        "The meeting is to be held at the registered office at Pune.",
        (Citation(0, len(DOC_TEXT) - 5, len(DOC_TEXT) + 400, "registered office"),),
        sources)
    check(s_range.verdict == SPAN_OUT_OF_RANGE, "offsets past the end of the source are "
                                                "refused, not clamped")
    s_src = verify_sentence("Something about a third document.",
                            (Citation(7, 0, 10, "whatever"),), sources)
    check(s_src.verdict == CITATION_NOT_IN_EVIDENCE,
          "a citation naming a source we never sent is refused")

    # ── 4. the quote must be what is actually at those offsets ───────────────
    start, end = at(doc, "paid-up share capital of the Company being Rs. 3,50,00,000")
    s_fake = verify_sentence(
        "The paid-up share capital of the Company is Rs. 3,50,00,00,000.",
        (Citation(0, start, end,
                  "paid-up share capital of the Company being Rs. 3,50,00,00,000"),),
        sources)
    check(s_fake.verdict == SPAN_MISQUOTED,
          f"a quote that is not what sits at those offsets is refused "
          f"({s_fake.verdict})")
    check(any("byte" in r or "not what" in r for r in s_fake.reasons),
          f"...and the reason says the span was misquoted ({s_fake.reasons})")

    # ── 5. a span that establishes nothing ───────────────────────────────────
    s_vac = verify_sentence("The Company is well governed.",
                            (cite(0, " of the "),), sources)
    check(s_vac.verdict == SPAN_VACUOUS,
          f"a citation pointing at filler traces nothing ({s_vac.verdict})")

    # ── 6. reasoning.review()'s teeth, run against the CITED SPAN ────────────
    s_date = verify_sentence(
        "The Annual General Meeting of Vaidya Industries was held on 3 March 2024.",
        (cite(0, "Annual General Meeting of Vaidya Industries"),), sources)
    check(s_date.verdict != TRACED and any("date" in r.lower() for r in s_date.reasons),
          f"a date absent from the cited span is refused ({s_date.verdict}: "
          f"{s_date.reasons})")
    s_fig = verify_sentence(
        "The Annual General Meeting of Vaidya Industries concerns Rs. 9,00,00,000.",
        (cite(0, "Annual General Meeting of Vaidya Industries"),), sources)
    check(s_fig.verdict != TRACED,
          f"a figure absent from the cited span is refused ({s_fig.verdict})")
    s_cit = verify_sentence(
        "The Annual General Meeting of Vaidya Industries falls under section 173.",
        (cite(0, "Annual General Meeting of Vaidya Industries"),), sources)
    check(s_cit.verdict != TRACED,
          f"a provision citation absent from the cited span is refused ({s_cit.verdict})")

    # ── 7. fluent, real span, wrong subject ──────────────────────────────────
    s_off = verify_sentence(
        "The auditors resigned during the year and the vacancy remains unfilled.",
        (cite(0, "registered\noffice of the Company at Pune"),), sources)
    check(s_off.verdict == TERMS_NOT_IN_SPAN,
          f"a fluent sentence about something the cited span does not mention is "
          f"refused ({s_off.verdict})")

    # ── 8. the wedge: law restated from the document's own recital ───────────
    s_law = verify_sentence(
        "A small company must have paid-up share capital within the prescribed limit "
        "under section 2(85) of the Companies Act, 2013.",
        (cite(0, "small company within the meaning of section 2(85) of the Companies\n"
                 "Act, 2013"),), sources)
    check(s_law.verdict == LAW_FROM_DOCUMENT,
          f"a statement of what the law requires, cited only to the document, is "
          f"refused ({s_law.verdict})")
    check(any("not the law" in r or "engine" in r.lower() for r in s_law.reasons),
          f"...and says why: the document is not the law ({s_law.reasons})")

    s_report = verify_sentence(
        "The notice states that the Company is a small company within the meaning of "
        "section 2(85).",
        (cite(0, "The Company is a small company within the meaning of section 2(85)"),),
        sources)
    check(s_report.verdict == TRACED,
          f"...but REPORTING what the document says is a fact about the document "
          f"({s_report.verdict}: {s_report.reasons})")

    s_eng_law = verify_sentence(
        "The prescribed small-company limits were raised by G.S.R. 880(E).",
        (cite(1, "the prescribed small-company limits were raised by G.S.R. 880(E)"),),
        sources)
    check(s_eng_law.verdict == TRACED,
          f"a legal position cited to the ENGINE's own output is traced "
          f"({s_eng_law.verdict}: {s_eng_law.reasons})")

    # ── a citation that gestures at a source traces nothing ─────────────────
    # Both bars are absolute. A verifier broke the sentence-scaled version twice: a long
    # sentence bought itself a budget big enough to swallow the source, and the floor sat
    # above the primary fixture so citing ALL of it was never refused.
    whole_primary = Citation(0, 0, len(DOC_TEXT), DOC_TEXT)
    s_whole = verify_sentence("The meeting is at Pune and the capital is small.",
                              (whole_primary,), sources)
    check(s_whole.verdict == SPAN_OVERBROAD,
          f"citing an ENTIRE short source is refused — the case the sentence-scaled "
          f"floor let through ({s_whole.verdict})")
    long_sentence = ("The notice records that the Annual General Meeting of the Company "
                     "will be held at the registered office at Pune, and it further "
                     "records the paid-up share capital, the class of the company, the "
                     "meaning of section 2(85), the date it bears and the hour at which "
                     "the meeting is to commence, all of which appear on its face. " * 2)
    s_long = verify_sentence(long_sentence, (whole_primary,), sources)
    check(s_long.verdict == SPAN_OVERBROAD,
          f"a long sentence does not buy itself a bigger span budget "
          f"({len(long_sentence)} characters of sentence: {s_long.verdict})")
    s_para = verify_sentence(
        "The notice records that the meeting is at the registered office at Pune.",
        (cite(0, "will be held on Thursday, 14 August 2025 at 11:00 a.m. at the "
                 "registered\noffice of the Company at Pune"),), sources)
    check(s_para.verdict == TRACED,
          f"...while an ordinary passage behind a short sentence still traces "
          f"({s_para.verdict}: {s_para.reasons})")

    # ── a true clause may not buy a false one a passing fraction ─────────────
    # The verifier's finding, reproduced as a test: the fabrication refuses alone, and
    # must still refuse when conjoined to something the span does support.
    span_meeting = ("Annual General Meeting of Vaidya Industries\nLimited will be held "
                    "on Thursday, 14 August 2025")
    alone = verify_sentence("The auditors have resigned.", (cite(0, span_meeting),),
                            sources)
    check(alone.verdict == TERMS_NOT_IN_SPAN, "the fabrication refuses on its own")
    diluted = verify_sentence(
        "The notice records that the Annual General Meeting will be held on Thursday, "
        "14 August 2025 and that the auditors have resigned.",
        (cite(0, span_meeting),), sources)
    check(diluted.verdict == TERMS_NOT_IN_SPAN,
          f"...and still refuses when conjoined to a clause the span DOES support "
          f"({diluted.verdict})")
    check(any("auditors" in r for r in diluted.reasons),
          f"...naming the clause that failed, not the sentence as a whole "
          f"({diluted.reasons})")
    check(diluted.text not in mixed_prose_probe(diluted, sources),
          "...and it never reaches the readable body")

    # ── the wedge is not bypassed by citing the engine BESIDE the document ───
    law_text = ("A small company must have paid-up share capital within the prescribed "
                "limit under section 2(85).")
    both = verify_sentence(
        law_text,
        (cite(0, "small company within the meaning of section 2(85) of the Companies\n"
                 "Act, 2013"),
         cite(1, "result state: partial")), sources)
    check(both.verdict != TRACED,
          f"a law claim is not laundered by adding an engine citation beside the "
          f"document one ({both.verdict})")
    check(both.verdict in (TERMS_NOT_IN_SPAN, SPAN_VACUOUS, CITATION_OUTSIDE_PACK),
          f"...it is judged against the ENGINE span alone: here the provision it names "
          f"is not in that span either, so the citation check refuses it first "
          f"({both.verdict}: {both.reasons})")
    check(verify_sentence(law_text, (cite(0, "small company within the meaning of "
                                             "section 2(85) of the Companies\nAct, "
                                             "2013"),), sources).verdict
          == LAW_FROM_DOCUMENT,
          "...and with no engine citation at all it is LAW_FROM_DOCUMENT, as before")

    # ── the reporting frame is not charged against the span ─────────────────
    s_frame = verify_sentence(
        "The notice records that the meeting is to be held at the registered office "
        "of the Company at Pune.",
        (cite(0, "will be held on Thursday, 14 August 2025 at 11:00 a.m. at the "
                 "registered\noffice of the Company at Pune"),), sources)
    check(s_frame.verdict == TRACED,
          f"a reporting sentence is not charged for the frame words our own prompt "
          f"asks for ({s_frame.verdict}: {s_frame.reasons})")
    s_frame_empty = verify_sentence(
        "The notice records that the auditors resigned during the year.",
        (cite(0, "registered\noffice of the Company at Pune"),), sources)
    check(s_frame_empty.verdict == TERMS_NOT_IN_SPAN,
          f"...and stripping the frame does not let its SUBSTANCE through unchecked "
          f"({s_frame_empty.verdict})")

    # ── a block holding two sentences: each is checked on its own ────────────
    span = "Annual General Meeting of Vaidya Industries\nLimited will be held on Thursday, 14 August 2025"
    blocks = ((
        "The notice records that the Annual General Meeting will be held on Thursday, "
        "14 August 2025. The Company has also declared a dividend of Rs. 5,00,000.",
        (cite(0, span),)),)
    two = check_blocks(blocks, sources)
    check(len(two.sentences) == 2, f"a block holding two sentences yields two "
                                   f"({len(two.sentences)})")
    check(two.sentences[0].traced and not two.sentences[1].traced,
          "...and the second cannot ride in on the first's citation")
    check(all(s.shares_citation for s in two.sentences),
          "...both are marked as sharing one block's citation")

    # ── the refusal design: kept, quarantined, counted, never deleted ────────
    mixed = check_blocks((
        ("The notice records that the Annual General Meeting will be held on Thursday, "
         "14 August 2025.", (cite(0, span),)),
        ("The Company is in compliance with the Companies Act, 2013.", ()),
    ), sources)
    check(len(mixed.traced) == 1 and len(mixed.refused) == 1,
          "one traced, one refused")
    body = mixed.prose()
    check("in compliance" not in body,
          "the readable summary does not contain the refused sentence")
    check("1" in body and "not trace" in body,
          f"...but it says on its face that a sentence did not trace ({body[:120]!r})")
    rendered = mixed.render()
    check("The Company is in compliance with the Companies Act, 2013." in rendered,
          "the refused sentence is preserved VERBATIM, not deleted and not summarised")
    check("NOT TRACED" in rendered and "written" in rendered,
          "...under a heading saying it is shown because it was written, not because "
          "it is true")
    check(NO_CITATION in rendered, "...with the verdict that refused it")
    check(not mixed.refused_entirely and mixed.refusal_reason() is None,
          "one refusal does not make the whole summary refuse")

    # ── nothing traced: the summary refuses rather than reading as empty ─────
    nothing = check_blocks((("The Company is in compliance.", ()),), sources)
    check(nothing.refused_entirely and nothing.prose().strip() != "",
          "when nothing traces the summary refuses, and does not render as blank")
    check("nothing" in (nothing.refusal_reason() or "").lower(),
          f"...and says so ({nothing.refusal_reason()})")
    empty = check_blocks((), sources)
    check(empty.refused_entirely, "a model that returned nothing produces a refusal")

    # ── the wire: citations on, document byte-identical, clause carried ──────
    class FakeResp:
        class _U:
            input_tokens, output_tokens = 9000, 600

        def __init__(self, blocks):
            self.content = [
                type("B", (), {"type": "text", "text": t,
                               "citations": [type("C", (), {
                                   "type": "char_location",
                                   "cited_text": c.quoted,
                                   "document_index": c.source_index,
                                   "start_char_index": c.start,
                                   "end_char_index": c.end})() for c in cs]})()
                for t, cs in blocks]
            self.usage = self._U()

    class FakeClient:
        def __init__(self, resp):
            self.resp, self.seen = resp, None

        class _M:
            def __init__(self, outer):
                self.outer = outer

            def create(self, **kw):
                self.outer.seen = kw
                return self.outer.resp

        @property
        def messages(self):
            return self._M(self)

    fc = FakeClient(FakeResp((
        ("The notice records that the Annual General Meeting will be held on Thursday, "
         "14 August 2025.", (cite(0, span),)),)))
    live = summarise(sources, client=fc)
    check(live.traced and live.sentences[0].traced,
          "the whole path, on a stub: a cited sentence comes back TRACED")
    check(live.call is not None and live.call.model == SUMMARISE
          and live.call.cost_inr > 0,
          f"...and the call records its model and what it cost "
          f"(₹{live.call.cost_inr if live.call else 0})")

    sent = fc.seen
    doc_blocks = [b for b in sent["messages"][0]["content"] if b["type"] == "document"]
    check(len(doc_blocks) == 2, "both sources are sent as document blocks")
    check(all(b["citations"] == {"enabled": True} for b in doc_blocks),
          "every source asks for citations -- the char offsets tracing depends on")
    check(doc_blocks[0]["source"]["data"] == DOC_TEXT,
          "the document reaches Anthropic BYTE-IDENTICAL: not one character prepended")
    check("<source>" not in doc_blocks[0]["source"]["data"],
          "...specifically unwrapped, because a prefix would shift every offset")
    check(UNTRUSTED_CLAUSE.split("\n")[0] in sent["system"],
          "the clause travels in the system prompt instead")
    check("output_config" not in sent,
          "no output_config, which would 400 alongside citations")
    check(sent["model"] == "claude-opus-5", f"the summary runs on Opus ({sent['model']})")

    # ── the parser reads the SDK's REAL citation shape, not a memory of it ───
    # Every other check here builds its own stubs, so a field-name drift in the SDK
    # would be invisible to all of them AND total in production: `blocks_from_response`
    # would find no citations, every sentence would refuse for NO_CITATION, and the
    # summary would look principled while being broken. So this one check builds the
    # installed SDK's own model objects. It still spends nothing and touches no network.
    try:
        from anthropic.types import TextBlock
        from anthropic.types.citation_char_location import CitationCharLocation
    except ImportError:            # counted in neither column; printed so it is seen
        print("  [SKIP] the anthropic SDK is not installed here, so the SDK-shape "
              "check did not run")
    else:
        sdk_start, sdk_end = at(doc, "will be held on Thursday, 14 August 2025 at "
                                     "11:00 a.m. at the registered\noffice of the "
                                     "Company at Pune")
        sdk_cit = CitationCharLocation(
            cited_text=DOC_TEXT[sdk_start:sdk_end], document_index=0,
            document_title=doc.source_id, start_char_index=sdk_start,
            end_char_index=sdk_end, type="char_location")
        sdk_resp = type("R", (), {
            "content": [TextBlock(text="The notice records that the meeting is to be "
                                       "held at the registered office of the Company "
                                       "at Pune.", type="text", citations=[sdk_cit])],
            "usage": type("U", (), {"input_tokens": 10, "output_tokens": 3})()})()
        parsed = blocks_from_response(sdk_resp)
        check(len(parsed) == 1 and len(parsed[0][1]) == 1,
              "a real SDK TextBlock carrying a real CitationCharLocation parses")
        got = parsed[0][1][0]
        check((got.source_index, got.start, got.end) == (0, sdk_start, sdk_end)
              and got.quoted == DOC_TEXT[sdk_start:sdk_end],
              "...into the offsets and the quote this module traces against")
        check(check_blocks(parsed, sources).sentences[0].traced,
              "...and the sentence it carries traces end to end")

    # ── no key: refuse, never a blank summary ────────────────────────────────
    import os as _os
    held = _os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        check(not available(), "with no key, available() is False")
        try:
            summarise(sources)
            check(False, "with no key, summarise() raises")
        except ModelUnavailable:
            check(True, "with no key, summarise() raises rather than returning an "
                        "empty summary")
    finally:
        if held is not None:
            _os.environ["ANTHROPIC_API_KEY"] = held

    class Broke:
        def can_make_call(self):
            return False

    try:
        summarise(sources, client=fc, budget=Broke())
        check(False, "an exhausted budget refuses BEFORE the call")
    except ModelUnavailable as e:
        check("no call was made" in str(e),
              "an exhausted budget refuses before the call, not after")

    # ── the record is complete: every sentence is in to_dict() ───────────────
    d = mixed.to_dict()
    check(len(d["sentences"]) == 2 and any(s["verdict"] == NO_CITATION
                                           for s in d["sentences"]),
          "the machine-readable record carries the refused sentence too")
    check(all(s["verdict"] in VERDICTS for s in d["sentences"]),
          "every verdict in the record is a declared one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
