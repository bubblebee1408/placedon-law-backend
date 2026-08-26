"""The frozen entailment benchmark: load it, or refuse.

A benchmark that regenerates itself whenever the miner changes cannot measure
progress — every improvement in the generator silently moves the target, and a
score from Tuesday is not comparable to a score from Monday. So the pairs are
written once, hashed, and the loader verifies the hash on every read.

## Refusing is the feature

`load()` raises if the file's digest does not match the manifest. It does not
warn, re-derive, or fall back to mining fresh pairs. A benchmark that quietly
repairs itself is indistinguishable from one that was never frozen.

Re-freezing is deliberate and awkward on purpose: `--refreeze` must name the
digest being replaced, so it cannot happen by reflex or by a script.

## Why the headline number is per-kind

The set is 34% `quoted_span` — positives whose hypothesis is lifted verbatim from
the premise. They are trivially easy, and a single pooled accuracy over them
would read as competence the system has not demonstrated. `evaluate()` therefore
returns per-kind metrics and refuses to emit one pooled figure, in the same
spirit as reporting n alongside every rate.

The number that matters is on the **matched** subset: `prior_as_current` against
`current_wording`, where the only difference between an entailed and a
not-entailed pair is whether the quoted words are still in force.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

BENCH = Path("corpus/benchmark/entailment_pairs.jsonl")
MANIFEST = Path("corpus/benchmark/entailment_manifest.json")

ENTAILED = "ENTAILED"
NOT_ENTAILED = "NOT_ENTAILED"

# The subset on which a claim of grounding ability stands or falls.
MATCHED_KINDS = ("prior_as_current", "current_wording")


class BenchmarkError(RuntimeError):
    """The frozen set is missing or altered. Never recovered from."""


@dataclass(frozen=True)
class Row:
    id: str
    premise: str
    hypothesis: str
    label: str
    kind: str
    section: str
    rule: str
    provenance: dict = field(default_factory=dict)

    @property
    def entailed(self) -> bool:
        return self.label == ENTAILED


def digest_of(path: Path = BENCH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(pairs_path: Path = BENCH, manifest_path: Path = MANIFEST,
           *, replacing: str | None = None) -> dict:
    """Write the manifest for the current pairs file."""
    if not pairs_path.exists():
        raise BenchmarkError(f"no pairs file at {pairs_path}")
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if replacing != old.get("sha256"):
            raise BenchmarkError(
                f"{manifest_path} already freezes {old.get('sha256', '?')[:16]}…; "
                "pass the digest being replaced to overwrite it deliberately")

    rows = _read_rows(pairs_path)
    kinds: dict[str, dict[str, int]] = {}
    for r in rows:
        k = kinds.setdefault(r.kind, {ENTAILED: 0, NOT_ENTAILED: 0})
        k[r.label] += 1

    man = {
        "sha256": digest_of(pairs_path),
        "rows": len(rows),
        "entailed": sum(r.entailed for r in rows),
        "not_entailed": sum(not r.entailed for r in rows),
        "sections": len({r.section for r in rows}),
        "kinds": kinds,
        "matched_kinds": list(MATCHED_KINDS),
        "source": "checker/entail_mine.py --emit",
        "note": ("Frozen. Do not regenerate to make a score improve. "
                 "Per-kind metrics only; the pooled figure is dominated by "
                 "trivially-easy quoted_span positives."),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(man, indent=1) + "\n")
    return man


def _read_rows(path: Path) -> list[Row]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rows.append(Row(**{k: d[k] for k in Row.__dataclass_fields__ if k in d}))
    return rows


def load(pairs_path: Path = BENCH, manifest_path: Path = MANIFEST) -> list[Row]:
    """The frozen rows, or an exception. Never silently re-derived."""
    if not manifest_path.exists():
        raise BenchmarkError(f"no manifest at {manifest_path}; run freeze() first")
    man = json.loads(manifest_path.read_text())
    if not pairs_path.exists():
        raise BenchmarkError(f"manifest exists but {pairs_path} is missing")
    actual = digest_of(pairs_path)
    if actual != man["sha256"]:
        raise BenchmarkError(
            f"{pairs_path} has changed since it was frozen\n"
            f"  frozen : {man['sha256']}\n"
            f"  actual : {actual}\n"
            "Refusing to evaluate against a moved target. Either restore the file "
            "or re-freeze deliberately, naming the digest you are replacing.")
    rows = _read_rows(pairs_path)
    if len(rows) != man["rows"]:
        raise BenchmarkError(f"row count {len(rows)} != frozen {man['rows']}")
    return rows


# --- scoring ----------------------------------------------------------------
@dataclass
class Score:
    kind: str
    n: int
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_current_rate(self) -> float:
        """Share of NOT_ENTAILED rows wrongly accepted.

        The one that matters legally: a false positive here is repealed wording
        served as current law.
        """
        d = self.fp + self.tn
        return self.fp / d if d else 0.0


def evaluate(predict, rows: list[Row] | None = None) -> dict[str, Score]:
    """Score a predictor. `predict(row) -> bool` meaning "entailed".

    Returns per-kind scores plus `MATCHED` and `ALL`. There is deliberately no
    single headline number.
    """
    rows = rows if rows is not None else load()
    out: dict[str, Score] = {}

    def tally(key: str, r: Row, said_yes: bool) -> None:
        s = out.setdefault(key, Score(key, 0))
        s.n += 1
        if r.entailed and said_yes:
            s.tp += 1
        elif r.entailed:
            s.fn += 1
        elif said_yes:
            s.fp += 1
        else:
            s.tn += 1

    for r in rows:
        said = bool(predict(r))
        tally(r.kind, r, said)
        tally("ALL", r, said)
        if r.kind in MATCHED_KINDS:
            tally("MATCHED", r, said)
    return out


def report(scores: dict[str, Score]) -> str:
    lines = [f"{'subset':<20}{'n':>6}{'acc':>7}{'prec':>7}{'rec':>7}{'F1':>7}"
             f"{'false-current':>15}"]
    for k in sorted(scores, key=lambda x: (x not in ("MATCHED", "ALL"), x)):
        s = scores[k]
        lines.append(f"  {k:<18}{s.n:>6}{s.accuracy:>7.2f}{s.precision:>7.2f}"
                     f"{s.recall:>7.2f}{s.f1:>7.2f}{s.false_current_rate:>15.2f}")
    lines.append("  false-current = NOT_ENTAILED rows wrongly accepted; on MATCHED")
    lines.append("  that is repealed wording served as current law.")
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

    print("benchmark_freeze")

    rows = load()
    check(len(rows) > 1500, f"the frozen set loads ({len(rows)} rows)")
    man = json.loads(MANIFEST.read_text())
    check(digest_of() == man["sha256"], "the file matches its frozen digest")

    matched = [r for r in rows if r.kind in MATCHED_KINDS]
    check(len(matched) >= 100, f"the matched subset is usable ({len(matched)})")
    check(any(r.entailed for r in matched) and any(not r.entailed for r in matched),
          "the matched subset has both labels")

    # Tamper detection is the whole point.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "pairs.jsonl"
        p.write_text(BENCH.read_text(encoding="utf-8") + '{"id":"x","premise":"a",'
                     '"hypothesis":"b","label":"ENTAILED","kind":"k","section":"1",'
                     '"rule":"r"}\n', encoding="utf-8")
        try:
            load(p, MANIFEST)
            check(False, "an altered pairs file is refused")
        except BenchmarkError as exc:
            check("changed since it was frozen" in str(exc),
                  "an altered pairs file is refused, and says so")

        m = Path(d) / "manifest.json"
        try:
            load(BENCH, m)
            check(False, "a missing manifest is refused")
        except BenchmarkError:
            check(True, "a missing manifest is refused")

        # Re-freezing must name what it replaces.
        m.write_text(json.dumps({"sha256": "deadbeef", "rows": 1}))
        try:
            freeze(BENCH, m)
            check(False, "re-freezing without naming the old digest is refused")
        except BenchmarkError as exc:
            check("deliberately" in str(exc),
                  "re-freezing without naming the old digest is refused")
        man2 = freeze(BENCH, m, replacing="deadbeef")
        check(man2["sha256"] == digest_of(), "naming the old digest permits a re-freeze")

    # Scoring behaves.
    always_yes = evaluate(lambda r: True, rows)
    check(always_yes["ALL"].recall == 1.0, "always-yes has perfect recall")
    check(always_yes["MATCHED"].false_current_rate == 1.0,
          "always-yes serves every repealed wording as current")
    always_no = evaluate(lambda r: False, rows)
    check(always_no["ALL"].recall == 0.0, "always-no has no recall")
    check(always_no["MATCHED"].false_current_rate == 0.0,
          "always-no never serves repealed wording")
    perfect = evaluate(lambda r: r.entailed, rows)
    check(perfect["ALL"].accuracy == 1.0, "an oracle scores 1.00")
    check(perfect["ALL"].f1 == 1.0, "...with F1 1.00")

    txt = report(perfect)
    check("MATCHED" in txt and "ALL" in txt, "the report shows both subsets")
    check("false-current" in txt, "the report names the legally dangerous error")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--freeze" in sys.argv:
        i = sys.argv.index("--freeze")
        old = sys.argv[i + 1] if len(sys.argv) > i + 1 else None
        m = freeze(replacing=old)
        print(json.dumps(m, indent=1))
    else:
        _test()
