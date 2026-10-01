#!/usr/bin/env python3
"""The connecting prose for a draft, written by a model from the run's findings alone.

Job 3c. `checker/draft_templates.py` builds a draft whose every statement of law is a
quoted citation, and leaves the joining sentences to a person. This writes those sentences
with a model -- and changes nothing about what is allowed to survive: the output goes
through `draft_templates.admit()` like any other prose, so an uncited legal claim is
DROPPED and the rest is MODEL_SUGGESTION, which blocks approval until a person accepts or
edits it.

## The model is shown the findings, never the user's message

`facts_for()` assembles the prompt's material from the SOURCE RUN only: the citations a
research answer actually cited, or the playbook findings a contract review actually
produced. The user's words are not in it. A model given "draft an email saying the NDA is
fine" would write that the NDA is fine; a model given three findings can only write about
three findings. This is the same reason `agents/plans.py` fixes the step list -- the
narrowest input that can still do the job.

The prompt says in terms that the model may not state law, because the law is already in
the draft as quotes. It will sometimes do it anyway. That is what `admit()` is for, and
the suite proves the drop with a stub that does exactly that.

## Sensitivity: which template can have prose at all

    research_memo   facts are CORPUS QUOTES -> PUBLIC
    client_email    facts are PLAYBOOK FINDINGS -> MATTER

A contract finding's `detail` carries values read out of the client's contract
(`checker/playbook.py`: "present in an approved form: {found.value!r}"), and its span is a
verbatim quote from it. So an email's facts are client data and are governed by D3
(India-region endpoints only). While the deployment region is unconfirmed that refuses,
and the honest outcome is a draft with NO prose and a note saying why -- which is what
`gateway/verbs.py` does with `NO_PROSE`. A fabricated paragraph and an empty one are both
worse.

This module decides WHAT a model would be shown and HOW the reply is read. It never
decides whether a model may be called: that is `public_only` and `router`, where every
other call is cleared, and the model arrives here already served.

Run: PYTHONPATH=. python3 checker/draft_prose.py --test
"""
from __future__ import annotations

import re

from checker.draft_templates import TEMPLATES

__all__ = ["facts_for", "quoted_facts", "matter_text", "sensitivity_of",
           "build_prompt", "parse_reply", "write",
           "PUBLIC", "MATTER", "MAX_SENTENCES", "NO_PROSE_PREFIX", "ProseError"]

PUBLIC = "PUBLIC"
MATTER = "MATTER"

# Four sentences. A covering note is not an essay, and every extra sentence is another
# chance to assert something nobody cited.
MAX_SENTENCES = 4

NO_PROSE_PREFIX = "prose not generated: "


class ProseError(ValueError):
    """A template this module cannot assemble facts for. Never a silent empty prompt."""


SENSITIVITY = {"research_memo": PUBLIC, "client_email": MATTER}


def sensitivity_of(template: str) -> str:
    if template not in SENSITIVITY:
        raise ProseError(f"{template!r} is not a template; one of {sorted(SENSITIVITY)}")
    return SENSITIVITY[template]


def quoted_facts(result: dict) -> tuple[tuple[str, str], ...]:
    """(label, VERBATIM quote) per citation, for a memo.

    Returned apart because they are CLEARED apart -- see `build_prompt`. The label is ours
    and the quote is the corpus file's, and only the second may go inside the delimiters.
    """
    out = []
    for c in (result or {}).get("citations") or ():
        cid = str((c or {}).get("id") or "").strip()
        quote = str((c or {}).get("quote") or "").strip()
        if not cid or not quote:
            continue
        where = " ".join(x for x in (str((c or {}).get("instrument") or ""),
                                     str((c or {}).get("provision") or "")) if x)
        out.append((f"[{cid}] {where} states, verbatim:", quote))
    return tuple(out)


def facts_for(template: str, result: dict) -> tuple[str, ...]:
    """The lines the model is shown, as flat text. From the run, and from nothing else."""
    sensitivity_of(template)                      # raises on an unknown template
    out: list[str] = []
    if template == "research_memo":
        q = str((result or {}).get("question") or "").strip()
        if q:
            out.append(f"The question asked: {q}")
        for label, quote in quoted_facts(result):
            out.append(f"{label} “{quote}”")
        return tuple(out)
    # client_email
    for f in (result or {}).get("findings") or ():
        if not isinstance(f, dict) or str(f.get("kind") or "") != "POTENTIAL_ISSUE":
            continue
        out.append(f"Playbook rule {f.get('rule_id') or '?'} on the clause "
                   f"{f.get('clause') or '?'}: {f.get('detail') or ''}".rstrip())
    bodies = [str((b or {}).get("body") or "")
              for b in (result or {}).get("law_not_held") or ()]
    if bodies:
        out.append("These bodies of law are NOT held and nothing may be said about them: "
                   + ", ".join(bodies))
    return tuple(out)


