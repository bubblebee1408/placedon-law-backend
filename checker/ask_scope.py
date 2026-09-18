"""Which body of law a question is about, read from `checker/scope.py` alone.

Used by `checker/ask.py` to decide `out_of_scope` (contract.md §6 D2). Two errors are possible
and they are not equally bad:

- **A missed refusal** — a question about unheld law that is not detected — falls to the
  general path and comes back `partial`, saying what was and was not read. Safe, and weak.
- **A wrong refusal** of a question about law we HOLD tells the user we do not cover what we
  do. That is the worse error, and this module is built around not making it.

So a question is refused only on something that identifies the unheld body and nothing else:

- **Title signals** (strong): multi-word chunks of the body's `name` ("Insolvency and
  Bankruptcy Code"), capitalised acronyms of three or more letters in that name ("FDI",
  "SEBI", "ICDR"), and the register key's own acronym where the key is one token ("LLP",
  "FEMA", "IBC"). Acronyms match case-sensitively: "POSH" is a statute, "posh" is not.
- **Terms of art** (strong): words that name one unheld body and nothing we hold
  (`TERMS_OF_ART`: "CIRP", "resolution professional"), each proven absent from the held text.
- **Regulator signals** (weak): each regulator the register names ("RBI", "SEBI").

When several bodies are named, the title the user named decides, not register order: a
signal only one body declares ("ICDR"), then the body whose `covers` the question names
("buyback"), then register order. SEBI ICDR, SAST, PIT and Buyback share one key
(SEBI_OTHER) in the register, so a question naming any of them refuses with SEBI_OTHER's
text, which names all four.

Any signal that is also the HELD Act's own vocabulary is dropped: MCA regulates the Companies
Act, so "MCA" never refuses anything; and the NCLT and IBBI (`HELD_ACT_FORUMS`) are forums the
Companies Act itself constitutes or relies on, so they never refuse on their own either. The `covers` phrases are never a
signal — "board composition", "annual filings", "issue of capital" and "internal committee"
are the Companies Act's vocabulary as much as any declared body's — and serve only to choose
between bodies already named ("SEBI … insider trading" is SEBI's PIT regulations, not LODR).

**Held law named alongside.** A regulator named next to held law is not a refusal: the
Companies Act's own procedure runs through the NCLT ("NCLT approval … under section 66"). A
title named next to held law is a MIXED turn — the held part is read and the unheld part is
refused in the register's words (`ask.py`), because refusing the whole question would deny
what we hold. A bare section number does not count as held law next to a title: in "section 6
of FEMA" the section is FEMA's, and reading Companies Act s.6 for it would be a near-miss.

Only `scope.py` is read. A body it does not declare (the Income-tax Act) is never detected.

Run: PYTHONPATH=. python3 checker/ask_scope.py
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import scope
from checker.legal_retrieval import names_a_provision


@dataclass(frozen=True)
class Reading:
    """What the question says about scope."""
    body: "scope.Body | None"     # the unheld body the question is about, if any
    by_title: bool                # named by its own title or acronym, not only a regulator
    names_held: bool              # the question or the request also names held law

    @property
    def refuse(self) -> bool:
        """The whole question is about law we do not hold."""
        return self.body is not None and not self.names_held

    @property
    def mixed(self) -> bool:
        """Held law and an unheld body's title, in one question."""
        return self.body is not None and self.names_held


# Forums the HELD Act itself constitutes or relies on. The register lists them as another
# body's regulators (IBC2016: "IBBI / NCLT"), but a Companies Act question names them all
# the time -- capital reduction, schemes, oppression, winding up, conversion, valuations --
# and refusing those as insolvency questions denies what we hold. Founder decision,
# 18-09-2026 (runbook DEMO PLAN, D1), recorded HERE because scope.py is the authority and is
# not edited by this job. Each entry says what it rests on, and whether that is our corpus.
HELD_ACT_FORUMS: dict[str, str] = {
    "NCLT": ("constituted by Companies Act 2013 s.408 (corpus section_id 49303: 'a Tribunal "
             "to be known as the National Company Law Tribunal') -- our own corpus"),
    "IBBI": ("the authority registered valuers under Companies Act 2013 s.247 register with. "
             "That role is set by the Companies (Registered Valuers and Valuation) Rules, "
             "2017, which this engine does NOT hold: a founder decision, not a corpus fact"),
}

