"""Turning a run into an answer: bodies of law, the envelope, findings and citations."""
from __future__ import annotations

from gateway import access
from gateway.verbs.core import Context, V2, _law_date, _long_date, _refuse
from gateway.verbs.documents import SUMMARY_UNAVAILABLE_WHY


def _bodies_from_events(result: dict) -> list:
    """events.assess findings -> envelope bodies. The mapping, in one place."""
    from gateway import envelope as ev
    from checker import events, scope
    handling = {events.DECIDED: ev.B_ANSWERED,
                events.CURRENT_TEXT_ONLY: ev.B_CURRENT_ONLY,
                events.REFUSED: ev.B_NOT_HELD,
                events.UNCLASSIFIED: ev.B_NEED_FACT}
    out = []
    for f in result.get("findings", ()):
        try:
            name = scope.body(f["body_id"]).name
        except Exception:                                       # noqa: BLE001
            name = f["body_id"]
        out.append(ev.body(f["body_id"], name,
                           handling.get(f.get("handling"), ev.B_NEED_FACT),
                           f.get("text") or f.get("reason") or "engaged"))
    return out


def _bodies_from_ask(result: dict, question: str = "") -> list:
    """An `ask` result -> envelope bodies, read from the two authorities.

    **`checker/ask_scope.read()` is asked, not the result dict.** The first version read
    `result["out_of_scope_bodies"]` and `result["refusal"]["bodies"]` -- and the `ask` verb
    returns NEITHER key. So the unheld-body branch was dead code, the spec's own named case
    (CA2013 + FEMA -> PARTIAL with FEMA NOT_HELD) came back ABSTAINED with one body, and
    nothing failed to say so. `ask_scope` is the module `checker/ask.py` itself uses to
    decide out-of-scope, so asking it is asking the same authority rather than hoping a
    result carries a summary of it.

    A body we do not hold is NOT_HELD with the REGISTER'S OWN words. CA2013 is ANSWERED
    when provisions were traced, NOT_ENGAGED when the question was wholly about another
    body, and NEED_FACT when it was ours to answer and nothing on point was found.
    """
    from gateway import envelope as ev
    from checker import ask_scope, scope

    out = []
    held = scope.body("CA2013")
    traced = bool(result.get("provisions") or result.get("citations"))
    reading = ask_scope.read(question or result.get("question") or "")

    if reading.refuse:
        # The question is wholly about law we do not hold. Saying CA2013 was "read and
        # found nothing" would be answering a question nobody asked.
        out.append(ev.body(held.key, held.name, ev.B_NOT_ENGAGED,
                           "this question is about another body of law, so the Companies "
                           "Act was not engaged"))
    elif result.get("resource") == "case":
        # `_ask_case` never searches the held corpus: the resource router sent this
        # question to judgment discovery instead. NEED_FACT's wording ("nothing on point
        # was found") would claim a search that never ran -- the exact lie R-018 was fixed
        # to stop -- so this is its own NOT_ENGAGED branch rather than reusing the
        # "not among the picked sources" wording below, which is about a caller's @-pick
        # and would misname what actually happened here.
        out.append(ev.body(held.key, held.name, ev.B_NOT_ENGAGED,
                           "this question was routed to case-law discovery (a party, case "
                           "name, citation, or 'vs'/'v.'/'judgment' was recognised), not "
                           "the held statute, so the Companies Act was not searched"))
    else:
        _searched = (result.get("sources") or {}).get("searched")
        if _searched is not None and "held" not in _searched:
            # The held corpus was not among the picked sources, so it was not searched.
            # NEED_FACT "nothing on point was found" would claim a search that never ran
            # (R-018); NOT_ENGAGED with the reason is the honest body.
            out.append(ev.body(held.key, held.name, ev.B_NOT_ENGAGED,
                               "the held corpus was not among the picked sources, so it "
                               "was not searched"))
        elif result.get("code") == "NOTHING_TRACED":
            # Provisions WERE found; the model just could not trace a sentence to them.
            # "nothing on point was found" would be false -- that is the NO_EVIDENCE case.
            out.append(ev.body(held.key, held.name, ev.B_NEED_FACT,
                               "relevant provisions were found, but no sentence could be "
                               "traced to them"))
        else:
            out.append(ev.body(held.key, held.name,
                               ev.B_ANSWERED if traced else ev.B_NEED_FACT,
                               "held and read as at the date shown" if traced else
                               "held, and nothing on point was found for this question"))

    if reading.body is not None and reading.body.key != held.key:
        b = reading.body
        out.append(ev.body(b.key, b.name,
                           ev.B_CURRENT_ONLY if b.status == scope.CURRENT_ONLY
                           else ev.B_NOT_HELD,
                           scope.refusal_for(b.key)))
    return out


