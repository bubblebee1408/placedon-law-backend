#!/usr/bin/env python3
"""Where a vault's bytes live. Local and Azure Blob are supported; S3 stays blocked.

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

## Azure Blob uses workload identity; S3 remains BLOCKED

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
import logging
import re
import os
import tempfile
from urllib.parse import urlsplit
from dataclasses import dataclass
from pathlib import Path

__all__ = ["FileStoreError", "FileStoreBlocked", "FileStoreUnavailable",
           "LocalFileStore", "AzureBlobFileStore", "S3FileStore",
           "digest", "MAX_BYTES"]

# One file. A vault holds twenty thousand of them, and the limit that matters for the
# machine is the archive guard's, not this one; this refuses the single absurd upload.
MAX_BYTES = 512 * 1024 * 1024

_KEY = re.compile(r"^[0-9a-f]{64}$")


class FileStoreError(RuntimeError):
    """A store that cannot do what was asked."""


class FileStoreBlocked(FileStoreError):
    """A backend that exists and is deliberately not available yet."""


class FileStoreUnavailable(FileStoreError):
    """A configured backing store could not serve this operation right now."""

    def __init__(self, message: str, *, retryable: bool = True,
                 status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


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
            descriptor, temporary = tempfile.mkstemp(prefix=".upload-", suffix=".part", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(bytes(data))
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
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
class AzureBlobFileStore:
    """Private Azure container storage using an Entra managed identity.

    The container is provisioned separately with public access disabled. No account key or
    SAS token is accepted here. `client` is injectable for the no-network contract tests;
    production construction uses DefaultAzureCredential.
    """
    account_url: str
    container: str
    client: object | None = None
    kind: str = "azure-blob"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.account_url)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if (parsed.scheme != "https" or not parsed.hostname
                or not re.fullmatch(r"[a-z0-9]{3,24}\.blob\.core\.windows\.net",
                                    parsed.hostname.lower())
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or port not in (None, 443)):
            raise FileStoreError(
                "Azure Blob URL must be an account host in Azure public cloud over HTTPS"
            )
        if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]", self.container)
                or "--" in self.container):
            raise FileStoreError("Azure Blob container name is invalid")
        if self.client is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.storage.blob import BlobServiceClient
            except ImportError:
                raise FileStoreBlocked(
                    "Azure Blob support requires azure-identity and azure-storage-blob"
                ) from None
            service = BlobServiceClient(
                account_url=self.account_url,
                credential=DefaultAzureCredential(),
            )
            self.client = service.get_container_client(self.container)

    @staticmethod
    def _validate_key(key: str) -> str:
        if not _KEY.fullmatch(key or ""):
            raise FileStoreError("blob key must be a lowercase sha256")
        return key

    @staticmethod
    def _failure(operation: str, exc: Exception) -> FileStoreError:
        # Keep useful operator diagnostics without logging SDK messages, URLs, or tokens.
        status = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) or {}
        request_id = headers.get("x-ms-request-id") if hasattr(headers, "get") else None
        logging.getLogger(__name__).warning(
            "azure_blob_operation_failed",
            extra={"operation": operation, "exception_type": type(exc).__name__,
                   "status_code": status, "request_id": request_id})
        retryable = status is None or status in (408, 429) or (isinstance(status, int) and status >= 500)
        reason = "temporarily unavailable" if retryable else "is not accessible"
        return FileStoreUnavailable(f"Azure Blob {operation} {reason}",
                                    retryable=retryable, status_code=status)

    @staticmethod
    def _not_found(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) == 404

    def put(self, data: bytes) -> str:
        if not isinstance(data, (bytes, bytearray)):
            raise FileStoreError(f"bytes are required, got {type(data).__name__}")
        body = bytes(data)
        if len(body) > MAX_BYTES:
            raise FileStoreError(f"{len(body)} bytes is over the {MAX_BYTES} limit for one file")
        key = digest(body)
        blob = self.client.get_blob_client(key)
        try:
            blob.upload_blob(body, overwrite=False)
            return key
        except Exception as exc:
            if getattr(exc, "status_code", None) not in (409, 412):
                raise self._failure("upload", exc) from None
        existing = self.get(key)
        if existing == body:
            return key
        if existing is not None:
            raise FileStoreError("Azure Blob content does not match its sha256 key")
        # A concurrent delete may race the conflict response. Recreate the same content;
        # its content-addressed key makes this overwrite deterministic and idempotent.
        try:
            blob.upload_blob(body, overwrite=True)
            return key
        except Exception as exc:
            raise self._failure("upload", exc) from None

    def get(self, key: str) -> bytes | None:
        blob = self.client.get_blob_client(self._validate_key(key))
        try:
            data = blob.download_blob().readall()
        except Exception as exc:
            if self._not_found(exc):
                return None
            raise self._failure("download", exc) from None
        if digest(data) != key:
            raise FileStoreError("Azure Blob content does not match its sha256 key")
        return data

    def exists(self, key: str) -> bool:
        blob = self.client.get_blob_client(self._validate_key(key))
        try:
            return bool(blob.exists())
        except Exception as exc:
            if self._not_found(exc):
                return False
            raise self._failure("exists", exc) from None

    def delete(self, key: str) -> bool:
        blob = self.client.get_blob_client(self._validate_key(key))
        try:
            blob.delete_blob()
            return True
        except Exception as exc:
            if self._not_found(exc):
                return False
            raise self._failure("delete", exc) from None

    def check_ready(self) -> None:
        """Verify the pre-created container exists and this identity can access it."""
        try:
            if not self.client.exists():
                raise FileStoreUnavailable("Azure Blob vault container does not exist",
                                           retryable=False, status_code=404)
        except FileStoreUnavailable:
            raise
        except Exception as exc:
            raise self._failure("readiness check", exc) from None


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

    # ── Azure Blob contract, without cloud credentials or network access ────
    class FakeAzureError(RuntimeError):
        def __init__(self, status_code: int, message: str = ""):
            self.status_code = status_code
            super().__init__(message)

    class FakeDownload:
        def __init__(self, data: bytes):
            self.data = data

        def readall(self) -> bytes:
            return self.data

    class FakeAzureBlob:
        def __init__(self, blobs: dict[str, bytes], key: str):
            self.blobs, self.key = blobs, key

        def upload_blob(self, data: bytes, *, overwrite: bool) -> None:
            if self.key in self.blobs and not overwrite:
                raise FakeAzureError(409)
            self.blobs[self.key] = bytes(data)

        def download_blob(self) -> FakeDownload:
            if self.key not in self.blobs:
                raise FakeAzureError(404)
            return FakeDownload(self.blobs[self.key])

        def exists(self) -> bool:
            return self.key in self.blobs

        def delete_blob(self) -> None:
            if self.key not in self.blobs:
                raise FakeAzureError(404)
            del self.blobs[self.key]

    class FakeAzureContainer:
        def __init__(self):
            self.blobs: dict[str, bytes] = {}

        def exists(self) -> bool:
            return True

        def get_blob_client(self, key: str) -> FakeAzureBlob:
            return FakeAzureBlob(self.blobs, key)

    container = FakeAzureContainer()
    azure = AzureBlobFileStore(
        "https://placedon.blob.core.windows.net", "vault", client=container,
    )
    try:
        azure.check_ready()
        check(True, "Azure Blob readiness confirms an accessible container")
    except FileStoreError:
        check(False, "Azure Blob readiness confirms an accessible container")
    azure_data = b"synthetic staging document"
    azure_key = azure.put(azure_data)
    check(azure_key == digest(azure_data) and azure.get(azure_key) == azure_data,
          "Azure Blob writes and reads content-addressed bytes")
    check(azure.put(azure_data) == azure_key and len(container.blobs) == 1,
          "parallel-safe duplicate upload is idempotent after conflict check")
    check(azure.exists(azure_key) and azure.get("0" * 64) is None,
          "Azure existence and not-found responses have explicit results")
    check(azure.delete(azure_key) and not azure.delete(azure_key),
          "Azure delete is idempotent and treats an absent blob as already deleted")
    try:
        AzureBlobFileStore("http://insecure.example", "vault", client=container)
        check(False, "Azure Blob refuses an insecure account URL")
    except FileStoreError:
        check(True, "Azure Blob refuses an insecure account URL")
    for untrusted_url in (
        "https://storage.blob.core.windows.net.attacker.example",
        "https://attacker.example",
        "https://placedon.blob.core.windows.net:8443",
    ):
        try:
            AzureBlobFileStore(untrusted_url, "vault", client=container)
            check(False, "managed identity refuses an untrusted Blob endpoint")
        except FileStoreError:
            check(True, "managed identity refuses an untrusted Blob endpoint")
    try:
        AzureBlobFileStore("https://safe.example", "bad--container", client=container)
        check(False, "Azure Blob refuses an invalid container name")
    except FileStoreError:
        check(True, "Azure Blob refuses an invalid container name")
    try:
        azure.get("../outside")
        check(False, "Azure Blob validates object keys before requesting them")
    except FileStoreError:
        check(True, "Azure Blob validates object keys before requesting them")
    container.blobs["0" * 64] = b"tampered"
    try:
        azure.get("0" * 64)
        check(False, "Azure Blob detects a body whose digest differs from its key")
    except FileStoreError:
        check(True, "Azure Blob detects a body whose digest differs from its key")
    class FakeFailingBlob:
        def upload_blob(self, data: bytes, *, overwrite: bool) -> None:
            raise FakeAzureError(503, "credential=secret-value")

    class FakeFailingContainer:
        def get_blob_client(self, key: str) -> FakeFailingBlob:
            return FakeFailingBlob()

    try:
        AzureBlobFileStore(
            "https://placedon.blob.core.windows.net", "vault",
            client=FakeFailingContainer(),
        ).put(b"test")
        check(False, "Azure outages surface as safe store errors")
    except FileStoreError as exc:
        check("credential=secret-value" not in str(exc),
              "Azure SDK errors are surfaced without leaking response details")
        check(isinstance(exc, FileStoreUnavailable) and exc.retryable,
              "transient Azure 503 failures are classified as retryable")
    _forbidden = AzureBlobFileStore._failure("upload", FakeAzureError(403, "private detail"))
    check(isinstance(_forbidden, FileStoreUnavailable) and not _forbidden.retryable
          and "private detail" not in str(_forbidden),
          "Azure permission failures are non-retryable and sanitized")

    class MissingAzureContainer(FakeAzureContainer):
        def exists(self) -> bool:
            return False

    try:
        AzureBlobFileStore(
            "https://placedon.blob.core.windows.net", "vault",
            client=MissingAzureContainer(),
        ).check_ready()
        check(False, "an absent Azure container blocks service startup")
    except FileStoreUnavailable:
        check(True, "an absent Azure container blocks service startup")

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