# Terms that name one unheld body and nothing we hold. A question using one is about that
# body even when it does not name it ("Who appoints the resolution professional?"). They
# rank with title signals. The test requires every one to be absent from the held Companies
# Act text, so none of them can be the held Act's own vocabulary; "liquidator" and
# "winding up" are therefore NOT here -- the Act uses both.
TERMS_OF_ART: dict[str, tuple[str, ...]] = {
    "IBC2016": ("CIRP", "corporate insolvency resolution process", "resolution professional",
                "insolvency commencement"),
}


def _norm(text: str) -> str:
    """The question as it is meant, for matching only -- never for display.

    NFKC folds full-width and compatibility forms ("ＳＥＢＩ" -> "SEBI"); a dotted acronym
    loses its dots ("R.B.I." -> "RBI"); runs of whitespace become one space. Homoglyphs
    from other scripts (a Cyrillic "Е" in "SЕBI") are NOT folded: that needs a confusables
    table this module does not hold.
    """
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"\b((?:[A-Za-z]\.){2,})", lambda m: m.group(1).replace(".", ""), t)
    return re.sub(r"\s+", " ", t).strip()


def _chunks(text: str) -> list[str]:
    """Multi-word phrases of a declared string, split at its own punctuation."""
    parts = (re.sub(r"\s+", " ", c).strip() for c in re.split(r"[,;()/\u2014]", text))
    return [c for c in parts if len(c.split()) >= 2 and not c[:1].isdigit()]


def _has(text: str, phrase: str, *, exact_case: bool) -> bool:
    """Whole-phrase match. 'comp' never matches 'company'."""
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])", text,
                     0 if exact_case else re.I) is not None


def _held() -> tuple:
    return tuple(b for b in scope.BODIES if b.status == scope.IN_CORPUS)


def _unheld() -> tuple:
    return tuple(b for b in scope.BODIES if b.status != scope.IN_CORPUS)


def _shared(signal: str) -> bool:
    """Is this string also the HELD Act's own vocabulary? Then it refuses nothing."""
    return signal in HELD_ACT_FORUMS or any(
        _has(f"{b.name} | {b.covers} | {b.regulator}", signal, exact_case=False)
        for b in _held())


def _signals(b) -> tuple[list[str], list[str]]:
    """(title signals, regulator signals) this body declares, minus the held Act's words.

    Title phrases match in any case; acronyms and single-word regulators match exactly.
    """
    titles = _chunks(b.name)
    titles += re.findall(r"\b[A-Z]{3,}\b", b.name)
    titles += TERMS_OF_ART.get(b.key, ())
    key = re.sub(r"\d+$", "", b.key)
    if re.fullmatch(r"[A-Z]{3,}", key):
        titles.append(key)
    regulators = [r.strip() for r in re.split(r"[,/]", b.regulator)
                  if len(r.strip()) >= 3 and any(ch.isalpha() for ch in r)]
    keep = lambda xs: list(dict.fromkeys(x for x in xs if not _shared(x)))
    return keep(titles), keep(regulators)


def _named_by(text: str, signals: list[str]) -> bool:
    return any(_has(text, s, exact_case=len(s.split()) == 1) for s in signals)


def _covers_named(text: str, b) -> bool:
    """Does the question name something this body declares it covers? Single words count
    here ("buyback"), because this only chooses between bodies already named -- it never
    refuses anything on its own."""
    items = (c.strip() for c in re.split(r"[,;()/\u2014]", b.covers))
    return any(_has(text, c, exact_case=False) for c in items
               if len(c) >= 3 and any(ch.isalpha() for ch in c))


def _own_title_named(text: str, b) -> bool:
    """Did the question name a title signal ONLY this body declares ("ICDR", not "SEBI")?"""
    others = {sig for o in _unheld() if o is not b for sig in _signals(o)[0]}
    return _named_by(text, [t for t in _signals(b)[0] if t not in others])


