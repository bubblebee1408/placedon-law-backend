"""Independent corroboration of prior wording, using the amending Act as witness.

The problem this solves is recorded in `docs/RETRACTIONS.md`. We once reported
"119/119 EXACT" for point-in-time reconstruction against what turned out to be the
current consolidation, and later "43/43 prior wordings found in the PDF" — which was
circular, because the footnotes quoting those wordings are *in that same PDF*. Both
were retracted. Every prior wording we hold still comes from one publisher's
footnote, so a defect in India Code's own footnote is invisible to us.

The witness that breaks the circle is the **amending Act**. When the Companies
(Amendment) Act 2017 says

    in clause (p), for the words "annual evaluation has been made by the Board of
    its own performance and that of its committees and individual directors", the
    words "..." shall be substituted

it names the pre-amendment text in a *different document by a different publisher*.
If India Code's footnote and the amending instrument agree, the wording is
corroborated. If they disagree, one of them carries a defect and we have found it.

**What a PASS here does and does not establish.** It establishes that the prior
wording we extracted for one amended span matches the instrument that made the
change. It does *not* establish that a whole reconstructed section is correct: a
section may carry spans we never parsed, un-footnoted editorial changes, or
commencement dates that differ from the w.e.f. we recorded. Section-level
reconstruction remains UNVERIFIED. This module raises the evidence for one
component of it, and the distinction is the whole reason the earlier claims were
retracted.

Source: Indian Kanoon, under its attribution terms. Fetches go through
`checker.robots`, which enforces the ~9,300-document denylist and fails closed.
"""
from __future__ import annotations

import html
import json
import re
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path

from checker.robots import Fetcher

ORIGIN = "https://indiankanoon.org"
ATTRIBUTION = "Source: Indian Kanoon (indiankanoon.org), retrieved under its terms of use."
CACHE = Path("corpus/corroboration")

# Verdicts
EXACT = "EXACT"                  # instrument quotes our wording character-for-character
NORMALISED = "NORMALISED"        # agrees after quote/space/case normalisation
CONFLICT = "CONFLICT"            # instrument found, and it names different words
NO_WITNESS = "NO_WITNESS"        # no amending-Act text located; proves nothing
UNREACHABLE = "UNREACHABLE"      # network or robots refusal; proves nothing

CORROBORATING = (EXACT, NORMALISED)


@dataclass(frozen=True)
class Claim:
    """What our corpus asserts: these words stood here until this instrument."""

    section: str
    prior_wording: str
    instrument: str | None
    wef: date | None


@dataclass
class Result:
    claim_section: str
    verdict: str
    prior_wording: str
    witness_quote: str | None = None
    witness_title: str | None = None
    witness_url: str | None = None
    note: str = ""
    fetched_at: str = ""

    @property
    def corroborated(self) -> bool:
        return self.verdict in CORROBORATING


def normalise(s: str) -> str:
    """Collapse the differences that are typography, not law.

    Curly vs straight quotes, non-breaking spaces, and runs of whitespace differ
    between publishers for reasons that have nothing to do with the enacted text.
    Case is folded too: statutory quotation is not reliably case-consistent across
    renderings. What is *not* normalised is word choice, order, or punctuation
    that separates clauses — those are the differences worth catching.
    """
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip().strip('"\'').lower()


def _visible_text(page_html: str) -> str:
    txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page_html, flags=re.S | re.I)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    return re.sub(r"[ \t\xa0]+", " ", txt)


# "for the words \"X\", the words \"Y\" shall be substituted" and its many variants.
_SUBST = re.compile(
    r"for\s+the\s+(?:words?|figures?|brackets?|letters?|expression)"
    r"(?:\s*(?:,|and)\s*(?:words?|figures?|brackets?|letters?))*\s*"
    r"[\"“]([^\"”]{4,600})[\"”]",
    re.I | re.S,
)


# Indian Kanoon titles the instrument "The Companies (Amendment) Act, 2017" — the
# closing parenthesis sits between the two words, so `amendment\s+act` never fires.
# That typo silently filtered out every witness and reported 0/12 corroborated,
# which reads exactly like a failed verification rather than a broken filter.
_IS_AMENDING_ACT = re.compile(r"amendment\W{0,3}act", re.I)