# Which bodies a document-review task reads against. Named, because an empty bodies[] on a
# review said nothing about what the findings rest on -- and for a CONTRACT that silence is
# the dangerous direction: a playbook finding looks like a legal one unless the envelope
# says the law it would rest on is not held.
_REVIEW_DOC_BODIES = ("CA2013",)
_REVIEW_CONTRACT_BODIES = ("CONTRACT1872", "ARBITRATION1996")


def _bodies_for_review(task: str, result: dict) -> list:
    from gateway import envelope as ev
    from checker import scope

    out = []
    if task == "REVIEW_DOCUMENT":
        for key in _REVIEW_DOC_BODIES:
            b = scope.body(key)
            out.append(ev.body(b.key, b.name, ev.B_ANSWERED,
                               f"the SS-1/SS-2 checks are read against {b.name}, which is "
                               f"held; a check that does not apply to this document type "
                               f"makes no claim"))
        return out
    for key in _REVIEW_CONTRACT_BODIES:
        b = scope.body(key)
        out.append(ev.body(
            b.key, b.name,
            ev.B_ANSWERED if b.status == scope.IN_CORPUS else ev.B_NOT_HELD,
            f"{scope.refusal_for(b.key)} Every finding here is a POTENTIAL_ISSUE against "
            f"your own playbook, which is a company standard and not a statement of law."
            if b.status != scope.IN_CORPUS else "held"))
    return out


def _bodies_for(task: str, result: dict, question: str = "") -> list:
    """The body table for any task. One place, so no task silently reports none."""
    if task == "EVENT_ASSESS":
        return _bodies_from_events(result)
    if task == "RESEARCH_QUESTION":
        return _bodies_from_ask(result, question)
    if task in ("REVIEW_DOCUMENT", "REVIEW_CONTRACT"):
        return _bodies_for_review(task, result)
    # A task no verb serves ran nothing, so it claims nothing about any body. The
    # ABSTAINED text says so in words; an invented NOT_ENGAGED row would imply we looked.
    return []


def _files_block(file_ids, ctx: Context) -> list:
    """The file panel. A stored document is READ; one we cannot find is CANNOT_READ.

    An unknown file_id is NOT silently dropped: a file the user attached and we cannot see
    is exactly the case where an empty answer would read as "your document said nothing".
    """
    from gateway import envelope as ev
    out = []
    for fid in file_ids or ():
        doc = ctx.documents.get(fid)
        if doc is None and ctx.store is not None:
            try:
                doc = ctx.store.get_document(fid)
            except Exception:                                   # noqa: BLE001
                doc = None
        if doc is None:
            out.append(ev.file_state(fid, fid[:12] or "file", ev.CANNOT_READ,
                                     reason=("this engine holds no document under that id, "
                                             "so nothing was read from it. Upload it again "
                                             "rather than treating this as a finding")))
            continue
        name = str(doc.get("name") or fid[:12])
        # A STORED document is READ: `documents.upload` refuses blank text, so anything
        # in the store has content. The first version of this checked `doc["text"]`, which
        # upload does not keep -- it stores the hash, the byte count and the name -- so
        # every real upload came back CANNOT_READ. A file panel that reports a readable
        # document as unreadable is the same lie as the reverse, pointed the other way.
        reason = doc.get("cannot_read")
        if reason:
            out.append(ev.file_state(fid, name, ev.CANNOT_READ, reason=str(reason)))
        else:
            out.append(ev.file_state(fid, name, ev.READ,
                                     pages=doc.get("pages")))
    return out