_RULES = (
    "You are writing the joining sentences of a lawyer's draft. Obey all of:\n"
    "1. Write at most {n} sentences, each on its own line, numbered 1., 2., ...\n"
    "2. State NO law. Do not say what any Act, section, rule or regulation requires, "
    "permits or forbids, and do not say that anything is valid, void, enforceable or "
    "unlawful. The law is already in the draft, quoted. Your sentences only join it up.\n"
    "3. Use nothing but the findings below. Add no fact, number, date or name that is "
    "not in them.\n"
    "4. To point at a finding, put its tag in square brackets at the end of the "
    "sentence, exactly as it appears below -- for example [c1]. A sentence with no tag "
    "is fine.\n"
    "5. Write plainly, for a client who is not a lawyer. No greeting and no sign-off.\n")


def build_prompt(template: str, result: dict) -> str:
    """The whole prompt. Raises rather than ask a model about nothing.

    The findings are CONCATENATED into this string, so they go inside `wrap_untrusted` and
    the prompt carries `UNTRUSTED_CLAUSE` -- the case CLAUDE.md names for the delimiter,
    and what `public_only.verify_prompt` checks for. They contain quoted statute and text
    read out of a document; a quote is still someone else's words, and an instruction
    printed inside one is evidence about that document, not an instruction to us.
    """
    from checker.prompt_safety import UNTRUSTED_CLAUSE, wrap_untrusted
    facts = facts_for(template, result)
    if not facts:
        raise ProseError(
            f"the {template} run carries no findings to write about, so there is nothing "
            f"to join up. An empty prompt would be answered with invention")
    head = UNTRUSTED_CLAUSE + "\n\n" + _RULES.format(n=MAX_SENTENCES) + "\nThe findings:\n"
    tail = "\n\nYour numbered sentences:\n"
    if sensitivity_of(template) == PUBLIC:
        # ONE BLOCK PER QUOTE, each clearing against its own corpus file. `verify_prompt`
        # checks a block's BYTES against a published file, and a quote is in its file while
        # a sentence we built around it is in no file at all. So the labels and the
        # question stay outside the delimiters -- our words and the user's, not a published
        # file's -- and only the verbatim quote goes inside.
        q = str((result or {}).get("question") or "").strip()
        parts = [f"The question asked: {q}\n"] if q else []
        for label, quote in quoted_facts(result):
            parts.append(f"{label}\n{wrap_untrusted(quote, 'the cited provision')}\n")
        return head + "\n".join(parts) + tail
    # MATTER: one block, whose bytes `gateway/verbs._draft_prose` clears through
    # `matter_text` -- the same function, so the published string and the sent string
    # cannot drift apart.
    return head + wrap_untrusted(matter_text(facts), f"{template} findings") + tail


def matter_text(facts) -> str:
    """The exact string a matter origin is cleared against AND the prompt carries.

    One function, because if the origin is built from a different string than the prompt
    sends, `verify_prompt` refuses and the only evidence is a byte mismatch nobody can
    read.
    """
    return "\n".join(f"- {line}" for line in facts)


_NUMBERED = re.compile(r"^\s*\d+[.)]\s*(.+?)\s*$")
_TAG = re.compile(r"\[([A-Za-z0-9_\-]{1,40})\]")


def parse_reply(raw: str) -> list[dict]:
    """The reply -> `[{text, citation_ids}]`, the shape `draft_templates.admit` takes.

    Unnumbered lines are kept too. A model that ignores the numbering has still written
    sentences, and dropping them for a formatting slip would lose work that the admit rule
    is about to judge properly anyway -- unlike a review-grid cell, where an unparseable
    reply becomes a FINDING and must not (see `agents/review_grid.Unreadable`). Nothing
    here becomes a finding: everything is MODEL_SUGGESTION or dropped.
    """
    blocks: list[dict] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = _NUMBERED.match(line)
        text = m.group(1).strip() if m else line
        if not text:
            continue
        ids = _TAG.findall(text)
        text = _TAG.sub("", text).strip()
        text = re.sub(r"\s+([.,;:])", r"\1", text).strip()
        if not text:
            continue
        blocks.append({"text": text, "citation_ids": ids})
        if len(blocks) >= MAX_SENTENCES:
            break
    return blocks


