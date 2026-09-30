"""Which body of law ONE claim rests on, decided from the evidence it traced to.

`checker/events.py` says which bodies a TRANSACTION engages. That is a fact about the
transaction and it is the wrong answer for a sentence: using it per claim would stamp every
sentence with every body the event touched, and the weakest body would then contaminate
claims that never rested on it. `bodies_for_event`'s own docstring says claim-level
attribution is the caller's job. This module is that job.

## Attribution is from the PATH, not from the label

A `Source.source_id` is a human label -- "Companies Act 2013, s.96" -- written by whatever
built the evidence. A label can say anything. What cannot is
`public_only.Origin.path`: the repo-relative path of the committed file the text was cleared
against, with its git blob id. That is the instrument, established rather than asserted, and
it is what this module reads.

## Never default, and why the table is so short

**An unknown instrument makes the claim UNATTRIBUTED, and an unattributed claim is not
admitted.** There is no fallback to CA2013. A default would mean a sentence traced to
something nobody mapped gets served as though it rested on the one body we hold -- which is
the most confident possible answer produced by the least information.

The table is deliberately narrow, and one entry that is NOT here is the reason why.
`corpus/sources/acquisition_fema1999.json` exists, and its own contents say
"NOTHING WAS ACQUIRED AND NOTHING WAS INGESTED". A prefix rule keyed on the filename would
map it to FEMA1999 and start attributing claims to a body where nothing is held. A path
named after a body is not that body's text, and a test asserts that file attributes to
nothing.

Secretarial Standards (`corpus/reference/SS-1.txt`) are likewise absent: SS-1 and SS-2 are
ICSI standards, not one of `scope.py`'s bodies, and inventing a body for them here would put
a key in a record that the register cannot resolve.

Run: PYTHONPATH=. python3 checker/claim_bodies.py
"""
from __future__ import annotations

from dataclasses import dataclass

from checker import events, scope

# A claim whose evidence maps to no known instrument. Not a body: the ABSENCE of one.
UNATTRIBUTED = "UNATTRIBUTED"


class AttributionError(ValueError):
    """The table is wrong. Raised at import, never carried into a claim."""


@dataclass(frozen=True)
class Instrument:
    """One repo-relative path prefix, the body whose text lives under it, and why."""

    prefix: str
    body_id: str
    reason: str

    def __post_init__(self) -> None:
        scope.body(self.body_id)          # a renamed body breaks at import, not at runtime
        if not self.prefix or self.prefix.startswith("/"):
            raise AttributionError(
                f"{self.prefix!r} must be a repo-relative path prefix; an absolute path "
                f"would attribute by where this checkout happens to sit")
        if len(self.reason) < 25:
            raise AttributionError(
                f"{self.prefix!r} is mapped with no real reason. An entry a reader cannot "
                f"evaluate is one nobody can correct.")


# ── the table ────────────────────────────────────────────────────────────────
# Longest prefix wins, so a specific file can override the directory above it. Only paths
# whose CONTENT is the instrument's text appear. See the module docstring on what does not.
INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument("corpus/companies_act/", "CA2013",
               "the ingested, hash-stamped sections of the Act itself -- this is the "
               "corpus the obligation engine and structural retrieval both read"),
    Instrument("corpus/rules/", "CA2013",
               "delegated rules made under the Act; a rule made under an Act is an "
               "instrument of that Act and not a body of its own"),
    Instrument("corpus/provisions/", "CA2013",
               "provision-level extracts of rules made under the Act, held in the same "
               "form and for the same purpose as corpus/rules"),
    Instrument("corpus/sources/companies_act_2013_indiacode", "CA2013",
               "the India Code rendering of the Act that the ingested corpus was checked "
               "against; a quote from it is a quote of the Act"),
)

_BY_LENGTH = tuple(sorted(INSTRUMENTS, key=lambda i: -len(i.prefix)))


def body_for_path(path: str | None) -> str:
    """The body whose instrument lives at `path`, or UNATTRIBUTED. Never a default.

    `path` is `public_only.Origin.path`: repo-relative POSIX, established against a
    committed file rather than asserted by whoever built the evidence.
    """
    if not path:
        return UNATTRIBUTED
    p = str(path).replace("\\", "/").lstrip("./")
    for inst in _BY_LENGTH:
        if p.startswith(inst.prefix):
            return inst.body_id
    return UNATTRIBUTED