def _envelope_for(task: str, result: dict, *, as_of: str, run_id=None,
                  files=(), ctx: Context, question: str = "") -> dict:
    """One result from one task -> one envelope. The only place a reply is shaped."""
    from gateway import envelope as ev

    trace = f"{V2}/runs/{run_id}/trace" if run_id else None
    if result.get("status") == "FAILED":
        return ev.failed(task=task, as_of=as_of,
                         detail="The request could not finish. Your question is saved; please retry.",
                         run_id=run_id, trace_url=trace)
    # NO_MODEL (the provider was unavailable) is a could-not-run state, NOT an abstention:
    # the model never evaluated the law. Render it in the FAILED register (whose definition
    # includes "a dead provider") with its own message and no bodies, so a cold start can
    # never read as "nothing held answers this". The code rides the response as a sibling.
    if isinstance(result.get("document_summary_unavailable"), dict):
        # Not a transient outage, so no "try again": see _summary_unavailable.
        reason = result["document_summary_unavailable"].get("reason")
        return ev.failed(task=task, as_of=as_of, run_id=run_id, trace_url=trace,
                         text=("Document summarization is unavailable in this deployment. "
                               f"{SUMMARY_UNAVAILABLE_WHY.get(reason, '')} No summary was "
                               "generated and your document is unchanged. Retrying will not "
                               "help until an administrator restores access. This is not a "
                               "finding about the document or the law."))
    if result.get("code") == "NO_MODEL":
        return ev.failed(task=task, as_of=as_of, run_id=run_id, trace_url=trace,
                         text="The model was unavailable — this is not a finding about the "
                              "law. Try again.")

    if task == "RESEARCH_QUESTION" and isinstance(result.get("document_summary"), dict):
        summary = result["document_summary"]
        text = ("A review-draft summary was generated from the selected document text. Quotes are exact text matches, not proof that each point is accurate; check each quote in context."
                if summary.get("status") == "SUMMARY_DRAFT_READY" else
                "No summary items passed the quotation-format checks. No summary text was shown.")
        return ev.build(status=ev.PARTIAL, task=task, as_of=as_of,
                        text_blocks=[{"text": text, "citation_ids": []}],
                        bodies=[], citations=[], files=files, run_id=run_id, trace_url=trace)

    bodies = _bodies_for(task, result, question)
    if task == "REVIEW_TABLE" and result.get("grid_id"):
        t = result.get("scheduled") or {}
        result = dict(result, note=(
            f"Review table {result['grid_id']} created: {result.get('documents')} "
            f"document(s) x {result.get('columns')} column(s) = {result.get('cells')} "
            f"cells, {len(t.get('enqueued') or [])} queued. Nothing is answered until a "
            f"worker runs each cell, and a PENDING cell is not a NOT_FOUND one. Poll "
            f"review_table.status."))
    if task == "DRAFT" and result.get("draft_id"):
        # The id is what the next turn revises, so it has to come back. Put in the text
        # block rather than invented as a new envelope field: the schema is a contract.
        result = dict(result, note=(
            f"Draft {result['draft_id']} created at version {result.get('version')}. "
            f"{len(result.get('blocking') or [])} slot(s) block approval"
            + (f": {', '.join(result['blocking'])}. " if result.get('blocking') else ". ")
            + (f"Built from run {result['drafted_from']} with the "
               f"{result.get('template')} template: every statement of law in it is a "
               f"quote from that run's citations, and the model's connecting prose is a "
               f"MODEL_SUGGESTION that blocks approval until a person accepts or edits "
               f"it. " if result.get("drafted_from") else
               "Nothing has been drafted for you: this engine does not write legal prose "
               "unprompted. Fill the slots with draft.revise.")
            + (f"{len(result['dropped_claims'])} sentence(s) the model wrote were DROPPED "
               f"because they state something about the law with no citation behind it; "
               f"they are in dropped_claims and are in no version of this draft. "
               if result.get("dropped_claims") else "")
            + (f"No connecting prose was written -- {result['prose_note']}. The draft "
               f"below is built from the run's own findings, which is the whole of it."
               if result.get("prose_note") else "")))
    citations, dropped = _citations_for(task, result)
    # NOTHING_TRACED: relevant provisions WERE retrieved; the model's sentences did not trace
    # to them, so no generated prose is shown. Surface the provisions themselves as openable
    # sources (verbatim via citation.get, no model prose) rather than a bare abstention, and
    # say exactly that -- never "nothing on point was found", which belongs to NO_EVIDENCE.
    nothing_traced = result.get("code") == "NOTHING_TRACED"
    if nothing_traced:
        citations = _provision_citations(result.get("provisions") or [],
                                         _law_as_of_date(result))
        dropped = []
    # `abstained_reason` before `note`: when `ask` abstains (e.g. the held corpus was not
    # picked) it carries the reason there, and dropping it left the envelope saying "See the
    # findings." over an abstention that read nothing. R-018.
    text = (result.get("answer") or result.get("detail")
            or result.get("abstained_reason")
            or result.get("note") or "See the findings.")
    if nothing_traced:
        text = ("Relevant provisions were found, but no sentence could be traced to them, "
                "so nothing generated is shown.")
    blocks = [{"text": str(text), "citation_ids": [c["id"] for c in citations]}] \
        if str(text).strip() else []
    if result.get("unaddressed") and result.get("reason"):
        # The relevance gate (checker/answer_relevance.py) said the cited sections are about
        # something else. Right after the answer, never before it: clients read block 0 as the
        # cited answer, and the PARTIAL status already marks it.
        blocks.insert(1, {"text": str(result["reason"]), "citation_ids": []})
    if _law_as_of_date(result):
        # After the answer (and any relevance note), never before it.
        blocks.insert(len(blocks), {"text": _law_as_of_block(result["law_as_of"]), "citation_ids": []})
    blocks += _finding_blocks(task, result)
    if dropped:
        # Stated, not silent. A dropped citation changes what the reader is looking at.
        blocks.append({"text": (
            f"{len(dropped)} citation(s) were dropped because the quote no longer "
            f"byte-matches the section it names. Nothing rests on them."),
            "citation_ids": []})

    unheld = [b for b in bodies if b["status"] in (ev.B_NOT_HELD, ev.B_CURRENT_ONLY)]
    answered = [b for b in bodies if b["status"] == ev.B_ANSWERED]
    if result.get("status") in ("REFUSED", ev.ABSTAINED):
        status = ev.ABSTAINED
    elif result.get("status") == ev.NEEDS_CLARIFICATION:
        status = ev.NEEDS_CLARIFICATION
    elif result.get("requires_review") or result.get("status") == ev.NEEDS_LAWYER:
        # A finding a machine cannot close. `review_contract` is the clear case: every
        # finding is a POTENTIAL_ISSUE against the company's own playbook, which is not
        # law, so there is no outcome this system may call compliant. NEEDS_LAWYER was in
        # the enum and nothing produced it, which made the enum a wish.
        status = ev.NEEDS_LAWYER
    elif result.get("status") == ev.PARTIAL:
        status = ev.PARTIAL
    elif dropped:
        status = ev.PARTIAL if citations else ev.ABSTAINED
    elif unheld and answered:
        status = ev.PARTIAL
    elif unheld and not answered:
        status = ev.ABSTAINED
    else:
        status = ev.ANSWERED
    return ev.build(status=status, task=task, as_of=as_of, text_blocks=blocks,
                    bodies=bodies, citations=citations, files=list(files), run_id=run_id,
                    trace_url=trace)


