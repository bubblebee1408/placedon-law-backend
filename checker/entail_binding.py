"""E4: check that a claim binds its quantity to the obligation the source does.

The error taxonomy split E3's failures into two shapes that need opposite fixes:

    wrong_binding       n=45   20 false accepts    4 false rejects
    paraphrase          n=17    0 false accepts   12 false rejects
    dropped_qualifier   n= 9    4 false accepts    0 false rejects

E3 checks whether the *tokens* of a claim appear in the premise. Every rebound
claim passes that test, because the quantity is genuinely in the provision — it
simply governs something else. "Section 103 sets fifteen members as the quorum
for a private company" contains no invented word; fifteen members is a real
quorum in s.103, for public companies with 1,000-5,000 members.

So this does not check tokens. It extracts **(quantity → obligation) bindings**
from the source and from the claim, and asks whether the claim's pairing is one
the source actually makes.

## Why this is deterministic and stays that way

The binding is recoverable from sentence structure — a quantity governs the
clause it sits in, bounded by the clause separators statutory drafting uses
(semicolons, lettered sub-clauses, "in the case of"). No model is needed to see
that "five members personally present if the number of members ... is not more
than one thousand" binds *five members* to *not more than one thousand*, and
"fifteen members ... more than one thousand but up to five thousand" binds
*fifteen* to a different band.

## Measured, including the part that did not work

On the strict set (n=71, 24 entailed / 47 not, majority class 0.66):

    strategy                        acc     F1    false-acc  false-rej
    always NOT_ENTAILED            0.66   0.00       0          24
    E3 alone                       0.44   0.29      24          16
    E4 alone, abstain -> refuse    0.63   0.28       7          19
    E4 then E3 (cascade)           0.62   0.37      11          16
    E4 AND E3 (both must accept)   0.65   0.36       8          17

On the bucket it targets, it does what it was built to do: wrong_binding
accuracy 0.47 -> 0.81, false accepts 20 -> 4.

**No configuration beats the majority baseline on accuracy.** That is worth
stating plainly rather than burying, and so is the reason: "always
NOT_ENTAILED" scores 0.66 accuracy with **F1 0.00**. It accepts nothing, ever,
and cannot be a product. On a set that is 66% negative, accuracy rewards refusal.
The informative pair is (false accepts, F1), where E4+E3 gives 8 and 0.36 against
E3's 24 and 0.29 — a threefold reduction in the legally dangerous error while
accepting more true claims.

Neither number licenses a claim that this validates grounding generally.

## Where it still fails, characterised

The four remaining false accepts on the target bucket share one shape:
**within-clause role confusion**. The quantity and the wrong obligation live in
the SAME clause, so clause-level segmentation cannot separate them.

    s.174   "two directors as the fraction of total strength"   overlap 0.71
            source: "one-third of its total strength or two directors,
                     whichever is higher" — both roles, one sentence
    s.96    "fifteen months as the deadline for the first AGM"  overlap 0.44
    s.173   "120 days as the minimum number of Board meetings"  overlap 0.40

This checker separates *between* clauses. It cannot separate *roles within* one.
Closing that needs argument-role extraction — which quantity is the fraction and
which is the floor — not finer segmentation, and the s.174 case shows why: the
two quantities are joined by "or", in one clause, by design.

## What it deliberately does not do

It does not judge paraphrase. A claim with no extractable quantity binding is
returned UNRESOLVED, not rejected — E3's 12 false rejects on qualified
paraphrases are a different problem, and answering it here by guessing would
trade one error for another. UNRESOLVED means "this checker has nothing to say",
which is the honest output for a mechanism aimed at one failure shape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SUPPORTED = "SUPPORTED"          # the claim's binding is one the source makes
CONTRADICTED = "CONTRADICTED"    # the quantity is in the source, bound to something else
ABSENT = "ABSENT"                # the quantity is not in the source at all
UNRESOLVED = "UNRESOLVED"        # no binding could be extracted; not this checker's call

_WORDS = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
          r"fifteen|twenty|twenty-one|thirty|forty|fifty|sixty|ninety|"
          r"one hundred and twenty|hundred|thousand|lakh|crore|"
          r"one-third|two-thirds|one-half")
_UNITS = (r"days?|months?|years?|weeks?|members?|directors?|meetings?|"
          r"per cent\.?|percent|lakh|crore|rupees")

# A quantity is a numeral (word or digit) plus the unit it counts.
_QTY = re.compile(rf"(?<![\w-])((?:{_WORDS}|\d[\d,]*)\s+(?:{_UNITS}))", re.I)

# Statutory drafting separates obligations with these. A quantity governs the
# text up to the next one — that is the clause it lives in.
_BOUNDARY = re.compile(
    r";|:\s|\.\s|\bprovided\s+(?:that|further|also)\b|"
    r"\(\s*[a-z0-9]{1,4}\s*\)|\bin\s+(?:the\s+)?case\s+of\b|\bwhere\b|\bunless\b"
    # Statutory prose often runs several obligations through one sentence with no
    # punctuation between them. s.173(1) states three — a thirty-day deadline, a
    # minimum of four meetings, and a one-hundred-and-twenty-day gap — separated
    # only by these connectives. Without them all three quantities inherit the
    # same context and become indistinguishable.
    r"|\band\s+thereafter\b|\bin\s+such\s+a?\s*manner\s+that\b"
    r"|\bso\s+that\b|\bbut\s+(?:not|if)\b|\bexcept\s+that\b",
    re.I)

_STOP = {"the", "a", "an", "of", "in", "to", "and", "or", "for", "by", "with",
         "that", "this", "is", "are", "be", "shall", "may", "as", "on", "at",
         "any", "such", "its", "from", "under", "section", "sets", "not", "no",
         "than", "more", "less", "personally", "present"}


def _norm(s: str) -> str:
    s = (s.replace("’", "'").replace("“", '"').replace("”", '"')
          .replace("—", "-").replace("–", "-"))
    return re.sub(r"\s+", " ", s).strip().lower()


def _plain(html: str) -> str:
    return _norm(re.sub(r"<[^>]+>", " ", html or ""))


# Comparison direction. s.173 states a ceiling ("not more than one hundred and
# twenty days shall intervene") and a floor ("the gap ... is not less than ninety
# days") in the same section, and the whole legal content of s.173(5) is that its
# ninety days is a MINIMUM — the inverse of the 120-day maximum. The words that
# carry that distinction were in the stop list, so "not less than ninety days"
# and "not more than ninety days" compared identical. Direction is now a property
# of the binding, not a word to be filtered out.
CEILING = "CEILING"        # at most
FLOOR = "FLOOR"            # at least
UNSPECIFIED = "UNSPECIFIED"

_CEILING = re.compile(
    r"\bnot\s+more\s+than\b|\bnot\s+exceed(?:ing)?\b|\bwithin\b|\bmaximum\b"
    r"|\bat\s+most\b|\bnot\s+later\s+than\b|\bup\s+to\b|\bshall\s+not\s+exceed\b",
    re.I)
_FLOOR = re.compile(
    r"\bnot\s+less\s+than\b|\bat\s+least\b|\bminimum\b|\bnot\s+fewer\s+than\b"
    r"|\bor\s+more\b|\bno\s+less\s+than\b",
    re.I)


def direction_near(text: str, at: int, window: int = 60) -> str:
    """Whether the quantity at `at` is bounded above or below.

    Read from the words immediately before it — statutory drafting puts the
    comparator there ("not more than ninety days"). A window rather than the
    whole clause, because one clause can carry both a floor and a ceiling.
    """
    lo = max(0, at - window)
    before = text[lo:at]
    c, f = _CEILING.search(before), _FLOOR.search(before)
    if c and f:
        return CEILING if c.start() > f.start() else FLOOR
    if c:
        return CEILING
    if f:
        return FLOOR
    return UNSPECIFIED


@dataclass(frozen=True)
class Binding:
    quantity: str
    context: str            # the clause the quantity governs
    at: int
    direction: str = UNSPECIFIED

    @property
    def terms(self) -> frozenset[str]:
        """Context words, EXCLUDING the quantity's own.

        Two bindings are only ever compared when they share a quantity, so its
        words match by construction. Counting them inflated every comparison:
        "fifteen members ... private company" against "fifteen members ... one
        thousand" scored 0.40 on the strength of "fifteen" and "members" alone,
        and a rebound claim read as supported. Excluding them, the overlap is
        what it should be — zero.
        """
        own = set(re.findall(r"[a-z][a-z-]+", self.quantity))
        return frozenset(w for w in re.findall(r"[a-z][a-z-]+", self.context)
                         if w not in _STOP and w not in own and len(w) > 2)


def bindings(text: str) -> list[Binding]:
    """Every (quantity, governing clause) pair the text states."""
    t = _plain(text)
    out: list[Binding] = []
    for m in _QTY.finditer(t):
        qty = _norm(m.group(1))
        # The clause runs from the previous boundary to the next one. Taking the
        # whole sentence would merge sibling sub-clauses — which is exactly how
        # "fifteen members" and "five members" become indistinguishable.
        starts = [b.end() for b in _BOUNDARY.finditer(t, 0, m.start())]
        lo = starts[-1] if starts else 0
        nxt = _BOUNDARY.search(t, m.end())
        hi = nxt.start() if nxt else len(t)
        out.append(Binding(qty, t[lo:hi].strip(), m.start(),
                           direction_near(t, m.start())))
    return out


@dataclass
class BindingVerdict:
    status: str
    quantity: str = ""
    claim_context: str = ""
    source_context: str = ""
    overlap: float = 0.0
    note: str = ""

    @property
    def supported(self) -> bool:
        return self.status == SUPPORTED


def judge(premise: str, claim: str, *, threshold: float = 0.34) -> BindingVerdict:
    """Does the claim bind its quantity the way the premise does?"""
    cb = bindings(claim)
    if not cb:
        return BindingVerdict(UNRESOLVED,
                              note="the claim states no quantity; this checker has "
                                   "nothing to say about it")
    sb = bindings(premise)
    if not sb:
        return BindingVerdict(UNRESOLVED,
                              note="the premise states no quantity to compare against")

    # If several quantities in the premise share one context, the segmentation
    # separated nothing and cannot say which obligation any of them governs.
    # Answering anyway would produce exactly the false accept this exists to
    # prevent, so it abstains and names the reason.
    # Keyed on (context, direction), not context alone. Direction now separates
    # quantities that share a clause — "at least one meeting" and "not less than
    # ninety days" sit in one sentence but bind differently, and treating the
    # clause as degenerate abstained on the whole of s.173(5).
    keys = [(s.context, s.direction) for s in sb]
    if len(sb) > 1 and len(set(keys)) < len(keys):
        dupes = [q for q in {s.quantity for s in sb
                             if keys.count((s.context, s.direction)) > 1}]
        return BindingVerdict(
            UNRESOLVED,
            note=("several quantities in the provision share one clause "
                  f"({', '.join(sorted(dupes)[:4])}); the text does not separate the "
                  "obligations they govern, so no binding can be checked"))

    worst: BindingVerdict | None = None
    for c in cb:
        same = [s for s in sb if s.quantity == c.quantity]
        if not same:
            v = BindingVerdict(ABSENT, c.quantity, c.context,
                               note=f"{c.quantity!r} does not appear in the provision")
            if worst is None or v.status == ABSENT:
                worst = v
            continue
        # Direction first. A claim that turns a floor into a ceiling is false
        # however well its words match — and it is exactly the error that makes
        # s.173(5) compliance look satisfied by meetings held thirty days apart.
        dir_clash = [s for s in same
                     if c.direction != UNSPECIFIED and s.direction != UNSPECIFIED
                     and c.direction != s.direction]
        if dir_clash and not [s for s in same if s.direction == c.direction]:
            v = BindingVerdict(
                CONTRADICTED, c.quantity, c.context, dir_clash[0].context, 0.0,
                note=(f"the claim bounds {c.quantity!r} as a "
                      f"{c.direction.lower()}; the provision states it as a "
                      f"{dir_clash[0].direction.lower()}"))
            worst = v
            continue

        # The claim's clause must resemble the clause the source binds it to.
        same = [s for s in same
                if c.direction == UNSPECIFIED or s.direction == UNSPECIFIED
                or s.direction == c.direction] or same
        best = max(same, key=lambda s: _sim(c.terms, s.terms))
        score = _sim(c.terms, best.terms)
        if score >= threshold:
            v = BindingVerdict(SUPPORTED, c.quantity, c.context, best.context, score)
        else:
            v = BindingVerdict(
                CONTRADICTED, c.quantity, c.context, best.context, score,
                note=(f"{c.quantity!r} is in the provision, but governing "
                      f"{_short(best.context)!r} — not {_short(c.context)!r}"))
        if worst is None or (v.status != SUPPORTED and worst.status == SUPPORTED):
            worst = v
        elif worst.status == SUPPORTED and v.status == SUPPORTED:
            worst = v
    return worst or BindingVerdict(UNRESOLVED)


def _sim(a: frozenset[str], b: frozenset[str]) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def _short(s: str, n: int = 58) -> str:
    return s if len(s) <= n else s[:n].rstrip() + "…"


def predict(row) -> bool | None:
    """True/False where this checker has a view; None where it abstains."""
    v = judge(getattr(row, "source_span", None) or getattr(row, "premise", ""),
              getattr(row, "claim", None) or getattr(row, "hypothesis", ""))
    if v.status == UNRESOLVED:
        return None
    return v.supported


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

    print("entail_binding")

    S103 = ("Unless the articles of the company provide for a larger number,-- "
            "(a) in case of a public company,-- (i) five members personally present "
            "if the number of members as on the date of meeting is not more than one "
            "thousand; (ii) fifteen members personally present if the number of "
            "members as on the date of meeting is more than one thousand but up to "
            "five thousand; (iii) thirty members personally present if the number of "
            "members as on the date of the meeting exceeds five thousand; (b) in the "
            "case of a private company, two members personally present, shall be the "
            "quorum for a meeting of the company.")

    b = bindings(S103)
    qs = {x.quantity for x in b}
    check({"five members", "fifteen members", "thirty members", "two members"} <= qs,
          f"every quorum quantity is extracted ({sorted(qs)[:5]})")
    ctx = {x.quantity: x.context for x in b}
    check("one thousand" in ctx.get("five members", ""),
          "five members is bound to the one-thousand band")
    check("five thousand" in ctx.get("fifteen members", "")
          or "up to" in ctx.get("fifteen members", ""),
          "fifteen members is bound to a different band")
    check(ctx.get("five members") != ctx.get("fifteen members"),
          "sibling sub-clauses are not merged into one context")

    # The case E3 gets wrong.
    v = judge(S103, "Section 103 sets fifteen members as the quorum for a private "
                    "company.")
    check(v.status == CONTRADICTED,
          f"a real quantity bound to the wrong class is CONTRADICTED ({v.status})")
    check("private" not in v.source_context or "public" in v.source_context,
          "...and the verdict names the clause the source actually binds it to")

    v = judge(S103, "Section 103 sets two members as the quorum for a private company.")
    check(v.supported, f"the correct binding is SUPPORTED ({v.status})")

    v = judge(S103, "Section 103 sets seven members as the quorum for a private "
                    "company.")
    check(v.status == ABSENT, f"a quantity not in the provision is ABSENT ({v.status})")

    # Abstention: no quantity to check.
    v = judge(S103, "A private company's meeting requires members to attend in person.")
    check(v.status == UNRESOLVED,
          "a claim with no quantity is UNRESOLVED, not rejected")
    check("nothing to say" in v.note, "...and says the checker has no view")

    S173 = ("Every company shall hold the first meeting of the Board of Directors "
            "within thirty days of the date of its incorporation and thereafter hold "
            "a minimum number of four meetings of its Board of Directors every year "
            "in such a manner that not more than one hundred and twenty days shall "
            "intervene between two consecutive meetings of the Board")
    v = judge(S173, "The first Board meeting must be held within one hundred and "
                    "twenty days of incorporation.")
    check(v.status == CONTRADICTED,
          f"the fixture case — 120 days rebound to the first meeting ({v.status})")
    b173 = bindings(S173)
    check(len({x.context for x in b173}) == len(b173),
          f"s.173's three obligations segment into distinct clauses "
          f"({len({x.context for x in b173})} of {len(b173)})")

    # Degenerate segmentation must abstain rather than answer.
    flat = "A company shall keep ten members and twenty members and thirty members"
    v = judge(flat, "It requires twenty members for the register.")
    check(v.status == UNRESOLVED,
          f"quantities sharing one clause yield UNRESOLVED, not a guess ({v.status})")
    check("does not separate the obligations" in v.note,
          "...and the reason names the segmentation failure")
    v = judge(S173, "The first Board meeting must be held within thirty days of "
                    "incorporation.")
    check(v.supported, f"the true binding is SUPPORTED ({v.status})")

    check(predict(type("R", (), {"premise": S103, "hypothesis": "no numbers here"})())
          is None, "predict() returns None where the checker abstains")

    # Direction — the s.173(5) failure mode.
    check(direction_near("the gap is not less than ninety days", 33) == FLOOR,
          "'not less than' reads as a floor")
    check(direction_near("not more than one hundred and twenty days shall", 13)
          == CEILING, "'not more than' reads as a ceiling")
    check(direction_near("at least one meeting shall be held", 9) == FLOOR,
          "'at least' reads as a floor")
    check(direction_near("hold four meetings every year", 5) == UNSPECIFIED,
          "a bare quantity has no direction")

    FLOOR_SRC = "the gap between the two meetings is not less than ninety days"
    v = judge(FLOOR_SRC, "the gap between the two meetings is not less than ninety days")
    check(v.supported, f"a floor restated as a floor is supported ({v.status})")
    v = judge(FLOOR_SRC, "the gap between the two meetings is not more than ninety days")
    check(v.status == CONTRADICTED,
          f"a floor restated as a ceiling is CONTRADICTED ({v.status})")
    check("floor" in v.note and "ceiling" in v.note,
          f"...and the verdict names both directions ({v.note[:70]})")

    # The measured claim, pinned. If a future edit stops it beating E3 on the
    # bucket it was built for, that is the whole reason it exists.
    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED
    from checker.entail_baseline import judge as e3_judge
    from checker.eval_taxonomy import bucket_of

    wb = [p for p in all_pairs()
          if p.label in (ENTAILED, NOT_ENTAILED) and bucket_of(p.kind) == "wrong_binding"]
    e3_fa = sum(1 for p in wb
                if e3_judge(p.source_span, p.claim).entailed and p.label != ENTAILED)
    e4_fa = sum(1 for p in wb
                if judge(p.source_span, p.claim).supported and p.label != ENTAILED)
    check(e4_fa < e3_fa,
          f"E4 accepts fewer unsupported rebound claims than E3 ({e4_fa} vs {e3_fa})")
    check(e4_fa <= 6, f"false accepts on the target bucket stay low ({e4_fa})")
    src = __import__("pathlib").Path(__file__).read_text()
    check("No configuration beats the majority baseline" in src,
          "the module states that no configuration beats the majority baseline")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
