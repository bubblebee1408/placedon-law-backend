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
- **Regulator signals** (weak): each regulator the register names ("RBI", "NCLT").

Any signal that also appears among a HELD body's own declared strings is dropped: MCA
regulates the Companies Act, so "MCA" never refuses anything. The `covers` phrases are never a
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
    """Is this string also a HELD body's own vocabulary? Then it refuses nothing."""
    return any(_has(f"{b.name} | {b.covers} | {b.regulator}", signal, exact_case=False)
               for b in _held())


def _signals(b) -> tuple[list[str], list[str]]:
    """(title signals, regulator signals) this body declares, minus the held Act's words.

    Title phrases match in any case; acronyms and single-word regulators match exactly.
    """
    titles = _chunks(b.name)
    titles += re.findall(r"\b[A-Z]{3,}\b", b.name)
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
    return any(_has(text, c, exact_case=False) for c in _chunks(b.covers))


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
    # Several bodies named: the one whose declared subject matter the question also
    # names, else the first in register order.
    chosen = next((b for b in candidates if _covers_named(text, b)), candidates[0])
    return Reading(chosen, bool(by_title), names_held)


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
