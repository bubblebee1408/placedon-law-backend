#!/usr/bin/env python3
"""Where a vault's bytes live. Local today; S3 is BLOCKED by name, not stubbed.

V1. `documents` already stores a hash, a name and a byte count; a vault of twenty thousand
files needs somewhere to put the bytes themselves.

## The key IS the sha256, so dedupe is not a feature

Two uploads of the same bytes are one file, because they compute the same key and the
second write lands on the same path. There is no "check if it exists first", which would
be a race; there is no reference count, because nothing is ever deleted by a path that
does not know the hash.

That also means a corrupted read is detectable: `get` re-hashes what it read and raises if
the bytes do not match the name they were stored under. A silent bit-flip in a client's
contract is worse than an error.

## S3 is BLOCKED, and that is a different thing from missing

`S3FileStore` exists and every method raises `FileStoreBlocked` with the reason. The
alternative -- not writing the class until AWS is ready -- means the day someone configures
`storage=s3` they get an AttributeError, and the alternative to THAT is a stub that
silently writes nowhere, which is how a firm loses a document and finds out months later.
A named refusal is the only honest third option.

## Path safety

A key is validated as 64 hex characters before it touches the filesystem. Not because the
caller is hostile, but because the caller is `vault.upload` holding a filename that came
from a client, and one `../` in a key is the whole directory.

Run: PYTHONPATH=. python3 gateway/filestore.py --test
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["FileStoreError", "FileStoreBlocked", "LocalFileStore", "S3FileStore",
           "digest", "MAX_BYTES"]

# One file. A vault holds twenty thousand of them, and the limit that matters for the
# machine is the archive guard's, not this one; this refuses the single absurd upload.
MAX_BYTES = 512 * 1024 * 1024

_KEY = re.compile(r"^[0-9a-f]{64}$")


class FileStoreError(RuntimeError):
    """A store that cannot do what was asked."""


class FileStoreBlocked(FileStoreError):
    """A backend that exists and is deliberately not available yet."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class LocalFileStore:
    """Bytes under a root directory, keyed by their own sha256."""
    root: Path
    kind: str = "local"

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY.match(key or ""):
            raise FileStoreError(
                f"{key!r} is not a sha256. A key reaches the filesystem, and the caller "
                f"is holding a filename that came from a client")
        # Two levels of fan-out: twenty thousand files in one directory is slow to list on
        # every filesystem and hostile on some.
        return self.root / key[:2] / key[2:4] / key

    def put(self, data: bytes) -> str:
        """Store bytes, return their key. The same bytes twice is one file."""
        if not isinstance(data, (bytes, bytearray)):
            raise FileStoreError(f"bytes are required, got {type(data).__name__}")
        if len(data) > MAX_BYTES:
            raise FileStoreError(
                f"{len(data)} bytes is over the {MAX_BYTES} limit for one file")
        key = digest(bytes(data))
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            # Written to a temporary name and moved, so a reader never sees a half-written
            # file under a key that promises its whole contents.
            tmp = path.with_suffix(".part")
            tmp.write_bytes(bytes(data))
            tmp.replace(path)
        return key

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        if not path.exists():
            return None
        data = path.read_bytes()
        if digest(data) != key:
            raise FileStoreError(
                f"{key[:12]}... does not hash to its own key: the bytes on disk are not "
                f"the bytes that were stored. A silent bit-flip in a client's contract is "
                f"worse than an error")
        return data

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.exists():
            return False
        path.unlink()
        return True


