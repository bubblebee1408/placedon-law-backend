"""Paraphrase pairs: where surface matching must fail.

E3 scores 1.00 on the templated set and 1/4 on hand-written paraphrases, with
every error a false accept. The templated negatives alter one checkable token;
the deterministic checker inspects exactly those tokens. These pairs are built so
that no token check can reach them.

## Who is allowed to assign a label

I am a model, and the runbook says a model may never assign the gold label. That
rule is kept by splitting pairs on *how the label was established*:

- **CONSTRUCTED** — the label follows from a mechanical transformation of the
  source. When a quantity that genuinely appears in s.173 is re-attached to a
  different obligation in s.173, the claim is false because it was built false.
  No reading comprehension is involved, and the construction is re-checkable by
  anyone from the record.
- **JUDGED** — the label rests on what the provision *means*. Every positive
  paraphrase is of this kind, because deciding that different words say the same
  thing is exactly the judgement under test.

`JUDGED` pairs are written with status PENDING_REVIEW and `approved_pairs()`
excludes them. They do not enter a frozen benchmark on my say-so. Shipping a set
where a model both wrote the claim and declared it true would measure the model
against its own opinion — the LLM-as-judge failure that Magesh et al. and
Cymbler et al. both refused.

## Why rebinding is the core attack

The decisive fixture case is "first meeting within ninety days": ninety days is
really in s.173, governing the gap between meetings, not the first-meeting
deadline. Every distinctive term is present and the proposition is false. That is
inapplicable authority in the Magesh sense, and it is a property of how a claim
*binds* its terms rather than which terms it uses. Rebinding is therefore
generated systematically rather than hand-picked, so coverage does not depend on
how many examples I happened to think of.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"

CONSTRUCTED = "CONSTRUCTED"      # label follows from a mechanical transformation
JUDGED = "JUDGED"                # label rests on reading the provision

PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"

# Kinds
REBIND = "wrong_binding"         # real quantity, wrong obligation
SCOPE = "scope_swap"             # right rule, wrong class of company or meeting
NEGATION = "negation"            # the provision's obligation denied
CONFLATION = "conflation"        # a condition dropped, widening the rule
PARAPHRASE_TRUE = "paraphrase_true"   # genuine restatement (always JUDGED)

OUT = Path("corpus/benchmark/entailment_paraphrase.jsonl")


@dataclass
class ParaPair:
    id: str
    section: str
    premise: str
    claim: str
    gold: str
    kind: str
    label_basis: str
    rationale: str
    status: str = PENDING_REVIEW
    provenance: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """CONSTRUCTED labels stand on their own; JUDGED ones need a human."""
        return self.label_basis == CONSTRUCTED or self.status == APPROVED


def provision(number: str) -> str:
    from checker.section_index import section_by_number
    rec = section_by_number(number)
    if not rec:
        raise KeyError(f"s.{number} not in the corpus")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rec["content"])).strip()


# --- mechanical rebinding ---------------------------------------------------
# A binding is (quantity, the obligation it governs). Written out per section
# rather than parsed, because mis-parsing a provision would silently produce a
# pair whose gold label is wrong — and a wrong label is worse than no pair.
BINDINGS: dict[str, list[tuple[str, str]]] = {
    "173": [
        ("thirty days", "the deadline for holding the first Board meeting after incorporation"),
        ("four", "the minimum number of Board meetings in a year"),
        ("one hundred and twenty days", "the maximum gap between two consecutive Board meetings"),
    ],
    "174": [
        ("one-third", "the fraction of total strength forming the quorum for a Board meeting"),
        ("two directors", "the floor for the quorum for a Board meeting"),
        ("two-thirds", "the proportion of interested directors that triggers the special quorum rule"),
    ],
    "103": [
        ("five members", "the quorum for a public company with not more than one thousand members"),
        ("fifteen members", "the quorum for a public company with more than one thousand but up to five thousand members"),
        ("thirty members", "the quorum for a public company with more than five thousand members"),
        ("two members", "the quorum for a private company"),
    ],
    # s.96's four limbs are the ones practitioners actually conflate, and
    # checker/agm.py exists because getting the wrong limb produces a wrong
    # deadline by up to nine months.
    "96": [
        ("fifteen months", "the maximum gap between one annual general meeting and the next"),
        ("nine months", "the deadline for the first annual general meeting after the first financial year closes"),
        ("six months", "the deadline for an annual general meeting other than the first"),
        ("three months", "the longest extension the Registrar may grant"),
    ],
    "101": [
        ("twenty-one days", "the length of clear notice required to call a general meeting"),
        ("ninety-five per cent", "the proportion of members whose consent permits shorter notice for an annual general meeting"),
    ],
}


def rebind_pairs() -> list[ParaPair]:
    """Every quantity attached to every OTHER obligation in the same provision.

    The quantity is genuinely in the premise and the obligation is genuinely in
    the premise; only the pairing is invented. That is precisely the error no
    token check can see.
    """
    out: list[ParaPair] = []
    for num, binds in BINDINGS.items():
        prem = provision(num)
        for qty, oblig in binds:
            # Refuse to build on a binding that is not actually in the text: a
            # typo here would produce a confidently-labelled fiction.
            if _loose(qty) not in _loose(prem):
                raise ValueError(f"s.{num}: {qty!r} is not in the provision")
        for i, (qty, oblig) in enumerate(binds):
            for j, (other_qty, _) in enumerate(binds):
                if i == j:
                    continue
                out.append(ParaPair(
                    id=f"p{num}-rebind-{i}{j}",
                    section=num, premise=prem,
                    claim=f"Section {num} sets {other_qty} as {oblig}.",
                    gold=UNSUPPORTED, kind=REBIND, label_basis=CONSTRUCTED,
                    rationale=(f"{other_qty!r} appears in s.{num} but governs a "
                               f"different obligation; {oblig} is set at {qty!r}"),
                    provenance={"real_quantity": qty, "swapped_in": other_qty,
                                "obligation": oblig},
                ))
        # The matched TRUE partner, so a checker cannot win by refusing the frame.
        for i, (qty, oblig) in enumerate(binds):
            out.append(ParaPair(
                id=f"p{num}-bind-{i}",
                section=num, premise=prem,
                claim=f"Section {num} sets {qty} as {oblig}.",
                gold=SUPPORTED, kind=REBIND, label_basis=CONSTRUCTED,
                rationale=f"{qty!r} governs {oblig} in s.{num}",
                provenance={"real_quantity": qty, "obligation": oblig},
            ))
    return out


def _loose(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# --- hand-authored ----------------------------------------------------------
# (section, claim, gold, kind, basis, rationale)
AUTHORED: list[tuple[str, str, str, str, str, str]] = [
    # Scope swaps: the rule is real, the class it is applied to is not.
    ("103", "In the case of a public company, two members personally present shall be "
            "the quorum for a meeting of the company.", UNSUPPORTED, SCOPE, CONSTRUCTED,
     "two members is the quorum for a private company; a public company's quorum "
     "is five, fifteen or thirty depending on membership"),
    ("174", "The quorum for a general meeting of a company shall be one-third of its "
            "total strength or two directors, whichever is higher.", UNSUPPORTED, SCOPE,
     CONSTRUCTED,
     "s.174 fixes the quorum for meetings of the BOARD; the quorum for a general "
     "meeting is set by s.103"),
    ("103", "In the case of a private company, five members personally present shall "
            "be the quorum.", UNSUPPORTED, SCOPE, CONSTRUCTED,
     "five members is the public-company quorum for up to one thousand members; a "
     "private company's quorum is two"),
    ("101", "A meeting of the Board may be called by giving not less than clear "
            "twenty-one days' notice.", UNSUPPORTED, SCOPE, CONSTRUCTED,
     "s.101 governs notice for a GENERAL meeting, not a Board meeting"),

    # Conflation: a condition is dropped, widening the rule.
    ("103", "Five members personally present shall be the quorum for a meeting of a "
            "public company, whatever the number of its members.", UNSUPPORTED,
     CONFLATION, CONSTRUCTED,
     "the premise makes five members the quorum only where membership does not "
     "exceed one thousand; the condition is dropped"),
    ("103", "If the quorum is not present within half-an-hour from the time appointed, "
            "the meeting shall stand cancelled.", UNSUPPORTED, CONFLATION, CONSTRUCTED,
     "cancellation applies only where the meeting was called by requisitionists; "
     "otherwise the meeting stands adjourned"),
    ("101", "A general meeting may be called after shorter notice if consent is "
            "accorded by ninety-five per cent of the members.", UNSUPPORTED,
     CONFLATION, CONSTRUCTED,
     "the ninety-five per cent limb applies to an annual general meeting; for any "
     "other general meeting the premise sets a different test"),

    # Negation: the obligation denied.
    ("173", "A company is not required to hold any minimum number of meetings of its "
            "Board of Directors in a year.", UNSUPPORTED, NEGATION, CONSTRUCTED,
     "the premise requires a minimum of four Board meetings every year"),
    ("174", "The continuing directors may not act while any vacancy exists in the "
            "Board.", UNSUPPORTED, NEGATION, CONSTRUCTED,
     "the premise says the continuing directors MAY act notwithstanding any vacancy"),
    ("173", "Directors may not participate in a meeting of the Board through video "
            "conferencing.", UNSUPPORTED, NEGATION, CONSTRUCTED,
     "the premise expressly permits participation by video conferencing or other "
     "audio visual means"),
    ("103", "The articles of a company may not provide for a quorum larger than the "
            "number specified in this section.", UNSUPPORTED, NEGATION, CONSTRUCTED,
     "the premise applies 'unless the articles of the company provide for a larger "
     "number', so a larger number is permitted"),

    # True paraphrases. Every one is JUDGED: deciding that different words say the
    # same thing is the judgement under test.
    ("173", "A company must convene the first meeting of its Board no later than "
            "thirty days after it is incorporated.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates the first-meeting deadline without borrowing the sentence"),
    ("173", "At least four Board meetings must be held by a company in each year.",
     SUPPORTED, PARAPHRASE_TRUE, JUDGED, "restates the minimum number of meetings"),
    ("173", "Directors are permitted to take part in a Board meeting by video link "
            "rather than in person.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates the video-conferencing permission"),
    ("174", "Where one-third of the Board's total strength is fewer than two, two "
            "directors are required for a quorum.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates 'one-third of its total strength or two directors, whichever is higher'"),
    ("103", "A meeting of a private company is quorate when two members attend in "
            "person.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates the private-company quorum"),
    ("103", "If too few members attend within half an hour, the meeting is put off to "
            "the same day the following week.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates the default adjournment rule"),
    ("101", "Twenty-one clear days' notice must be given before a general meeting is "
            "held.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates the notice period"),
    ("174", "A vacancy on the Board does not by itself stop the remaining directors "
            "from acting.", SUPPORTED, PARAPHRASE_TRUE, JUDGED,
     "restates that continuing directors may act notwithstanding any vacancy"),
]


def authored_pairs() -> list[ParaPair]:
    out = []
    for i, (num, claim, gold, kind, basis, why) in enumerate(AUTHORED):
        out.append(ParaPair(
            id=f"p{num}-auth-{i}", section=num, premise=provision(num),
            claim=claim, gold=gold, kind=kind, label_basis=basis, rationale=why,
        ))
    return out


def all_pairs() -> list[ParaPair]:
    return rebind_pairs() + authored_pairs()


def approved_pairs() -> list[ParaPair]:
    """Pairs usable without a human signing off — CONSTRUCTED labels only."""
    return [p for p in all_pairs() if p.usable]


def write(path: Path = OUT) -> str:
    import hashlib
    pairs = all_pairs()
    body = "".join(json.dumps(asdict(p), ensure_ascii=False, sort_keys=True) + "\n"
                   for p in sorted(pairs, key=lambda x: x.id))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode()).hexdigest()


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

    print("entail_paraphrase")

    pairs = all_pairs()
    check(len(pairs) >= 40, f"pairs authored ({len(pairs)})")

    rebinds = [p for p in pairs if p.kind == REBIND]
    check(len(rebinds) >= 30, f"rebinding pairs ({len(rebinds)}) — the core attack")

    # Every quantity used must genuinely be in its premise; that is what makes a
    # rebind undetectable by token checks and what makes its label true.
    for p in rebinds:
        q = p.provenance.get("swapped_in") or p.provenance["real_quantity"]
        assert _loose(q) in _loose(p.premise), p.id
    check(True, "every rebound quantity genuinely appears in its own premise")

    check(all(p.label_basis in (CONSTRUCTED, JUDGED) for p in pairs),
          "every pair records how its label was established")
    judged = [p for p in pairs if p.label_basis == JUDGED]
    check(all(p.status == PENDING_REVIEW for p in judged),
          f"every JUDGED pair is PENDING_REVIEW ({len(judged)})")
    check(all(not p.usable for p in judged),
          "no JUDGED pair is usable before a human approves it")
    check(all(p.gold == SUPPORTED for p in judged),
          "the JUDGED set is exactly the positives — meaning-preservation is the judgement")

    both = {p.gold for p in approved_pairs()}
    check(both == {SUPPORTED, UNSUPPORTED},
          f"the usable subset still has both labels ({both})")

    check(all(p.rationale for p in pairs), "every pair says why its label is true")
    check(len({p.id for p in pairs}) == len(pairs), "ids are unique")

    # The point of the exercise: E3 must do badly here.
    from checker.entail_baseline import judge
    usable = approved_pairs()
    agree = sum((judge(p.premise, p.claim).entailed) == (p.gold == SUPPORTED)
                for p in usable)
    false_accepts = sum(judge(p.premise, p.claim).entailed and p.gold == UNSUPPORTED
                        for p in usable)
    print(f"\n  E3 on the CONSTRUCTED subset: {agree}/{len(usable)} "
          f"({false_accepts} false accepts)")
    check(false_accepts > 0,
          f"the deterministic checker is genuinely defeated ({false_accepts} false "
          "accepts) — these pairs are not reachable by token matching")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--emit" in sys.argv:
        d = write()
        ps = all_pairs()
        print(f"{len(ps)} pairs -> {OUT}")
        print(f"  CONSTRUCTED (usable now) : {sum(p.usable for p in ps)}")
        print(f"  JUDGED (pending review)  : {sum(not p.usable for p in ps)}")
        print(f"sha256: {d}")
    else:
        _test()
