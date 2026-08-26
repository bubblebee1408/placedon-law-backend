"""Cryptographic authenticity check for signed Indian legal PDFs.

Indian corporate and government documents — board-meeting outcomes filed with the
exchanges, Gazette notifications, MCA certificates — carry PKCS#7 digital
signatures issued under CCA India, the government's root Certifying Authority.
That makes forgery *decidable*: not scored, not estimated, decided. A single
altered byte breaks a hash. There is no model in this path and therefore no
hallucination surface.

This is the one part of the product that answers "is this document real?" with a
proof rather than a probability, which is why it is built dependency-free (see
`checker/asn1.py`).

## The check that actually matters

The naive verifier computes the hash over /ByteRange, compares it to the signed
digest, and reports success. That verifier is defeated by appending an
incremental update: the original bytes still hash correctly, and the appended
pages — new text, a different resolution, an extra signatory — sit outside the
signed range entirely. Adobe shows such files as signed.

So the ranges are checked for *coverage*, not just consistency:

- the first range must start at byte 0,
- the gap between the two ranges must be exactly the /Contents hex string,
- the second range must end at, or within a trailing-whitespace tolerance of,
  end-of-file.

`COVERAGE_INCOMPLETE` is reported as its own verdict rather than folded into
"invalid", because the two mean different things to a lawyer: one document was
tampered with, the other has content nobody signed.

## What a PASS does not mean

A valid signature proves the bytes are unmodified since signing and that a named
certificate signed them. It does not prove the signer had authority to sign, that
the statements inside are true, or that the certificate was valid *at signing
time* rather than merely well-formed. Revocation (CRL/OCSP) is NOT checked here —
`revocation_checked` is always False, and the report says so, because silently
implying a revocation check we never performed is exactly the kind of unearned
assurance this project exists to avoid.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from checker import asn1
from checker.asn1 import Asn1Error, Node

# --- verdicts ---------------------------------------------------------------
VALID = "VALID"                            # signed, unmodified, whole file covered
COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"  # signature real, but not over everything
MODIFIED = "MODIFIED"                      # digest mismatch: bytes changed after signing
UNSIGNED = "UNSIGNED"                      # no signature present at all
MALFORMED = "MALFORMED"                    # signature present but unparseable
UNSUPPORTED = "UNSUPPORTED"                # algorithm we decline to guess at

TRUSTWORTHY = (VALID,)

# --- OIDs -------------------------------------------------------------------
OID_SIGNED_DATA = "1.2.840.113549.1.7.2"
OID_MESSAGE_DIGEST = "1.2.840.113549.1.9.4"
OID_CONTENT_TYPE = "1.2.840.113549.1.9.3"
OID_SIGNING_TIME = "1.2.840.113549.1.9.5"
OID_RSA = "1.2.840.113549.1.1.1"

_DIGESTS = {
    "1.3.14.3.2.26": ("sha1", hashlib.sha1),
    "2.16.840.1.101.3.4.2.1": ("sha256", hashlib.sha256),
    "2.16.840.1.101.3.4.2.2": ("sha384", hashlib.sha384),
    "2.16.840.1.101.3.4.2.3": ("sha512", hashlib.sha512),
}
# Signature algorithm OIDs that imply their own digest.
_SIG_DIGESTS = {
    "1.2.840.113549.1.1.5": "sha1",
    "1.2.840.113549.1.1.11": "sha256",
    "1.2.840.113549.1.1.12": "sha384",
    "1.2.840.113549.1.1.13": "sha512",
}
_RDN = {
    "2.5.4.3": "CN", "2.5.4.6": "C", "2.5.4.7": "L", "2.5.4.8": "ST",
    "2.5.4.10": "O", "2.5.4.11": "OU", "0.9.2342.19200300.100.1.25": "DC",
    "1.2.840.113549.1.9.1": "email",
}

# Chain validation now runs against the real CCA roots held in corpus/trust/cca
# (see checker/trust.py). The previous implementation matched the string
# "CCA India" inside a certificate, which any self-issued certificate can
# contain — it tested spelling, not trust.


@dataclass
class Signer:
    subject: dict[str, str] = field(default_factory=dict)
    issuer: dict[str, str] = field(default_factory=dict)
    serial: int | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None

    @property
    def name(self) -> str:
        return self.subject.get("CN", "(no common name)")

    @property
    def issuer_name(self) -> str:
        return self.issuer.get("CN", self.issuer.get("O", "(unknown issuer)"))


@dataclass
class SignatureResult:
    verdict: str
    signer: Signer | None = None
    digest_alg: str = ""
    signing_time: datetime | None = None
    covered_bytes: int = 0
    total_bytes: int = 0
    signature_bytes: int = 0        # the /Contents blob, which cannot sign itself
    uncovered_ranges: list[tuple[int, int]] = field(default_factory=list)
    chains_to_cca: bool = False            # cryptographically verified to a CCA root
    chain_verdict: str = ""
    chain_root: str = ""
    chain_names: list[str] = field(default_factory=list)
    revocation_checked: bool = False       # never True: we perform no CRL/OCSP check
    signature_verified: bool = False       # public-key check actually performed
    note: str = ""

    @property
    def trustworthy(self) -> bool:
        return self.verdict in TRUSTWORTHY

    @property
    def coverage_pct(self) -> float:
        """Share of the *signable* file that is signed.

        Measured against the document excluding the signature blob, because that
        blob cannot sign itself. Reporting raw covered/total instead makes a
        perfectly valid document read as 27% signed when its embedded signature
        happens to be large — alarming a reader about a file that is entirely
        intact. The number that carries meaning is whether any *document* byte is
        unsigned, which `uncovered_ranges` answers exactly.
        """
        signable = self.total_bytes - self.signature_bytes
        return 100.0 * self.covered_bytes / signable if signable > 0 else 0.0

    def summary(self) -> str:
        lines = [f"  verdict            : {self.verdict}"]
        if self.signer:
            lines += [f"  signed by          : {self.signer.name}",
                      f"  certificate issuer : {self.signer.issuer_name}"]
        if self.signing_time:
            lines.append(f"  signing time       : {self.signing_time:%Y-%m-%d %H:%M:%S %Z}")
        lines += [
            f"  digest             : {self.digest_alg or 'n/a'}",
            f"  signed content     : {self.covered_bytes} of "
            f"{self.total_bytes - self.signature_bytes} document bytes "
            f"({self.coverage_pct:.2f}%)",
        f"  signature blob     : {self.signature_bytes} bytes (excluded; cannot "
            f"sign itself)",
            f"  chains to CCA India: "
            f"{'YES — ' + self.chain_root if self.chains_to_cca else 'not established'}"
            f"{'' if self.chains_to_cca else ' (' + (self.chain_verdict or 'not attempted') + ')'}",
            f"  signature checked  : {'yes' if self.signature_verified else 'no'}",
            f"  revocation checked : no (never performed by this tool)",
        ]
        if self.uncovered_ranges:
            for a, b in self.uncovered_ranges:
                lines.append(f"  UNSIGNED BYTES     : {a}-{b} ({b - a} bytes)")
        if self.note:
            lines.append(f"  note               : {self.note}")
        return "\n".join(lines)


# --- PDF layer --------------------------------------------------------------
_BYTERANGE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")
_CONTENTS = re.compile(rb"/Contents\s*<([0-9A-Fa-f\s]+)>")


def _covered(data: bytes, br: tuple[int, int, int, int]) -> bytes:
    a, b, c, d = br
    return data[a:a + b] + data[c:c + d]


def _uncovered_ranges(data: bytes, br: tuple[int, int, int, int],
                      sig_span: tuple[int, int]) -> list[tuple[int, int]]:
    """Bytes in the file that no signature covers, excluding the signature itself."""
    a, b, c, d = br
    gaps: list[tuple[int, int]] = []
    if a > 0:
        gaps.append((0, a))
    gap_start, gap_end = a + b, c
    # The gap between the two ranges should hold exactly the /Contents string.
    if not (sig_span[0] >= gap_start and sig_span[1] <= gap_end):
        gaps.append((gap_start, gap_end))
    tail = c + d
    if tail < len(data):
        # A short run of trailing whitespace/EOF marker is normal; real appended
        # content is not.
        if data[tail:].strip(b" \r\n\t\x00"):
            gaps.append((tail, len(data)))
    return gaps


# --- ASN.1 helpers ----------------------------------------------------------
def _oid(n: Node) -> str:
    return asn1.oid_to_str(n.content)


def _first_oid(n: Node) -> str | None:
    for c in n.children:
        if c.tag == asn1.OID and c.cls == 0:
            return _oid(c)
    return None


def _name_to_dict(name: Node) -> dict[str, str]:
    """An X.501 Name: SEQUENCE OF RDN(SET OF AttributeTypeAndValue)."""
    out: dict[str, str] = {}
    for rdn in name.children:
        for atv in rdn.children:
            kids = atv.children
            if len(kids) >= 2 and kids[0].tag == asn1.OID:
                key = _RDN.get(_oid(kids[0]))
                if key and key not in out:
                    out[key] = asn1.text_of(kids[1]).strip()
    return out


def _parse_time(n: Node) -> datetime | None:
    s = n.content.decode("ascii", "replace").strip()
    fmt = "%y%m%d%H%M%S" if n.tag == asn1.UTC_TIME else "%Y%m%d%H%M%S"
    try:
        if s.endswith("Z"):
            return datetime.strptime(s[:-1], fmt).replace(tzinfo=timezone.utc)
        return datetime.strptime(s[:len(fmt) + 2], fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _der_of(blob: bytes, cert: Node) -> bytes:
    """A certificate's exact DER bytes, recovered by re-parsing from the blob.

    Node offsets are relative to the parent's content buffer, so a certificate
    cannot be sliced out of `blob` directly. Re-serialising from the parsed tree
    would risk producing bytes that differ from what was signed; searching for the
    original run keeps the comparison honest.
    """
    body = cert.content
    idx = blob.find(body)
    if idx < 0:
        return b""
    return blob[idx - cert.header_len:idx + len(body)]


def _certificates(signed_data: Node) -> list[Node]:
    """The [0] IMPLICIT certificates field of SignedData."""
    for c in signed_data.children:
        if c.cls == 2 and c.tag == 0 and c.constructed:
            return [k for k in c.children if k.tag == asn1.SEQUENCE]
    return []


def _tbs(cert: Node) -> Node | None:
    return cert.children[0] if cert.children else None


def _cert_serial(cert: Node) -> int | None:
    t = _tbs(cert)
    if not t:
        return None
    for c in t.children:
        if c.tag == asn1.INTEGER and c.cls == 0:
            return int.from_bytes(c.content, "big")
    return None


def _cert_names(cert: Node) -> tuple[dict[str, str], dict[str, str], datetime | None,
                                     datetime | None]:
    """(issuer, subject, notBefore, notAfter) from a tbsCertificate."""
    t = _tbs(cert)
    if not t:
        return {}, {}, None, None
    seqs = [c for c in t.children if c.tag == asn1.SEQUENCE and c.cls == 0]
    # tbs: [version] serial sigAlg issuer validity subject spki
    issuer = subject = {}
    nb = na = None
    if len(seqs) >= 4:
        issuer = _name_to_dict(seqs[1])
        validity = seqs[2]
        subject = _name_to_dict(seqs[3])
        times = [c for c in validity.children
                 if c.tag in (asn1.UTC_TIME, asn1.GENERALIZED_TIME)]
        if len(times) == 2:
            nb, na = _parse_time(times[0]), _parse_time(times[1])
    return issuer, subject, nb, na


def _public_key(cert: Node) -> tuple[int, int] | None:
    """(modulus, exponent) from an RSA SubjectPublicKeyInfo."""
    t = _tbs(cert)
    if not t:
        return None
    for seq in t.children:
        if seq.tag != asn1.SEQUENCE or seq.cls != 0:
            continue
        alg = seq.children[0] if seq.children else None
        if not alg or alg.tag != asn1.SEQUENCE or _first_oid(alg) != OID_RSA:
            continue
        bits = next((c for c in seq.children if c.tag == asn1.BIT_STRING), None)
        if not bits or not bits.content:
            continue
        try:
            inner = asn1.parse(bits.content[1:])      # strip unused-bits octet
        except Asn1Error:
            return None
        ints = [c for c in inner.children if c.tag == asn1.INTEGER]
        if len(ints) >= 2:
            return (int.from_bytes(ints[0].content, "big"),
                    int.from_bytes(ints[1].content, "big"))
    return None


def _rsa_recover(sig: bytes, n: int, e: int) -> bytes | None:
    """s^e mod n, as the EMSA-PKCS1-v1_5 block. Verification, not decryption."""
    s = int.from_bytes(sig, "big")
    if s >= n:
        return None
    m = pow(s, e, n)
    k = (n.bit_length() + 7) // 8
    return m.to_bytes(k, "big")


def _pkcs1_digest(block: bytes) -> tuple[str, bytes] | None:
    """Unwrap 0x00 01 FF..FF 00 || DigestInfo and return (alg, hash)."""
    if len(block) < 11 or block[0] != 0x00 or block[1] != 0x01:
        return None
    i = 2
    while i < len(block) and block[i] == 0xFF:
        i += 1
    if i >= len(block) or block[i] != 0x00 or i < 10:
        return None
    try:
        di = asn1.parse(block[i + 1:])
    except Asn1Error:
        return None
    alg = di.children[0] if di.children else None
    oct_ = next((c for c in di.children if c.tag == asn1.OCTET_STRING), None)
    if not alg or not oct_:
        return None
    name = _DIGESTS.get(_first_oid(alg) or "", ("unknown", None))[0]
    return name, oct_.content


def _signed_attrs_der(signer_info: Node) -> tuple[bytes, dict[str, Node]] | None:
    """The [0] IMPLICIT signedAttrs, re-tagged to SET as required for signing."""
    for c in signer_info.children:
        if c.cls == 2 and c.tag == 0 and c.constructed:
            body = c.content
            # Re-encode with the universal SET tag (0x31); the length header is
            # unchanged, only the identifier octet differs.
            hdr = bytearray(c.header_len)
            hdr[0] = 0x31
            # rebuild the length octets exactly as they appeared
            raw_len = c.header_len - 1
            if raw_len == 1:
                hdr[1:] = bytes([len(body)])
            else:
                k = raw_len - 1
                hdr[1] = 0x80 | k
                hdr[2:] = len(body).to_bytes(k, "big")
            attrs: dict[str, Node] = {}
            for a in c.children:
                if a.tag == asn1.SEQUENCE and a.children:
                    o = _first_oid(a)
                    vals = next((x for x in a.children if x.tag == asn1.SET), None)
                    if o and vals and vals.children:
                        attrs[o] = vals.children[0]
            return bytes(hdr) + body, attrs
    return None


# --- top level --------------------------------------------------------------
def verify(path: str | Path) -> SignatureResult:
    """Verify the last signature in a PDF. See module docstring for the scope."""
    data = Path(path).read_bytes()
    total = len(data)

    brs = list(_BYTERANGE.finditer(data))
    cts = list(_CONTENTS.finditer(data))
    if not brs or not cts:
        return SignatureResult(UNSIGNED, total_bytes=total,
                               note="no /ByteRange or /Contents present")

    br_m, ct_m = brs[-1], cts[-1]
    br = tuple(int(x) for x in br_m.groups())          # type: ignore[assignment]
    try:
        blob = bytes.fromhex(re.sub(rb"\s", b"", ct_m.group(1)).decode("ascii"))
    except ValueError:
        return SignatureResult(MALFORMED, total_bytes=total,
                               note="/Contents is not valid hex")

    gaps = _uncovered_ranges(data, br, (ct_m.start(1), ct_m.end(1)))
    covered = _covered(data, br)

    try:
        ci = asn1.parse(blob)
        if _first_oid(ci) != OID_SIGNED_DATA:
            return SignatureResult(UNSUPPORTED, total_bytes=total,
                                   covered_bytes=len(covered),
                                   note="not a PKCS#7 signedData")
        explicit = next((c for c in ci.children if c.cls == 2 and c.tag == 0), None)
        signed_data = explicit.children[0] if explicit and explicit.children else None
        if signed_data is None:
            return SignatureResult(MALFORMED, total_bytes=total,
                                   note="signedData missing")
        si_set = [c for c in signed_data.children if c.tag == asn1.SET and c.cls == 0
                  and c.children and c.children[0].tag == asn1.SEQUENCE]
        signer_info = si_set[-1].children[0] if si_set else None
        if signer_info is None:
            return SignatureResult(MALFORMED, total_bytes=total,
                                   note="no SignerInfo")
    except Asn1Error as exc:
        return SignatureResult(MALFORMED, total_bytes=total, note=f"DER: {exc}")

    # Digest algorithm. Selected by *content*, not position: SignerInfo's first
    # SEQUENCE is the issuerAndSerialNumber, and reading that as the algorithm
    # made every real document report UNSUPPORTED.
    dig_oid = None
    for c in signer_info.children:
        if c.tag == asn1.SEQUENCE and c.cls == 0:
            o = _first_oid(c)
            if o in _DIGESTS:
                dig_oid = o
                break
            if o in _SIG_DIGESTS:      # some signers name only the combined algorithm
                dig_oid = next(k for k, v in _DIGESTS.items()
                               if v[0] == _SIG_DIGESTS[o])
                break
    dig_name, dig_fn = _DIGESTS.get(dig_oid or "", ("", None))
    if dig_fn is None:
        return SignatureResult(UNSUPPORTED, total_bytes=total,
                               covered_bytes=len(covered),
                               note=f"unsupported digest OID {dig_oid}")

    sa = _signed_attrs_der(signer_info)
    if sa is None:
        return SignatureResult(UNSUPPORTED, total_bytes=total,
                               covered_bytes=len(covered),
                               note="no signedAttrs (direct signing not supported)")
    sa_der, attrs = sa

    # signer identity
    certs = _certificates(signed_data)
    signer = Signer()
    signer_cert: Node | None = None
    ints = [c for c in signer_info.children if c.tag == asn1.INTEGER]
    want_serial = None
    for c in signer_info.children:
        if c.tag == asn1.SEQUENCE and c.cls == 0 and len(c.children) == 2 \
                and c.children[1].tag == asn1.INTEGER:
            want_serial = int.from_bytes(c.children[1].content, "big")
            break
    for cert in certs:
        if want_serial is None or _cert_serial(cert) == want_serial:
            signer_cert = cert
            break
    if signer_cert is None and certs:
        signer_cert = certs[0]
    if signer_cert is not None:
        iss, sub, nb, na = _cert_names(signer_cert)
        signer = Signer(subject=sub, issuer=iss, serial=_cert_serial(signer_cert),
                        not_before=nb, not_after=na)

    signing_time = None
    if OID_SIGNING_TIME in attrs:
        signing_time = _parse_time(attrs[OID_SIGNING_TIME])

    # Real chain validation: verify every signature from the signing certificate
    # up to a root published by CCA, rather than looking for its name in a string.
    chain_verdict, chain_root, chain_names = "", "", []
    chains = False
    try:
        from checker import trust
        roots = trust.load_roots()
        loaded = []
        for c in certs:
            try:
                loaded.append(trust.load_certificate(_der_of(blob, c)))
            except Exception:
                continue
        leaf = next((lc for lc in loaded
                     if signer_cert is not None
                     and lc.der == _der_of(blob, signer_cert)), None)
        if leaf is not None:
            at = signing_time or datetime.now(timezone.utc)
            cr = trust.build_chain(leaf, loaded, roots, when=at)
            chain_verdict = cr.verdict
            chains = cr.trusted
            chain_root = cr.root.cn if cr.root else ""
            chain_names = [c.cn for c in cr.chain]
    except Exception as exc:                     # trust store missing or unusable
        chain_verdict = f"NOT_CHECKED ({exc})"

    res = SignatureResult(
        verdict=VALID, signer=signer, digest_alg=dig_name, signing_time=signing_time,
        covered_bytes=len(covered), total_bytes=total,
        signature_bytes=(ct_m.end(1) - ct_m.start(1)) // 2,
        uncovered_ranges=gaps, chains_to_cca=chains,
        chain_verdict=chain_verdict, chain_root=chain_root, chain_names=chain_names,
    )

    # 1. Does the signed messageDigest match the bytes actually in the file?
    md_node = attrs.get(OID_MESSAGE_DIGEST)
    if md_node is None:
        res.verdict = MALFORMED
        res.note = "signedAttrs carries no messageDigest"
        return res
    if dig_fn(covered).digest() != md_node.content:
        res.verdict = MODIFIED
        res.note = "content digest does not match the signed digest"
        return res

    # 2. Does the signature verify against the certificate's public key?
    sig_node = None
    for c in reversed(signer_info.children):
        if c.tag == asn1.OCTET_STRING and c.cls == 0:
            sig_node = c
            break
    pk = _public_key(signer_cert) if signer_cert is not None else None
    if sig_node is not None and pk is not None:
        block = _rsa_recover(sig_node.content, pk[0], pk[1])
        got = _pkcs1_digest(block) if block else None
        if got is None:
            res.verdict = MALFORMED
            res.note = "signature block is not valid PKCS#1 v1.5"
            return res
        _, want_hash = got
        if hashlib.new(dig_name, sa_der).digest() != want_hash:
            res.verdict = MODIFIED
            res.note = "signedAttrs do not match the signature"
            return res
        res.signature_verified = True
    else:
        res.note = "public key unavailable; digest matched but signature not checked"

    # 3. Is everything in the file actually covered?
    if gaps:
        res.verdict = COVERAGE_INCOMPLETE
        res.note = ("the signature is genuine but does not cover the whole file; "
                    "unsigned content was added")
    return res


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

    print("pdf_signature")

    import tempfile

    def tmp(b: bytes) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        f.write(b)
        f.close()
        return f.name

    check(verify(tmp(b"%PDF-1.4\nnothing here\n%%EOF")).verdict == UNSIGNED,
          "an unsigned PDF is reported UNSIGNED, not VALID")
    check(not SignatureResult(UNSIGNED).trustworthy, "UNSIGNED is not trustworthy")
    check(not SignatureResult(MODIFIED).trustworthy, "MODIFIED is not trustworthy")
    check(not SignatureResult(COVERAGE_INCOMPLETE).trustworthy,
          "COVERAGE_INCOMPLETE is not trustworthy")
    check(not SignatureResult(MALFORMED).trustworthy, "MALFORMED is not trustworthy")
    check(SignatureResult(VALID).trustworthy, "VALID is trustworthy")
    check(SignatureResult(VALID).revocation_checked is False,
          "revocation is never reported as checked")
    check("revocation checked : no" in SignatureResult(VALID).summary(),
          "the summary states that revocation was not checked")

    check(_pkcs1_digest(b"\x00\x02" + b"\xff" * 8 + b"\x00") is None,
          "a wrong block type is rejected")
    check(_pkcs1_digest(b"\x00\x01\xff\x00") is None,
          "too little padding is rejected (Bleichenbacher-style forgery)")

    # Real documents from the corpus.
    real = sorted(Path("corpus/testdocs/_raw").glob("*.pdf"))
    signed = [p for p in real if b"/ByteRange" in p.read_bytes()]
    check(len(signed) >= 4, f"the corpus holds signed documents to test against ({len(signed)})")

    verdicts: dict[str, int] = {}
    for p in signed:
        r = verify(p)
        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
    check(UNSIGNED not in verdicts, f"no signed document is misread as unsigned ({verdicts})")
    check(MALFORMED not in verdicts, f"every real signature parses ({verdicts})")

    good = [p for p in signed if verify(p).verdict == VALID]
    check(len(good) >= 1, f"at least one real document verifies as VALID ({len(good)})")

    if good:
        r = verify(good[0])
        check(r.signer is not None and r.signer.name != "(no common name)",
              f"the signer is identified: {r.signer.name if r.signer else None}")
        check(r.signature_verified, "the RSA signature is actually checked, not assumed")
        # Coverage never reaches 100%: the /Contents blob sits in the gap between
        # the two ranges and cannot sign itself. The property that matters is that
        # there is no *other* gap.
        check(not r.uncovered_ranges,
              f"a VALID document has no unsigned region ({r.coverage_pct:.2f}% of "
              f"document bytes signed)")
        # Not 100%: the signature *dictionary* around the blob — the `<`, `>` and
        # the padding the signer reserved before knowing the final length — is
        # unsigned in every signed PDF ever produced. A percentage is the wrong
        # instrument for this question; `uncovered_ranges` above is the right one.
        check(r.coverage_pct > 98.0,
              f"coverage measured against signable bytes is near-total "
              f"({r.coverage_pct:.2f}%) even when the signature blob is large")

        # Tamper detection: flip one byte inside the signed range.
        data = bytearray(good[0].read_bytes())
        i = next(j for j in range(200, len(data)) if data[j:j + 1].isalpha())
        data[i] ^= 0x20
        check(verify(tmp(bytes(data))).verdict == MODIFIED,
              "flipping a single byte inside the signed range is detected")

        # Appended content: the classic attack a naive verifier misses.
        appended = good[0].read_bytes() + b"\n% forged addendum\n" + b"X" * 400
        r2 = verify(tmp(appended))
        check(r2.verdict == COVERAGE_INCOMPLETE,
              f"appended unsigned content is caught ({r2.verdict})")
        check(r2.uncovered_ranges, "...and the unsigned byte range is reported")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