def reason_for_path(path: str | None) -> str:
    """Why `path` attributes as it does -- including why it does not."""
    if not path:
        return ("the claim carries no evidence path, so there is no instrument to "
                "attribute it to")
    p = str(path).replace("\\", "/").lstrip("./")
    for inst in _BY_LENGTH:
        if p.startswith(inst.prefix):
            return inst.reason
    return (f"{p} is not a mapped instrument. It may be a working file, an acquisition log "
            f"or a source nobody has attributed yet -- and a path named after a body is not "
            f"that body's text, so nothing is inferred from the name.")


@dataclass(frozen=True)
class Attribution:
    """The admitted claims, and the ones that could not be attributed."""

    admitted: tuple = ()
    unattributed: tuple = ()          # (claim, why) pairs

    @property
    def body_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for c in self.admitted:
            if c.body_id not in seen:
                seen.append(c.body_id)
        return tuple(seen)


def attribute(claims) -> Attribution:
    """Split claims into those whose evidence names an instrument and those that do not.

    An unattributed claim is NOT admitted. It is returned with its reason so a caller can
    say what was dropped and why -- a dropped sentence that is merely absent is
    indistinguishable from one that was never written.
    """
    from dataclasses import replace

    admitted, dropped = [], []
    for c in claims:
        body = body_for_path(getattr(c, "evidence_path", ""))
        if body == UNATTRIBUTED:
            dropped.append((c, reason_for_path(getattr(c, "evidence_path", ""))))
            continue
        # The body is SET from the evidence rather than trusted from the claim: whatever
        # built the claim may have guessed, and this is the step that stops a guess.
        admitted.append(replace(c, body_id=body))
    return Attribution(tuple(admitted), tuple(dropped))


def bodies_for(claims, *, event_key: str | None = None, facts: dict | None = None
               ) -> tuple[str, ...]:
    """The UNION of the bodies the claims rest on and the bodies the event engages.

    Claim bodies first, in the order they were first claimed; then any body the event
    engages that no claim rested on. The union is the point: a body the answer TOUCHES but
    cannot claim FROM -- the FEMA case -- would otherwise vanish from the record, taking its
    named refusal with it, and the answer would read as fully supported.

    Wire it into `model_cascade.run` as
    `bodies_for=lambda claims: claim_bodies.bodies_for(claims, event_key=..., facts=...)`.
    """
    out = list(attribute(claims).body_ids)
    if event_key:
        for b in events.bodies_for_event(event_key, facts):
            if b not in out:
                out.append(b)
    return tuple(out)


