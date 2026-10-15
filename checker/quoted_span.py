"""Attribution without a Citations API: the model quotes, and we go and find the quote.

`checker/lawyer_summary.py` traces every sentence to a span of admitted evidence, and it
gets the spans from Anthropic's Citations API -- `citations: {enabled: true}` returns a
`char_location` per text block, a document index and exact start/end offsets. Nothing else
in the market returns that. Gemini does not, Ollama does not, and the founder has no
Anthropic credit, so today the summariser cannot run at all.

This is the same guarantee reached the other way round.

    Citations API        the PROVIDER asserts offsets, and we check the text at them
    quoted span          the MODEL asserts text, and we find the offsets ourselves

## The second one is the stronger check, and this repo already knew it

`gemini_model.py` says it in its own header about a different path: *"`ground()` checks
the quoted span is ACTUALLY IN THE DOCUMENT, which is stronger than a provider asserting
where it read something. We verify against the source; the citation API only reports a
claim."* That is exactly the trade here. Under Citations, the check that bites is
`source.text[start:end] == cited_text` -- a check on the provider's bookkeeping. Under
this protocol the offsets are DERIVED from a search, so they cannot disagree with the text
by construction, and the check that bites is harder to pass: **the quote must exist in the
evidence at all**. A model cannot fabricate a passage that is in the document.

What is lost is real and worth naming: the provider's offsets tell you WHERE THE MODEL
READ, and a search tells you where the words happen to be. If a quote appears twice, this
picks the first occurrence, and that may not be the one the model meant. For this corpus
that is a small loss -- the spans are provisions and findings, not repeated boilerplate --
and the sentence is checked against the located span either way, so a sentence that only
works against the *other* occurrence is refused rather than mis-traced.

## Whitespace, and why the located offsets are still exact

A model reflows. It will return "small company within the meaning of section 2(85)" for
text that has a line break in the middle of it, and a byte-identical search would find
nothing. So the search is whitespace-tolerant, over a normalised copy carrying an index
back to the original -- and the Citation is then built with `quoted = source.text[start:end]`,
the ACTUAL bytes at the located offsets, not the model's reflowed version. Downstream,
`verify_sentence`'s byte-identity check therefore passes by construction on this path.
That is not the check being weakened; it is the check having already been done, earlier
and harder, by the search that refused to find anything else.

## The delimiter rule, which cuts the other way here

CLAUDE.md: `wrap_untrusted()` applies where untrusted text is CONCATENATED INTO A PROMPT
STRING, and must NEVER wrap the Anthropic extract path, because a prefix shifts the
`char_location` offsets that span grounding depends on. This path concatenates -- there is
no content block to carry the boundary -- so it wraps. And it can, safely, for the precise
reason the other path could not: the offsets here are located against `source.text`, the
original, which the wrapper never touched. Nothing can drift.

Run: PYTHONPATH=. python3 checker/quoted_span.py
"""
from __future__ import annotations

import re

from checker.lawyer_summary import (Call, Citation, Source, Summary, check_blocks,
                                    cost_inr)
from checker.prompt_safety import UNTRUSTED_CLAUSE, wrap_untrusted

# The output contract. Two labelled lines per sentence, because a model asked to produce
# JSON around legal prose spends its obedience on the braces -- and a malformed brace
# loses the whole answer, where a malformed line loses one sentence.
SENTENCE_TAG = "SENTENCE:"
QUOTE_TAG = "QUOTE:"

PROTOCOL = f"""
FORMAT. Write nothing but pairs of lines, in this exact form, and nothing else:

{SENTENCE_TAG} <one sentence of the summary>
{QUOTE_TAG} <the exact words you read that sentence from, copied from a source above>

The {QUOTE_TAG} line is checked by searching the sources for those words. If they are not
found, the sentence is thrown away -- so copy, never paraphrase, and never join two
passages into one quote. Quote the passage, not the whole source: a quote that covers
everything shows nothing about where you read. Line breaks inside a quote may be replaced
by single spaces; nothing else may change."""


def system_prompt(base: str) -> str:
    """The caller's instructions, plus the untrusted-text clause and this protocol.

    The clause is universal (CLAUDE.md) and is added here rather than left to the caller,
    because this function is the only way into the path and a caller that forgets is the
    one sending a document to a model with no boundary declared at all.
    """
    body = base if UNTRUSTED_CLAUSE in base else UNTRUSTED_CLAUSE + "\n\n" + base
    return body + "\n" + PROTOCOL