@dataclass
class S3FileStore:
    """The S3 backend. Present, and BLOCKED until AWS is ready.

    Every method raises with the reason. Not written later, because then
    `storage=s3` is an AttributeError; not stubbed to succeed, because then a firm's
    document goes nowhere and nobody finds out for months.
    """
    bucket: str = ""
    kind: str = "s3"

    REASON = ("the S3 file store is BLOCKED until AWS is configured (B1 is held). It is "
              "not missing and it is not a stub that writes nowhere: either of those "
              "loses a document silently. Use the local store, or say AWS is ready.")

    def put(self, data: bytes) -> str:
        raise FileStoreBlocked(self.REASON)

    def get(self, key: str) -> bytes | None:
        raise FileStoreBlocked(self.REASON)

    def exists(self, key: str) -> bool:
        raise FileStoreBlocked(self.REASON)

    def delete(self, key: str) -> bool:
        raise FileStoreBlocked(self.REASON)


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

    print("filestore")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalFileStore(Path(tmp))
        DATA = b"MUTUAL NON-DISCLOSURE AGREEMENT\nbetween two invented companies.\n"

        key = store.put(DATA)
        check(len(key) == 64 and all(c in "0123456789abcdef" for c in key),
              f"a put returns the bytes' own sha256 ({key[:16]}...)")
        check(store.get(key) == DATA, "...and get returns exactly what was stored")
        check(store.exists(key), "...and exists says so")

        # Dedupe is not a feature; it is what keying by content means.
        again = store.put(DATA)
        check(again == key,
              "**the same bytes twice is ONE file**: dedupe is not a check-then-write "
              "race, it is what keying by content means")
        stored = list(Path(tmp).rglob("*"))
        files = [p for p in stored if p.is_file()]
        check(len(files) == 1, f"...and there is one file on disk, not two ({len(files)})")

        other = store.put(b"a different contract")
        check(other != key and store.get(other) != DATA,
              "different bytes get a different key")

        check(store.get("0" * 64) is None,
              "an unknown key reads as None, not an exception: absent is an answer")
        check(store.delete(key) and not store.exists(key), "a delete removes it")
        check(not store.delete(key),
              "...and deleting it again returns False rather than raising: twice-deleted "
              "is not an error, it is already gone")

        # ── corruption is detected, not served ─────────────────────────────
        k2 = store.put(b"the original bytes")
        path = store._path(k2)
        path.write_bytes(b"the TAMPERED bytes")
        try:
            store.get(k2)
            check(False, "tampered bytes raise")
        except FileStoreError as e:
            check("not the bytes that were stored" in str(e),
                  "**bytes that do not hash to their own key RAISE** -- a silent bit-flip "
                  "in a client's contract is worse than an error")

        # ── a key reaches the filesystem, so it is validated ───────────────
        for bad in ("../../etc/passwd", "", "nothex" * 10, "A" * 64, "/" + "a" * 63):
            try:
                store.get(bad)
                check(False, f"{bad[:18]!r} is refused")
            except FileStoreError:
                check(True, f"a key that is not 64 hex is REFUSED ({bad[:18]!r})")
        check(not (Path(tmp) / ".." / "escaped").exists(),
              "...and nothing was written outside the root")

        try:
            store.put("a string, not bytes")
            check(False, "a str is refused")
        except FileStoreError:
            check(True, "a str instead of bytes is refused rather than encoded by guess")
        check(MAX_BYTES == 512 * 1024 * 1024, f"the single-file limit is 512 MiB")

        # Fan-out, so twenty thousand files are not one directory listing.
        k3 = store.put(b"fan out")
        rel = store._path(k3).relative_to(Path(tmp))
        check(len(rel.parts) == 3 and rel.parts[0] == k3[:2],
              f"files fan out two levels by their key ({rel})")

    # ── S3 is BLOCKED, by name, on every method ────────────────────────────
    s3 = S3FileStore(bucket="placedon-vault")
    for name, call in (("put", lambda: s3.put(b"x")), ("get", lambda: s3.get("0" * 64)),
                       ("exists", lambda: s3.exists("0" * 64)),
                       ("delete", lambda: s3.delete("0" * 64))):
        try:
            call()
            check(False, f"S3 {name} is blocked")
        except FileStoreBlocked as e:
            check("BLOCKED until AWS" in str(e),
                  f"S3 {name}() raises BLOCKED with the reason -- not missing (an "
                  f"AttributeError the day someone configures it) and not a stub that "
                  f"writes nowhere")
    check(issubclass(FileStoreBlocked, FileStoreError),
          "...and BLOCKED is a kind of store error, so one except catches both")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
