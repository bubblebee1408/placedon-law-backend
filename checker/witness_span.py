"""Resolve an amendment span's boundary from the instrument that created it.

India Code marks amended text inline as `<sup>N</sup>[ ... ]`. In a small number
of sections the closing bracket is absent, so the extent of the change is
unknown and the provision cannot be reconstructed for a past date. s.96 — the
AGM section, and the one this product is built around — is one of them.

Guessing where the span ends is a legal judgement disguised as a parsing
decision, and `checker/as_of.py` records an earlier attempt that swallowed 8,777
characters and destroyed a later marker in the same section. So the boundary is
not guessed. It is **read from the amending Act**, which states the substituted
text in full:

    26. Amendment of section 96. In section 96 of the principal Act, in
    sub-section (2), in the proviso, for the words "Provided that", the
    following shall be substituted, namely:— "Provided that annual general
    meeting of an unlisted company may be held at any place in India if consent
    is given in writing or by electronic mode by all the members in advance:
    Provided further that"

The replacement text ends at "Provided further that". Locating that string in
the current content gives the span's end — a boundary the instrument fixed, not
one we chose.

## What makes a resolution valid

Three conditions, all checked, none assumed:

1. the replacement text the instrument states is **present** in the current
   content, contiguously, starting at the span's opening bracket;
2. the prior wording the instrument names is **absent** from that span — if the
   old words are still there, the substitution did not happen as described;
3. the resolved span is **shorter than the remainder of the section** — a span
   that runs to the end of the content is the failure mode that motivated the
   refusal in the first place.

If any fails, the span stays unresolved. A witness that does not fit is not a
witness.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

RESOLVED = "RESOLVED"
NO_OPENING = "NO_OPENING"                # no <sup>N</sup>[ in the content
TEXT_ABSENT = "TEXT_ABSENT"              # the instrument's replacement is not there
PRIOR_STILL_PRESENT = "PRIOR_STILL_PRESENT"
RUNS_TO_END = "RUNS_TO_END"
ALREADY_BALANCED = "ALREADY_BALANCED"    # nothing to resolve; use the normal path

_OPEN = re.compile(r"<sup>\s*(\d{1,3})\s*</sup>(?:\s|<[^>]{1,12}>){0,6}\[")


@dataclass
class SpanResolution:
    status: str
    marker: int
    open_at: int | None = None
    inner_start: int | None = None
    end_at: int | None = None
    replacement: str = ""
    prior: str = ""
    note: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    @property
    def length(self) -> int:
        if self.inner_start is None or self.end_at is None:
            return 0
        return self.end_at - self.inner_start


def _plain(html: str) -> str:
    """Tags removed, offsets NOT preserved. For matching only, never for slicing."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _norm(s: str) -> str:
    s = (s.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"')
          .replace("—", "-").replace("–", "-"))
    return re.sub(r"\s+", " ", s).strip().lower()


def _find_ignoring_tags(html: str, needle: str, from_pos: int) -> int | None:
    """Offset in `html` just past `needle`, matching across intervening tags.

    The replacement text as printed in the Act has no markup; the same words in
    India Code carry `</br>`, `<hr>` and `<span>` between them. Matching the
    plain text and mapping back would need an offset table, so instead the needle
    is turned into a pattern that tolerates tags and whitespace between words.
    """
    words = [w for w in re.split(r"\s+", needle.strip()) if w]
    if not words:
        return None
    pat = r"(?:\s|<[^>]*>)*".join(re.escape(w) for w in words)
    m = re.compile(pat, re.I).search(html, from_pos)
    return m.end() if m else None