# ── citations: built from the traced spans, re-verified against the corpus ───

_DOC_FINDING_LABEL = {"DEFECT": "Defect", "NEEDS_BOOK": "Needs the minutes book"}
_CONTRACT_FINDING_LABEL = {"DEVIATES": "Deviates from your playbook",
                           "MISSING": "Missing against your playbook",
                           "NEEDS_LAWYER": "A lawyer needs to decide"}


def _finding_blocks(task: str, result: dict) -> list:
    """A review's findings as envelope text blocks, one per finding that needs attention.

    The conversation envelope used to carry only the review's `note`, so a minutes review
    with five defects rendered as "A lawyer needs to decide this" and named none of them.
    Each block keeps the rule, its source and (for minutes) the precedent, because a finding
    without its basis is an assertion. Passes and inapplicable checks are counted, not
    listed, so the reader still sees the list is not the whole of what was checked.
    """
    findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)]
    out = []
    if task == "REVIEW_DOCUMENT":
        for f in findings:
            label = _DOC_FINDING_LABEL.get(f.get("status"))
            if not label or f.get("applies") is False:
                continue
            text = f"{label}: {f.get('defect') or f.get('rule_id')}."
            if f.get("source"):
                text += f" Rule {f.get('rule_id')}, {f['source']}."
            if f.get("precedent"):
                text += f" Precedent: {f['precedent']}."
            out.append({"text": text, "citation_ids": []})
        passed = sum(1 for f in findings if f.get("status") == "PASS")
        skipped = sum(1 for f in findings if f.get("status") == "N/A")
    elif task == "REVIEW_CONTRACT":
        for f in findings:
            label = _CONTRACT_FINDING_LABEL.get(f.get("status"))
            if not label:
                continue
            text = f"{label}: {f.get('clause') or f.get('rule_id')}"
            text += f" -- {f['detail']}." if f.get("detail") else "."
            if f.get("standard_text"):
                text += f" Standard: {f['standard_text']}"
            out.append({"text": text, "citation_ids": []})
        passed = sum(1 for f in findings if f.get("status") == "MATCHES")
        skipped = 0
    else:
        return []
    if findings:
        out.append({"text": (f"{len(out)} finding(s) above; {passed} check(s) passed"
                             + (f" and {skipped} did not apply to this document"
                                if skipped else "") + "."),
                    "citation_ids": []})
    return out


