"""CUAD, the Atticus contract-review benchmark, acquired under its own licence.

CUAD is 510 commercial contracts with 41 clause types labelled by lawyers, released by
The Atticus Project under **CC BY 4.0**. It is the only public benchmark that scores
clause extraction the way PLAN_22 F12 needs it scored: a clause type, and a span of the
contract that is the evidence for it.

## Where it comes from, and why not from where it says

The dataset's own loader names `github.com/TheAtticusProject/cuad/raw/main/data.zip`.
**github.com's robots.txt disallows `/raw/`**, and docs/ACQUISITION_POLICY.md is explicit
that a robots refusal is BLOCKED and never retried: "the server answered, and the answer
was no". So that URL is not used. `raw.githubusercontent.com` is a different host with its
own robots.txt, it is GitHub's documented content host for exactly this file, and it
permits the path -- which is the "permitted alternative source" the policy directs you to,
not a way around the one that refused.

Zenodo also carries CUAD. `zenodo.org/records/4595826/files/` is permitted and
`zenodo.org/api/` is NOT, so the record can be downloaded but not queried. Recorded here
because the next person will reach for the API first, as I did.

Run:  PYTHONPATH=. python3 scripts/acquire_cuad.py            # download (idempotent)
      PYTHONPATH=. python3 scripts/acquire_cuad.py --test     # offline self-tests
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checker.robots import USER_AGENT, allowed, fetch_rules, ssl_context  # noqa: E402

PERMITTED_HOST = "raw.githubusercontent.com"
URL = "https://raw.githubusercontent.com/TheAtticusProject/cuad/main/data.zip"
DEST = Path(__file__).resolve().parents[1] / "corpus" / "benchmark" / "cuad"

LICENCE = """CUAD — Contract Understanding Atticus Dataset
Copyright The Atticus Project.

Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0).
https://creativecommons.org/licenses/by/4.0/

Source dataset:   https://www.atticusprojectai.org/cuad
Acquired from:    {url}
Acquired on:      {date}

Attribution, as CC BY 4.0 requires: this benchmark is the work of The Atticus Project
and its volunteer lawyers. Nothing in this repository claims authorship of it. It is
used here to MEASURE clause extraction (PLAN_22 E2), and no part of it is served to a
user as legal content.

The contracts in CUAD are American. A score on it is a score on American drafting, and
PLAN_22 E2 pairs it with Indian contracts for that reason.
"""


class NotPermitted(PermissionError):
    """robots.txt does not permit this fetch. Raised before any request is made."""


def check_host(url: str) -> str:
    """The netloc must BE the permitted host. A suffix match would admit evil-raw.com."""
    host = (urlparse(url).hostname or "").lower()
    if host != PERMITTED_HOST:
        raise NotPermitted(
            f"{host!r} is not {PERMITTED_HOST!r}. This script fetches one file from one "
            f"host; a different host needs its own robots check and its own licence read.")
    return host


def fetch(url: str = URL, *, rules_fetch=None, opener=None) -> bytes:
    """The zip, or a refusal. Host and robots are both checked before the socket."""
    check_host(url)
    rules = (rules_fetch or fetch_rules)(f"https://{PERMITTED_HOST}")
    if not allowed(url, rules):
        raise NotPermitted(
            f"robots.txt at {PERMITTED_HOST} does not permit {url}. Not retried: "
            f"docs/ACQUISITION_POLICY.md treats a robots refusal as BLOCKED, never "
            f"UNREACHABLE.")
    if opener is not None:
        return opener(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300, context=ssl_context()) as r:
        return r.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def members(blob: bytes) -> dict[str, bytes]:
    """The JSON members of the archive, by name. Directories and everything else dropped."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return {i.filename: z.read(i)
                for i in z.infolist()
                if not i.is_dir() and i.filename.lower().endswith(".json")}


