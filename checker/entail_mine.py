"""Mine labelled entailment pairs from the corpus we already hold.

The grounding gap is that we can verify a citation exists, is admitted, and is in
force, but never that the sentence we produced *follows from* the text we served.
Closing it needs labelled data, and buying it is not an option: ILDC, HLDC and
IL-TUR are all non-commercial, and a third-party MIT re-upload does not cure a
CC-BY-NC licence.

We do not need to buy it. Our own corpus is a labelled entailment set that nobody
has mined, and its labels are **correct by construction** rather than by anyone's
judgement.

## The pair that matters

The valuable rows are not the positives. They are `PRIOR_AS_CURRENT`: the wording
that *used to* stand in a provision, phrased as a claim about what the provision
says now. Those two texts are semantically near-identical — often a few words
apart — and legally opposite. A checker that cannot separate them is exactly the
checker that lets a model serve repealed law as current, which is the failure mode
Huang et al. measured and the one Magesh et al. found contributing to 23-38% of
hallucinations in commercial tools.

**Measured, not assumed.** On the matched set, a single lexical-overlap threshold
reaches **88%** against a 67% majority-class floor. I expected it to be near
useless and it is not: a phrase that was substituted *out* shares visibly fewer
words with the current text than the phrase that replaced it, and that is real
signal. So the deterministic baseline in E3 starts strong, and any model has to
beat 88% on this set rather than 50%.

Two caveats travel with that number. It is measured on constructed pairs whose
hypotheses quote the source verbatim; a real hallucination paraphrases, and
overlap will do far worse there. And 88% still means roughly one in eight matched
pairs — repealed wording served as current — comes out wrong.

## Labels are constructed, never guessed

Every generator states the rule that makes its label true, and the rule is
*checked* rather than assumed:

- A `PRIOR_AS_CURRENT` negative is emitted only after confirming the prior wording
  is genuinely absent from the current text. If a substituted phrase still appears
  in the section, the label would be wrong, so the pair is dropped and counted.
- A `QUOTED_SPAN` positive quotes a span lifted verbatim from the premise, so it
  cannot be anything but entailed.
- Date and instrument negatives alter exactly one fact and keep everything else,
  so the label turns on that fact alone.

Pairs carry their provenance and the rule that produced them. A row whose label
cannot be justified from its own record should not be in the file.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path

from checker.amendment import parse_footnote
from checker.as_of import prior_wording, _find_span

CORPUS = Path("corpus/companies_act")

ENTAILED = "ENTAILED"
NOT_ENTAILED = "NOT_ENTAILED"

# Generator kinds
QUOTED_SPAN = "quoted_span"                # positive: verbatim from the premise
AMENDED_BY = "amended_by"                  # positive: instrument + date from footnote
PRIOR_AS_CURRENT = "prior_as_current"      # HARD negative: repealed wording as current
WRONG_INSTRUMENT = "wrong_instrument"      # negative: a different amending Act
WRONG_DATE = "wrong_date"                  # negative: date shifted
WRONG_NUMBER = "wrong_number"              # negative: numeric limit altered
CURRENT_WORDING = "current_wording"        # positive: the MATCHED partner of a hard negative

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

# Word numerals that carry legal force in the Act's time limits.
_NUMERALS = {
    "one": "two", "two": "three", "three": "four", "four": "five", "five": "six",
    "six": "seven", "seven": "eight", "eight": "nine", "nine": "ten",
    "ten": "eleven", "twelve": "fifteen", "fifteen": "twelve", "thirty": "sixty",
    "sixty": "ninety", "ninety": "sixty", "hundred": "thousand",
}
_UNIT = r"(?:days?|months?|years?|weeks?)"


@dataclass
class Pair:
    id: str
    premise: str
    hypothesis: str
    label: str
    kind: str
    section: str
    rule: str                     # why this label is true, in one sentence
    provenance: dict = field(default_factory=dict)


def _clean(html: str) -> str:
    """Readable text from a corpus record's stored HTML."""
    t = re.sub(r"<[^>]+>", " ", html or "")
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\s+", " ", t).strip()


def _fmt_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def _sentences(text: str, min_words: int = 8, max_words: int = 45) -> list[str]:
    out = []
    for s in re.split(r"(?<=[.:;])\s+", text):
        s = s.strip()
        if min_words <= len(s.split()) <= max_words:
            out.append(s)
    return out