def _choose(text: str, candidates: list):
    """Which of several named bodies the question is about (D2, round 3).

    The title the user named beats register order: a body named by a signal no other body
    shares ("SEBI ICDR" -> SEBI_OTHER), then a body whose declared subject matter the
    question names ("SEBI … buyback" -> SEBI_OTHER), and only then register order ("SEBI"
    alone -> SEBI_LODR).
    """
    order = _unheld()
    return min(candidates, key=lambda b: (not _own_title_named(text, b),
                                          not _covers_named(text, b), order.index(b)))


def read(question: str, provisions: Sequence[str] = ()) -> Reading:
    """What the question says about scope. Pure; reads scope.py and the citation grammar."""
    text = _norm(question)
    by_title = [b for b in _unheld() if _named_by(text, _signals(b)[0])]
    by_regulator = [b for b in _unheld() if _named_by(text, _signals(b)[1])]
    held_title = any(_named_by(text, _chunks(b.name)) for b in _held())
    if by_title:
        # A bare section number next to a declared title is that body's section.
        names_held = bool(provisions) or held_title
        candidates = by_title
    else:
        names_held = bool(provisions) or held_title or names_a_provision(text)
        # A regulator named next to held law is the held Act's own procedure.
        candidates = [] if names_held else by_regulator
    if not candidates:
        return Reading(None, False, names_held)
    return Reading(_choose(text, candidates), bool(by_title), names_held)


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

    print("ask_scope")

    # ── the held Act's own vocabulary never refuses (verifier finding 1) ─────
    for q in ("Which MCA form do we file after the AGM under s.137?",
              "Do we need NCLT approval to reduce share capital under section 66?",
              "What are the board composition rules under s.149 for a private company?",
              "What are our annual filings under the Companies Act, 2013?",
              "Does a further issue of capital need a special resolution under s.62?",
              "Must our Internal Committee report under the s.177 vigil mechanism?"):
        r = read(q)
        check(not r.refuse and not r.mixed,
              f"a Companies Act question is not refused: {q[:52]!r} "
              f"({r.body.key if r.body else None})")
    check(all("MCA" not in _signals(b)[0] + _signals(b)[1] for b in _unheld()),
          "MCA regulates the held Act, so it is a signal for no unheld body")

    # ── the fixture questions, and the true positive ─────────────────────────
    for q in ("Is this company a small company?",
              "What does s.173 require, and does s.16 apply here?",
              "Is the law this document relies on still current?",
              "And the turnover limit?", "What does rule 2(1)(t) prescribe?",
              "Can the board approve these debentures and the related agreements?",
              "Can we use AI to draft the board minutes?",
              "How much TDS must we deduct under the Income-tax Act on this payment?"):
        check(read(q).body is None, f"no unheld body in {q[:48]!r}")
    r = read("What must we report to RBI for this share allotment to a foreign investor?")
    check(r.refuse and r.body.key == "FEMA1999",
          f"'report to RBI … foreign investor' is still refused as FEMA "
          f"({r.body.key if r.body else None})")

    # ── detection survives the way people write (verifier finding 6) ─────────
    for q, key in (("Is a FEMA FC-GPR filing due for this allotment?", "FEMA1999"),
                   ("Does the IBC moratorium stop this suit?", "IBC2016"),
                   ("What does \uff33\uff25\uff22\uff29 require us to disclose?", "SEBI_LODR"),
                   ("Do we report this to the R.B.I.?", "FEMA1999"),
                   ("Who files under the Limited  Liability   Partnership Act?", "LLP2008"),
                   ("What do the SEBI rules on insider trading require?", "SEBI_OTHER"),
                   ("Is stamp duty payable on this share transfer?", "STAMP"),
                   ("Does our POSH policy need an Internal Committee?", "POSH")):
        r = read(q)
        check(r.refuse and r.body.key == key,
              f"{q[:44]!r} -> {key} ({r.body.key if r.body else None})")

    # ── the Companies Act's own forums never refuse (round 3, item 1) ────────
    # The NCLT is constituted by the held Act (s.408); registered valuers under s.247
    # register with the IBBI. A question naming either is, first, a Companies Act question.
    for q in ("Do we need NCLT approval to reduce share capital?",
              "Do we need NCLT approval to reduce share capital under section 66?",
              "Must the NCLT sanction our scheme of amalgamation?",
              "Does the NCLT convene the creditors' meeting for a scheme of arrangement "
              "under s.230?",
              "Can minority shareholders petition the NCLT for oppression and mismanagement?",
              "Can minority shareholders petition the NCLT under s.241?",
              "Can the NCLT wind up the company on just and equitable grounds?",
              "Can the NCLT wind up the company under s.271(e)?",
              "Does converting from a public to a private company need NCLT approval?",
              "Does a public-to-private conversion under s.14 need NCLT approval?",
              "Must the valuer for this allotment be registered with IBBI?",
              "Must the valuer under s.247 be registered with the IBBI?"):
        r = read(q)
        check(r.body is None,
              f"not refused: {q[:58]!r} ({r.body.key if r.body else None})")
    check(all(f not in _signals(b)[0] + _signals(b)[1]
              for b in _unheld() for f in HELD_ACT_FORUMS),
          "NCLT and IBBI are a signal for no unheld body")
    from checker.section_index import section_by_number
    s408 = section_by_number("408") or {}
    check(str(s408.get("section_id")) == "49303"
          and "National Company Law Tribunal" in s408.get("content", ""),
          "...and the NCLT's entry rests on our own corpus: s.408 constitutes it")

    # ── ...while the IBC itself still refuses ────────────────────────────────
    for q in ("Does the IBC moratorium stop this suit?",
              "What does the Insolvency and Bankruptcy Code say about this?",
              "Is a CIRP pending against our supplier?",
              "Who appoints the resolution professional?",
              "What is the insolvency commencement date for this company?",
              "Can the NCLT admit a CIRP application against us?"):
        r = read(q)
        check(r.refuse and r.body.key == "IBC2016",
              f"refused as the IBC: {q[:52]!r} ({r.body.key if r.body else None})")
    import glob, json as _json
    corpus = " ".join(_json.load(open(f)).get("content", "")
                      for f in glob.glob(str(Path(__file__).resolve().parent.parent
                                             / "corpus/companies_act/[0-9]*.json")))
    check(corpus and all(not _has(corpus, t, exact_case=len(t.split()) == 1)
                         for terms in TERMS_OF_ART.values() for t in terms),
          "no IBC term of art occurs anywhere in the held Companies Act text -- so none "
          "can be the held Act's vocabulary")
    check(all(scope.body(k).status != scope.IN_CORPUS for k in TERMS_OF_ART),
          "terms of art are declared only for bodies we do not hold")

    # ── a title the user names beats register order (round 3, item 3) ────────
    r = read("Does s.62 and SEBI ICDR apply to our rights issue?")
    check(r.refuse and r.body.key == "SEBI_OTHER",
          f"'SEBI ICDR' is refused as the body whose title names ICDR, not as LODR "
          f"({r.body.key if r.body else None})")
    r = read("Does s.62 and SEBI ICDR apply to our rights issue?", provisions=["s.62"])
    check(r.mixed and r.body.key == "SEBI_OTHER", "...and so is its mixed form")
    for q, key in (("Do we need SEBI approval for a buyback?", "SEBI_OTHER"),
                   ("What do the SAST regulations require of an acquirer?", "SEBI_OTHER"),
                   ("What does SEBI require us to disclose continuously?", "SEBI_LODR")):
        r = read(q)
        check(r.refuse and r.body.key == key,
              f"{q[:46]!r} -> {key} ({r.body.key if r.body else None})")

    # ── mixed: a title named next to held law ────────────────────────────────
    r = read("Is our LLP a small company?", provisions=["s.2(85)"])
    check(r.mixed and r.body.key == "LLP2008",
          "an LLP question with a Companies Act provision named is mixed, not answered")
    r = read("Does the Companies Act or the Competition Act govern this merger?")
    check(r.mixed and r.body.key == "COMP2002", "...as is one naming both Acts by title")
    r = read("What does section 6 of FEMA say about capital account transactions?")
    check(r.refuse and r.body.key == "FEMA1999",
          "a bare section number next to a declared title is that body's section, not "
          "held law -- refused, not read against Companies Act s.6")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