def _split_provision(source_id: str) -> tuple[str, str]:
    """"Companies Act 2013, s.174" -> ("Companies Act 2013", "s.174")."""
    if ", s." in source_id:
        head, _, tail = source_id.partition(", s.")
        return head.strip(), f"s.{tail.strip()}"
    return source_id.strip(), ""


def _provision_citations(provisions, as_of: str | None = None) -> list:
    """Retrieved provisions as openable citations, for the NOTHING_TRACED path.

    Each quotes a VERBATIM leading span of its section, so `citation.get` re-reads and serves
    the whole provision verbatim -- the law itself, with no model prose. A provision the
    corpus cannot resolve, or one that will not pass `ev.citation`, is skipped rather than
    shown. The spans are a contiguous slice of `html_to_text`, the exact text `citation.get`
    re-reads against, so the quote byte-matches and the panel opens.
    """
    from gateway import envelope as ev
    from checker import section_index
    out: list = []
    for name in provisions:
        instrument, provision = _split_provision(name)
        if not provision:
            continue
        rec = section_index.section_by_number(provision.removeprefix("s."))
        if not rec:
            continue
        quote = _section_text(rec, as_of)[:200].strip()
        if not quote:
            continue
        try:
            out.append(ev.citation(
                id=f"c{len(out) + 1}", instrument=instrument, provision=provision,
                source=f"corpus/companies_act/{rec.get('section_id')}.json",
                fetched_at=str(rec.get("fetched_at") or "unrecorded"),
                sha256=str(rec.get("sha256") or ""), quote=quote, in_force_from=None))
        except ev.EnvelopeError:
            continue
    return out


def verify_citation(c: dict, as_of: str | None = None) -> tuple[bool, str]:
    """Re-read the section this citation names and confirm the quote is still in it."""
    ok, why, _text = _reread(c, as_of)
    return ok, why


def _section_text(rec: dict, as_of: str | None) -> str:
    """The readable section: today's, or as it stood on `as_of` (rebuilt, unknown parts masked)."""
    from checker.sarvam_model import html_to_text
    if not as_of:
        return html_to_text(rec.get("content") or "")
    from datetime import date
    from checker.as_of import readable_as_of
    return readable_as_of(rec, date.fromisoformat(as_of)).text or ""