# ── self-test ────────────────────────────────────────────────────────────────

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

    from pathlib import Path

    from checker import model_cascade as mc

    def claim(path, text="a sentence"):
        return mc.Claim(text=text, body_id="", quote="q", source_id="s",
                        evidence_path=path)

    # ── a CA2013 span attributes to CA2013 ──────────────────────────────────
    check(body_for_path("corpus/companies_act/1220.json") == "CA2013",
          "a span from the ingested Act attributes to CA2013")
    check(body_for_path("corpus/rules/board_powers_2014.json") == "CA2013",
          "...a rule made under the Act attributes to the Act, not to a body of its own")
    check(body_for_path("corpus/sources/companies_act_2013_indiacode.txt") == "CA2013",
          "...and so does the India Code rendering the corpus was checked against")

    # ── an unknown source is UNATTRIBUTED and is NOT admitted ───────────────
    check(body_for_path("corpus/testdocs/some_minutes.txt") == UNATTRIBUTED,
          "an unmapped path is UNATTRIBUTED")
    check(body_for_path("") == UNATTRIBUTED and body_for_path(None) == UNATTRIBUTED,
          "...as is a claim with no evidence path at all")
    att = attribute([claim("corpus/companies_act/1220.json"),
                     claim("corpus/testdocs/x.txt")])
    check(len(att.admitted) == 1 and len(att.unattributed) == 1,
          f"an unattributed claim is NOT admitted ({len(att.admitted)} admitted, "
          f"{len(att.unattributed)} dropped)")
    check(att.unattributed[0][1],
          "...and is returned WITH its reason: a sentence that is merely absent is "
          "indistinguishable from one nobody wrote")
    check(att.body_ids == ("CA2013",), f"...leaving only real bodies {att.body_ids}")

    # THE rule. No default, ever.
    check(all(body_for_path(p) == UNATTRIBUTED for p in
              ("", "corpus/", "corpus/reference/SS-1.txt", "somewhere/else.json",
               "corpus/admission/instrument_ACT_COMPANIES_ACT_2013.json")),
          "NOTHING defaults to CA2013 -- an unmapped path stays unattributed however much "
          "it looks like the Act")

    # The entry deliberately absent, and the reason it is absent.
    fema_log = "corpus/sources/acquisition_fema1999.json"
    check(Path(fema_log).exists(), "the FEMA acquisition log is really there")
    check(body_for_path(fema_log) == UNATTRIBUTED,
          "...and attributes to NOTHING: its own contents say nothing was acquired or "
          "ingested, so a filename rule would attribute claims to a body we do not hold")
    check("named after a body is not that body's text" in reason_for_path(fema_log),
          "...and the reason says why, so the next author does not add the rule")
    check(body_for_path("corpus/reference/SS-1.txt") == UNATTRIBUTED,
          "Secretarial Standards attribute to nothing: SS-1 is an ICSI standard, not one "
          "of scope.py's bodies, and inventing a key here would put one in a record the "
          "register cannot resolve")

    # ── the union with an event ─────────────────────────────────────────────
    only_ca = [claim("corpus/companies_act/1220.json")]
    check(bodies_for(only_ca) == ("CA2013",),
          "with no event, the bodies are the claims' bodies")
    union = bodies_for(only_ca, event_key="share_allotment",
                       facts={"foreign_investor": True})
    check("CA2013" in union and "FEMA1999" in union,
          f"...and with an event, a body the answer TOUCHES but cannot claim from is kept "
          f"{union}")
    check(union[0] == "CA2013",
          "...claim bodies first, then the event-only ones")
    check(mc.answer_status(list(union)) == mc.PARTIAL,
          "...so the answer is PARTIAL rather than reading as fully supported")
    refusals = dict(mc.refusals_for(list(union)))
    check("FEMA1999" in refusals and "Foreign Exchange Management" in refusals["FEMA1999"],
          "...and FEMA's named refusal survives, which is what would have been lost")

    # An event body with NO claims at all still yields its refusal.
    none_claimed = bodies_for([], event_key="commercial_contract")
    check(set(none_claimed) >= {"CONTRACT1872", "STAMP", "ARBITRATION1996"},
          f"an event engaging only unheld bodies still reports them {none_claimed}")
    check(len(mc.refusals_for(list(none_claimed))) == len(none_claimed),
          "...each with its named refusal, none silently dropped")
    check(mc.answer_status(list(none_claimed)) == mc.PARTIAL,
          "...and the status reflects them")

    # ── it drops into the cascade unchanged ─────────────────────────────────
    got = {}

    def verify(_raw):
        return True, "", (claim("corpus/companies_act/1220.json"),
                          claim("corpus/testdocs/junk.txt"))

    r = mc.run("q", stages=[mc.Stage(mc.SMALL, lambda _p: "x", model="m")],
               verify=verify,
               bodies_for=lambda claims: bodies_for(claims, event_key="share_allotment",
                                                    facts={"foreign_investor": True}))
    got["status"] = r.status
    check(r.status == mc.PARTIAL, f"the cascade takes it unchanged ({r.status})")
    check("FEMA1999" in r.body_ids and "CA2013" in r.body_ids,
          f"...recording both the claimed and the touched bodies {r.body_ids}")
    check(dict(r.refusals).get("FEMA1999"), "...with the refusal present")

    # ── the table itself ────────────────────────────────────────────────────
    check(all(i.body_id in {b.key for b in scope.BODIES} for i in INSTRUMENTS),
          "every body_id in the table exists in scope.py")
    check(all(scope.body(i.body_id).status == scope.IN_CORPUS for i in INSTRUMENTS),
          "...and every mapped instrument belongs to a body we actually HOLD: mapping a "
          "path to an unheld body would make it claimable")
    check(_BY_LENGTH[0].prefix.count("/") >= _BY_LENGTH[-1].prefix.count("/"),
          "the table is matched longest-prefix-first, so a specific file can override the "
          "directory above it")
    for bad, why in (
        (lambda: Instrument("/abs/path", "CA2013", "a reason long enough to pass"),
         "an absolute path prefix"),
        (lambda: Instrument("corpus/x/", "CA2013", "short"), "a mapping with no reason"),
        (lambda: Instrument("corpus/x/", "NOT_A_BODY", "a reason long enough to pass"),
         "a body that is not in the register"),
    ):
        try:
            bad()
            check(False, f"{why} is refused")
        except (AttributionError, LookupError):
            check(True, f"refused at construction: {why}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