def extract_substituted_quotes(text: str) -> list[str]:
    """Every phrase an instrument declares it is replacing."""
    return [m.group(1) for m in _SUBST.finditer(text)]


class Corroborator:
    def __init__(self, *, fetcher: Fetcher | None = None, cache: Path = CACHE) -> None:
        self.f = fetcher or Fetcher(ORIGIN)
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)

    # ---- fetching -------------------------------------------------------
    def _cached_get(self, url: str) -> tuple[int, str]:
        key = re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:]
        p = self.cache / f"{key}.html"
        if p.exists():
            return 200, p.read_text(encoding="utf-8")
        st, body = self.f.get(url)
        if st == 200:
            p.write_text(body, encoding="utf-8")
        return st, body

    def search(self, phrase: str) -> tuple[int, list[tuple[str, str]]]:
        """Exact-phrase search. Returns (status, [(title, url)])."""
        q = urllib.parse.quote(f'"{phrase}"')
        st, body = self._cached_get(f"{ORIGIN}/search/?formInput={q}")
        if st != 200:
            return st, []
        hits: list[tuple[str, str]] = []
        for m in re.finditer(r'<a href="(/doc/\d+/[^"]*)"[^>]*>(.*?)</a>', body, re.S):
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
            if title:
                hits.append((title, ORIGIN + m.group(1).split("?")[0]))
        return st, hits

    # ---- the test -------------------------------------------------------
    def corroborate(self, claim: Claim) -> Result:
        """Look for an amending instrument that names this wording as replaced."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # Search on a prefix: instruments and consolidations sometimes differ in
        # trailing punctuation, and an over-long exact phrase returns nothing at all.
        probe = " ".join(claim.prior_wording.split()[:18])
        st, hits = self.search(probe)
        if st != 200:
            return Result(claim.section, UNREACHABLE, claim.prior_wording,
                          note=f"search HTTP {st}", fetched_at=now)

        # Only amending Acts are witnesses. The consolidated Act and the Rules
        # restate the current text and cannot testify about what preceded it.
        witnesses = [(t, u) for t, u in hits if _IS_AMENDING_ACT.search(t)]
        if not witnesses:
            return Result(claim.section, NO_WITNESS, claim.prior_wording,
                          note=f"{len(hits)} hits, none an amending Act", fetched_at=now)

        target = normalise(claim.prior_wording)
        best: Result | None = None

        for title, url in witnesses[:4]:
            st, page = self._cached_get(url)
            if st != 200:
                continue
            text = _visible_text(page)
            for quote in extract_substituted_quotes(text):
                nq = normalise(quote)
                if nq == target:
                    verdict = EXACT if quote.strip() == claim.prior_wording.strip() else NORMALISED
                    return Result(claim.section, verdict, claim.prior_wording,
                                  witness_quote=quote, witness_title=title,
                                  witness_url=url, fetched_at=now)
                # Containment either way is still a conflict, but a more
                # informative one than an unrelated quote: it usually means one
                # publisher clipped the span differently.
                if best is None and (nq in target or target in nq):
                    best = Result(claim.section, CONFLICT, claim.prior_wording,
                                  witness_quote=quote, witness_title=title,
                                  witness_url=url,
                                  note="witness names an overlapping but different span",
                                  fetched_at=now)

        if best:
            return best
        return Result(claim.section, NO_WITNESS, claim.prior_wording,
                      witness_title=witnesses[0][0], witness_url=witnesses[0][1],
                      note="amending Act found but it names no matching substitution",
                      fetched_at=now)


def claims_from_corpus(limit: int | None = None, min_words: int = 6) -> list[Claim]:
    """Prior-wording claims our corpus makes that are specific enough to test.

    Short phrases are excluded, not because they are wrong but because they are
    untestable: "fifty thousand rupees" appears across dozens of statutes, so a
    search hit would corroborate nothing.
    """
    from checker.amendment import parse_footnote
    from checker.as_of import prior_wording

    out: list[Claim] = []
    seen: set[str] = set()
    for p in sorted(Path("corpus/companies_act").glob("*.json")):
        if p.stem.startswith("_"):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for a in parse_footnote(rec.get("footnote") or ""):
            pw = prior_wording(a)
            if not pw or a.wef_implausible:
                continue
            if len(pw.split()) < min_words:
                continue
            key = normalise(pw)
            if key in seen:
                continue
            seen.add(key)
            out.append(Claim(section=rec.get("number") or p.stem,
                             prior_wording=pw, instrument=a.instrument, wef=a.wef))
            if limit and len(out) >= limit:
                return out
    return out


def report(results: list[Result]) -> str:
    n = len(results)
    corr = sum(r.corroborated for r in results)
    conflict = sum(r.verdict == CONFLICT for r in results)
    silent = sum(r.verdict in (NO_WITNESS, UNREACHABLE) for r in results)
    lines = [
        "INDEPENDENT CORROBORATION OF PRIOR WORDING",
        f"  corroborated by the amending instrument : {corr}/{n}",
        f"  conflicts (a defect in one source)      : {conflict}",
        f"  no witness reachable (proves nothing)   : {silent}",
        "",
        "  Scope: this corroborates the prior wording of individual amended spans.",
        "  Section-level point-in-time reconstruction remains UNVERIFIED.",
        f"  {ATTRIBUTION}",
    ]
    return "\n".join(lines)


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

    print("corroborate")

    check(normalise('  "The  Board’s report" ') == "the board's report",
          "normalisation folds quotes, spacing and case")
    check(normalise("a-b") == normalise("a–b"), "en dash and hyphen agree")
    check(normalise("Board") != normalise("Boards"),
          "normalisation does not erase a word difference")

    # The real sentence from the Companies (Amendment) Act, 2017, s.36(b)(ii).
    real = ('in clause (p), for the words "annual evaluation has been made by the '
            'Board of its own performance and that of its committees and individual '
            'directors", the words "annual evaluation of the performance of the '
            'Board, its Committees and of individual directors has been made" shall '
            'be substituted;')
    q = extract_substituted_quotes(real)
    check(len(q) == 1, f"one substituted phrase extracted from the real clause ({len(q)})")
    check(q and q[0].startswith("annual evaluation has been made by the Board"),
          "...and it is the PRIOR wording, not the replacement")
    check(q and q[0].endswith("individual directors"),
          "...captured to the end of the span")

    check(extract_substituted_quotes(
        'for the figures and letters "2013", the figures "2017" shall be substituted') ,
        "the figures/letters variant is recognised")

    # Regression: the real Indian Kanoon title puts a ")" between the two words.
    for title in ("Section 9 in The Companies (Amendment) Act, 2017",
                  "The Companies (Amendment) Act, 2017",
                  "The Companies Amendment Act, 2019"):
        check(bool(_IS_AMENDING_ACT.search(title)), f"recognised as a witness: {title!r}")
    check(not _IS_AMENDING_ACT.search("Section 134 in The Companies Act, 2013"),
          "the consolidated Act is not treated as a witness to its own history")
    check(not extract_substituted_quotes("the following section shall be inserted"),
          "an insertion offers no prior wording and yields none")

    # Verdict semantics: silence must never read as success.
    r = Result("s1", NO_WITNESS, "x")
    check(not r.corroborated, "NO_WITNESS is not corroboration")
    check(not Result("s1", UNREACHABLE, "x").corroborated,
          "UNREACHABLE is not corroboration")
    check(not Result("s1", CONFLICT, "x").corroborated, "CONFLICT is not corroboration")
    check(Result("s1", EXACT, "x").corroborated and Result("s1", NORMALISED, "x").corroborated,
          "EXACT and NORMALISED are corroboration")

    cl = claims_from_corpus(limit=40)
    check(len(cl) >= 10, f"the corpus yields testable claims ({len(cl)})")
    check(all(len(c.prior_wording.split()) >= 6 for c in cl),
          "every claim is specific enough to search")

    txt = report([Result("s1", EXACT, "x"), Result("s2", NO_WITNESS, "y")])
    check("1/2" in txt, "the report counts only corroborated claims")
    check("UNVERIFIED" in txt,
          "the report restates that section-level reconstruction is unverified")
    check("indiankanoon.org" in txt, "the report carries the required attribution")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