def _reread(c: dict, as_of: str | None = None) -> tuple[bool, str, str | None]:
    """`verify_citation`, plus the readable section text it verified the quote AGAINST.

    The text is returned only when the quote byte-matches it. A section whose file changed,
    or that no longer holds the quote, returns None: showing today's text beside a quote it
    does not contain would invite a reader to trust the wrong words.

    **A real round-trip, through the same two functions the evidence path used**:
    `section_index.section_by_number` for the record and `html_to_text` for the readable
    form. The first version of `citation.get` built a throwaway object with the right
    attribute names and handed it to `held.span_matches`, which checked a different field
    against a different source -- a verification that could not fail for the reason it
    claimed to check.

    Three ways it fails, and each is a different fact:
      the section is gone      the corpus no longer holds what the answer cited
      the file changed         sha256 differs from the one recorded at answer time
      the quote is absent      the words are not in the section they are attributed to

    `as_of` (YYYY-MM-DD): the quote is checked against the section AS IT STOOD THEN, rebuilt
    the same way the answer's evidence was, so a past-date quote is not "no longer matching".
    """
    from checker import section_index

    number = (c.get("provision") or "").removeprefix("s.").strip()
    if not number:
        return False, "the citation names no provision, so there is nothing to re-read", None
    rec = section_index.section_by_number(number)
    if not rec:
        return False, (f"the corpus no longer holds s.{number}, which this citation "
                       f"names"), None
    if c.get("sha256") and rec.get("sha256") != c.get("sha256"):
        return False, (f"s.{number} has changed since this answer was given: the corpus "
                       f"file now hashes to {str(rec.get('sha256'))[:12]}..., the citation "
                       f"records {str(c.get('sha256'))[:12]}.... The quote is not "
                       f"re-verified against text we did not read"), None
    text = _section_text(rec, as_of)
    when = f"as it stood on {as_of}" if as_of else "as the corpus holds it today"
    if not (c.get("quote") or "") or c["quote"] not in text:
        return False, (f"the quote is NOT present in s.{number} {when}, so nothing may "
                       f"rest on it"), None
    return True, (f"re-read from corpus/companies_act/{rec['section_id']}.json "
                  + (f"rebuilt to {as_of} " if as_of else "")
                  + "and the quote byte-matches"), text


def _citations_from_summary(summary, pairs, *, index_out: dict | None = None) -> list:
    """The traced spans as citations. Every quote is the VERIFIED span, not the model's
    claim about it.

    `Citation.quoted` is what the model SAID it read; `sources[i].text[start:end]` is what
    is actually there. `check_blocks` has already compared them -- that is what TRACED
    means -- and taking the slice rather than the claim is what keeps that true downstream.

    `index_out`, when given, is filled with {1-based sentence position: [citation ids]} --
    built in THIS loop rather than reconstructed afterwards. Job 6b needs to know which
    citations die with a sentence the critic removes, and a second function replaying this
    id assignment would be a copy that drifts the first time either changes.

    The positions are into `summary.sentences`, not `summary.traced`, so they line up with
    the `s1..sN` claim ids `_apply_critic` builds. `Summary.traced` is exactly
    `(s for s in sentences if s.traced)` (checker/lawyer_summary.py), so skipping the
    untraced here walks the same sentences in the same order and assigns the same ids.
    """
    from gateway import envelope as ev

    by_id = {src.source_id: org for src, org in pairs}
    out, seen = [], {}
    for position, sentence in enumerate(summary.sentences, 1):
        if not sentence.traced:
            continue
        for cit in sentence.citations:
            if not 0 <= cit.source_index < len(summary.sources):
                continue
            src = summary.sources[cit.source_index]
            span = src.text[cit.start:cit.end]
            key = (src.source_id, cit.start, cit.end)
            if not span.strip():
                continue
            if key in seen:
                # A span two sentences share. BOTH record it, which is what keeps a
                # citation alive when one of them is removed and the other is not.
                if index_out is not None:
                    index_out.setdefault(position, []).append(seen[key])
                continue
            instrument, provision = _split_provision(src.source_id)
            org = by_id.get(src.source_id)
            number = provision.removeprefix("s.")
            from checker import section_index
            rec = section_index.section_by_number(number) or {}
            cid = f"c{len(out) + 1}"
            try:
                out.append(ev.citation(
                    id=cid, instrument=instrument, provision=provision,
                    source=(getattr(org, "path", None)
                            or f"corpus/companies_act/{rec.get('section_id')}.json"),
                    fetched_at=str(rec.get("fetched_at") or "unrecorded"),
                    sha256=str(rec.get("sha256") or ""), quote=span,
                    # Not available per section in the corpus record. NULL means NOT
                    # RECORDED, and the schema says so -- a commencement date guessed
                    # here would be a statutory date we invented.
                    in_force_from=None))
            except ev.EnvelopeError:
                # A span we cannot describe fully is not shown. Same rule as the drop.
                # `seen` is NOT marked: nothing was emitted, so a later sentence citing the
                # same span should get its own chance to fail rather than inherit an id
                # that does not exist.
                continue
            seen[key] = cid
            if index_out is not None:
                index_out.setdefault(position, []).append(cid)
    return out

