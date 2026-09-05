"""Immutable benchmark versions, and the correction records between them.

A frozen benchmark must never be mutated in place. If it is, two scores taken a
week apart look comparable and are not, and there is no way afterwards to say
which dataset produced which number.

So a correction does not overwrite. It archives the old version, writes an
adjudication record naming every changed pair and why, and creates a new
version. A published score names the version it came from.

    corpus/benchmark/versions/v2/approved_pairs.jsonl   archived, immutable
    corpus/benchmark/versions/v2/manifest.json
    corpus/benchmark/versions/v3/...
    corpus/benchmark/corrections/v2-to-v3.json          the adjudication

## Two kinds of change, and they are not equivalent

A SPAN correction says the evidence cited was wrong or incomplete. A LABEL
correction says the expected answer itself was wrong — it changes what the
system is being judged against. A record must separate them, because a run
before and a run after a label correction are measuring different things, and
presenting the two scores side by side without saying so is the failure this
module exists to prevent.

## Archives are write-once

`archive()` refuses to overwrite an existing version directory. A version that
could be rewritten is not a version.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

DIR = Path("corpus/benchmark")
VERSIONS = DIR / "versions"
CORRECTIONS = DIR / "corrections"
CURRENT = DIR / "approved_pairs.jsonl"
MANIFEST = DIR / "manifest.json"

SPAN_CORRECTION = "SPAN_CORRECTION"
LABEL_CORRECTION = "LABEL_CORRECTION"
PAIR_ADDED = "PAIR_ADDED"
PAIR_REMOVED = "PAIR_REMOVED"


class VersionError(RuntimeError):
    """A versioning operation was refused. Nothing was written."""


@dataclass(frozen=True)
class Change:
    pair_id: str
    kind: str                       # one of the four above
    old: str | None
    new: str | None
    reason: str


@dataclass
class Correction:
    from_version: str
    to_version: str
    reviewer_id: str
    decided_at: str
    changes: list[Change] = field(default_factory=list)
    note: str = ""

    @property
    def label_changes(self) -> list[Change]:
        return [c for c in self.changes if c.kind == LABEL_CORRECTION]

    @property
    def comparable(self) -> bool:
        """Whether a score on the new version may be compared with the old.

        False whenever a gold label moved or the pair set changed size. A span
        correction alone leaves the question and the answer intact, so scores
        remain broadly comparable and the record says so.
        """
        return not any(c.kind in (LABEL_CORRECTION, PAIR_ADDED, PAIR_REMOVED)
                       for c in self.changes)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def archive(version_id: str) -> Path:
    """Copy the current frozen set into an immutable version directory."""
    dest = VERSIONS / version_id
    if dest.exists():
        raise VersionError(
            f"{dest} already exists. A version that can be rewritten is not a "
            f"version; choose a new id.")
    if not CURRENT.exists():
        raise VersionError(f"{CURRENT} is missing; there is nothing to archive")

    dest.mkdir(parents=True)
    shutil.copy2(CURRENT, dest / CURRENT.name)
    if MANIFEST.exists():
        shutil.copy2(MANIFEST, dest / MANIFEST.name)

    (dest / "SHA256SUMS").write_text(
        "".join(f"{_sha(p.read_bytes())}  {p.name}\n"
                for p in sorted(dest.iterdir()) if p.name != "SHA256SUMS"),
        encoding="utf-8")
    return dest


def verify_archive(version_id: str) -> list[str]:
    """Has an archived version been altered since it was written?"""
    d = VERSIONS / version_id
    if not d.exists():
        return [f"{version_id}: no such archived version"]
    sums = d / "SHA256SUMS"
    if not sums.exists():
        return [f"{version_id}: no SHA256SUMS; the archive cannot be checked"]
    out = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        want, name = line.split("  ", 1)
        f = d / name
        if not f.exists():
            out.append(f"{version_id}/{name}: missing")
        elif _sha(f.read_bytes()) != want:
            out.append(f"{version_id}/{name}: altered since archiving")
    return out


def write_correction(c: Correction) -> Path:
    """Record the adjudication between two versions. Refuses a bare assertion."""
    if not c.changes:
        raise VersionError("a correction with no changes is not a correction")
    for ch in c.changes:
        if not ch.reason.strip():
            raise VersionError(
                f"{ch.pair_id}: every change needs a reason. A label that moved "
                f"without a recorded reason is indistinguishable from a mistake.")
    if "@" in c.reviewer_id:
        raise VersionError("record a pseudonymous reviewer id, not an address")

    CORRECTIONS.mkdir(parents=True, exist_ok=True)
    path = CORRECTIONS / f"{c.from_version}-to-{c.to_version}.json"
    if path.exists():
        raise VersionError(f"{path} already exists; corrections are write-once")

    path.write_text(json.dumps({
        "from_version": c.from_version,
        "to_version": c.to_version,
        "reviewer_id": c.reviewer_id,
        "decided_at": c.decided_at,
        "note": c.note,
        "comparable_with_previous": c.comparable,
        "why_not_comparable": (
            "" if c.comparable else
            "a gold label moved or the pair set changed size, so a score on the "
            "new version measures a different question from a score on the old; "
            "the two must not be presented side by side as a trend"),
        "counts": {k: sum(1 for ch in c.changes if ch.kind == k)
                   for k in (SPAN_CORRECTION, LABEL_CORRECTION,
                             PAIR_ADDED, PAIR_REMOVED)},
        "changes": [{"pair_id": ch.pair_id, "kind": ch.kind, "old": ch.old,
                     "new": ch.new, "reason": ch.reason} for ch in c.changes],
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def versions() -> list[str]:
    return sorted(d.name for d in VERSIONS.iterdir() if d.is_dir()) \
        if VERSIONS.exists() else []


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

    print("benchmark_versions")
    import tempfile

    span = Change("p1", SPAN_CORRECTION, "old text", "new text", "truncated")
    label = Change("p2", LABEL_CORRECTION, "ENTAILED", "INVALID_FIXTURE", "wrong")

    c1 = Correction("v2", "v3", "reviewer-01", "2026-09-02T00:00:00Z", [span])
    check(c1.comparable, "a span-only correction leaves scores comparable")

    c2 = Correction("v2", "v3", "reviewer-01", "2026-09-02T00:00:00Z", [span, label])
    check(not c2.comparable,
          "a label correction makes the scores incomparable")
    check(len(c2.label_changes) == 1, "label changes are counted separately")

    c3 = Correction("v2", "v3", "reviewer-01", "t",
                    [Change("p3", PAIR_ADDED, None, "ENTAILED", "new coverage")])
    check(not c3.comparable, "adding a pair also breaks comparability")

    # A change without a reason is refused.
    with tempfile.TemporaryDirectory() as td:
        global CORRECTIONS
        keep = CORRECTIONS
        CORRECTIONS = Path(td) / "corrections"
        try:
            write_correction(Correction("v2", "v3", "reviewer-01", "t",
                                        [Change("p", SPAN_CORRECTION, "a", "b", "  ")]))
            check(False, "a change without a reason is refused")
        except VersionError as e:
            check("needs a reason" in str(e),
                  "a change without a reason is refused")

        try:
            write_correction(Correction("v2", "v3", "a@b.com", "t", [span]))
            check(False, "an email reviewer id is refused")
        except VersionError:
            check(True, "an email reviewer id is refused")

        try:
            write_correction(Correction("v2", "v3", "reviewer-01", "t", []))
            check(False, "an empty correction is refused")
        except VersionError:
            check(True, "an empty correction is refused")

        p = write_correction(c2)
        check(p.exists(), "a valid correction is written")
        rec = json.loads(p.read_text())
        check(rec["comparable_with_previous"] is False,
              "the record states the scores are not comparable")
        check("must not be presented side by side" in rec["why_not_comparable"],
              "...and says why, in words a reader can act on")
        check(rec["counts"][LABEL_CORRECTION] == 1,
              "label and span corrections are counted apart")

        try:
            write_correction(c2)
            check(False, "corrections are write-once")
        except VersionError:
            check(True, "corrections are write-once")
        CORRECTIONS = keep

    # Archives refuse to be overwritten.
    with tempfile.TemporaryDirectory() as td:
        global VERSIONS, CURRENT, MANIFEST
        kv, kc, km = VERSIONS, CURRENT, MANIFEST
        VERSIONS = Path(td) / "versions"
        CURRENT = Path(td) / "approved_pairs.jsonl"
        MANIFEST = Path(td) / "manifest.json"
        CURRENT.write_text('{"pair_id":"x","label":"ENTAILED"}\n')
        MANIFEST.write_text('{"pair_count": 1}\n')

        d = archive("v2")
        check(d.exists() and (d / "approved_pairs.jsonl").exists(),
              "a version is archived with its pairs")
        check((d / "SHA256SUMS").exists(), "...and a checksum file")
        check(verify_archive("v2") == [], "a fresh archive verifies")

        (d / "approved_pairs.jsonl").write_text("tampered\n")
        check(verify_archive("v2") != [], "a tampered archive fails verification")

        try:
            archive("v2")
            check(False, "archiving over an existing version is refused")
        except VersionError as e:
            check("not a version" in str(e),
                  "archiving over an existing version is refused")
        VERSIONS, CURRENT, MANIFEST = kv, kc, km

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
