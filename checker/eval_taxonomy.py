"""Where the checker fails, and fixtures for whether it knows when to refuse.

Two things the strict benchmark did not give us.

## 1. An error taxonomy

E3 scores 0.44 on the strict set against a 0.66 majority baseline, and 1.00 on
the templated set. "It fails" is not actionable; *which shape* it fails on is.
Bucketing every disagreement by the kind of claim it was tells us whether the
gap is qualifier handling, quantity rebinding, or something else — and therefore
whether the fix is more rules or a different mechanism.

## 2. Abstention fixtures, generated rather than hand-written

SearchFireSafety (ACL 2026) had to synthesise partial-context items by hand. We
do not: the corpus records which provision a claim depends on, so withholding it
is deterministic. A claim about s.96's fifteen-month limb, served the text of
s.101, is unanswerable by construction — and the only correct behaviour is to
say so.

Abstention is reported as **recall**: of the items that are unanswerable, how
many did the system refuse? Precision is generally high and rate is not a
measure of anything (a system that refuses everything scores 100%).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

FIXTURES = Path("corpus/benchmark/abstention_fixtures.jsonl")

# Failure buckets, ordered by how much they matter for a legal answer.
DROPPED_QUALIFIER = "dropped_qualifier"      # proviso, exception, articles override
WRONG_BINDING = "wrong_binding"              # real quantity, wrong obligation
SCOPE_ERROR = "scope_error"                  # right rule, wrong class of company
NEGATION = "negation"                        # obligation denied
WRONG_INSTRUMENT = "wrong_instrument"
WRONG_DATE = "wrong_date"
WRONG_QUANTITY = "wrong_quantity"
PARAPHRASE = "paraphrase"                    # a true restatement it failed to accept
OTHER = "other"

# Which pair kinds map to which bucket. Kinds not listed fall to OTHER rather
# than being forced into a bucket they do not belong in.
_KIND_BUCKET = {
    "dropped_proviso": DROPPED_QUALIFIER,
    "dropped_exception": DROPPED_QUALIFIER,
    "dropped_articles_override": DROPPED_QUALIFIER,
    "dropped_delegated_rule": DROPPED_QUALIFIER,
    "dropped_government_exemption": DROPPED_QUALIFIER,
    "dropped_threshold": DROPPED_QUALIFIER,
    "wrong_binding": WRONG_BINDING,
    "scope_swap": SCOPE_ERROR,
    "negation": NEGATION,
    "conflation": DROPPED_QUALIFIER,
    "paraphrase_qualified": PARAPHRASE,
    "arithmetic_claim": PARAPHRASE,
    "by_itself_claim": PARAPHRASE,
    "wrong_instrument": WRONG_INSTRUMENT,
    "wrong_date": WRONG_DATE,
    "wrong_number": WRONG_QUANTITY,
    "quoted_span": PARAPHRASE,
    "amended_by": PARAPHRASE,
    "current_wording": PARAPHRASE,
    "prior_as_current": WRONG_BINDING,
}


@dataclass
class Bucket:
    name: str
    n: int = 0
    wrong: int = 0
    false_accept: int = 0     # said supported, gold says not
    false_reject: int = 0     # said unsupported, gold says supported

    @property
    def error_rate(self) -> float:
        return self.wrong / self.n if self.n else 0.0


def bucket_of(kind: str) -> str:
    return _KIND_BUCKET.get(kind, OTHER)


def taxonomy(predict) -> dict[str, Bucket]:
    """Bucket every disagreement on the strict set by the shape of the claim."""
    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED

    out: dict[str, Bucket] = {}
    for p in all_pairs():
        if p.label not in (ENTAILED, NOT_ENTAILED):
            continue
        b = out.setdefault(bucket_of(p.kind), Bucket(bucket_of(p.kind)))
        b.n += 1
        said = bool(predict(p))
        gold = p.label == ENTAILED
        if said == gold:
            continue
        b.wrong += 1
        if said:
            b.false_accept += 1
        else:
            b.false_reject += 1
    return out


def taxonomy_report(buckets: dict[str, Bucket]) -> str:
    lines = ["", "ERROR TAXONOMY — strict set, by claim shape",
             f"  {'bucket':<24}{'n':>5}{'wrong':>7}{'err':>7}"
             f"{'false-acc':>11}{'false-rej':>11}"]
    for k in sorted(buckets, key=lambda x: -buckets[x].error_rate):
        b = buckets[k]
        lines.append(f"    {k:<22}{b.n:>5}{b.wrong:>7}{b.error_rate:>7.2f}"
                     f"{b.false_accept:>11}{b.false_reject:>11}")
    lines.append("  false-acc = unsupported claim accepted; the legally dangerous one.")
    return "\n".join(lines)


# --- abstention fixtures ----------------------------------------------------
@dataclass
class AbstentionItem:
    id: str
    claim: str
    served_section: str
    required_section: str
    served_text: str
    answerable: bool
    reason: str
    provenance: dict = field(default_factory=dict)


def build_fixtures(limit: int = 40) -> list[AbstentionItem]:
    """Pairs served the WRONG provision, plus matched answerable controls.

    Withholding is deterministic: each claim names the section it depends on, so
    serving a different section makes it unanswerable by construction. Controls
    matter as much as the withheld items — a set of only-unanswerable items is
    passed by a system that refuses everything.
    """
    from checker.entail_pairs_v2 import all_pairs, provision
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED

    pairs = [p for p in all_pairs()
             if p.label in (ENTAILED, NOT_ENTAILED) and p.source_span]
    by_section: dict[str, list] = {}
    for p in pairs:
        by_section.setdefault(p.section, []).append(p)
    sections = sorted(by_section)
    if len(sections) < 2:
        return []

    out: list[AbstentionItem] = []
    for i, p in enumerate(pairs):
        if len(out) >= limit:
            break
        # The wrong provision: the next section in rotation, never its own.
        other = sections[(sections.index(p.section) + 1) % len(sections)]
        if other == p.section:
            continue
        try:
            wrong_text = provision(other)[:900]
        except Exception:
            continue
        out.append(AbstentionItem(
            id=f"abst-{p.id}", claim=p.claim, served_section=other,
            required_section=p.section, served_text=wrong_text, answerable=False,
            reason=(f"the claim is about s.{p.section}; the text served is s.{other}. "
                    "Nothing in the served evidence can settle it."),
            provenance={"source_pair": p.id, "kind": p.kind}))
        # The matched control: same claim, correct provision.
        out.append(AbstentionItem(
            id=f"ctrl-{p.id}", claim=p.claim, served_section=p.section,
            required_section=p.section, served_text=p.source_span, answerable=True,
            reason="the claim's own provision is served; refusing here is a failure",
            provenance={"source_pair": p.id, "kind": p.kind}))
    return out


def score_abstention(items: list[AbstentionItem], predict_refuses) -> dict:
    """Abstention recall on unanswerable items, and over-refusal on controls.

    `predict_refuses(item) -> bool` — True when the system declines to answer.
    """
    unans = [i for i in items if not i.answerable]
    ans = [i for i in items if i.answerable]
    refused_unans = sum(bool(predict_refuses(i)) for i in unans)
    refused_ans = sum(bool(predict_refuses(i)) for i in ans)
    return {
        "unanswerable": len(unans),
        "answerable": len(ans),
        "abstention_recall": refused_unans / len(unans) if unans else 0.0,
        "over_refusal_rate": refused_ans / len(ans) if ans else 0.0,
        "refused_unanswerable": refused_unans,
        "refused_answerable": refused_ans,
    }


def write_fixtures(items: list[AbstentionItem], path: Path = FIXTURES) -> str:
    import hashlib
    body = "".join(json.dumps(asdict(i), ensure_ascii=False, sort_keys=True) + "\n"
                   for i in sorted(items, key=lambda x: x.id))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


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

    print("eval_taxonomy")

    check(bucket_of("dropped_proviso") == DROPPED_QUALIFIER,
          "a dropped proviso buckets as a qualifier failure")
    check(bucket_of("prior_as_current") == WRONG_BINDING,
          "repealed-wording-as-current buckets as wrong binding")
    check(bucket_of("something_new") == OTHER,
          "an unknown kind falls to OTHER rather than being forced into a bucket")

    from checker.entail_baseline import predict as e3
    buckets = taxonomy(lambda p: e3(type("R", (), {
        "premise": p.source_span, "hypothesis": p.claim})()))
    check(sum(b.n for b in buckets.values()) > 50,
          f"the whole strict set is bucketed ({sum(b.n for b in buckets.values())})")
    check(any(b.wrong for b in buckets.values()), "failures are recorded")
    txt = taxonomy_report(buckets)
    check("false-acc" in txt and "legally dangerous" in txt,
          "the report names the dangerous error direction")
    print(txt)

    items = build_fixtures(limit=20)
    check(len(items) >= 10, f"fixtures are generated ({len(items)})")
    check(any(i.answerable for i in items) and any(not i.answerable for i in items),
          "both unanswerable items and answerable controls are present")
    check(all(i.served_section != i.required_section
              for i in items if not i.answerable),
          "every unanswerable item is served a DIFFERENT provision")
    check(all(i.served_section == i.required_section for i in items if i.answerable),
          "every control is served its own provision")
    check(all(i.reason for i in items), "every item states why it is what it is")

    # A system that refuses everything must not score well.
    always = score_abstention(items, lambda i: True)
    check(always["abstention_recall"] == 1.0 and always["over_refusal_rate"] == 1.0,
          "refusing everything shows perfect recall AND total over-refusal")
    never = score_abstention(items, lambda i: False)
    check(never["abstention_recall"] == 0.0 and never["over_refusal_rate"] == 0.0,
          "answering everything shows no abstention and no over-refusal")
    oracle = score_abstention(items, lambda i: not i.answerable)
    check(oracle["abstention_recall"] == 1.0 and oracle["over_refusal_rate"] == 0.0,
          "only an oracle gets recall 1.0 with no over-refusal")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--emit" in sys.argv:
        its = build_fixtures(limit=60)
        print(f"{len(its)} fixtures -> {write_fixtures(its)}")
    else:
        _test()
