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
from checker.doc_verification import verify_document as _vd  # noqa: E402

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


# Exit codes are not ordered by severity — 3 (incomplete) is numerically larger
# than 1 (modified) but far less serious — so aggregating with max() would report
# "incomplete" for a batch containing an altered document. Precedence is explicit.
_SEVERITY = [1, 2, 4, 3, 0]      # modified > unsupported > config > incomplete > ok


def _worst(codes: list[int]) -> int:
    for c in _SEVERITY:
        if c in codes:
            return c
    return 0


def run(paths: list[str], as_json: bool) -> int:
    results = []
    # Tracks only files we could not open. Whether a signature verified is
    # already carried by each document's own exit code; folding the two together
    # made a batch containing one UNSUPPORTED document report "modified".
    missing_file = False
    for p in paths:
        f = Path(p)
        if not f.exists():
            print(f"{p}: no such file", file=sys.stderr)
            missing_file = True
            continue
        results.append((f, verify(f)))

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
                "verification": json.loads(_vd(f).to_json()),
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
        codes = [_vd(f, offline=True).exit_code() for f, _ in results]
        return _worst(codes + ([1] if missing_file else []))

    from checker.doc_verification import verify_document
    for f, r in results:
        v = verify_document(f, offline=as_json is None)
        print(f"\n{f.name}")
        rows = [("File structure", "PASS" if r.verdict != MALFORMED else "FAIL"),
                ("PDF signature", v.signature),
                ("Signed byte integrity", v.file_integrity),
                ("Unsigned appended content",
                 "FOUND" if r.uncovered_ranges else "NOT_FOUND"),
                ("Certificate chain", v.certificate_chain),
                ("Certificate validity at signing", v.certificate_validity_at_signing),
                ("Revocation", v.detail.get("revocation", {}).get("status", "NOT_CHECKED")),
                ("Trusted timestamp", v.trusted_timestamp),
                ("Official issuer match", v.official_issuer_match),
                ("Official record match", v.official_record_match)]
        for k, val in rows:
            print(f"  {k:<34}{val}")
        if r.chain_names:
            print(f"  {'Chain':<34}{' <- '.join(r.chain_names)}")
        print(f"\n  Overall: {v.overall_status}")
        print(f"  {v.sentence()}")

    codes = [_vd(f, offline=True).exit_code() for f, _ in results]
    return _worst(codes + ([1] if missing_file else []))


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
    from checker.doc_verification import (EXIT_INCOMPLETE, EXIT_MODIFIED,
                                          EXIT_UNSUPPORTED, EXIT_CONFIG)
    check({EXIT_INCOMPLETE, EXIT_MODIFIED, EXIT_UNSUPPORTED, EXIT_CONFIG} == {3, 1, 2, 4},
          "the documented exit-code contract is what the code uses")
    # The batch contains one document whose signing mode we do not implement, and
    # 2 outranks 3 — so the batch code is 2. Asserting 3 here was wrong about the
    # corpus, not about the code.
    code = run([str(p) for p in signed], as_json=True)
    check(code == EXIT_UNSUPPORTED,
          f"a batch containing an unsupported signature exits 2 ({code})")
    supported = [str(p) for p in signed if verify(p).verdict == VALID]
    check(run(supported, as_json=True) == EXIT_INCOMPLETE,
          "documents with valid signatures still exit 3 — none is fully verified")
    check(run(supported, as_json=True) != 0,
          "no real document exits 0; full verification needs a trusted timestamp")
    check(run(["/nonexistent.pdf"], as_json=True) == 1,
          "a missing file is an error, not a silent pass")
    check(_worst([3, 1]) == 1,
          "a modified document outranks an incomplete one, despite 3 > 1")
    check(_worst([3, 2]) == 2, "an unsupported signature outranks incomplete")
    check(_worst([3, 3]) == 3 and _worst([0]) == 0, "otherwise the code passes through")

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
