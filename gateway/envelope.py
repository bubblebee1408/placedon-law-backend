#!/usr/bin/env python3
"""One answer envelope, versioned, validated against the schema file beside it.

C2 §3. Every reply the conversation layer returns has this shape, whatever task produced
it, so a UI renders one thing and a stored message renders the same way next month.

## The version is in the filename, and that is the whole point

`gateway/schemas/answer_envelope.v1.json`. A v2 is a NEW FILE, never an edit to that one:
`messages.envelope` stores what was sent, a conversation is re-opened months later, and a
schema edited in place would silently re-interpret a stored answer. `SCHEMA_ID` is written
into every envelope so a reader can tell which contract it was built under without guessing
from its keys.

## Two validators, on purpose

`validate()` is stdlib and runs in the served path, because an envelope that does not match
its own schema must not reach a UI. `jsonschema` (declared in requirements-dev.txt) runs
over the SAME schema file in `_test()` as an independent oracle. A hand-written validator
that is the only judge of its own correctness is the census problem again -- `pdf_pages` is
judged by a different parser for the same reason -- and the test asserts the two agree on
every envelope and that the oracle can reject.

## FAILED is transport, and it is never a refusal

A refusal is a legal position: we read the law and it says nothing on point, or the body is
not held. FAILED means the attempt broke -- a timeout, a dead provider, a crashed worker.
Rendering one as the other is the failure `checker/ask.py` was rewritten to stop (H0), and
it is worse here because a UI shows this to a lawyer. So `failed()` is the only way to build
one, it carries no bodies and no citations, and `is_refusal` is False for it while being
True for ABSTAINED and PARTIAL. A caller cannot reach FAILED by filling in fields.

## A citation without a byte-matching quote is dropped, not flagged

`drop_unquoted()` removes it and RETURNS what it removed, so the count can be stated rather
than discovered. Flagging would leave it on screen for a reader to trust; dropping and
saying so is the same choice `checker/quoted_span.py` makes about a sentence.

Run: PYTHONPATH=. python3 gateway/envelope.py --test
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "gateway" / "schemas" / "answer_envelope.v1.json"
SCHEMA_ID = "answer_envelope.v1"

# ── statuses ─────────────────────────────────────────────────────────────────
ANSWERED = "ANSWERED"
PARTIAL = "PARTIAL"
NEEDS_LAWYER = "NEEDS_LAWYER"
ABSTAINED = "ABSTAINED"
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
FAILED = "FAILED"
STATUSES = (ANSWERED, PARTIAL, NEEDS_LAWYER, ABSTAINED, NEEDS_CLARIFICATION, FAILED)

# What a lawyer may read as a position about the law. FAILED is not among them, and that
# absence is the rule this module is built around.
LEGAL_OUTCOMES = (ANSWERED, PARTIAL, NEEDS_LAWYER, ABSTAINED)

# ── per-body statuses ────────────────────────────────────────────────────────
B_ANSWERED = "ANSWERED"
B_NOT_HELD = "NOT_HELD"
B_CURRENT_ONLY = "CURRENT_ONLY"
B_NEED_FACT = "NEED_FACT"
B_NOT_ENGAGED = "NOT_ENGAGED"
BODY_STATUSES = (B_ANSWERED, B_NOT_HELD, B_CURRENT_ONLY, B_NEED_FACT, B_NOT_ENGAGED)

# ── file states ──────────────────────────────────────────────────────────────
READING = "READING"
READ = "READ"
CANNOT_READ = "CANNOT_READ"
FILE_STATES = (READING, READ, CANNOT_READ)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EnvelopeError(ValueError):
    """An envelope that does not match its own schema. Never a warning."""


def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


_SCHEMA_CACHE: dict = {}


def _schema() -> dict:
    if not _SCHEMA_CACHE:
        _SCHEMA_CACHE.update(schema())
    return _SCHEMA_CACHE


# ── the stdlib validator, run in the served path ─────────────────────────────

def _fail(path: str, why: str) -> str:
    return f"{path or '<root>'}: {why}"


def _check(node: dict, value, path: str) -> list:
    """Errors against one schema node. Covers the subset this schema uses, and REFUSES a
    keyword it does not implement rather than ignoring it -- an unimplemented keyword
    silently skipped is a rule the served path stops enforcing the day someone adds it."""
    known = {"$schema", "$id", "title", "description", "type", "enum", "const",
             "properties", "required", "additionalProperties", "items", "minLength",
             "minimum", "pattern"}
    unknown = set(node) - known
    if unknown:
        raise EnvelopeError(
            f"{path}: the schema uses keyword(s) {sorted(unknown)} that gateway/envelope.py "
            f"does not implement. Implement them or the served path is not checking them")

    errs = []
    if "const" in node and value != node["const"]:
        errs.append(_fail(path, f"must be {node['const']!r}, got {value!r}"))
        return errs
    if "enum" in node and value not in node["enum"]:
        errs.append(_fail(path, f"{value!r} is not one of {node['enum']}"))
        return errs

    types = node.get("type")
    if types is not None:
        want = [types] if isinstance(types, str) else list(types)
        if not _typed(value, want):
            errs.append(_fail(path, f"must be {'/'.join(want)}, got "
                                    f"{type(value).__name__}"))
            return errs

    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            errs.append(_fail(path, f"must be at least {node['minLength']} character(s)"))
        if "pattern" in node and not re.match(node["pattern"], value):
            errs.append(_fail(path, f"{value!r} does not match {node['pattern']}"))
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            errs.append(_fail(path, f"must be >= {node['minimum']}"))

    if isinstance(value, dict):
        for key in node.get("required", ()):
            if key not in value:
                errs.append(_fail(path, f"missing required field {key!r}"))
        props = node.get("properties", {})
        if node.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                errs.append(_fail(path, f"unknown field(s) {extra}; known {sorted(props)}"))
        for key, sub in props.items():
            if key in value:
                errs.extend(_check(sub, value[key], f"{path}.{key}" if path else key))
    if isinstance(value, list) and "items" in node:
        for i, item in enumerate(value):
            errs.extend(_check(node["items"], item, f"{path}[{i}]"))
    return errs


def _typed(value, want: list) -> bool:
    for t in want:
        if t == "null" and value is None:
            return True
        if t == "string" and isinstance(value, str):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "object" and isinstance(value, dict):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
    return False


def errors(env: dict) -> list:
    """Every way `env` fails the schema. Empty means it matches."""
    return _check(_schema(), env, "")


def validate(env: dict) -> dict:
    """Return the envelope, or raise. Nothing reaches a UI unvalidated."""
    bad = errors(env)
    if bad:
        raise EnvelopeError(f"{len(bad)} schema error(s): " + "; ".join(bad[:6]))
    return env


# ── building one ─────────────────────────────────────────────────────────────

def body(body_id: str, name: str, status: str, note: str) -> dict:
    if status not in BODY_STATUSES:
        raise EnvelopeError(f"{status!r} is not a body status; one of {BODY_STATUSES}")
    if not note.strip():
        raise EnvelopeError(f"{body_id}: a body with no note says nothing about why")
    return {"body_id": body_id, "name": name, "status": status, "note": note}


def citation(*, id: str, instrument: str, provision: str, source: str, fetched_at: str,
             sha256: str, quote: str, in_force_from: str | None = None) -> dict:
    if not _SHA256.match(sha256 or ""):
        raise EnvelopeError(f"{id}: sha256 must be 64 lowercase hex, got {sha256!r}")
    if not (quote or "").strip():
        raise EnvelopeError(f"{id}: a citation with no quote is not a citation")
    out = {"id": id, "instrument": instrument, "provision": provision, "source": source,
           "fetched_at": fetched_at, "sha256": sha256, "quote": quote}
    if in_force_from is not None:
        out["in_force_from"] = in_force_from
    return out


def file_state(file_id: str, name: str, state: str, *, pages: int | None = None,
               reason: str | None = None) -> dict:
    if state not in FILE_STATES:
        raise EnvelopeError(f"{state!r} is not a file state; one of {FILE_STATES}")
    if state == CANNOT_READ and not (reason or "").strip():
        raise EnvelopeError(
            f"{name}: CANNOT_READ must carry a reason. 'We could not read this page' and "
            f"'this document says nothing' are different answers and a UI that renders "
            f"them the same turns a broken upload into a finding about the law")
    if state != CANNOT_READ and reason:
        raise EnvelopeError(f"{name}: {state} carries a reason for not reading it anyway")
    out = {"file_id": file_id, "name": name, "state": state}
    if pages is not None:
        out["pages"] = pages
    if reason is not None:
        out["reason"] = reason
    return out


def drop_unquoted(citations: list, *, verify) -> tuple[list, list]:
    """(kept, dropped). `verify(citation) -> bool` byte-matches the quote to its source.

    Dropped, not flagged. A flagged citation stays on screen for a reader to trust; the
    only honest thing to do with a quote we cannot find in its source is remove it and say
    how many were removed -- which is why this returns both lists.
    """
    kept, dropped = [], []
    for c in citations:
        (kept if verify(c) else dropped).append(c)
    return kept, dropped


def build(*, status: str, task: str, as_of: str, text_blocks=(), bodies=(), citations=(),
          files=(), run_id: str | None = None, trace_url: str | None = None,
          searched: dict | None = None) -> dict:
    """One validated envelope. Raises rather than returning something malformed."""
    if status == FAILED:
        raise EnvelopeError(
            "FAILED is built by failed(), not by build(). It is a TRANSPORT outcome and "
            "must carry no bodies and no citations; reaching it by filling in fields is "
            "how a broken provider becomes a statement about the law")
    if status not in STATUSES:
        raise EnvelopeError(f"{status!r} is not a status; one of {STATUSES}")
    if not _DATE.match(as_of or ""):
        raise EnvelopeError(f"as_of must be YYYY-MM-DD, got {as_of!r}: an answer with no "
                            f"date is an answer about no particular law")
    known = {c["id"] for c in citations}
    for i, block in enumerate(text_blocks):
        missing = [cid for cid in block.get("citation_ids", ()) if cid not in known]
        if missing:
            raise EnvelopeError(
                f"text_blocks[{i}] cites {missing}, which is not in citations. A block "
                f"pointing at a citation that is not there renders as an unsourced "
                f"sentence with a footnote marker")
    env = {"schema": SCHEMA_ID, "status": status, "task": task, "as_of": as_of,
           "text_blocks": list(text_blocks), "bodies": list(bodies),
           "citations": list(citations), "files": list(files),
           "run_id": run_id, "trace_url": trace_url}
    if searched is not None:
        # Optional, and absent on every envelope written before it existed: an old stored
        # envelope still validates and still means what it meant.
        env["searched"] = searched
    return validate(env)


def failed(*, task: str, as_of: str, detail: str, run_id: str | None = None,
           trace_url: str | None = None) -> dict:
    """A TRANSPORT failure. Carries no bodies and no citations, by construction.

    The text block says what broke in words a reader can act on, and says explicitly that
    it is not a statement about the law -- because the one thing a reader must not conclude
    from a failure is that there was no obligation.
    """
    env = {"schema": SCHEMA_ID, "status": FAILED, "task": task, "as_of": as_of,
           "text_blocks": [{"text": (f"This attempt did not complete: {detail}. That is a "
                                     f"failure of ours, not a finding about the law -- "
                                     f"nothing was read and nothing was decided, so no "
                                     f"conclusion about any obligation follows from it. "
                                     f"Please try again."),
                            "citation_ids": []}],
           "bodies": [], "citations": [], "files": [],
           "run_id": run_id, "trace_url": trace_url}
    return validate(env)


def is_refusal(env: dict) -> bool:
    """Is this a position about the law that declines to answer? FAILED never is."""
    return env.get("status") in (ABSTAINED, PARTIAL, NEEDS_LAWYER)


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

    print("gateway.envelope")
    import hashlib
    H = hashlib.sha256(b"Every company shall hold").hexdigest()
    CIT = citation(id="c1", instrument="Companies Act, 2013", provision="s.173",
                   source="corpus/companies_act", fetched_at="2026-10-01T00:00:00+00:00",
                   sha256=H, quote="Every company shall hold", in_force_from="2014-04-01")

    # ── the schema file is the contract, and it is IN THE REPO ──────────────
    check(SCHEMA_PATH.is_file(), f"the schema file exists at {SCHEMA_PATH.name}")
    check(schema()["title"] == SCHEMA_ID, f"...and its title is {SCHEMA_ID}")
    check(SCHEMA_ID.endswith(".v1") and "v1" in SCHEMA_PATH.name,
          "the version is in the filename AND in every envelope, so a stored message says "
          "which contract it was built under")

    # ── the envelope validates for EVERY task ───────────────────────────────
    from agents import intake
    for task in intake.TASKS + (intake.NEEDS_CLARIFICATION,):
        env = build(status=ANSWERED if task != intake.NEEDS_CLARIFICATION
                    else NEEDS_CLARIFICATION,
                    task=task, as_of="2026-10-01",
                    text_blocks=[{"text": "A block.", "citation_ids": ["c1"]}],
                    bodies=[body("CA2013", "Companies Act, 2013", B_ANSWERED, "held")],
                    citations=[CIT],
                    files=[file_state("f1", "minutes.pdf", READ, pages=3)],
                    run_id="r1", trace_url="/v2/runs/r1/trace")
        check(errors(env) == [], f"the envelope validates for task {task}")
    check(len(intake.TASKS) == 8,
          f"...all eight tasks plus NEEDS_CLARIFICATION ({len(intake.TASKS)})")
    check(set(intake.TASKS) | {intake.NEEDS_CLARIFICATION}
          == set(schema()["properties"]["task"]["enum"]),
          "the schema's task enum is EXACTLY intake's closed set plus "
          "NEEDS_CLARIFICATION -- so a task intake can name and the envelope cannot carry "
          "is impossible, in either direction")

    # ── the independent oracle, over the SAME schema file ───────────────────
    import jsonschema
    good = build(status=ANSWERED, task="RESEARCH_QUESTION", as_of="2026-10-01",
                 citations=[CIT],
                 text_blocks=[{"text": "x", "citation_ids": ["c1"]}])
    jsonschema.validate(good, schema())
    check(True, "jsonschema (declared in requirements-dev.txt) accepts a built envelope, "
                "over the same schema file -- a hand-written validator that is the only "
                "judge of itself proves nothing")
    # ...and it must be able to REJECT.
    for broken, why in [({**good, "status": "MAYBE"}, "a status outside the enum"),
                        ({**good, "as_of": "01-10-2026"}, "a non-ISO as_of"),
                        ({k: v for k, v in good.items() if k != "task"}, "no task"),
                        ({**good, "surprise": 1}, "an unknown field"),
                        ({**good, "citations": [{**CIT, "sha256": "short"}]},
                         "a malformed sha256"),
                        ({**good, "bodies": [{"body_id": "X", "name": "X",
                                              "status": "NOPE", "note": "n"}]},
                         "a body status outside the enum")]:
        try:
            jsonschema.validate(broken, schema())
            check(False, f"the oracle rejects {why}")
        except jsonschema.ValidationError:
            check(True, f"the oracle rejects {why}")
        check(errors(broken) != [], f"...and so does validate() ({why})")

    # The two agree on a corpus of envelopes, including the malformed ones.
    disagreements = []
    for env in [good, {**good, "status": "MAYBE"}, {**good, "surprise": 1},
                {**good, "files": [{"file_id": "f", "name": "n", "state": "READING"}]},
                {**good, "run_id": None}, {**good, "citations": []}]:
        mine = not errors(env)
        try:
            jsonschema.validate(env, schema())
            theirs = True
        except jsonschema.ValidationError:
            theirs = False
        if mine != theirs:
            disagreements.append((env.get("status"), mine, theirs))
    check(not disagreements,
          f"the stdlib validator and jsonschema agree on every envelope tried "
          f"({disagreements})")

    # A schema keyword the served validator does not implement must RAISE, not be skipped.
    try:
        _check({"type": "object", "maxProperties": 2}, {}, "x")
        check(False, "an unimplemented schema keyword raises")
    except EnvelopeError as e:
        check("does not implement" in str(e),
              "an unimplemented schema keyword RAISES rather than being silently skipped "
              "-- a skipped keyword is a rule the served path stops enforcing")

    # ── a CA2013 + FEMA question is PARTIAL with FEMA NOT_HELD ──────────────
    from checker import scope
    fema = scope.body("FEMA1999")
    mixed = build(
        status=PARTIAL, task="RESEARCH_QUESTION", as_of="2026-10-01",
        text_blocks=[{"text": "Under the Companies Act the allotment return is filed.",
                      "citation_ids": ["c1"]}],
        bodies=[body("CA2013", "Companies Act, 2013", B_ANSWERED,
                     "held and read as at 2026-10-01"),
                body("FEMA1999", fema.name, B_NOT_HELD, scope.refusal_for("FEMA1999"))],
        citations=[CIT])
    check(errors(mixed) == [], "a CA2013 + FEMA envelope validates")
    check(mixed["status"] == PARTIAL, "...its status is PARTIAL")
    byid = {b["body_id"]: b for b in mixed["bodies"]}
    check(byid["CA2013"]["status"] == B_ANSWERED and byid["FEMA1999"]["status"] == B_NOT_HELD,
          "...CA2013 ANSWERED, FEMA1999 NOT_HELD")
    check(fema.status == scope.DECLARED,
          f"...and NOT_HELD is read from checker/scope.py, where FEMA1999 is "
          f"{fema.status} -- not asserted here")
    check(len(byid["FEMA1999"]["note"]) > 40,
          "...the FEMA note is the register's own refusal text, not the word 'no'")
    check(is_refusal(mixed), "PARTIAL is a position about the law")

    # ── a scanned PDF shows CANNOT_READ with a reason ───────────────────────
    scanned = build(status=ABSTAINED, task="REVIEW_DOCUMENT", as_of="2026-10-01",
                    text_blocks=[{"text": "Nothing was read.", "citation_ids": []}],
                    files=[file_state("f9", "scan.pdf", CANNOT_READ,
                                      reason="no text layer on any of 1 page(s); this "
                                             "looks like a scan")])
    check(errors(scanned) == [], "a CANNOT_READ envelope validates")
    f = scanned["files"][0]
    check(f["state"] == CANNOT_READ and f["reason"] and "text layer" in f["reason"],
          f"...CANNOT_READ carries a reason ({f['reason'][:40]!r})")
    try:
        file_state("f", "scan.pdf", CANNOT_READ)
        check(False, "CANNOT_READ with no reason is refused")
    except EnvelopeError as e:
        check("different answers" in str(e),
              "CANNOT_READ with NO reason is refused -- 'could not read' and 'says "
              "nothing' must never render the same")
    try:
        file_state("f", "ok.pdf", READ, reason="why not")
        check(False, "READ with a reason is refused")
    except EnvelopeError:
        check(True, "...and READ carrying a reason for not reading it is refused too")
    for st in FILE_STATES:
        check(st in schema()["properties"]["files"]["items"]["properties"]["state"]["enum"],
              f"file state {st} is in the schema")

    # ── a transport error gives FAILED, and FAILED is never a refusal ───────
    bad = failed(task="RESEARCH_QUESTION", as_of="2026-10-01",
                 detail="the provider timed out after 30s", run_id="r2")
    check(errors(bad) == [], "a FAILED envelope validates")
    check(bad["status"] == FAILED and bad["bodies"] == [] and bad["citations"] == [],
          "FAILED carries no bodies and no citations, by construction")
    check(not is_refusal(bad),
          "**FAILED is not a refusal** -- a refusal is a position about the law, and this "
          "is a broken socket")
    check(FAILED not in LEGAL_OUTCOMES,
          f"...and it is absent from LEGAL_OUTCOMES ({LEGAL_OUTCOMES})")
    txt = bad["text_blocks"][0]["text"]
    check("not a finding about the law" in txt and "nothing was decided" in txt,
          "...and its text says so in words, because the one thing a reader must not "
          "conclude from a failure is that there was no obligation")
    try:
        build(status=FAILED, task="RESEARCH_QUESTION", as_of="2026-10-01",
              bodies=[body("CA2013", "x", B_ANSWERED, "n")])
        check(False, "build() refuses FAILED")
    except EnvelopeError as e:
        check("built by failed()" in str(e),
              "build() REFUSES to make a FAILED envelope: it cannot be reached by filling "
              "in fields")
    for st in (ABSTAINED, PARTIAL, NEEDS_LAWYER):
        check(is_refusal({"status": st}), f"{st} IS a refusal")
    for st in (ANSWERED, NEEDS_CLARIFICATION, FAILED):
        check(not is_refusal({"status": st}), f"{st} is not")

    # ── a citation with no byte-matching quote is DROPPED ───────────────────
    real = "Every company shall hold the first meeting of its Board"
    good_c = citation(id="k", instrument="CA2013", provision="s.173",
                      source="corpus", fetched_at="2026-10-01T00:00:00+00:00",
                      sha256=H, quote="the first meeting of its Board")
    bad_c = citation(id="b", instrument="CA2013", provision="s.173", source="corpus",
                     fetched_at="2026-10-01T00:00:00+00:00", sha256=H,
                     quote="the first meeting of its Committee")
    kept, dropped = drop_unquoted([good_c, bad_c], verify=lambda c: c["quote"] in real)
    check([c["id"] for c in kept] == ["k"] and [c["id"] for c in dropped] == ["b"],
          "a quote that does not byte-match its source is DROPPED, not flagged")
    check(len(dropped) == 1,
          "...and returned, so the count can be STATED rather than discovered")
    try:
        citation(id="x", instrument="i", provision="p", source="s",
                 fetched_at="t", sha256=H, quote="  ")
        check(False, "a citation with no quote is refused")
    except EnvelopeError:
        check(True, "a citation with no quote at all is refused at construction")

    # ── a text block may not cite what is not there ─────────────────────────
    try:
        build(status=ANSWERED, task="RESEARCH_QUESTION", as_of="2026-10-01",
              text_blocks=[{"text": "x", "citation_ids": ["ghost"]}], citations=[CIT])
        check(False, "a block citing a missing id is refused")
    except EnvelopeError as e:
        check("not in citations" in str(e),
              "a text block citing an id that is not in citations is REFUSED -- it would "
              "render as an unsourced sentence with a footnote marker")
    check(errors(build(status=ANSWERED, task="RESEARCH_QUESTION", as_of="2026-10-01",
                       text_blocks=[{"text": "x", "citation_ids": []}])) == [],
          "...while a block with no citations at all is fine")

    # ── as_of is always present ─────────────────────────────────────────────
    for bad_date in ("", "2026-1-1", "01-10-2026", "today"):
        try:
            build(status=ANSWERED, task="RESEARCH_QUESTION", as_of=bad_date)
            check(False, f"as_of {bad_date!r} is refused")
        except EnvelopeError:
            check(True, f"as_of {bad_date!r} is refused: an answer with no date is an "
                        f"answer about no particular law")

    check(set(STATUSES) == set(schema()["properties"]["status"]["enum"]),
          "the module's statuses and the schema's enum are the same set")
    check(set(BODY_STATUSES) == set(
              schema()["properties"]["bodies"]["items"]["properties"]["status"]["enum"]),
          "...and so are the body statuses")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(json.dumps(schema(), indent=2)[:600])