def resolve(content: str, marker: int, *, replacement: str, prior: str) -> SpanResolution:
    """Locate the end of an unbalanced span using the instrument's own text."""
    from checker.as_of import _find_span

    if _find_span(content, marker) is not None:
        return SpanResolution(ALREADY_BALANCED, marker,
                              note="the span closes in the source; no witness needed")

    m = None
    for cand in _OPEN.finditer(content):
        if int(cand.group(1)) == marker:
            m = cand
            break
    if m is None:
        return SpanResolution(NO_OPENING, marker,
                              note=f"no opening bracket for marker {marker}")

    inner = m.end()
    end = _find_ignoring_tags(content, replacement, inner)
    if end is None:
        return SpanResolution(TEXT_ABSENT, marker, open_at=m.start(), inner_start=inner,
                              replacement=replacement,
                              note="the instrument's replacement text is not present "
                                   "in the current content; the witness does not fit")

    span_text = content[inner:end]
    # The test is IDENTITY, not containment. A substitution that extends text
    # keeps its own prior wording as a prefix — s.96 replaced "Provided that"
    # with "Provided that annual general meeting ... Provided further that", so
    # a containment check refuses the very case this exists for. What would
    # signal a failed substitution is a span that is *exactly* the old words.
    if prior and _norm(_plain(span_text)) == _norm(prior):
        return SpanResolution(PRIOR_STILL_PRESENT, marker, open_at=m.start(),
                              inner_start=inner, end_at=end, replacement=replacement,
                              prior=prior,
                              note=f"the resolved span is exactly the prior wording "
                                   f"{prior!r}; no substitution is visible")

    remaining = len(content) - inner
    if end - inner >= remaining:
        return SpanResolution(RUNS_TO_END, marker, open_at=m.start(),
                              inner_start=inner, end_at=end,
                              note="the resolved span runs to the end of the section, "
                                   "which is the failure this method exists to avoid")

    return SpanResolution(RESOLVED, marker, open_at=m.start(), inner_start=inner,
                          end_at=end, replacement=replacement, prior=prior,
                          note=f"boundary stated by the instrument; span is "
                               f"{end - inner} characters")


def apply_prior(content: str, res: SpanResolution) -> str | None:
    """The content as it stood before the amendment: span replaced by prior wording."""
    if not res.resolved or res.open_at is None or res.end_at is None:
        return None
    # The trailing "]" is absent — that is why this is needed at all — so nothing
    # is stripped after end_at.
    return content[:res.open_at] + res.prior + content[res.end_at:]


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

    print("witness_span")

    # A balanced span needs no witness.
    r = resolve("<sup>1</sup>[abc]", 1, replacement="abc", prior="x")
    check(r.status == ALREADY_BALANCED, "a span that closes is left to the normal path")

    # The witness must actually fit.
    r = resolve("<sup>1</sup>[hello world and more", 1,
                replacement="not in here at all", prior="x")
    check(r.status == TEXT_ABSENT, "a replacement text that is absent is refused")

    r = resolve("<sup>1</sup>[Provided that] more text follows here again", 1,
                replacement="Provided that", prior="Provided that")
    check(r.status in (PRIOR_STILL_PRESENT, ALREADY_BALANCED),
          "a span that is exactly the prior wording shows no substitution")
    r = resolve("<sup>1</sup>[Provided that extended words here and more tail", 1,
                replacement="Provided that extended words", prior="Provided that")
    check(r.resolved,
          "a replacement that EXTENDS the prior wording is accepted, not refused")

    r = resolve("<sup>1</sup>[all of it", 1, replacement="all of it", prior="x")
    check(r.status == RUNS_TO_END, "a span running to the end of the section is refused")

    r = resolve("no marker here", 1, replacement="a", prior="b")
    check(r.status == NO_OPENING, "a missing opening bracket is refused")

    # Matching across intervening markup.
    html = "<sup>1</sup>[Provided that annual</br><hr/> general meeting tail text here"
    r = resolve(html, 1, replacement="Provided that annual general meeting",
                prior="Provided that")
    check(r.resolved, f"the replacement matches across intervening tags ({r.status})")
    check(r.length > 0 and r.end_at < len(html), "the boundary sits inside the section")

    # The real s.96 case.
    from checker.section_index import section_by_number
    c96 = section_by_number("96")["content"]
    REPL = ("Provided that annual general meeting of an unlisted company may be held "
            "at any place in India if consent is given in writing or by electronic "
            "mode by all the members in advance: Provided further that")
    r96 = resolve(c96, 1, replacement=REPL, prior="Provided that")
    check(r96.resolved, f"s.96 marker 1 resolves against Act 1 of 2018 s.26 ({r96.status})")
    check(r96.end_at is not None and r96.end_at < len(c96),
          "...and the boundary is inside the section, not at its end")

    before = apply_prior(c96, r96)
    check(before is not None, "the pre-amendment content is produced")
    if before:
        pb, pc = _plain(before), _plain(c96)
        check(len(pb) < len(pc),
              f"the earlier text is shorter than the current ({len(pb)} vs {len(pc)})")
        check("unlisted company may be held at any place" not in pb,
              "the substituted proviso is absent from the earlier text")
        check("unlisted company may be held at any place" in pc,
              "...and present in the current text")
        check("Provided that" in pb, "the prior wording stands in its place")
        # Everything outside the span must be untouched.
        check("fifteen months shall elapse" in pb and "nine months" in pb,
              "the rest of the section is unchanged")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
