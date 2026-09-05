"""Which structural spans each obligation rests on — path + hash, never text.

T6 in docs/NEXT_MOVE_PLAN_2026_09_04.md. An obligation row today cites a provision
at section granularity ("s.2(85)"). The structural layer (structural_index) lets
it cite the exact limb ("s.2(85)(i)"), and carry that limb's content hash, so a
diligence reader can see precisely which sub-clause a finding stands on and check
it against the corpus by hash.

## Path and hash only — never the statutory text

s.52(1)(q)(ii) / the project rule "never emit bare statutory text" means this
module must not surface a chunk's TEXT into the pack. It surfaces the chunk's
PATH (a citation) and its sha256 (a fingerprint). Both are references, not
reproductions. The text stays in the corpus; the pack points at it.

## Declared, not guessed

The mapping is explicit and small. An obligation appears here only where the
precise sub-clause is unambiguous from the statute's structure — the small-company
limbs, the first-AGM proviso. Where the exact span is a matter of legal judgement
it is LEFT OUT (empty), not guessed: a wrong sub-clause citation is worse than a
section-level one. Extending it is a per-obligation decision with a fixture, the
same discipline as everywhere else. Every declared path is verified to exist in
the corpus by the self-test, so a typo cannot ship as a citation.
"""
from __future__ import annotations

from dataclasses import dataclass

from checker.structural_index import chunk_by_path

# obligation_id -> the structural paths its finding rests on. Declared only where
# the sub-clause is unambiguous; empty/absent means "cite at section level, we do
# not assert a finer span". See module docstring.
_CITES: dict[str, tuple[str, ...]] = {
    "CA13-S2-85-SMALL": ("2(85)(i)", "2(85)(ii)"),   # the capital and turnover limbs
    "CA13-S96-AGM": ("96(1)/proviso[1]",),           # the first-AGM nine-month limb
}


@dataclass(frozen=True)
class Citation:
    path: str
    sha256: str | None       # None if the path does not resolve in the corpus
    resolved: bool

    def __str__(self) -> str:
        if not self.resolved:
            return f"s.{self.path} (UNRESOLVED — not found in corpus)"
        return f"s.{self.path} [{(self.sha256 or '')[:19]}…]"


def structural_cites(obligation_id: str) -> list[Citation]:
    """The declared structural citations for an obligation, path + hash only.

    Returns [] for an obligation with no declared fine-grained span — the caller
    then cites at section level, as before. Each declared path is resolved against
    the corpus so the hash travels with the citation and an unresolved path is
    flagged rather than silently emitted.
    """
    out: list[Citation] = []
    for path in _CITES.get(obligation_id, ()):
        c = chunk_by_path(path)
        out.append(Citation(path, c.sha256 if c else None, c is not None))
    return out


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

    print("obligation_citations")

    # ── the small-company obligation cites both limbs, with hashes ──────────
    cites = structural_cites("CA13-S2-85-SMALL")
    paths = [c.path for c in cites]
    check(paths == ["2(85)(i)", "2(85)(ii)"],
          f"the small-company row cites both sub-clause limbs ({paths})")
    check(all(c.resolved and c.sha256 and c.sha256.startswith("sha256:") for c in cites),
          "each cited limb resolves and carries its content hash")

    # ── an obligation with no declared span returns [] (cite at section level) ─
    check(structural_cites("CA13-S137-AOC4") == [],
          "an obligation with no declared fine span returns no structural cites")
    check(structural_cites("NONEXISTENT-OBLIGATION") == [],
          "an unknown obligation id returns [], not an error")

    # ── EVERY declared path must resolve in the corpus (no shipped typo) ─────
    for oid, ps in _CITES.items():
        for p in ps:
            if chunk_by_path(p) is None:
                check(False, f"declared citation {p} for {oid} does not resolve in the corpus")
                break
        else:
            continue
        break
    else:
        check(True, "every declared citation path resolves in the corpus")

    # ── the citation string carries a reference, NOT statutory text ─────────
    s = str(cites[0])
    check("2(85)(i)" in s and "sha256" in s, f"citation renders path + hash ({s})")
    # A crude guard: the rendered citation must not contain the limb's own prose.
    limb_text = chunk_by_path("2(85)(i)").text
    check(limb_text[:30] not in s, "the citation does not reproduce the statutory text")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
