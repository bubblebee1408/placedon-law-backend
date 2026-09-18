"""On-disk, content-hashed, dated cache. An observation is an artifact.

## Why this is the opposite of ais-store.js on purpose

`server/providers/vessels/ais-store.js` (STEP 1) keeps one mutable, in-memory,
single-actuality cache: a vessel's newest position simply overwrites the last one
(`_aisStreamVessels.set(mmsi, {...})`), and staleness is handled by pruning entries
past `AISSTREAM_STALE_MS`. That is the right design for vessel telemetry, where only
the current fix matters and an old one is worthless once superseded.

It is the wrong design for legal evidence. `checker/acquisition_log.py` exists
because a fetched byte is evidence of what a source said AT A MOMENT, and
overwriting it destroys that evidence the instant a newer fetch arrives -- the
whole reason that log is append-only and hash-chained. This cache follows the same
principle for feed payloads: **content-addressed** (the file name IS the sha256, so
two fetches that happen to return identical bytes collide harmlessly into one file
instead of two) and **dated** (partitioned by the observation's date, so the SAME
url fetched on two different days produces two artifacts side by side, never one
overwriting the other).

## What this module does not decide

It does not decide what an artifact MEANS -- see `checker/feeds/__init__.py`'s
`Observation` for that. This module only proves bytes were fetched and preserves
them exactly, the way `checker/acquisition_log.py` proves an attempt happened
without judging whether the attempt succeeded.

## Tamper evidence, not just storage

`load()` recomputes the hash of what it reads back and refuses to return content
that no longer matches the name it is filed under -- a hand-edited or corrupted
artifact must not be handed back silently as though nothing happened, the same
discipline `checker/acquisition_log.py` applies to its own chain.

Run: python3 checker/feeds/common/cache.py
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from checker.feeds import FetchResult, _require_sha256

CACHE_SCHEMA = "feed_cache/v1"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class CacheError(ValueError):
    """Raised when a stored artifact no longer matches its own name."""


@dataclass(frozen=True)
class CacheEntry:
    """Where one artifact and its metadata live. Frozen: a path handed back does
    not change identity if the caller mutates the object it came from."""
    path: Path
    meta_path: Path
    sha256: str


def _date_part(observed_at: str) -> str:
    """The date component of a bitemporal known_at, for PARTITIONING only -- never
    re-parsed as a timestamp. `checker/feeds/__init__.py` already validates the
    full value; this just needs its first ten characters."""
    m = _DATE.match(observed_at)
    if not m:
        raise ValueError(f"observed_at must start with an ISO-8601 date (YYYY-MM-DD), got {observed_at!r}")
    return m.group(0)


def artifact_path(root: Path, source_id: str, observed_at: str, sha256: str) -> Path:
    """Where this exact artifact lives. Content-addressed: identical bytes fetched
    on the same date always resolve to the same path, deterministically -- no
    directory listing or index is needed to find it again."""
    _require_sha256(sha256, "artifact_path sha256")
    return root / source_id / _date_part(observed_at) / f"{sha256}.bin"


def store(root: Path, result: FetchResult, *, observed_at: str) -> CacheEntry:
    """Persist one fetch's bytes and metadata.

    Idempotent: re-storing identical content for the same (source, date) writes
    nothing new to the content file -- the hash already proves the bytes are
    unchanged, so a second write would only risk a partial-write race for no
    benefit. The metadata sidecar IS rewritten each time (cheap, and captures the
    most recent recording of a repeated observation, e.g. a second fetch on the
    same day that reached the same content by a different route).

    Refuses to cache a refusal: an ACCESSIBLE FetchResult is required, because
    caching a BLOCKED/NOT_FOUND/UNREACHABLE result (with its FetchResult.content
    already validated empty at construction) would be filing an empty artifact
    under a hash that means nothing -- checker/feeds/__init__.py's own invariant
    already forbids that FetchResult from carrying content in the first place.
    """
    if result.source_behaviour != "ACCESSIBLE":
        raise CacheError(
            f"{result.source_id}: refusing to cache a {result.source_behaviour} fetch -- "
            f"only successfully-fetched content is an artifact worth keeping")

    path = artifact_path(root, result.source_id, observed_at, result.sha256)
    meta_path = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(result.content)

    meta = {
        "schema": CACHE_SCHEMA,
        "source_id": result.source_id,
        "url": result.url,
        "sha256": result.sha256,
        "observed_at": observed_at,
        "source_behaviour": result.source_behaviour,
        "http_status": result.http_status,
        "resolved_host": result.resolved_host,
        "note": result.note,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    return CacheEntry(path=path, meta_path=meta_path, sha256=result.sha256)


def load(entry: CacheEntry) -> tuple[bytes, dict]:
    """Read back exactly what was stored. Recomputes the hash and refuses to
    return content that no longer matches the name it is filed under."""
    content = entry.path.read_bytes()
    got = hashlib.sha256(content).hexdigest()
    if got != entry.sha256:
        raise CacheError(
            f"{entry.path}: content hash {got} does not match its filename {entry.sha256} -- "
            f"the artifact was altered after it was written")
    meta = json.loads(entry.meta_path.read_text(encoding="utf-8"))
    if meta.get("schema") != CACHE_SCHEMA:
        raise CacheError(f"{entry.meta_path}: unknown schema {meta.get('schema')!r}; expected {CACHE_SCHEMA!r}")
    return content, meta


def _test() -> None:
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("feeds.common.cache")

    def _fr(source_id="TEST_FEED", url="https://x.gov/a", content=b"hello", behaviour="ACCESSIBLE",
           status=200):
        return FetchResult(source_id=source_id, url=url, sha256=hashlib.sha256(content).hexdigest(),
                           content=content, source_behaviour=behaviour, http_status=status)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        entry = store(root, _fr(), observed_at="2026-09-17")
        check(entry.path.is_file(), "storing writes the content file")
        check(entry.meta_path.is_file(), "...and its metadata sidecar")
        check(entry.path.name == hashlib.sha256(b"hello").hexdigest() + ".bin",
              "the file name IS the content hash -- content-addressed")

        content, meta = load(entry)
        check(content == b"hello", "load() returns exactly what was stored")
        check(meta["source_id"] == "TEST_FEED" and meta["observed_at"] == "2026-09-17",
              "metadata round-trips")
        check(meta["resolved_host"] == "" and "note" in meta,
              "the redirect-audit fields from FetchResult survive into the cache")

        # ── content-addressing: identical bytes on the same date collide on purpose ──
        entry2 = store(root, _fr(url="https://x.gov/b"), observed_at="2026-09-17")
        check(entry2.path == entry.path,
              "identical content on the same date resolves to the SAME artifact path -- "
              "a second fetch that agrees with the first does not duplicate storage")

        # ── dated: the SAME content on a DIFFERENT date is a SEPARATE artifact ──────
        entry3 = store(root, _fr(), observed_at="2026-09-18")
        check(entry3.path != entry.path,
              "the same bytes observed on a different date get a DIFFERENT path -- "
              "two observations are two pieces of evidence, even if the source didn't change")
        check(entry3.path.parent.parent == entry.path.parent.parent,
              "...but they still live under the same source_id root")

        # ── different content never collides ────────────────────────────────────────
        entry4 = store(root, _fr(content=b"different bytes"), observed_at="2026-09-17")
        check(entry4.path != entry.path, "different content on the same date gets a different path")

        # ── refusing to cache a non-ACCESSIBLE result ───────────────────────────────
        refused = FetchResult(source_id="TEST_FEED", url="https://x.gov/missing",
                              sha256=hashlib.sha256(b"").hexdigest(), content=b"",
                              source_behaviour="NOT_FOUND", http_status=404)
        try:
            store(root, refused, observed_at="2026-09-17")
            check(False, "storing a NOT_FOUND FetchResult must be refused")
        except CacheError as e:
            check("refusing to cache" in str(e), f"...and it is: {e}")

        # ── tamper evidence ──────────────────────────────────────────────────────────
        entry.path.write_bytes(b"tampered")
        try:
            load(entry)
            check(False, "loading a tampered artifact must raise")
        except CacheError as e:
            check("altered" in str(e), f"...and it does: {e}")
        entry.path.write_bytes(b"hello")  # restore, so later assertions in this block are clean

        # ── malformed observed_at is rejected before touching the filesystem ────────
        try:
            artifact_path(root, "X", "not-a-date", hashlib.sha256(b"x").hexdigest())
            check(False, "a non-ISO observed_at must be rejected")
        except ValueError:
            check(True, "a non-ISO observed_at is rejected before any path is built")

        try:
            artifact_path(root, "X", "2026-09-17", "not-a-hash")
            check(False, "a malformed sha256 must be rejected")
        except ValueError:
            check(True, "a malformed sha256 is rejected before any path is built")

        # ── a doctored metadata schema is refused at load, like acquisition_log.py ──
        doctored_meta = json.loads(entry.meta_path.read_text(encoding="utf-8"))
        doctored_meta["schema"] = "feed_cache/v0"
        entry.meta_path.write_text(json.dumps(doctored_meta), encoding="utf-8")
        try:
            load(entry)
            check(False, "an unknown metadata schema must be refused")
        except CacheError as e:
            check("unknown schema" in str(e), f"...and it is: {e}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