def _citations_for(task: str, result: dict) -> tuple[list, list]:
    """(kept, dropped). Every citation is re-verified against the corpus before it is shown.

    Dropped, never flagged: a citation on screen is one a reader will trust, and the only
    honest thing to do with a quote we cannot find in the section it names is remove it and
    say how many were removed.
    """
    from gateway import envelope as ev

    raw = result.get("citations") or []
    if not raw:
        return [], []
    as_of = _law_as_of_date(result)
    return ev.drop_unquoted(raw, verify=lambda c: verify_citation(c, as_of)[0])


def _law_as_of_date(result: dict) -> str | None:
    """The past date an answer's law was read as at, or None for current law."""
    law = result.get("law_as_of") if isinstance(result, dict) else None
    return law.get("date") if isinstance(law, dict) and law.get("date") else None


def _law_as_of_block(law: dict) -> str:
    """What the reader is told about a past-date answer, in words."""
    from datetime import date
    out = f"Law as it stood on {_long_date(date.fromisoformat(law['date']))}."
    if law.get("rebuilt"):
        out += (" Wording that has since changed was rebuilt from India Code's amendment "
                "notes. That rebuilt wording has not yet been independently checked against "
                "the amending Acts.")
    for x in law.get("sections") or ():
        if x.get("fidelity") == "PARTIAL":
            out += (f" Part of {x['provision']} on that date is not known: the source does not "
                    f"give the earlier wording for: " + "; ".join(x.get("unknown") or ()))
        elif x.get("fidelity") == "ABSTAIN":
            out += f" {x['provision']} was left out: its wording on that date cannot be recovered."
    return out


def _citation_get(args: dict, ctx: Context) -> dict:
    """One citation in full, for the source panel, RE-READ from the corpus.

    The panel is where a lawyer goes to check, so it is the last place that should show a
    quote nobody re-read. `verify_citation` goes back to
    `section_index.section_by_number` and `html_to_text` -- the same two functions the
    evidence path used -- and reports which of three things failed if any did.
    """
    cid = (args.get("citation_id") or "").strip()
    conv_id = (args.get("conversation_id") or "").strip()
    if not cid:
        return _refuse("BAD_REQUEST", "citation_id is required")
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    if not conv_id:
        return _refuse("BAD_REQUEST",
                       "conversation_id is required: a citation is read back from the "
                       "message that made it, so the tenant's own policy governs the read")
    if not access.row_allowed(ctx, ctx.store.read_conversation(conv_id)):
        return _refuse("NOT_FOUND", f"no citation {cid!r} in that conversation")
    asked = (args.get("as_of") or "").strip() or None
    if asked is not None:
        _d, refusal = _law_date(asked, ctx)
        if refusal:
            return refusal
        asked = _d.isoformat() if _d else None
    for msg in ctx.store.read_messages(conv_id):
        for c in (msg.get("envelope") or {}).get("citations", ()):
            if c.get("id") != cid:
                continue
            # The date the ANSWER was read as at wins: it is what the quote was matched
            # against. `as_of` from the caller covers a message stored without one.
            law_date = _law_as_of_date(msg.get("metadata") or {}) or asked
            ok, why, text = _reread(c, law_date)
            # The whole section, so the panel can show the quote IN its context. Only when
            # it re-verified: `text` is then the very text the quote was matched against,
            # and `start`/`end` are the first byte-exact occurrence, found here rather than
            # carried from answer time.
            section = None
            if ok and text is not None:
                start = text.index(c["quote"])
                section = {"text": text, "start": start, "end": start + len(c["quote"])}
            return {"citation": c, "message_id": msg["message_id"],
                    "reverified": ok, "reverified_note": why, "section": section,
                    **({"law_as_of": dict((msg.get("metadata") or {}).get("law_as_of")
                                          or {"date": law_date, "rebuilt": False})}
                       if law_date else {}),
                    "note": ("The quote was re-read from the corpus just now, not trusted "
                             "from the stored answer. reverified=false means nothing may "
                             "rest on it, whatever the stored envelope says.")}
    return _refuse("NOT_FOUND", f"no citation {cid!r} in conversation {conv_id!r}")