def _records() -> list[dict]:
    from checker.section_index import lookup
    recs = []
    idx = json.loads((CORPUS / "_index.json").read_text())["entries"]
    by_id = {v["section_id"]: k for k, v in idx.items() if v.get("section_id")}
    for p in sorted(CORPUS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        try:
            r = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        r["_number"] = by_id.get(p.stem, "")
        if r["_number"]:
            recs.append(r)
    return recs


def mine(seed: int = 20260826) -> tuple[list[Pair], dict[str, int]]:
    """Every pair the corpus supports, plus a count of what was dropped and why."""
    rng = random.Random(seed)
    pairs: list[Pair] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    recs = _records()
    # Instruments seen across the corpus, for constructing wrong-instrument rows.
    instruments = sorted({
        a.instrument for r in recs for a in parse_footnote(r.get("footnote") or "")
        if a.instrument
    })

    for r in recs:
        num = r["_number"]
        full_body = _clean(r.get("content"))
        foot = _clean(r.get("footnote"))[:2000]
        if not full_body:
            continue
        # The premise is what a checker will actually see. Every hypothesis must
        # be judged against *this* string — deriving claims from the untruncated
        # body produced 11 "positives" quoting text absent from their own premise.
        body = full_body[:2000]
        sid = r.get("sha256", "")[:12]

        # --- positive: a span lifted verbatim from the served text -----------
        for i, s in enumerate(_sentences(body)[:2]):
            pairs.append(Pair(
                id=f"{num}-quote-{i}", premise=body,
                hypothesis=f"Section {num} provides that {s[0].lower() + s[1:]}",
                label=ENTAILED, kind=QUOTED_SPAN, section=num,
                rule="the hypothesis restates a span taken verbatim from the premise",
                provenance={"sha256": sid},
            ))

        # --- numeric negative: alter one legally-operative numeral ----------
        # (?<![\w-]) not \b: a hyphen is a word boundary, so "twenty-one days"
        # matched as "one days" and recorded 'one days' as the premise's actual
        # wording. The label happened to survive; the stated reason did not.
        m = re.search(rf"(?<![\w-])({'|'.join(_NUMERALS)})\s+({_UNIT})\b", body, re.I)
        if m:
            word, unit = m.group(1).lower(), m.group(2)
            wrong = _NUMERALS[word]
            # Only safe if the replacement numeral is not itself in the text; if
            # it is, the altered claim might be true of some other limb.
            if not re.search(rf"(?<![\w-]){wrong}\s+{unit}\b", body, re.I):
                pairs.append(Pair(
                    id=f"{num}-num", premise=body,
                    # The unit is lifted verbatim from the premise, which may be
                    # singular ("one year"), so it is pluralised for the altered
                    # numeral rather than emitting "a period of two year".
                    hypothesis=(f"Section {num} specifies a period of {wrong} "
                                f"{unit if unit.endswith('s') else unit + 's'}."),
                    label=NOT_ENTAILED, kind=WRONG_NUMBER, section=num,
                    rule=f"the premise says '{word} {unit}', never '{wrong} {unit}'",
                    provenance={"sha256": sid, "actual": f"{word} {unit}"},
                ))
            else:
                drop("numeric: replacement numeral also present")

        if not foot:
            continue

        for j, a in enumerate(parse_footnote(r.get("footnote") or "")):
            if not a.instrument or not a.wef or a.wef_implausible:
                continue
            when = _fmt_date(a.wef)

            # --- positive: instrument and date, both stated in the footnote --
            pairs.append(Pair(
                id=f"{num}-amend-{j}", premise=foot,
                hypothesis=(f"Section {num} was amended by {a.instrument} "
                            f"with effect from {when}."),
                label=ENTAILED, kind=AMENDED_BY, section=num,
                rule="instrument and commencement date both appear in the premise",
                provenance={"sha256": sid, "instrument": a.instrument,
                            "wef": a.wef.isoformat()},
            ))

            # --- negative: a different amending Act ---------------------------
            others = [i for i in instruments if i != a.instrument and i not in foot]
            if others:
                other = rng.choice(others)
                pairs.append(Pair(
                    id=f"{num}-inst-{j}", premise=foot,
                    hypothesis=(f"Section {num} was amended by {other} "
                                f"with effect from {when}."),
                    label=NOT_ENTAILED, kind=WRONG_INSTRUMENT, section=num,
                    rule=f"the premise names {a.instrument}; {other} does not appear in it",
                    provenance={"sha256": sid, "actual": a.instrument, "claimed": other},
                ))
            else:
                drop("instrument: no distinct instrument absent from the footnote")

            # --- negative: the date shifted by a year -------------------------
            try:
                shifted = a.wef.replace(year=a.wef.year + 1)
            except ValueError:                      # 29 Feb
                shifted = a.wef.replace(year=a.wef.year + 1, day=28)
            if str(shifted.year) not in foot:
                pairs.append(Pair(
                    id=f"{num}-date-{j}", premise=foot,
                    hypothesis=(f"Section {num} was amended by {a.instrument} "
                                f"with effect from {_fmt_date(shifted)}."),
                    label=NOT_ENTAILED, kind=WRONG_DATE, section=num,
                    rule=f"the premise gives {when}, not {_fmt_date(shifted)}",
                    provenance={"sha256": sid, "actual": a.wef.isoformat(),
                                "claimed": shifted.isoformat()},
                ))
            else:
                drop("date: shifted year also appears in the footnote")

            # --- the MATCHED positive: the wording that replaced it -----------
            # Without this, the hard negatives are compared against verbatim-quote
            # positives (0.89 lexical overlap vs 0.48) and a bag-of-words scorer
            # separates them for the wrong reason — the template differs, not the
            # law. Same section, same sentence frame, same length range: the only
            # thing that changes is whether the quoted phrase is in force.
            span = _find_span(r.get("content") or "", a.marker)
            if span:
                cur = _clean((r.get("content") or "")[span[1]:span[2] - 1])
                if 6 <= len(cur.split()) <= 60 and _norm(cur) in _norm(body):
                    pairs.append(Pair(
                        id=f"{num}-current-{j}", premise=body,
                        hypothesis=(f'Section {num} currently includes the words '
                                    f'"{cur.rstrip(" ,.;:")}".'),
                        label=ENTAILED, kind=CURRENT_WORDING, section=num,
                        rule=(f"this wording was substituted IN by {a.instrument} "
                              f"w.e.f. {a.wef.isoformat()} and is in the current text"),
                        provenance={"sha256": sid, "instrument": a.instrument,
                                    "wef": a.wef.isoformat(), "current_wording": cur,
                                    "matched_with": f"{num}-prior-{j}"},
                    ))

            # --- THE HARD NEGATIVE: repealed wording presented as current -----
            pw = prior_wording(a)
            if pw and len(pw.split()) >= 6:
                # The label is only true if this wording is genuinely gone from the
                # current text. Substitutions sometimes reinstate a phrase
                # elsewhere in the section; emitting those would mislabel them.
                if _norm(pw) in _norm(full_body):
                    drop("prior_as_current: prior wording still present in current text")
                else:
                    pairs.append(Pair(
                        id=f"{num}-prior-{j}", premise=body,
                        hypothesis=(f'Section {num} currently includes the words '
                                    f'"{pw.rstrip(" ,.;:")}".'),
                        label=NOT_ENTAILED, kind=PRIOR_AS_CURRENT, section=num,
                        rule=("this wording was substituted out by "
                              f"{a.instrument} w.e.f. {a.wef.isoformat()} and does "
                              "not appear in the current text"),
                        provenance={"sha256": sid, "instrument": a.instrument,
                                    "wef": a.wef.isoformat(), "prior_wording": pw},
                    ))

    return pairs, dropped


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def summarise(pairs: list[Pair]) -> str:
    kinds: dict[str, list[int]] = {}
    for p in pairs:
        k = kinds.setdefault(p.kind, [0, 0])
        k[0 if p.label == ENTAILED else 1] += 1
    pos = sum(p.label == ENTAILED for p in pairs)
    lines = [f"{len(pairs)} pairs — {pos} entailed, {len(pairs) - pos} not entailed",
             f"{'kind':<20}{'entailed':>10}{'not':>8}"]
    for k in sorted(kinds):
        lines.append(f"  {k:<18}{kinds[k][0]:>10}{kinds[k][1]:>8}")
    lines.append(f"sections covered: {len({p.section for p in pairs})}")
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

    print("entail_mine")

    pairs, dropped = mine()
    check(len(pairs) >= 120, f"the corpus yields enough pairs ({len(pairs)})")

    pos = [p for p in pairs if p.label == ENTAILED]
    neg = [p for p in pairs if p.label == NOT_ENTAILED]
    check(len(pos) >= 40 and len(neg) >= 40,
          f"both labels are well represented ({len(pos)} / {len(neg)})")
    ratio = len(pos) / max(1, len(pairs))
    check(0.25 <= ratio <= 0.75, f"the set is not degenerate ({ratio:.0%} entailed)")

    def overlap(p: Pair) -> float:
        h = set(_norm(p.hypothesis).split())
        pr = set(_norm(p.premise).split())
        return len(h & pr) / max(1, len(h))

    hard = [p for p in pairs if p.kind == PRIOR_AS_CURRENT]
    check(len(hard) >= 20, f"hard negatives exist ({len(hard)} prior-as-current)")

    # The correctness guard that makes those labels true.
    bad = [p for p in hard if _norm(p.provenance["prior_wording"]) in _norm(p.premise)]
    check(not bad, f"no hard negative quotes wording still in its premise ({len(bad)})")

    # Hardness is measured against the MATCHED positives, not asserted. Comparing
    # prior-wording negatives to verbatim-quote positives flatters the benchmark:
    # those differ in template (0.89 vs 0.48 overlap), not in law.
    matched = [p for p in pairs if p.kind == CURRENT_WORDING]
    check(len(matched) >= 15, f"matched positives exist ({len(matched)})")

    if hard and matched:
        h_ov = sorted(overlap(p) for p in hard)
        m_ov = sorted(overlap(p) for p in matched)
        best = max(
            (sum(x >= th / 100 for x in m_ov) + sum(x < th / 100 for x in h_ov))
            / (len(m_ov) + len(h_ov))
            for th in range(101)
        )
        # A coin flip is 50%; a majority-class guess is len(bigger)/total.
        floor = max(len(m_ov), len(h_ov)) / (len(m_ov) + len(h_ov))
        # Recorded as the number E4 must beat, not asserted to be weak. Bounds are
        # wide because the point is to detect a *change* in difficulty if the
        # generators are edited, not to pin a specific value.
        check(floor < best < 0.97,
              f"lexical overlap on the matched set: {best:.0%} "
              f"(majority-class {floor:.0%}) — this is the baseline E4 must beat")

    check(all(p.rule for p in pairs), "every pair states the rule that makes its label true")
    check(all(p.premise and p.hypothesis for p in pairs), "no pair is empty")
    check(len({p.id for p in pairs}) == len(pairs), "ids are unique")

    # Positives must actually be supported.
    q = [p for p in pairs if p.kind == QUOTED_SPAN]
    unsupported = [p for p in q if _norm(p.hypothesis.split("provides that ", 1)[-1])[:60]
                   not in _norm(p.premise)]
    check(not unsupported, f"every quoted-span positive appears in its premise ({len(unsupported)} bad)")

    # Wrong-instrument negatives must not accidentally name the real instrument.
    wi = [p for p in pairs if p.kind == WRONG_INSTRUMENT]
    leaked = [p for p in wi if _norm(p.provenance["claimed"]) in _norm(p.premise)]
    check(not leaked, f"no wrong-instrument claim names an instrument in its premise ({len(leaked)})")

    check(mine()[0][0].id == pairs[0].id, "mining is deterministic for a fixed seed")
    print(f"\n  dropped: {dropped}")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def write_jsonl(path: Path, pairs: list[Pair]) -> str:
    """Emit pairs and return the sha256 of the file, for E2 to freeze against."""
    import hashlib
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(asdict(p), ensure_ascii=False, sort_keys=True) + "\n"
                   for p in sorted(pairs, key=lambda x: x.id))
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode()).hexdigest()


if __name__ == "__main__":
    import sys
    if "--emit" in sys.argv:
        pairs, dropped = mine()
        out = Path("corpus/benchmark/entailment_pairs.jsonl")
        digest = write_jsonl(out, pairs)
        print(summarise(pairs))
        print(f"\ndropped: {dropped}")
        print(f"\nwrote {len(pairs)} pairs -> {out}")
        print(f"sha256: {digest}")
    else:
        _test()