def render_sources(sources) -> str:
    """The evidence, concatenated and delimited. Offsets are never taken from this."""
    return "\n\n".join(
        f"SOURCE {i} ({s.source_id}, {s.kind}):\n" + wrap_untrusted(s.text, s.source_id)
        for i, s in enumerate(sources))


# ── locating a quote ─────────────────────────────────────────────────────────
def _normalise(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed text, plus the original index of each character kept.

    The map is what makes the located offsets exact. Collapsing without it would give a
    position in a string nobody holds, and mapping back by counting is the kind of
    arithmetic that is wrong once and silently thereafter.
    """
    out: list[str] = []
    idx: list[int] = []
    prev_space = True                      # leading whitespace is dropped, not kept
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch)
            idx.append(i)
            prev_space = False
    return "".join(out), idx


# Matching pairs a model wraps its own copy in, asked to quote "the exact words": gpt-4o
# (measured live, 15-10-2026, F1: "What is the time limit for holding an annual general
# meeting under section 96?") returned a byte-perfect copy of the provision on every one
# of 12 sentences and wrapped every one in these -- `QUOTE: "Every company other than a
# One Person Company shall..."` -- and an exact search for the WRAPPED string finds
# nothing, because the source has no such quote marks in it. All 12 refused as NO_CITATION
# though the quote underneath every one was real. Gemini and Ollama do not do this; Azure's
# model does, and a bridge that only works for the models that happen not to add
# punctuation is not a bridge.
_QUOTE_WRAPPERS = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"))


def _unwrap(quote: str) -> str:
    """`quote`, minus one OUTERMOST matching pair of quotation marks, if it has one.

    Only the outermost pair, and only when both ends match: an unterminated or crossed
    mark is left alone rather than guessed at. This does not change what counts as FOUND --
    it only widens what is TRIED, and `locate()` tries the model's own text first.
    """
    s = quote.strip()
    for left, right in _QUOTE_WRAPPERS:
        if len(s) >= 2 and s.startswith(left) and s.endswith(right):
            return s[len(left):-len(right)]
    return quote


# The second live mismatch (same measurement): a quote that STOPS mid-provision reads as
# an incomplete sentence, and gpt-4o closes it with a period even where the source
# continues with a comma or colon -- "...in the notices calling it." where the Act has
# "...in the notices calling it, and not more than fifteen months shall elapse...". The
# words up to the cut are byte-for-byte real; only the mark the model closed its own
# quotation with is invented. Dropping ONE trailing mark when it is not a word character
# costs nothing a real quote needed: `str.find` does not require the source to END there,
# so the match still lands on the exact words, never on one word more or fewer.
_TRAILING_PUNCT = ".,;:"


# The third live mismatch, same measurement: a quote that STARTS mid-provision reads, to
# the model, as the start of a sentence, and gpt-4o capitalises it even where the source
# is lower-case there -- "Not more than fifteen months..." where the Act has "...and not
# more than fifteen months...", "not" lower-case because a different clause precedes it in
# the same sub-section. Five of eleven quotes on the live F1 run failed for exactly this:
# every word right, only the FIRST letter's case invented. So case is tried last and only
# when EVERY exact-case candidate above has failed in EVERY source -- never instead of the
# exact search, only after it -- and `Citation.quoted` is still `source.text[start:end]`:
# the recorded span carries the source's real case, never the model's guess at it.
def locate(quote: str, sources) -> Citation | None:
    """The first source containing `quote`, as a Citation with real offsets, or None.

    None is the refusal: `verify_sentence` turns a sentence with no citation into
    NO_CITATION, and `Summary.prose()` never prints it. Nothing is repaired or guessed --
    the liberties taken are trying the quote with its own wrapping quotation marks
    stripped, with one trailing punctuation mark dropped, and case-insensitively, each
    AFTER trying it exactly as written, so a model's formatting habits cost it nothing and
    buy it nothing: either the WORDS are in the evidence, in order, or they are not.
    """
    unwrapped = _unwrap(quote)
    base = (quote,) if unwrapped == quote else (quote, unwrapped)
    candidates = list(base)
    for c in base:
        if c and c[-1] in _TRAILING_PUNCT and c[:-1] not in candidates:
            candidates.append(c[:-1])
    for fold in (False, True):
        for candidate in candidates:
            needle = " ".join(candidate.split())
            if not needle:
                continue
            for i, src in enumerate(sources):
                hay, idx = _normalise(src.text)
                h, n = (hay.lower(), needle.lower()) if fold else (hay, needle)
                at = h.find(n)
                if at < 0:
                    continue
                start = idx[at]
                end = idx[at + len(needle) - 1] + 1
                # `quoted` is what is ACTUALLY there, not what the model typed. The
                # model's version may differ in whitespace, wrapping, a trailing mark or
                # case, and recording its version would make verify_sentence's
                # byte-identity check fail on a span that genuinely exists.
                return Citation(i, start, end, src.text[start:end])
    return None


_PAIR = re.compile(
    rf"^\s*{re.escape(SENTENCE_TAG)}\s*(?P<sentence>.+?)\s*$\n"
    rf"^\s*{re.escape(QUOTE_TAG)}\s*(?P<quote>.+?)\s*$",
    re.MULTILINE)


def parse(raw: str) -> tuple[tuple[str, str], ...]:
    """(sentence, quote) pairs. A line that is not part of a pair is DROPPED.

    Dropped rather than kept as an uncited sentence: text outside the format is text the
    model wrote when it was asked not to, and admitting it would let a model bypass the
    quote requirement by simply not using the format.
    """
    return tuple((m.group("sentence"), m.group("quote")) for m in _PAIR.finditer(raw))


def blocks(raw: str, sources) -> tuple[tuple[str, tuple[Citation, ...]], ...]:
    """Model output -> the (text, citations) shape `check_blocks` already checks.

    One sentence per block, deliberately. `check_blocks` marks a multi-sentence block
    `shares_citation`, warning that the attribution belongs to the block rather than the
    sentence; here each sentence carries its own quote, so there is nothing to share and
    nothing to warn about.
    """
    out = []
    for sentence, quote in parse(raw):
        cit = locate(quote, sources)
        out.append((sentence, (cit,) if cit else ()))
    return tuple(out)


def summarise(sources, *, model, base_system: str, question: str = "",
              model_name: str = "", budget=None) -> Summary:
    """Call any text-in/text-out model and return the CHECKED summary.

    `model` is `Callable[[str], str]` -- the shape `ollama_runner.OllamaRunner` already
    is, and the shape a Gemini or Anthropic wrapper is two lines away from. That is the
    whole point: attribution stops depending on which provider is affordable this month.
    """
    srcs = tuple(sources)
    if budget is not None and not budget.can_make_call().allowed:
        from checker.anthropic_model import ModelUnavailable
        raise ModelUnavailable("budget exhausted; no call was made")

    prompt = (system_prompt(base_system) + "\n\n" + render_sources(srcs) + "\n\n"
              + (question or "Summarise these sources for a lawyer."))
    raw = model(prompt)
    if budget is not None:
        budget.record_call(0.0 if not model_name else cost_inr(model_name, 0, 0))
    call = Call(model_name or "unnamed", 0, 0, 0.0, raw)
    return check_blocks(blocks(raw, srcs), srcs, call=call)


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

    print("quoted_span")

    from checker.lawyer_summary import (DOC_TEXT, LAW_FROM_DOCUMENT, NO_CITATION, TRACED,
                                        TURN, document_source, engine_source)
    doc = document_source("notice.pdf", DOC_TEXT)
    eng = engine_source(TURN)
    SRC = (doc, eng)

    # ── locating: exact offsets, from a search, through reflowed whitespace ──
    c = locate("The Company is a small company within the meaning of section 2(85)", SRC)
    check(c is not None and c.source_index == 0, "a quote is located in the right source")
    check(doc.text[c.start:c.end] == c.quoted,
          "...and the Citation's `quoted` is what is ACTUALLY at those offsets")
    check(c.quoted.startswith("The Company is a small"),
          f"...which is the passage asked for ({c.quoted[:40]!r})")

    # The document wraps this sentence across a line break; the model will not.
    flowed = "Twelfth Annual General Meeting of Vaidya Industries Limited will be held"
    check("\n" in DOC_TEXT[DOC_TEXT.index("Twelfth"):DOC_TEXT.index("will be held")],
          "the source really does break this passage across lines, so the test is real")
    c2 = locate(flowed, SRC)
    check(c2 is not None and "\n" in doc.text[c2.start:c2.end],
          "a reflowed quote is located anyway, and the located span keeps the source's "
          "own newline -- which is why `quoted` may not be the model's version")
    check(" ".join(doc.text[c2.start:c2.end].split()) == flowed,
          "...and the located span IS the quote, once whitespace is put back")
    # This pair is what kills the mutant that records the MODEL's wording instead of the
    # located bytes. Everything above passes either way, because everything above only
    # asked about the offsets -- and the offsets are the same under both. The two
    # differ only in `quoted`, and only when the source's whitespace differs, which is
    # exactly the case the byte-identity check downstream turns on.
    check(c2.quoted == doc.text[c2.start:c2.end] and c2.quoted != flowed,
          "`quoted` holds the SOURCE's bytes, which here are not the model's -- "
          "recording the model's wording would make verify_sentence's byte-identity "
          "check fail on a span that genuinely exists")
    _reflowed = (f"{SENTENCE_TAG} The document records that the Twelfth Annual General "
                 f"Meeting of Vaidya Industries Limited will be held.\n"
                 f"{QUOTE_TAG} {flowed}\n")
    _s_reflow = check_blocks(blocks(_reflowed, SRC), SRC)
    check(len(_s_reflow.traced) == 1,
          f"...and end to end, a reflowed quote TRACES rather than being refused as a "
          f"misquote ({[x.verdict for x in _s_reflow.sentences]})")

    # ── a model's OWN wrapping quotation marks are tried and discarded ───────
    # The live bug this fixes: gpt-4o (Azure), asked to copy "the exact words", wraps its
    # copy in quotation marks -- 'QUOTE: "Every company other than a One Person Company
    # shall..."' -- and an exact search for the WRAPPED string finds nothing, because the
    # source carries no such marks. Measured live 15-10-2026 on the F1 fixture: all 12
    # sentences refused as NO_CITATION though the quote underneath every one was real.
    quoted_plain = "The Company is a small company within the meaning of section 2(85)"
    c_wrap = locate(f'"{quoted_plain}"', SRC)
    c_bare = locate(quoted_plain, SRC)
    check(c_wrap is not None and c_wrap.source_index == 0,
          "a quote wrapped in the model's OWN quotation marks still locates")
    check((c_wrap.start, c_wrap.end) == (c_bare.start, c_bare.end),
          "...at the SAME offsets as the unwrapped quote: the marks are tried and "
          "discarded, never kept as part of the located span")
    check(locate('"The Company resolved to acquire Beta Ltd for Rs 40 crore"', SRC)
          is None,
          "...and wrapping a FABRICATED quote does not make it locate either -- the "
          "fallback widens what is TRIED, never what counts as FOUND")
    check(locate(f'"{quoted_plain}', SRC) is None,
          "an unterminated quotation mark is left alone rather than guessed at, so the "
          "search still runs on the literal (unmatched) text and finds nothing")

    # ── a model's own TERMINAL punctuation is tried and discarded, once ──────
    # The second live mismatch, same measurement: a quote that stops mid-provision reads,
    # to the model, as an incomplete sentence, and gpt-4o closes it with a period even
    # where the source actually continues with a comma -- see `_TRAILING_PUNCT`'s comment.
    cut_words = ("The Company is a small company within the meaning of section 2(85) "
                "of the Companies Act, 2013")
    c_cut = locate(cut_words + ".", SRC)        # the model's own invented closing mark
    c_full = locate(cut_words, SRC)             # the same words, no invented mark
    check(c_cut is not None and (c_cut.start, c_cut.end) == (c_full.start, c_full.end),
          "a quote closed with the model's OWN period, where the source actually "
          "continues with a comma, still locates -- at the SAME offsets as the bare "
          "words, so the invented mark is discarded and not folded into the span")
    check(DOC_TEXT[c_cut.end] == ",",
          "...confirmed against the source itself: the character right after the "
          "located span really is the comma the model turned into a period")
    check(locate("The Company resolved to acquire Beta Ltd for Rs 40 crore.", SRC)
          is None,
          "...and a FABRICATED quote with an invented closing period still does not "
          "locate -- the fallback drops one mark, it does not forgive the words")

    # ── a model's own LEADING capitalisation is tried last, case-insensitively ──
    # The third live mismatch, same measurement: gpt-4o capitalises the first letter of a
    # quote that starts mid-sentence in the source -- "Not more than fifteen months..."
    # where the Act has "...and not more than fifteen months...". Every word is right.
    lower_words = "will be held on Thursday, 14 August 2025"
    c_cap = locate("Will be held on Thursday, 14 August 2025.", SRC)
    c_lower = locate(lower_words, SRC)
    check(c_cap is not None and (c_cap.start, c_cap.end) == (c_lower.start, c_lower.end),
          "a quote capitalised AND closed with an invented period at the point it was "
          "cut still locates, at the same offsets as the literal lower-case words")
    check(c_cap.quoted == lower_words,
          "...and the recorded `quoted` carries the SOURCE's real case ('will', lower), "
          "never the model's capitalised guess at it")
    check(locate("WILL BE HELD ON THURSDAY, 14 AUGUST 2025", SRC) is not None,
          "...and this fallback is tried case-insensitively in full, not patched onto "
          "one leading letter")
    check(locate("Will resolve to acquire Beta Ltd for Rs 40 crore", SRC) is None,
          "...while a FABRICATED quote still does not locate, in any case")

    # ── refusing ─────────────────────────────────────────────────────────────
    check(locate("The Company resolved to acquire Beta Ltd for Rs 40 crore", SRC) is None,
          "a fabricated quote is not located")
    check(locate("   ", SRC) is None, "an empty quote is not located")
    check(locate("", SRC) is None, "...nor a missing one")

    # ── the parser ───────────────────────────────────────────────────────────
    raw = (f"{SENTENCE_TAG} The document is a notice of annual general meeting.\n"
           f"{QUOTE_TAG} NOTICE OF ANNUAL GENERAL MEETING\n"
           f"{SENTENCE_TAG} The document states that the Company is a small company "
           f"within the meaning of section 2(85).\n"
           f"{QUOTE_TAG} The Company is a small company within the meaning of section 2(85)\n")
    check(len(parse(raw)) == 2, "two pairs parse out of two pairs")
    check(parse(f"{SENTENCE_TAG} alone with no quote\n") == (),
          "a sentence with no quote line yields no pair -- it is not admitted uncited")
    check(parse("Here is a lovely summary of the document.\n") == (),
          "free prose outside the format is DROPPED, so a model cannot escape the quote "
          "requirement by ignoring the format")
    check(parse(f"{QUOTE_TAG} orphan quote\n{SENTENCE_TAG} after it\n") == (),
          "the order is part of the contract; a quote before its sentence is not a pair")

    # ── end to end, through the checker that already exists ──────────────────
    b = blocks(raw, SRC)
    check(len(b) == 2 and all(len(cits) == 1 for _, cits in b),
          "both sentences reach check_blocks carrying exactly one located citation")
    summary = check_blocks(b, SRC)
    check(len(summary.traced) == 2,
          f"both sentences trace ({[s.verdict for s in summary.sentences]})")
    check(all(not s.shares_citation for s in summary.sentences),
          "no sentence is marked shares_citation -- one sentence per block, each with "
          "its own quote, so there is nothing to share")

    bad = (f"{SENTENCE_TAG} The Board resolved to acquire Beta Ltd for Rs 40 crore.\n"
           f"{QUOTE_TAG} The Board resolved to acquire Beta Ltd for Rs 40 crore\n")
    s_bad = check_blocks(blocks(bad, SRC), SRC)
    check(s_bad.refused_entirely and s_bad.sentences[0].verdict == NO_CITATION,
          f"an invented sentence with an invented quote is refused as NO_CITATION "
          f"({s_bad.sentences[0].verdict})")
    check("NO SUMMARY" in s_bad.prose() and "Beta Ltd" not in s_bad.prose(),
          "...and it does not reach a reader through prose()")

    mixed = raw + bad
    s_mix = check_blocks(blocks(mixed, SRC), SRC)
    check(len(s_mix.traced) == 2 and len(s_mix.refused) == 1,
          f"in a mixed answer the unmatched sentence is dropped and the rest survive "
          f"({len(s_mix.traced)} traced, {len(s_mix.refused)} refused)")
    check("Beta Ltd" not in s_mix.prose(),
          "...and the dropped one is still not in the prose")

    # ── a paraphrase is refused exactly like a fabrication ───────────────────
    # Neither a reworded QUOTE line nor an invented one is found by `locate()`, and this
    # protocol does not need to tell the two apart: both fail to produce a real offset,
    # and both refuse the same way. `bad`, above, already covers the fabrication; this is
    # the same mechanism exercised on a genuine paraphrase of real text.
    paraphrase = (f"{SENTENCE_TAG} The meeting will take place the following Thursday "
                 f"in August 2025.\n"
                 f"{QUOTE_TAG} the following Thursday in August 2025\n")
    s_phrase = check_blocks(blocks(paraphrase, SRC), SRC)
    check(s_phrase.sentences[0].verdict == NO_CITATION,
          f"a QUOTE line that paraphrases real text -- reworded, not copied -- is not "
          f"located, so the sentence refuses exactly like a fabrication "
          f"({s_phrase.sentences[0].verdict})")

    # ── the law-assertion gate survives a SEARCHED citation, not just a handed one ───
    # lawyer_summary.verify_sentence refuses a statement of what the law requires when it
    # rests on the client's DOCUMENT and not on primary law (`checker/lawyer_summary.py`
    # rule 8) -- proven there with Citations built by hand. This is the same two sentences,
    # the same sources, and the same expected verdicts, except the Citations now come from
    # `locate()`'s search. If the search path quietly bypassed the gate -- say, by finding
    # a quote and stopping there -- this would TRACE instead of refuse.
    law_from_doc = (
        f"{SENTENCE_TAG} A small company must have paid-up share capital within the "
        f"prescribed limit under section 2(85) of the Companies Act, 2013.\n"
        f"{QUOTE_TAG} small company within the meaning of section 2(85) of the "
        f"Companies Act, 2013\n")
    s_law_doc = check_blocks(blocks(law_from_doc, SRC), SRC)
    check(s_law_doc.sentences[0].verdict == LAW_FROM_DOCUMENT,
          f"a law assertion with a real, LOCATED quote from the DOCUMENT still refuses "
          f"as {LAW_FROM_DOCUMENT}, not TRACED: the search finding the quote is not the "
          f"same as the quote supporting a legal conclusion "
          f"({s_law_doc.sentences[0].verdict})")

    law_from_engine = (
        f"{SENTENCE_TAG} The prescribed small-company limits were raised by "
        f"G.S.R. 880(E).\n"
        f"{QUOTE_TAG} the prescribed small-company limits were raised by "
        f"G.S.R. 880(E)\n")
    s_law_eng = check_blocks(blocks(law_from_engine, SRC), SRC)
    check(s_law_eng.sentences[0].verdict == TRACED,
          f"...while the SAME shape of claim, located in the ENGINE source instead, "
          f"traces ({s_law_eng.sentences[0].verdict}) -- the gate turns on which source "
          f"the citation names, not on whether it was handed to verify_sentence or found "
          f"by a search")

    # ── the prompt carries the clause and delimits the sources ───────────────
    from checker.prompt_safety import carries_clause, contains_untrusted_block
    sysp = system_prompt("Summarise the document.")
    check(carries_clause(sysp),
          "the system prompt carries UNTRUSTED_CLAUSE even when the caller forgot it")
    check(system_prompt(UNTRUSTED_CLAUSE + "\n\nx").count(UNTRUSTED_CLAUSE) == 1,
          "...and does not add it twice when the caller remembered")
    check(QUOTE_TAG in sysp and "searching the sources" in sysp,
          "...and states that the quote is checked by search, which is what makes "
          "copying rather than paraphrasing the model's own interest")
    rendered = render_sources(SRC)
    check(contains_untrusted_block(rendered),
          "the sources are DELIMITED -- this path concatenates into a prompt string, so "
          "the wrapper applies where on the Anthropic extract path it must not")
    check(locate("The Company is a small company", SRC).start
          == DOC_TEXT.index("The Company is a small company"),
          "...and the offsets are still the ORIGINAL document's, because they are located "
          "against source.text, which the wrapper never touched")

    # ── summarise(): any text-in/text-out callable ───────────────────────────
    seen = {}

    def fake(prompt: str) -> str:
        seen["prompt"] = prompt
        return raw

    out = summarise(SRC, model=fake, base_system="Summarise the document.",
                    model_name="test-model")
    check(len(out.traced) == 2, f"summarise() runs on a plain callable ({len(out.traced)})")
    check(QUOTE_TAG in seen["prompt"] and "NOTICE OF ANNUAL GENERAL MEETING" in seen["prompt"],
          "...having sent the protocol and the evidence in one string")

    class Broke:
        def can_make_call(self, *a, **k):
            from backend.budget import Verdict
            return Verdict(False, "budget", "cap reached", 0.0, 3_500.0)
    untouched = []
    try:
        summarise(SRC, model=lambda p: untouched.append(1) or raw,
                  base_system="x", budget=Broke())
        check(False, "an exhausted budget refuses before the call")
    except Exception as e:
        check("no call was made" in str(e) and not untouched,
              "an exhausted budget refuses BEFORE the call -- none was made")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
