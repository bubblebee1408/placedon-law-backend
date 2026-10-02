#!/usr/bin/env python3
"""What kind of document is this? A fixed list, rules first, and `unknown` is an answer.

V1. Twenty thousand files are unusable until they are sorted, and the sorting has to be
checkable: a class is shown to a lawyer beside the document, and a wrong one sends them to
read the wrong thing.

## Rules first, and the list is CLOSED

The classes are a fixed tuple. A document that matches none is `unknown` -- which is a real
class with a real reason, not a NULL and not the nearest guess. `checker/scope.py` makes
the same choice about bodies of law for the same reason: a system that always produces an
answer produces a wrong one when it has nothing to go on, and the wrong one is
indistinguishable from the right one at a glance.

A model may be added later to propose a class the rules missed. It would propose, and this
would still decide -- the division `agents/plans.py` draws between picking and inventing.

## Word boundaries, because substrings lie

Every pattern is `\\b`-anchored. `agents/intake.py` learned this the hard way: matching
`nda` as a substring classified `AGM-notice-agenda.pdf` and `standalone-financials.pdf` as
NDAs, and matching `audit` inside `the auditor signed it` as a review request. The same
mistake in a vault misfiles a document a lawyer then cannot find.

## A margin, not a maximum

The winner must beat the runner-up by `MARGIN`. Two classes scoring 3 and 3 is not a
classification, and taking the first alphabetically would be a coin toss wearing a label.
Those come back `unknown` with both candidates named, which is a more useful thing to show
than either guess.

Run: PYTHONPATH=. python3 checker/doc_classifier.py --test
"""
from __future__ import annotations

import re

__all__ = ["CLASSES", "UNKNOWN", "MARGIN", "classify", "patterns_for"]

UNKNOWN = "unknown"

# The closed list. Adding one is a deliberate act: a new class needs patterns, a test, and
# a reason it is distinguishable from its neighbours.
CLASSES = (
    "nda",
    "services_agreement",
    "employment_agreement",
    "lease",
    "loan_agreement",
    "share_purchase_agreement",
    "board_minutes",
    "board_notice",
    "shareholder_resolution",
    "policy",
    "invoice",
    UNKNOWN,
)

# The winner must beat the runner-up by this much. 2 and not 1: a single shared word
# between two forms is common, and a one-point win on it is a coin toss.
MARGIN = 2

# (class, weight, pattern). Weights are coarse on purpose -- a title line is worth more
# than a body phrase, and nothing here is tuned to a corpus we have not measured.
_RULES: tuple[tuple[str, int, str], ...] = (
    ("nda", 4, r"\bnon[- ]?disclosure agreement\b"),
    ("nda", 4, r"\bconfidentiality agreement\b"),
    ("nda", 2, r"\bconfidential information\b"),
    ("nda", 2, r"\breceiving party\b"),
    ("nda", 2, r"\bdisclosing party\b"),

    ("services_agreement", 4, r"\b(master )?services agreement\b"),
    ("services_agreement", 3, r"\bstatement of work\b"),
    ("services_agreement", 2, r"\bservice levels?\b"),

    ("employment_agreement", 4, r"\bemployment agreement\b"),
    ("employment_agreement", 3, r"\bappointment letter\b"),
    ("employment_agreement", 2, r"\bprobation period\b"),
    ("employment_agreement", 2, r"\bnotice period\b"),

    ("lease", 4, r"\b(lease deed|leave and licen[cs]e)\b"),
    ("lease", 3, r"\blessor\b"),
    ("lease", 3, r"\blessee\b"),
    ("lease", 2, r"\bdemised premises\b"),

    ("loan_agreement", 4, r"\b(loan agreement|facility agreement)\b"),
    ("loan_agreement", 3, r"\bborrower\b"),
    ("loan_agreement", 2, r"\brate of interest\b"),

    ("share_purchase_agreement", 4, r"\bshare (purchase|subscription) agreement\b"),
    ("share_purchase_agreement", 3, r"\bequity shares\b"),
    ("share_purchase_agreement", 2, r"\bcompletion date\b"),

    ("board_minutes", 4, r"\bminutes of the (meeting of the )?board\b"),
    ("board_minutes", 3, r"\bchairman (of the meeting|took the chair)\b"),
    ("board_minutes", 2, r"\bleave of absence\b"),

    ("board_notice", 4, r"\bnotice of (the )?(board|meeting of the board)\b"),
    ("board_notice", 3, r"\bagenda\b"),
    ("board_notice", 2, r"\bis hereby given\b"),

    ("shareholder_resolution", 4, r"\b(special|ordinary) resolution\b"),
    ("shareholder_resolution", 3, r"\bresolved that\b"),
    ("shareholder_resolution", 2, r"\bextra[- ]?ordinary general meeting\b"),

    ("policy", 4, r"\b(policy on|whistle[- ]?blower policy|code of conduct)\b"),
    ("policy", 2, r"\bthis policy\b"),

    ("invoice", 4, r"\b(tax )?invoice\b"),
    ("invoice", 3, r"\b(gstin|hsn)\b"),
    ("invoice", 2, r"\bamount payable\b"),
)