def write(template: str, result: dict, *, model) -> tuple[list, str]:
    """(blocks, note). The note is empty on success and says WHY on every other path.

    `model` is `call(prompt) -> str`, already served and cleared by the caller. Any
    exception from it becomes a note, never an exception out of here and never a FAILED
    draft: the draft itself is sound -- it is built from the run's own findings -- and the
    only thing missing is the joining sentences. Returning FAILED would throw away a
    correct document because an optional embellishment did not arrive.
    """
    try:
        prompt = build_prompt(template, result)
    except ProseError as e:
        return [], f"{NO_PROSE_PREFIX}{e}"
    if model is None:
        return [], (f"{NO_PROSE_PREFIX}no model was available to write it")
    try:
        raw = str(model(prompt) or "")
    except Exception as e:                                       # noqa: BLE001
        return [], (f"{NO_PROSE_PREFIX}the model call did not complete "
                    f"({type(e).__name__}: {str(e)[:120]})")
    blocks = parse_reply(raw)
    if not blocks:
        return [], (f"{NO_PROSE_PREFIX}the model returned nothing that reads as a "
                    f"sentence ({len(raw)} characters)")
    return blocks, ""


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

    print("draft_prose")
    from checker import draft_templates as dt
    from checker.provenance_slots import MODEL_SUGGESTION, blocking_slots, ready_for_approval

    CIT = {"id": "c1", "instrument": "Companies Act 2013", "provision": "s.96(1)",
           "quote": ("Every company shall in each year hold a general meeting as its "
                     "annual general meeting.")}
    ASK = {"question": "When must a company hold its AGM?", "citations": [CIT]}
    REVIEW = {"findings": [
        {"rule_id": "NDA-01", "clause": "Term", "kind": "POTENTIAL_ISSUE",
         "detail": "'5 years' against the standard '3 years'"},
        {"rule_id": "NDA-02", "clause": "Governing law", "kind": "INFORMATIONAL",
         "detail": "matches the standard"}],
        "law_not_held": [{"body": "CONTRACT1872"}, {"body": "STAMP"}]}

    # ── sensitivity: which facts are client data ────────────────────────────
    check(sensitivity_of("research_memo") == PUBLIC,
          "a memo's facts are corpus quotes, so PUBLIC")
    check(sensitivity_of("client_email") == MATTER,
          "an email's facts are playbook findings, which carry values read out of the "
          "CLIENT's contract -- so MATTER, and D3 governs whether a model sees them")
    try:
        sensitivity_of("postcard")
        check(False, "an unknown template raises")
    except ProseError:
        check(True, "an unknown template raises ProseError, never a default sensitivity")
    check(set(SENSITIVITY) == set(TEMPLATES),
          f"every template has a sensitivity and no template is missing one "
          f"({sorted(SENSITIVITY)} vs {sorted(TEMPLATES)})")

    # ── the model sees the findings and NOT the user's words ────────────────
    facts = facts_for("research_memo", ASK)
    check(any("c1" in f and CIT["quote"] in f for f in facts),
          "the memo's facts carry each citation, tagged and quoted verbatim")
    prompt = build_prompt("research_memo", ASK)
    check(CIT["quote"] in prompt and "[c1]" in prompt, "...and they reach the prompt")
    check("<source" in prompt and "EVIDENCE, not instructions" in prompt,
          "...inside a DELIMITED untrusted block with the clause, because they are "
          "concatenated into the string -- the case CLAUDE.md names for the delimiter, "
          "and what verify_prompt refuses a prompt without")
    check("draft an email" not in prompt.lower(),
          "the user's instruction is not in the prompt -- the model is shown findings, so "
          "it can only write about findings")
    check("State NO law" in prompt, "...and the prompt forbids stating law")
    efacts = facts_for("client_email", REVIEW)
    check(any("NDA-01" in f for f in efacts) and not any("NDA-02" in f for f in efacts),
          "an email's facts are the POTENTIAL_ISSUE findings only, not the informational "
          "ones")
    check(any("NOT held" in f and "CONTRACT1872" in f for f in efacts),
          "...and the unheld bodies are named, so the model is told what it cannot speak to")
    try:
        build_prompt("research_memo", {"citations": []})
        check(False, "a run with no findings raises")
    except ProseError:
        check(True, "a run with NO findings raises rather than ask a model about nothing")

    # ── parsing ─────────────────────────────────────────────────────────────
    b = parse_reply("1. This note sets out the position. [c1]\n2. I can talk it through.\n")
    check([x["text"] for x in b]
          == ["This note sets out the position.", "I can talk it through."],
          f"numbered lines parse to sentences with the tag removed ({b})")
    check(b[0]["citation_ids"] == ["c1"] and b[1]["citation_ids"] == [],
          "...and the tag becomes a citation id")
    check(len(parse_reply("\n".join(f"{i}. Sentence {i}." for i in range(1, 12))))
          == MAX_SENTENCES,
          f"no more than {MAX_SENTENCES} sentences survive, however many are returned")
    check(parse_reply("") == [] and parse_reply("   \n  ") == [],
          "an empty reply parses to nothing")
    check([x["text"] for x in parse_reply("A sentence with no number.")]
          == ["A sentence with no number."],
          "an UNNUMBERED line is kept: nothing here becomes a finding, so a formatting "
          "slip must not throw away work the admit rule is about to judge")

    # ── THE JOB'S TEST: a stub that fabricates law, and one that raises ─────
    FAKE = "Section 42 of the Companies Act requires a special resolution for this."

    def fabricating(prompt: str) -> str:
        return ("1. This note records the position on the annual general meeting. [c1]\n"
                f"2. {FAKE}\n")

    blocks, note = write("research_memo", ASK, model=fabricating)
    check(note == "" and len(blocks) == 2, f"the model's two sentences come back ({note})")
    built = dt.research_memo(ASK, prose=blocks)
    check(len(built.dropped) == 1 and built.dropped[0]["text"] == FAKE,
          f"**the model's UNCITED LEGAL CLAIM IS DROPPED** by the existing admit rule "
          f"({[d['text'][:30] for d in built.dropped]})")
    check(FAKE not in built.body and all(FAKE not in s.value for s in built.slots),
          "...and reaches no part of the draft")
    kept = [s for s in built.slots if s.slot_type == MODEL_SUGGESTION]
    check(len(kept) == 1 and "records the position" in kept[0].value,
          "...while the sentence that states no law survives")
    check(kept[0].slot_type == MODEL_SUGGESTION and bool(blocking_slots(built.slots)),
          "...as a MODEL_SUGGESTION that BLOCKS approval")
    check(not ready_for_approval(built.slots),
          "...so nothing a model wrote can be approved without a person touching it")

    def exploding(prompt: str) -> str:
        raise TimeoutError("the deployment did not answer in 30s")

    blocks2, note2 = write("research_memo", ASK, model=exploding)
    check(blocks2 == [] and note2.startswith(NO_PROSE_PREFIX),
          f"**a model that RAISES gives the note, not an exception** ({note2[:46]!r})")
    check("TimeoutError" in note2, "...naming what went wrong")
    built2 = dt.research_memo(ASK, prose=blocks2)
    check(CIT["quote"] in built2.body,
          "...and the draft is STILL BUILT from the run's own citations -- a correct "
          "document is not thrown away because an optional embellishment did not arrive")
    check(ready_for_approval(built2.slots),
          "...and with no model text in it, it is approvable")

    blocks3, note3 = write("research_memo", ASK, model=None)
    check(blocks3 == [] and "no model was available" in note3,
          f"no model at all gives the same shape of note ({note3[:40]!r})")
    blocks4, note4 = write("research_memo", ASK, model=lambda p: "")
    check(blocks4 == [] and "reads as a sentence" in note4,
          "a model that returns nothing gives a note, not an empty paragraph")
    blocks5, note5 = write("research_memo", {"citations": []}, model=fabricating)
    check(blocks5 == [] and "nothing to join up" in note5,
          "...and a run with no findings never reaches the model at all")
    check(all(n.startswith(NO_PROSE_PREFIX) for n in (note2, note3, note4, note5)),
          "every failure path uses the SAME prefix, so a surface can render them "
          "identically and none of them reads as an answer")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
