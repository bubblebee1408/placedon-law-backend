"""
When the person asking is the person it happened to.

## Why this exists at all

This product is a compliance tool for employers. But the PoSH Act is a statute about harassment,
and *"do I need an Internal Committee?"* and *"what if they sack me for complaining?"* are the same
search box. Sooner or later someone types the second one.

At that moment a better citation is the wrong output. The literature on this is consistent and
worth taking seriously: [Wise (2025)](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/pra2.1349)
puts it as *chatbots are indifferent to their outputs, but survivors in crisis require
trauma-informed support* — indifference is the default and has to be designed against. Every
credible deployment — OlimpIA, HelloCass, AinoAid, Botler — **escalates to a human, early**. See
also [Designing Chatbots to Support Victims and Survivors of Domestic Abuse](https://arxiv.org/pdf/2402.17393).

So this module's job is to know when to stop being a system.

## What it does and does not do

It does **not** answer. It does not assess her case, tell her whether she has one, or explain the
law to her. It hands over three things we can source:

  * **s.6 of the Act, quoted** — the Local Committee receives complaints where an Internal
    Committee was not constituted, *"or if the complaint is against the employer himself"*. That
    clause is the most important fact in the statute for someone in this position: **she does not
    have to go to her own company's committee.**
  * **Her District Officer, by name and email**, from the register — a real person with a
    statutory duty, not a helpline number we found on a blog.
  * **SHe-Box**, the Government's own portal.

It says plainly that it is not a person.

## Design rules, and the reasoning behind each

**Recall over precision.** A false positive costs a user one paragraph they did not need. A false
negative hands a legal-compliance lecture to someone describing an assault. The patterns are
deliberately broad and the threshold is one match.

**Never priced, ever.** Whatever the pricing model becomes, this route is free. Someone hitting a
paywall while asking whether she can be sacked for complaining is the worst thing this product
could do, and a rule in code outlives a rule in a policy document.

**Runs before everything.** Before retrieval, before the epistemic gate, before any model call.
The route does not depend on `verified_by`, so it works today, while the rest of the product
abstains on everything.

**Nothing here is generated.** Every sentence is either statutory text or a directory entry we
hold with a source. There is no path by which a model writes to someone in distress.

Run: python3 checker/distress.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHEBOX = "https://shebox.wcd.gov.in"

# The National Commission for Women's 24x7 helpline. Added 2026-08-12 from the Sonnet Era plan,
# which supplied the number — and it is the one claim in that plan that survived checking, which
# is worth recording, because it is also the claim that most needed checking.
#
# An unverified helpline is a worse failure than an unverified citation. A wrong citation is read
# by an employer who may notice. A wrong number is DIALLED, by someone in distress, at the moment
# she has decided to ask for help, and it rings out. Nothing downstream catches that.
#
# So it was checked against the Ministry of External Affairs' listing and the NCW contact page
# before it was written down, and the source is recorded so the next person can re-check it
# rather than trust it:
#   https://www.mea.gov.in/helplineforwomenindistress  |  https://www.ncw.gov.in/contact-us/
# NCW, operational since 2021-07-24; links callers to police, hospitals, DLSAs and counselling.
NCW_HELPLINE = "7827170170"
NCW_SOURCE = "https://www.mea.gov.in/helplineforwomenindistress"

# First-person harm, retaliation fear, and distress. Written broad on purpose — see the recall
# rule above. Third-person and hypothetical phrasings ("if an employee complains…") are the
# employer's question and belong on the normal path, so the patterns require a first-person
# subject or an explicit statement about oneself.
_PATTERNS = (
    # what happened
    r"\b(he|she|they|my (?:boss|manager|senior|colleague|supervisor|hr))\b[^.?!]{0,60}\b"
    r"(touch(?:ed)?|grab(?:bed)?|groped|harass(?:ed|ing)?|assault(?:ed)?|stalk(?:ed|ing)?|"
    r"molest(?:ed)?|forced|threaten(?:ed)?)\b",
    r"\b(i|me|my)\b[^.?!]{0,50}\b(was|am being|being|got)\b[^.?!]{0,25}\b"
    r"(harassed|assaulted|touched|groped|molested|stalked|threatened)\b",
    # retaliation
    r"\b(fire[d]?|sack(?:ed)?|terminate[d]?|transfer(?:red)?|demote[d]?|punish(?:ed)?)\b"
    r"[^.?!]{0,40}\b(for|after|because)\b[^.?!]{0,30}\b(complain|report|posh|ic|committee)",
    r"\bwill they\b[^.?!]{0,30}\b(fire|sack|terminate)\b",
    # distress and safety
    r"\bi (?:am|feel|'m)\b[^.?!]{0,20}\b(scared|afraid|frightened|unsafe|threatened|terrified)\b",
    r"\bi (?:don'?t|do not) feel safe\b",
    r"\bwhat (?:do|should) i do\b[^.?!]{0,40}\b(harass|complain|posh|committee|boss)",
    # first-person complainant framing
    r"\bi (?:want to|need to|should i)\b[^.?!]{0,25}\b(complain|file a complaint|report)\b",
)
_RE = tuple(re.compile(p, re.I) for p in _PATTERNS)


@dataclass(frozen=True)
class Referral:
    """A handover, not an answer. `matched` names the pattern so the routing is auditable."""

    triggered: bool
    matched: str = ""
    message: str = ""
    contacts: list[dict] = field(default_factory=list)
    statutory_route: dict | None = None
    priced: bool = False              # invariant: always False. Checked by verify.py.


@lru_cache(maxsize=1)
def _officers() -> dict[str, dict]:
    path = ROOT / "corpus/reference/notified_dates.json"
    if not path.exists():
        return {}
    return {r["jurisdiction"]: r for r in json.loads(path.read_text())["districts"]}


@lru_cache(maxsize=1)
def _section_6() -> str:
    path = ROOT / "corpus/provisions/posh_act_2013.json"
    if not path.exists():
        return ""
    provs = json.loads(path.read_text())["provisions"]
    s6 = next((p for p in provs if p["section_number"] == 6), None)
    return " ".join((s6 or {}).get("text_statutory", "").split())


def detect(question: str) -> str:
    """The first pattern that matches, or empty. One match is enough."""
    q = " ".join((question or "").lower().split())
    for pat in _RE:
        if pat.search(q):
            return pat.pattern[:48]
    return ""


def route(question: str, district: str | None = None) -> Referral:
    """
    Hand over. Never answers, never assesses, never charges.

    `district` is a jurisdiction code. If we hold that officer, they are named. If not, the
    referral still stands on s.6 and SHe-Box — a missing directory entry must never reduce this
    to silence.
    """
    matched = detect(question)
    if not matched:
        return Referral(triggered=False)

    contacts: list[dict] = [{
        "kind": "helpline",
        "name": "National Commission for Women helpline (24x7)",
        "detail": NCW_HELPLINE,
        "note": ("A person, on the phone, at any hour. Listed first deliberately: a portal and an "
                 "email are things you use after deciding what to do, and this is for before."),
        "source": NCW_SOURCE,
    }, {
        "kind": "portal",
        "name": "SHe-Box, Ministry of Women & Child Development",
        "detail": SHEBOX,
        "note": "The Government's own portal for complaints of sexual harassment at work.",
    }]

    row = _officers().get(district or "")
    if row:
        contacts.append({
            "kind": "district_officer",
            "name": row.get("officer") or "District Officer",
            "detail": row.get("email") or "",
            "note": (f"District Officer for {row['district']}. Under s.6 the District Officer "
                     f"constitutes the Local Committee."),
        })

    # The clause that matters most to her, quoted rather than paraphrased.
    text = _section_6()
    i = text.lower().find("or if the complaint is against the employer himself")
    quote = text[max(0, i - 210):i + 52] if i >= 0 else text[:260]

    return Referral(
        triggered=True,
        matched=matched,
        message=(
            "This looks like it may be about something that happened to you, so here is where to "
            "go rather than what the law says.\n\n"
            "You do not have to raise this with your own company's committee. Under section 6 of "
            "the PoSH Act the District Officer's Local Committee receives complaints where no "
            "Internal Committee was constituted, **or where the complaint is against the employer "
            "himself**.\n\n"
            "This is a computer program, not a person, and it cannot advise you on your situation. "
            "The contacts below are people and offices with a duty to help."
        ),
        contacts=contacts,
        statutory_route={"citation": "s.6, PoSH Act 2013", "quote": quote},
        priced=False,
    )


# --------------------------------------------------------------------------------------------
_pass = _fail = 0


def check(name: str, got, want) -> None:
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}\n        got  {got!r}\n        want {want!r}")


DISTRESS = [
    "My manager touched me at the office party, what do I do?",
    "I was harassed by my supervisor and nobody did anything",
    "Will they fire me if I complain about harassment?",
    "I was transferred after I reported him to the IC",
    "I am scared to go to work",
    "I don't feel safe in my office",
    "I want to complain but I don't know how",
    "he threatened me when I said I would report it",
]

# Employer-side questions. These are the product's actual customers and must NOT be diverted —
# a compliance officer asking a policy question is not in distress.
ROUTINE = [
    "Do I need to constitute an Internal Committee?",
    "What is the penalty for not complying?",
    "When is the annual return due?",
    "How many members must the committee have?",
    "What are the duties of an employer under the Act?",
    "If an employee complains, how long does the inquiry take?",
    "Can the committee recommend a transfer during the inquiry?",
]


def _suite() -> int:
    for q in DISTRESS:
        check(f"routes: {q[:46]}", bool(detect(q)), True)
    for q in ROUTINE:
        check(f"leaves alone: {q[:42]}", bool(detect(q)), False)

    r = route("My manager touched me, what do I do?", "IN-KA-BLR")
    check("a referral is never priced", r.priced, False)
    check("it names SHe-Box", any(c["kind"] == "portal" for c in r.contacts), True)

    # The helpline, and the reason it comes first. The Sonnet Era plan proposes a freemium gate:
    # "3 free analyses, then upgrade". A quota that can count this route is a paywall in front of
    # a woman asking whether she can be sacked for complaining. The rule is asserted on the route
    # itself so it holds regardless of what a later billing layer believes.
    helpline = next((c for c in r.contacts if c["kind"] == "helpline"), None)
    check("it offers a human voice, not only a form", helpline is not None, True)
    check("the helpline is the NCW number", (helpline or {}).get("detail"), NCW_HELPLINE)
    check("the helpline carries its source",
          "mea.gov.in" in (helpline or {}).get("source", ""), True)
    check("a person comes before a portal", r.contacts[0]["kind"], "helpline")
    check("it names the District Officer when we hold one",
          any(c["kind"] == "district_officer" for c in r.contacts), True)
    check("the officer has a real email",
          "@" in next(c["detail"] for c in r.contacts if c["kind"] == "district_officer"), True)
    check("it quotes s.6 rather than paraphrasing",
          "employer himself" in (r.statutory_route or {}).get("quote", ""), True)
    check("it says it is not a person", "not a person" in r.message, True)
    check("it does not claim to advise", "cannot advise you" in r.message, True)

    # A district we do not hold must not silence the referral.
    r2 = route("I was harassed at work", "IN-XX-NOPE")
    check("unknown district still refers", r2.triggered, True)
    check("and still names SHe-Box", any(c["kind"] == "portal" for c in r2.contacts), True)

    check("a routine question yields nothing", route(ROUTINE[0], "IN-KA-BLR").triggered, False)
    check("empty input is safe", detect(""), "")

    print(f"\n  {_pass} passed, {_fail} failed")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(_suite())
