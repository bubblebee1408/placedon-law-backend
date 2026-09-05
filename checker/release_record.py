"""Provenance for a benchmark run, and the release snapshot that preserves it.

A score without the inputs that produced it is not a result. This records both,
and fails closed when any input cannot be named.

## "Current" is not a version

The failure this exists to prevent has already happened twice here. The release
gate scored a generator while a manifest hash protected a file the gate never
opened. Five modules still read `approved_pairs.jsonl` as *current*, so a score
taken today cannot be reproduced against the artifact it actually used unless
that artifact is named at run time.

So `provenance()` raises rather than substituting a default. A missing corpus
version is not "the current corpus"; it is a run that cannot be reproduced, and
the honest response is to refuse to record it.

## Two dates that are not the same date

    artifact version     which files were used
    law effective date   the date on which a provision applied

A corpus snapshot taken on 1 September says nothing about whether a provision
was in force on a transaction dated 2019. Both are recorded, separately, and
conflating them is how a system reports last year's law with this year's
confidence.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

DIR = Path("corpus/benchmark")
RELEASES = DIR / "releases"


class ProvenanceError(RuntimeError):
    """An input could not be named. The run is not reproducible and is refused."""


def _sha_file(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def _commit() -> tuple[str, bool]:
    try:
        h = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=10)
        d = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                           text=True, timeout=10)
        if h.returncode:
            return "", True
        return h.stdout.strip(), bool(d.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return "", True


def _corpus_version() -> str:
    """A content hash over the Act corpus index. Not a date — a date can be
    stamped on a file whose contents changed underneath it."""
    idx = Path("corpus/companies_act/_index.json")
    if not idx.exists():
        return ""
    return "sha256:" + hashlib.sha256(idx.read_bytes()).hexdigest()[:32]


def _rules_version() -> str:
    d = Path("corpus/rules")
    if not d.exists():
        return "none-held"
    files = sorted(p for p in d.iterdir() if p.is_file())
    if not files:
        return "none-held"
    h = hashlib.sha256()
    for p in files:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()[:32]


@dataclass
class Provenance:
    benchmark_version: str
    benchmark_sha256: str
    corpus_version: str
    rules_version: str
    checker_commit: str
    working_tree_dirty: bool
    profile_schema_version: str
    runtime_version: str
    run_timestamp: str
    # Distinct from every version above: the date the LAW is being applied as of.
    # None means the run did not fix one, which is legitimate for a benchmark
    # scored on constructed pairs and is NOT legitimate for a client answer.
    law_effective_date: str | None = None

    def missing(self) -> list[str]:
        required = ("benchmark_version", "benchmark_sha256", "corpus_version",
                    "checker_commit", "profile_schema_version", "runtime_version",
                    "run_timestamp")
        return [f for f in required if not getattr(self, f)]


PROFILE_SCHEMA_VERSION = "company-profile-v1"


def provenance(benchmark_version: str,
               law_effective_date: str | None = None) -> Provenance:
    """Name every input to a benchmark run. Raises if any cannot be named."""
    commit, dirty = _commit()
    p = Provenance(
        benchmark_version=benchmark_version,
        benchmark_sha256=_sha_file(DIR / "approved_pairs.jsonl"),
        corpus_version=_corpus_version(),
        rules_version=_rules_version(),
        checker_commit=commit,
        working_tree_dirty=dirty,
        profile_schema_version=PROFILE_SCHEMA_VERSION,
        runtime_version=f"python-{platform.python_version()}",
        run_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        law_effective_date=law_effective_date)

    gaps = p.missing()
    if gaps:
        raise ProvenanceError(
            f"cannot name {', '.join(gaps)}. A run whose inputs cannot be named "
            f"cannot be reproduced, and 'current' is not a version.")
    return p


@dataclass
class Release:
    """A preserved snapshot: what was promoted, what it scored, what it is not."""
    release_id: str
    provenance: dict
    gate_result: dict
    authorised_by: str
    decided_at: str
    what_this_establishes: str
    what_this_does_not_establish: str
    files: dict = field(default_factory=dict)


NOT_ESTABLISHED = (
    "v3 is an internally consistent benchmark artifact of constructed examples "
    "drawn from a limited legal corpus, labelled by one non-lawyer. It is not "
    "evidence of legal accuracy, statutory coverage, or production readiness. "
    "Two of its three buckets cannot measure the axis the gate reports for them: "
    "dropped_qualifier holds no positives, so its F1 is undefined; paraphrase "
    "holds no negatives, so its false-accept count is vacuous. No score from it "
    "may be compared with any score taken before it, because those were measured "
    "on a generator rather than on a named artifact.")

ESTABLISHED = (
    "That the verifier cascade, run against a named and hash-verified artifact, "
    "did not regress on four axes: false accepts, F1, abstention, and per-bucket "
    "reporting."
)


def snapshot(release_id: str, gate_result: dict, authorised_by: str,
             benchmark_version: str = "v3") -> Path:
    """Preserve a release. Write-once; refuses to overwrite."""
    dest = RELEASES / release_id
    if dest.exists():
        raise ProvenanceError(f"{dest} exists; a release is written once")

    prov = provenance(benchmark_version)
    dest.mkdir(parents=True)

    tracked = {}
    for src in (DIR / "approved_pairs.jsonl", DIR / "manifest.json",
                DIR / "corrections" / "v2-to-v3.json",
                DIR / "corrections" / "v2-to-v3-promotion.json"):
        if src.exists():
            (dest / src.name).write_bytes(src.read_bytes())
            tracked[src.name] = _sha_file(src)

    rel = Release(release_id=release_id, provenance=asdict(prov),
                  gate_result=gate_result, authorised_by=authorised_by,
                  decided_at=prov.run_timestamp,
                  what_this_establishes=ESTABLISHED,
                  what_this_does_not_establish=NOT_ESTABLISHED,
                  files=tracked)
    (dest / "release.json").write_text(
        json.dumps(asdict(rel), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (dest / "SHA256SUMS").write_text(
        "".join(f"{_sha_file(p)[7:]}  {p.name}\n"
                for p in sorted(dest.iterdir()) if p.name != "SHA256SUMS"),
        encoding="utf-8")
    return dest


def verify_release(release_id: str) -> list[str]:
    d = RELEASES / release_id
    if not d.exists():
        return [f"{release_id}: no such release"]
    sums = d / "SHA256SUMS"
    if not sums.exists():
        return [f"{release_id}: no SHA256SUMS"]
    out = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        want, name = line.split("  ", 1)
        f = d / name
        if not f.exists():
            out.append(f"{release_id}/{name}: missing")
        elif _sha_file(f)[7:] != want:
            out.append(f"{release_id}/{name}: altered since release")
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

    print("release_record")

    p = provenance("v3")
    check(p.benchmark_version == "v3", "the benchmark version is named")
    check(p.benchmark_sha256.startswith("sha256:"),
          "the benchmark file is hashed, not merely named")
    check(p.corpus_version.startswith("sha256:"),
          "the corpus is versioned by CONTENT, not by a date someone stamped")
    check(p.checker_commit, "the checker commit is recorded")
    check(p.runtime_version.startswith("python-"), "the runtime is recorded")
    check(p.profile_schema_version == PROFILE_SCHEMA_VERSION,
          "the profile schema version is recorded")
    check(not p.missing(), f"nothing required is missing ({p.missing()})")

    # The law's effective date is a different thing from the artifact version.
    check(p.law_effective_date is None,
          "a benchmark run fixes no law-effective date, and says so")
    p2 = provenance("v3", law_effective_date="2026-09-02")
    check(p2.law_effective_date == "2026-09-02",
          "...and a run that does fix one records it separately")
    check(p2.corpus_version == p.corpus_version,
          "the corpus version does not change when the law date does")

    # Fail closed on an unnameable input. Patch THIS module, not
    # checker.release_record: run as __main__ they are two distinct module
    # objects, and patching the wrong one silently does nothing.
    import sys as _sys
    mod = _sys.modules[__name__]
    keep = mod._corpus_version
    mod._corpus_version = lambda: ""
    try:
        provenance("v3")
        check(False, "a run with an unnameable input is refused")
    except ProvenanceError as e:
        check("cannot be reproduced" in str(e),
              "a run with an unnameable input is refused")
        check("'current' is not a version" in str(e),
              "...and the message says why a default would be wrong")
    finally:
        mod._corpus_version = keep

    # A release is write-once and states what it does not establish.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        kr = mod.RELEASES
        mod.RELEASES = Path(td) / "releases"
        try:
            d = snapshot("test-1", {"false_accepts": 2, "f1": 0.62}, "user")
            check((d / "release.json").exists(), "a release is written")
            rel = json.loads((d / "release.json").read_text())
            check("not evidence of legal accuracy" in
                  rel["what_this_does_not_establish"],
                  "the release states it is not evidence of legal accuracy")
            check("may be compared with any score taken before it" in
                  rel["what_this_does_not_establish"],
                  "...and that earlier scores are not comparable")
            check(rel["provenance"]["checker_commit"],
                  "the release carries its commit")
            check(verify_release("test-1") == [], "a fresh release verifies")

            (d / "approved_pairs.jsonl").write_text("tampered\n")
            check(verify_release("test-1") != [],
                  "a tampered release fails verification")

            try:
                snapshot("test-1", {}, "user")
                check(False, "a release is write-once")
            except ProvenanceError:
                check(True, "a release is write-once")
        finally:
            mod.RELEASES = kr

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
