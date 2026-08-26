#!/usr/bin/env python3
"""Is this document real?

    python3 scripts/verify_document.py <file.pdf> [more.pdf ...]
    python3 scripts/verify_document.py --json <file.pdf>
    python3 scripts/verify_document.py --test

Answers cryptographically, not probabilistically. Exit status is 0 only when every
document given is VALID, so this can gate a workflow.

Read `checker/pdf_signature.py` for what a VALID verdict does and does not mean.
The short version: it proves the bytes have not changed since signing and names
the certificate that signed them. It does not prove the signer had authority, that
the contents are true, or that the certificate was unrevoked at signing time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.pdf_signature import (  # noqa: E402
    COVERAGE_INCOMPLETE, MALFORMED, MODIFIED, UNSIGNED, UNSUPPORTED, VALID, verify,
)

# What each verdict means to someone who is not a cryptographer.
PLAIN = {
    VALID: "Signed and unmodified since signing.",
    MODIFIED: "ALTERED after signing. Do not rely on this document.",
    COVERAGE_INCOMPLETE: "Signature is genuine but does NOT cover the whole file — "
                         "content was added that nobody signed.",
    UNSIGNED: "No digital signature. Authenticity cannot be established from the file.",
    MALFORMED: "A signature is present but unreadable. Treat as unverified.",
    UNSUPPORTED: "Signature uses a form this tool does not implement. "
                 "Not a finding about the document — verify it another way.",
}


def run(paths: list[str], as_json: bool) -> int:
    results = []
    worst_ok = True
    for p in paths:
        f = Path(p)
        if not f.exists():
            print(f"{p}: no such file", file=sys.stderr)
            worst_ok = False
            continue
        r = verify(f)
        results.append((f, r))
        if r.verdict != VALID:
            worst_ok = False

    if as_json:
        out = []
        for f, r in results:
            out.append({
                "file": str(f),
                "verdict": r.verdict,
                "meaning": PLAIN.get(r.verdict, ""),
                "signer": r.signer.name if r.signer else None,
                "issuer": r.signer.issuer_name if r.signer else None,
                "signing_time": r.signing_time.isoformat() if r.signing_time else None,
                "digest": r.digest_alg or None,
                "signature_verified": r.signature_verified,
                "chains_to_cca_india": r.chains_to_cca,
                "chain_verdict": r.chain_verdict or None,
                "chain_root": r.chain_root or None,
                "chain_path": r.chain_names or None,
                "revocation_checked": r.revocation_checked,
                "covered_bytes": r.covered_bytes,
                "total_bytes": r.total_bytes,
                "unsigned_ranges": r.uncovered_ranges,
                "note": r.note,
            })
        print(json.dumps(out, indent=2))
        return 0 if worst_ok else 1

    for f, r in results:
        mark = "PASS" if r.verdict == VALID else "FAIL"
        print(f"\n[{mark}] {f.name}")
        print(f"  {PLAIN.get(r.verdict, r.verdict)}")
        print(r.summary())
        if r.chain_names:
            print(f"  chain              : {' <- '.join(r.chain_names)}")

    if results:
        n_ok = sum(1 for _, r in results if r.verdict == VALID)
        print(f"\n{n_ok}/{len(results)} verified as signed and unmodified.")
        if not worst_ok:
            print("Revocation is never checked by this tool; a valid signature does "
                  "not prove the signer's authority.")
    return 0 if worst_ok else 1


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

    print("verify_document")

    check(set(PLAIN) == {VALID, MODIFIED, COVERAGE_INCOMPLETE, UNSIGNED, MALFORMED,
                         UNSUPPORTED},
          "every verdict has a plain-language meaning")
    from checker.pdf_signature import SignatureResult
    check(SignatureResult(VALID).chains_to_cca is False,
          "chain trust defaults to false, never assumed from a valid signature")
    check("Do not rely" in PLAIN[MODIFIED],
          "the MODIFIED wording tells the reader not to rely on the document")
    check("not a finding about the document" in PLAIN[UNSUPPORTED].lower(),
          "UNSUPPORTED is not presented as a defect in the document")

    signed = [p for p in sorted(Path("corpus/testdocs/_raw").glob("*.pdf"))
              if b"/ByteRange" in p.read_bytes()]
    check(run([str(p) for p in signed if verify(p).verdict == VALID], as_json=True) == 0,
          "exit status is 0 when every document is VALID")
    check(run(["/nonexistent.pdf"], as_json=True) == 1,
          "a missing file is an error, not a silent pass")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if "--test" in args:
        _test()
    elif not args:
        print(__doc__)
        raise SystemExit(2)
    else:
        as_json = "--json" in args
        raise SystemExit(run([a for a in args if not a.startswith("--")], as_json))