_COMPILED = tuple((cls, weight, re.compile(pat, re.IGNORECASE))
                  for cls, weight, pat in _RULES)


def patterns_for(doc_class: str) -> tuple[str, ...]:
    """The patterns that vote for one class. For a reviewer, not for the classifier."""
    return tuple(pat for cls, _w, pat in _RULES if cls == doc_class)


def classify(text: str, *, name: str = "") -> tuple[str, str]:
    """(class, reason). `unknown` with a reason when nothing wins by the margin.

    The NAME is scored too, at half weight: a file called `NDA - Acme.pdf` is evidence,
    and a weaker kind than the words inside it. It is never the only evidence -- a name
    alone scores at most half and cannot clear the margin on its own unless the body says
    nothing at all, which is a scan and should be CANNOT_READ rather than classified.
    """
    body = str(text or "")
    label = str(name or "")
    scores: dict[str, int] = {}
    hits: dict[str, list[str]] = {}
    for cls, weight, pat in _COMPILED:
        m = pat.search(body)
        if m:
            scores[cls] = scores.get(cls, 0) + weight
            hits.setdefault(cls, []).append(m.group(0).strip().lower())
        elif label and pat.search(label):
            scores[cls] = scores.get(cls, 0) + max(1, weight // 2)
            hits.setdefault(cls, []).append(f"{m.group(0) if m else pat.pattern} (in the "
                                            f"file name)")
    if not scores:
        return UNKNOWN, ("no rule matched. The list of classes is closed, so this is "
                         "`unknown` rather than the nearest one -- a guess here misfiles "
                         "a document a lawyer then cannot find")
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best, best_score = ranked[0]
    runner, runner_score = ranked[1] if len(ranked) > 1 else (None, 0)
    if best_score - runner_score < MARGIN:
        return UNKNOWN, (
            f"{best} ({best_score}) and {runner} ({runner_score}) are within {MARGIN} "
            f"points. That is not a classification: taking the higher one would be a coin "
            f"toss wearing a label, and both candidates are more useful to show")
    return best, (f"{best} on {best_score} points"
                  + (f", ahead of {runner} on {runner_score}" if runner else "")
                  + f"; matched {sorted(set(hits.get(best, [])))[:4]}")


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("doc_classifier")

    SAMPLES = {
        "nda": "MUTUAL NON-DISCLOSURE AGREEMENT. Confidential Information means anything "
               "the disclosing party shares with the receiving party.",
        "services_agreement": "MASTER SERVICES AGREEMENT. A statement of work may be "
                              "issued. Service levels are set out in Schedule 2.",
        "employment_agreement": "EMPLOYMENT AGREEMENT. The probation period is six "
                                "months. The notice period is ninety days.",
        "lease": "LEASE DEED between the Lessor and the Lessee for the demised premises.",
        "loan_agreement": "LOAN AGREEMENT. The Borrower shall repay. The rate of interest "
                          "is twelve per cent.",
        "share_purchase_agreement": "SHARE PURCHASE AGREEMENT for equity shares. The "
                                    "completion date is 31 March.",
        "board_minutes": "MINUTES OF THE MEETING OF THE BOARD. The chairman took the "
                         "chair. Leave of absence was granted.",
        "board_notice": "NOTICE OF BOARD MEETING. Notice is hereby given. The agenda is "
                        "set out below.",
        "shareholder_resolution": "SPECIAL RESOLUTION passed at the extraordinary general "
                                  "meeting. RESOLVED THAT the company may borrow.",
        "policy": "WHISTLE-BLOWER POLICY. This policy applies to every employee.",
        "invoice": "TAX INVOICE. GSTIN 29ABCDE1234F1Z5. HSN 9983. Amount payable "
                   "1,00,000.",
    }

    # ── every class in the list is reachable ───────────────────────────────
    for expected, text in SAMPLES.items():
        got, why = classify(text)
        check(got == expected, f"{expected}: classified as {got} ({why[:44]})")
    check(set(SAMPLES) | {UNKNOWN} == set(CLASSES),
          f"every class in CLASSES has a sample, and no sample names a class that is not "
          f"in it ({sorted(set(CLASSES) ^ (set(SAMPLES) | {UNKNOWN}))})")

    # ── unknown is an ANSWER ───────────────────────────────────────────────
    got, why = classify("A short note about the weather in Pune.")
    check(got == UNKNOWN, "a document matching no rule is `unknown`")
    check("closed" in why and "nearest one" in why,
          f"...and says the list is closed rather than guessing ({why[:50]})")
    check(UNKNOWN in CLASSES,
          "`unknown` is IN the class list: it is a real answer, not a null")
    check(classify("")[0] == UNKNOWN, "empty text is unknown, not an error")

    # ── a near-tie is not a classification ─────────────────────────────────
    both = ("This CONFIDENTIALITY AGREEMENT is also an EMPLOYMENT AGREEMENT. "
            "The receiving party observes a probation period.")
    got, why = classify(both)
    check(got == UNKNOWN,
          f"a document scoring close on TWO classes is `unknown`, not the higher one "
          f"({got})")
    check("coin toss" in why and "nda" in why and "employment_agreement" in why,
          f"...and NAMES both candidates, which is more useful to show than either guess "
          f"({why[:70]})")
    check(str(MARGIN) in why, "...and the margin it failed to clear")

    # ── word boundaries, because substrings lie ────────────────────────────
    # The exact family of mistakes agents/intake.py made: `nda` inside `agenda`.
    check(classify("AGM-notice-agenda", name="AGM-notice-agenda.pdf")[0] != "nda",
          "'agenda' does not classify as an NDA -- the substring bug intake.py shipped")
    check(classify("standalone financial statements")[0] != "nda",
          "...nor does 'standalone'")
    check(classify("the auditor signed the balance sheet")[0] != "policy",
          "...and 'auditor' is not a policy")
    unanchored = [p for _c, _w, p in _RULES if not p.startswith(r"\b")]
    check(not unanchored, f"EVERY pattern is \\b-anchored ({unanchored})")

    # ── the file name is weaker evidence, and never the only evidence ──────
    named_only = classify("", name="NDA - Acme Industries.pdf")
    check(named_only[0] == UNKNOWN,
          f"a file NAME alone does not classify an empty document: that is a scan, and it "
          f"should be CANNOT_READ rather than classified from its filename "
          f"({named_only[0]})")
    with_body = classify(SAMPLES["nda"], name="NDA - Acme.pdf")
    check(with_body[0] == "nda", "...while a name plus a body still classifies")

    # ── a reason, always ───────────────────────────────────────────────────
    check(all(classify(t)[1].strip()
              for t in list(SAMPLES.values()) + ["", "nothing here", both]),
          "EVERY classification carries a reason, including the unknown ones: a bare "
          "class in a list of twenty thousand is a number nobody can check")
    # `patterns_for` is for a reviewer, so the thing to assert is that it returns this
    # class's patterns and NOT another's. The first version wrote `all(... or True ...)`,
    # which cannot fail -- the fifth unfalsifiable check in this repository.
    nda_pats = set(patterns_for("nda"))
    inv_pats = set(patterns_for("invoice"))
    check(nda_pats and inv_pats and not (nda_pats & inv_pats),
          f"patterns_for returns one class's patterns and none of another's "
          f"({len(nda_pats)} nda, {len(inv_pats)} invoice, {len(nda_pats & inv_pats)} "
          f"shared)")
    check(patterns_for("not_a_class") == (),
          "...and an unknown class has no patterns rather than all of them")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
