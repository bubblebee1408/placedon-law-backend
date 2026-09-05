"""Ground a model-proposed claim against a retrieved structural chunk.

T4 in docs/NEXT_MOVE_PLAN_2026_09_04.md — the "model proposes, the system
verifies" seam (MODEL_DEVELOPMENT_PLAN §3.5). A language model may propose a
claim about the law. Before that claim can appear anywhere, it must be ENTAILED
by a retrieved statutory span, or it is NOT_ESTABLISHED. This module does exactly
that and nothing more:

  1. SELECT — deterministically pick the structural chunk the claim is about,
     from the chunks structural_retrieve returned. No model is consulted in the
     selection; it is a path mention, then content-term overlap.
  2. VERIFY — hand (chunk.text, claim) to the existing E3→E6 cascade.
  3. DISPOSE — ESTABLISHED only if the cascade says supported; otherwise
     NOT_ESTABLISHED, distinguishing "contradicted" from "cascade abstained".

Why deterministic selection matters: if a model chose its own supporting span,
it could pick the one that happens to agree with it. The span is chosen by the
retrieval structure, then the claim must survive entailment against it. That is
strictly stronger than "the model cited something", which is all a hyperlink
check (Harvey) or output-traceability (Legora) guarantees — see the model plan §2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.cascade import verdict
from checker.structural_chunk import Chunk

ESTABLISHED = "ESTABLISHED"
NOT_ESTABLISHED = "NOT_ESTABLISHED"

# At least this many shared content terms before a chunk is even a candidate.
# Below it, "the claim is about no retrieved chunk" is the honest answer, and a
# forced near-miss would hand the cascade a premise the claim never referenced.
_MIN_OVERLAP = 2

# Legal filler that carries no subject matter; overlap on these is noise. Kept
# small and general — the same instinct as retrieve._RULE_MATCH_STOP.
_STOP = frozenset("""
shall company companies which such that this than from with under section clause
sub does more been being any all the and for not amount more other case within
means include includes referred person time made specify specified
""".split())


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower())} - _STOP


@dataclass(frozen=True)
class GroundResult:
    claim: str
    chosen_path: str | None      # the chunk the claim was grounded against
    chosen_sha: str | None
    supported: bool | None       # the cascade's raw verdict on (chunk, claim)
    status: str                  # ESTABLISHED | NOT_ESTABLISHED
    reason: str

    @property
    def established(self) -> bool:
        return self.status == ESTABLISHED


def select_chunk(claim: str, chunks: list[Chunk]) -> Chunk | None:
    """The chunk a claim is about, chosen deterministically. None if none fits.

    A claim that names a structural path outright (e.g. "under s.2(85)(i)") binds
    to that chunk. Otherwise the chunk with the most shared content terms wins,
    ties broken toward the shorter (more specific) chunk. Below `_MIN_OVERLAP`
    shared terms, nothing is selected.
    """
    if not chunks:
        return None
    # Explicit path mention wins, but with a boundary so "2(85)(i)" does not match
    # inside "2(85)(ii)", and the LONGEST matching path wins so the more specific
    # sub-clause beats its parent when both are named.
    mentioned = [c for c in chunks
                 if re.search(re.escape(c.path) + r"(?![\w(])", claim)]
    if mentioned:
        return max(mentioned, key=lambda c: len(c.path))
    claim_terms = _terms(claim)
    if not claim_terms:
        return None
    best: Chunk | None = None
    best_score = 0
    for c in chunks:
        score = len(claim_terms & _terms(c.text))
        if score > best_score or (score == best_score and score > 0
                                  and best is not None and len(c.text) < len(best.text)):
            best, best_score = c, score
    return best if best_score >= _MIN_OVERLAP else None


def ground(claim: str, chunks: list[Chunk]) -> GroundResult:
    """Select a chunk for the claim and verify entailment against it."""
    c = select_chunk(claim, chunks)
    if c is None:
        return GroundResult(claim, None, None, None, NOT_ESTABLISHED,
                            "no retrieved chunk is about this claim")
    v = verdict(c.text, claim)
    if v.supported is True:
        return GroundResult(claim, c.path, c.sha256, True, ESTABLISHED,
                            f"entailed by {c.path}")
    why = "contradicted by" if v.supported is False else "not confirmed by (cascade abstained on)"
    return GroundResult(claim, c.path, c.sha256, v.supported, NOT_ESTABLISHED,
                        f"{why} {c.path}")


def ground_query(claim: str, query: str, *, mode: str | None = None) -> GroundResult:
    """Retrieve the chunks for `query`, then ground `claim` against them.

    The full seam end to end: a model proposes `claim` about the provision named
    in `query`; we retrieve that provision's structural chunks under the normal
    admission discipline and require entailment. If retrieval abstains, there is
    nothing to ground against and the claim is NOT_ESTABLISHED.
    """
    from checker.structural_retrieve import structural_retrieve, MODE_MODEL
    chunks, _route, _withheld = structural_retrieve(query, mode=mode or MODE_MODEL)
    return ground(claim, chunks)


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

    print("ground_span")
    from checker.structural_index import chunks_for_section

    s2 = chunks_for_section("2")

    # ── SELECT: a capital-limit claim binds to 2(85)(i), not the turnover limb ─
    cap_claim = ("for a small company the paid-up share capital shall not exceed "
                 "the prescribed rupees amount")
    picked = select_chunk(cap_claim, s2)
    check(picked is not None and picked.path == "2(85)(i)",
          f"a capital claim selects 2(85)(i) ({picked.path if picked else None})")

    turn_claim = ("for a small company the turnover shall not exceed the prescribed "
                  "rupees amount for the preceding financial year")
    picked_t = select_chunk(turn_claim, s2)
    check(picked_t is not None and picked_t.path == "2(85)(ii)",
          f"a turnover claim selects 2(85)(ii) ({picked_t.path if picked_t else None})")

    # ── an explicit path mention binds outright ─────────────────────────────
    check(select_chunk("see 2(85)(ii) turnover", s2).path == "2(85)(ii)",
          "a claim naming a path binds to that chunk")

    # ── ESTABLISHED: an entailed paraphrase of (i) is grounded ──────────────
    good = ("paid-up share capital of a small company shall not exceed fifty lakh "
            "rupees or such higher amount as may be prescribed")
    r_good = ground(good, s2)
    check(r_good.chosen_path == "2(85)(i)", "the entailed claim grounds on 2(85)(i)")
    check(r_good.established and r_good.supported is True,
          f"an entailed paraphrase is ESTABLISHED ({r_good.status})")
    check(r_good.chosen_sha and r_good.chosen_sha.startswith("sha256:"),
          "an established result carries the grounding chunk's hash")

    # ── NOT_ESTABLISHED: a claim about nothing retrieved ────────────────────
    r_none = ground("the moon is composed principally of green cheese", s2)
    check(r_none.chosen_path is None and not r_none.established,
          "a claim about no retrieved chunk is NOT_ESTABLISHED")
    check("no retrieved chunk" in r_none.reason, "...and says so")

    # ── NOT_ESTABLISHED: selected a chunk, but the claim is not entailed ─────
    # The Act's (i) limb states fifty lakh / ten crore; "four crore" is the
    # PRESCRIBED rule (G.S.R. 700(E)), not the Act text, so a four-crore claim
    # grounded on the Act limb must not be ESTABLISHED.
    wrong = ("paid-up share capital of a small company shall not exceed "
             "rupees four crore under the Act")
    r_wrong = ground(wrong, s2)
    check(r_wrong.chosen_path == "2(85)(i)", "the four-crore claim still selects the capital limb")
    check(not r_wrong.established,
          f"a claim the Act text does not entail is NOT_ESTABLISHED ({r_wrong.status}, "
          f"supported={r_wrong.supported})")

    # ── empty chunk set grounds to nothing, never raises ────────────────────
    check(ground("anything at all here", []).status == NOT_ESTABLISHED,
          "grounding against no chunks is NOT_ESTABLISHED, not an error")

    # ── end-to-end via a citation query ─────────────────────────────────────
    from checker.retrieve import MODE_REVIEW
    r_q = ground_query(good, "s.2", mode=MODE_REVIEW)
    check(r_q.chosen_path == "2(85)(i)" and r_q.established,
          f"ground_query retrieves s.2 and grounds the claim ({r_q.status})")
    r_qa = ground_query(good, "rule 4")     # retrieval abstains -> nothing to ground
    check(not r_qa.established and r_qa.chosen_path is None,
          "a query retrieval abstains on grounds to nothing")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
