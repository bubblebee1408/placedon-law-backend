"""Document verification as separate dimensions, never as one verdict.

A document is not "real" or "fake". Those words compress a dozen independent
facts into one, and the compression is where the misleading happens: a file can
be cryptographically perfect and still be a forgery of a document that was never
issued, or genuinely issued and cryptographically broken by a careless re-save.

So verification returns an object, and `overall_status` is `COMPLETE` only when
every dimension that matters has actually been established. Anything else is
`INCOMPLETE_VERIFICATION`, which is a statement about *our knowledge*, not about
the document.

The user-facing sentence this produces is deliberately unexciting:

    The digital signature validates and the signed bytes have not changed.
    Certificate revocation and official-record matching were not completed, so
    the system does not determine that the document is legally genuine.

## Dimensions

    file_integrity                  the signed byte ranges hash as signed
    signature                       the PKCS#7 signature verifies
    certificate_chain               chains to a CCA India root we hold
    certificate_validity_at_signing the signer's certificate was in its validity
                                    window when it signed
    revocation                      the certificate was not revoked at signing
    trusted_timestamp               an RFC 3161 token, not the signer's own claim
    official_issuer_match           the issuing CA is CCA-licensed
    official_record_match           the document appears in the issuer's own record

The last is almost always NOT_CHECKED and says so. Matching a board-meeting
outcome against an exchange filing needs a source we do not hold, and asserting
it from the document's own contents would be circular.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

VALID = "VALID"
INVALID = "INVALID"
NOT_CHECKED = "NOT_CHECKED"
NOT_PRESENT = "NOT_PRESENT"
UNKNOWN = "UNKNOWN"
INCOMPLETE = "INCOMPLETE_VERIFICATION"
COMPLETE = "COMPLETE_VERIFICATION"
FAILED = "VERIFICATION_FAILED"

# Dimensions that must be VALID before a document may be called fully verified.
REQUIRED = ("file_integrity", "signature", "certificate_chain",
            "certificate_validity_at_signing", "revocation")

# Exit codes, per the CLI contract.
EXIT_OK = 0
EXIT_MODIFIED = 1          # document modified or unsigned content detected
EXIT_UNSUPPORTED = 2       # unsupported or malformed signature
EXIT_INCOMPLETE = 3        # verification incomplete
EXIT_CONFIG = 4            # configuration or trust-store failure


@dataclass
class Verification:
    file_integrity: str = NOT_CHECKED
    signature: str = NOT_CHECKED
    certificate_chain: str = NOT_CHECKED
    certificate_validity_at_signing: str = UNKNOWN
    revocation: str = NOT_CHECKED
    trusted_timestamp: str = NOT_PRESENT
    official_issuer_match: str = NOT_CHECKED
    official_record_match: str = NOT_CHECKED
    detail: dict = field(default_factory=dict)

    @property
    def overall_status(self) -> str:
        """Always derived, never stored.

        It was a stored field with a default of INCOMPLETE, and constructing a
        Verification directly left it stale: an object whose file_integrity was
        INVALID still reported INCOMPLETE_VERIFICATION. A summary that can
        disagree with the facts it summarises is the exact failure this module
        exists to prevent, so the value cannot be set independently of them.
        """
        return self.compute_overall()

    def compute_overall(self) -> str:
        vals = {k: getattr(self, k) for k in REQUIRED}
        if self.file_integrity == INVALID or self.signature == INVALID:
            return FAILED
        if all(v == VALID for v in vals.values()):
            return COMPLETE
        return INCOMPLETE

    def exit_code(self) -> int:
        if self.file_integrity == INVALID:
            return EXIT_MODIFIED
        if self.signature == INVALID:
            return EXIT_MODIFIED
        if self.detail.get("unsupported"):
            return EXIT_UNSUPPORTED
        if self.detail.get("trust_store_error"):
            return EXIT_CONFIG
        return EXIT_OK if self.overall_status == COMPLETE else EXIT_INCOMPLETE

    def sentence(self) -> str:
        """What a reader should be told. Deliberately unexciting."""
        if self.overall_status == FAILED:
            return ("The signed bytes do not match the signature. This document was "
                    "altered after signing and must not be relied on.")
        if self.overall_status == COMPLETE:
            return ("The signature validates, the signed bytes are unchanged, the "
                    "certificate chains to a CCA India root and was neither expired "
                    "nor revoked when it signed.")
        missing = [k.replace("_", " ") for k in REQUIRED if getattr(self, k) != VALID]
        good = []
        if self.signature == VALID:
            good.append("the digital signature validates")
        if self.file_integrity == VALID:
            good.append("the signed bytes have not changed")
        head = ("" if not good else
                (" and ".join(good)[0].upper() + " and ".join(good)[1:] + ". "))
        return (head + f"{', '.join(missing)} "
                f"{'was' if len(missing) == 1 else 'were'} not established, so the "
                "system does not determine that the document is legally genuine.")

    def to_json(self) -> str:
        d = asdict(self)
        d.pop("detail", None)
        d["overall_status"] = self.overall_status
        return json.dumps(d, indent=1)


def verify_document(path: str | Path, *, offline: bool = False) -> Verification:
    from checker import trust
    from checker.pdf_signature import (
        COVERAGE_INCOMPLETE, MALFORMED, MODIFIED, UNSIGNED, UNSUPPORTED, VALID as SIG_VALID,
        verify as verify_sig,
    )
    v = Verification()
    r = verify_sig(path)
    v.detail["signature_verdict"] = r.verdict
    v.detail["signer"] = r.signer.name if r.signer else None
    v.detail["signing_time"] = r.signing_time.isoformat() if r.signing_time else None

    if r.verdict == UNSIGNED:
        v.file_integrity = NOT_PRESENT
        v.signature = NOT_PRESENT
        return v
    if r.verdict in (MALFORMED, UNSUPPORTED):
        v.detail["unsupported"] = True
        v.signature = UNKNOWN
        v.detail["note"] = r.note
        return v
    if r.verdict == MODIFIED:
        v.file_integrity = INVALID
        v.signature = INVALID
        return v

    # COVERAGE_INCOMPLETE: the signature is real but does not cover everything.
    # That is an integrity failure of the *document*, even though the signature
    # itself verifies — which is exactly why the two are separate dimensions.
    v.file_integrity = INVALID if r.verdict == COVERAGE_INCOMPLETE else VALID
    v.signature = VALID if r.signature_verified else UNKNOWN
    v.certificate_chain = VALID if r.chains_to_cca else (
        INVALID if r.chain_verdict in ("BROKEN_CHAIN", "UNTRUSTED_ROOT") else UNKNOWN)
    v.detail["chain_verdict"] = r.chain_verdict
    v.detail["chain_root"] = r.chain_root
    v.detail["chain_path"] = r.chain_names

    # An issuing CA that chains to CCA India is by definition CCA-licensed; the
    # chain check already established it, so this dimension is not independent
    # evidence and says so rather than double-counting.
    v.official_issuer_match = VALID if r.chains_to_cca else NOT_CHECKED
    v.detail["official_issuer_match_basis"] = (
        "issuer chains to a CCA India root held locally" if r.chains_to_cca
        else "chain not established")

    # Validity window at signing.
    if r.signer and r.signer.not_before and r.signer.not_after and r.signing_time:
        inside = r.signer.not_before <= r.signing_time <= r.signer.not_after
        v.certificate_validity_at_signing = VALID if inside else INVALID
    elif r.signer and r.signer.not_before and r.signer.not_after:
        v.certificate_validity_at_signing = UNKNOWN
        v.detail["validity_note"] = "no signing time to test the window against"

    v.revocation, rev = _revocation(path, r, offline=offline)
    v.detail["revocation"] = rev

    # Official-record matching needs the issuer's own register. We hold none for
    # exchange filings, so this stays NOT_CHECKED rather than being inferred from
    # the document's own contents, which would be circular.
    v.official_record_match = NOT_CHECKED
    v.detail["official_record_match_basis"] = (
        "no issuer register is held for this document type")

    return v


def _revocation(path, r, *, offline: bool) -> tuple[str, dict]:
    import re
    from checker import asn1, revocation as rev
    from checker.pdf_signature import _certificates, _cert_names, _der_of
    data = Path(path).read_bytes()
    m = re.findall(rb"/Contents\s*<([0-9A-Fa-f\s]+)>", data)
    if not m:
        return NOT_CHECKED, {"status": rev.NOT_CHECKED}
    try:
        blob = bytes.fromhex(re.sub(rb"\s", b"", m[-1]).decode())
        ci = asn1.parse(blob)
        ex = next(c for c in ci.children if c.cls == 2 and c.tag == 0)
        certs = _certificates(ex.children[0])
    except Exception as exc:
        return NOT_CHECKED, {"status": rev.NOT_CHECKED, "note": str(exc)}

    by_subject = {_cert_names(c)[1].get("CN"): c for c in certs}
    leaf = next((c for c in certs
                 if r.signer and _cert_names(c)[1].get("CN") == r.signer.name), None)
    if leaf is None:
        return NOT_CHECKED, {"status": rev.NOT_CHECKED, "note": "signer cert not found"}
    issuer_cn = _cert_names(leaf)[0].get("CN")
    issuer = by_subject.get(issuer_cn)
    if issuer is None:
        return NOT_CHECKED, {"status": rev.NO_CRL_URL,
                             "note": f"issuer {issuer_cn!r} not embedded; cannot verify a CRL"}
    from checker.pdf_signature import _cert_serial
    res = rev.check(leaf, _der_of(blob, leaf), _der_of(blob, issuer),
                    serial=_cert_serial(leaf) or 0,
                    signing_time=r.signing_time, offline=offline)
    d = {"status": res.status, "crl_url": res.crl_url,
         "crl_entries": res.crl_entries,
         "crl_signature_verified": res.crl_signature_verified,
         "revoked_at": res.revoked_at.isoformat() if res.revoked_at else None,
         "note": res.note}
    if res.clean:
        return VALID, d
    if res.status == rev.REVOKED:
        return INVALID, d
    return NOT_CHECKED if res.status == rev.NOT_CHECKED else UNKNOWN, d


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

    print("doc_verification")

    # No dimension may default to VALID. A verifier that starts optimistic and
    # subtracts is one bug away from asserting something it never checked.
    d = Verification()
    check(all(getattr(d, k) != VALID for k in REQUIRED),
          "no required dimension defaults to VALID")
    check(d.overall_status == INCOMPLETE, "the default overall status is INCOMPLETE")
    check(d.compute_overall() == INCOMPLETE, "an unchecked document is never COMPLETE")

    full = Verification(**{k: VALID for k in REQUIRED})
    check(full.compute_overall() == COMPLETE,
          "a document with every required dimension VALID is COMPLETE")
    for k in REQUIRED:
        one = Verification(**{j: VALID for j in REQUIRED if j != k})
        check(one.compute_overall() == INCOMPLETE,
              f"missing {k} alone prevents COMPLETE")

    bad = Verification(file_integrity=INVALID, signature=VALID)
    check(bad.compute_overall() == FAILED and bad.exit_code() == EXIT_MODIFIED,
          "an integrity failure is FAILED and exits 1")
    check("must not be relied on" in bad.sentence(),
          "the failure sentence tells the reader not to rely on the document")
    check(Verification(detail={"unsupported": True}).exit_code() == EXIT_UNSUPPORTED,
          "an unsupported signature exits 2")
    check(Verification(detail={"trust_store_error": True}).exit_code() == EXIT_CONFIG,
          "a trust-store failure exits 4")
    check(d.exit_code() == EXIT_INCOMPLETE, "incomplete verification exits 3")
    check(full.exit_code() == EXIT_OK, "complete verification exits 0")

    # The sentence must not overstate.
    part = Verification(file_integrity=VALID, signature=VALID)
    s = part.sentence()
    check("does not determine that the document is legally genuine" in s,
          "a partial result explicitly declines to call the document genuine")
    check("revocation" in s, "the sentence names what was not established")
    check("genuine" not in full.sentence().replace("legally genuine", ""),
          "the complete sentence states facts rather than declaring 'genuine'")

    j = json.loads(d.to_json())
    check("detail" not in j, "internal detail is not part of the published object")
    check(len(j) == 9, f"the object carries all nine dimensions ({len(j)})")

    # Real documents.
    signed = [p for p in sorted(Path("corpus/testdocs/_raw").glob("*.pdf"))
              if b"/ByteRange" in p.read_bytes()]
    results = {p.name: verify_document(p, offline=True) for p in signed}
    check(all(r.overall_status != COMPLETE for r in results.values()),
          "no real document reaches COMPLETE — none carries a trusted timestamp")
    good = [r for r in results.values() if r.signature == VALID]
    check(len(good) >= 4, f"real signatures verify ({len(good)})")
    check(all(r.certificate_validity_at_signing == UNKNOWN for r in good),
          "validity-at-signing is UNKNOWN: these documents carry no signingTime")
    check(all(r.official_record_match == NOT_CHECKED for r in results.values()),
          "official-record matching is never asserted without an issuer register")
    check(all(r.exit_code() in (EXIT_INCOMPLETE, EXIT_UNSUPPORTED)
              for r in results.values()),
          "every real document exits 3 or 2, never 0")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