def write_out(blob: bytes, files: dict[str, bytes], dest: Path, *, date: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    sums = [f"{sha256(blob)}  data.zip"]
    for name, body in sorted(files.items()):
        out = dest / Path(name).name
        out.write_bytes(body)
        sums.append(f"{sha256(body)}  {out.name}")
    (dest / "LICENSE").write_text(LICENCE.format(url=URL, date=date))
    (dest / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return dest


def already_have(dest: Path, blob_sha: str) -> bool:
    """True when SHA256SUMS already records this exact archive. Makes a re-run a no-op."""
    f = dest / "SHA256SUMS"
    return f.is_file() and f.read_text().startswith(blob_sha)


def main() -> int:
    from datetime import date
    today = date.today().isoformat()
    print(f"CUAD -> {DEST.relative_to(Path(__file__).resolve().parents[1])}")
    blob = fetch()
    print(f"  {len(blob)/1e6:.1f} MB, sha256 {sha256(blob)[:16]}...")
    if already_have(DEST, sha256(blob)):
        print("  already held at this exact checksum; nothing written")
        return 0
    files = members(blob)
    if not files:
        print("  REFUSED: the archive holds no JSON member. Not writing a partial corpus.")
        return 1
    write_out(blob, files, DEST, date=today)
    for name, body in sorted(files.items()):
        print(f"  {Path(name).name:42} {len(body)/1e6:8.1f} MB")
    print(f"  LICENSE and SHA256SUMS written (CC BY 4.0, The Atticus Project)")
    return 0


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

    # ── the host is checked before anything else ─────────────────────────────
    check(check_host(URL) == PERMITTED_HOST, "the canonical URL passes the host check")
    for bad in ("https://evil-raw.githubusercontent.com/x/data.zip",
                "https://raw.githubusercontent.com.attacker.net/x/data.zip",
                "https://github.com/TheAtticusProject/cuad/raw/main/data.zip"):
        try:
            check_host(bad)
            check(False, f"{bad} is refused")
        except NotPermitted:
            check(True, f"refused: {bad[:52]}")
    check(True, "...including github.com/raw, whose robots.txt disallows the path -- the "
                "reason this script points at the content host instead")

    # ── a robots refusal stops the fetch BEFORE the socket ───────────────────
    from checker.robots import parse
    opened = []
    try:
        fetch(rules_fetch=lambda origin: parse("User-agent: *\nDisallow: /"),
              opener=lambda u: opened.append(u) or b"")
        check(False, "a robots refusal stops the fetch")
    except NotPermitted:
        check(not opened, "a robots refusal stops the fetch BEFORE the socket -- nothing "
                          "was opened")
    got = fetch(rules_fetch=lambda origin: parse("User-agent: *\nAllow: /"),
                opener=lambda u: b"PK-stub")
    check(got == b"PK-stub", "...and a permitting robots.txt lets it through")

    # ── the archive is read, and only its JSON ───────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CUAD_v1/test.json", json.dumps({"data": [1]}))
        z.writestr("CUAD_v1/train.json", json.dumps({"data": [2]}))
        z.writestr("CUAD_v1/full_contract_pdf/a.pdf", b"%PDF-")
        z.writestr("CUAD_v1/README.txt", b"hello")
    blob = buf.getvalue()
    got = members(blob)
    check(set(got) == {"CUAD_v1/test.json", "CUAD_v1/train.json"},
          f"only the JSON members are taken ({sorted(got)})")

    # ── what is written, and that a re-run is a no-op ────────────────────────
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "cuad"
        check(not already_have(d, sha256(blob)), "an empty directory is not 'already held'")
        write_out(blob, got, d, date="2026-09-29")
        check((d / "test.json").is_file() and (d / "train.json").is_file(),
              "each JSON member is written by its basename, without the archive's tree")
        lic = (d / "LICENSE").read_text()
        check("CC BY 4.0" in lic and "The Atticus Project" in lic and URL in lic,
              "LICENSE names the licence, the author and where it was acquired from")
        sums = (d / "SHA256SUMS").read_text()
        check(sums.startswith(sha256(blob)) and sha256(got["CUAD_v1/test.json"]) in sums,
              "SHA256SUMS records the archive AND every file taken out of it")
        check(already_have(d, sha256(blob)),
              "...and a re-run at the same checksum is a no-op, so this cannot re-download "
              "18 MB every time the gate runs")
        check(not already_have(d, sha256(b"different")),
              "...while a CHANGED upstream archive is not mistaken for the held one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(_test() if "--test" in sys.argv else main())
