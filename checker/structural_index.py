"""Path-addressable access to the statute's structural chunks.

T2 in docs/NEXT_MOVE_PLAN_2026_09_04.md. `structural_chunk.chunk_section` turns
one section's text into chunks; this layer sits over the corpus so a caller can
ask for "2(85)(i)" or "every chunk of s.96" without knowing where the section
JSON lives or how to clean its HTML.

It is the addressing layer the retriever (T3) and the E-gate wiring (T4) build on:
a structural citation like "s.2(85)(i)" resolves to exactly one chunk, with its
verbatim text, char span and content hash.

## Degrade, never raise

A section whose HTML is malformed must still be representable — `chunk_section`
already falls back to a single chapeau chunk rather than returning nothing, and
this layer never raises for a resolvable section number. A section number the
corpus does not carry returns an empty list (chunks) or None (single chunk),
which the caller treats as "nothing to ground against", not as an error.

## Caching

Chunking is pure and the corpus is immutable within a run, so results are cached
per section number. The cache is keyed by the section's stored sha256 so that if
the corpus file changes the cache does not serve stale structure.
"""
from __future__ import annotations

import re
from functools import lru_cache

from checker.section_index import section_by_number
from checker.structural_chunk import (Chunk, chunk_section, clean_html)

# The leading section number of a structural path: "2(85)(i)" -> "2",
# "96(1)/proviso[1]" -> "96", "5/chapeau" -> "5".
_PATH_SECTION = re.compile(r"^(\d+[A-Z]?)")


def section_of_path(path: str) -> str | None:
    """The section number a structural path belongs to, or None if unparseable."""
    m = _PATH_SECTION.match(path.strip())
    return m.group(1) if m else None


@lru_cache(maxsize=1024)
def _chunks_cached(section: str, _corpus_sha: str) -> tuple[Chunk, ...]:
    d = section_by_number(section)
    if not d:
        return ()
    return tuple(chunk_section(section, clean_html(d.get("content", ""))))


def chunks_for_section(section: str) -> list[Chunk]:
    """Every structural chunk of a section, in document order.

    Empty list if the corpus does not carry the section. Cache-keyed by the
    section's stored sha256 so a corpus edit invalidates it.
    """
    d = section_by_number(section)
    if not d:
        return []
    return list(_chunks_cached(section, d.get("sha256", "")))


def chunk_by_path(path: str) -> Chunk | None:
    """The single chunk a structural path addresses, or None if not present."""
    section = section_of_path(path)
    if section is None:
        return None
    for c in chunks_for_section(section):
        if c.path == path:
            return c
    return None


def resolve(section_or_path: str) -> list[Chunk]:
    """Chunks for a bare section number, or the single chunk for a full path.

    "96" -> all of s.96's chunks; "2(85)(i)" -> just that limb (as a 1-list);
    an unknown section or path -> empty list.
    """
    if "(" in section_or_path or "/" in section_or_path:
        c = chunk_by_path(section_or_path)
        return [c] if c else []
    return chunks_for_section(section_or_path)


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

    print("structural_index")

    # ── path parsing ────────────────────────────────────────────────────────
    check(section_of_path("2(85)(i)") == "2", "section_of_path reads the leading number")
    check(section_of_path("96(1)/proviso[1]") == "96", "...through a proviso path")
    check(section_of_path("135A(2)") == "135A", "...including a lettered section suffix")
    check(section_of_path("nonsense") is None, "an unparseable path yields None")

    # ── every obligation's governing section resolves to >= its sub-section ──
    OB_SECTIONS = ["96", "173", "149", "137", "92", "135", "2"]
    for sec in OB_SECTIONS:
        cs = chunks_for_section(sec)
        if not cs:
            check(False, f"s.{sec} resolves to at least one chunk")
            break
    else:
        check(True, "every obligation's governing section resolves to chunks")

    # ── s.2(85) resolves to both limbs, addressably ─────────────────────────
    cap = chunk_by_path("2(85)(i)")
    turn = chunk_by_path("2(85)(ii)")
    check(cap is not None and "capital" in cap.text.lower(),
          f"2(85)(i) addresses the capital limb ({cap.text[:50] if cap else 'MISSING'}…)")
    check(turn is not None and "turnover" in turn.text.lower(),
          "2(85)(ii) addresses the turnover limb")
    check(cap and turn and cap.sha256 != turn.sha256,
          "the two limbs are distinct chunks with distinct hashes")

    # ── s.96 has its provisos addressable ───────────────────────────────────
    provs = [c for c in chunks_for_section("96") if c.kind == "PROVISO"]
    check(len(provs) >= 1, f"s.96 exposes its proviso(s) as chunks ({len(provs)})")
    first_proviso = chunk_by_path("96(1)/proviso[1]")
    check(first_proviso is not None, "the first proviso of s.96(1) is path-addressable")

    # ── resolve() dual behaviour ────────────────────────────────────────────
    check(len(resolve("96")) == len(chunks_for_section("96")) > 1,
          "resolve('96') returns the whole section")
    check(len(resolve("2(85)(i)")) == 1, "resolve('2(85)(i)') returns exactly one chunk")
    check(resolve("9999") == [], "resolve of an absent section is empty, not an error")
    check(chunk_by_path("2(9999)(z)") is None, "an absent path returns None, not an error")

    # ── caching returns equal content on repeat ─────────────────────────────
    a = chunks_for_section("96")
    b = chunks_for_section("96")
    check([c.path for c in a] == [c.path for c in b], "repeat resolution is stable")

    # ── spans reproduce against the actual cleaned corpus text ──────────────
    d = section_by_number("96")
    cleaned = clean_html(d.get("content", ""))
    import re as _re
    for c in chunks_for_section("96"):
        span = _re.sub(r"\s+", " ", cleaned[c.start:c.end]).strip()
        if span != c.text:
            check(False, f"corpus span mismatch for {c.path}")
            break
    else:
        check(True, "chunk spans reproduce their text against the real corpus")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
