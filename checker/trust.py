"""X.509 chain validation against the Indian government's own root certificates.

`checker/pdf_signature.py` reported `chains_to_cca` by looking for the string
"CCA India" somewhere in a certificate. That is not a trust check — anyone can put
"CCA India" in a certificate they issue themselves. This module replaces it with
cryptography: each certificate's signature is verified against its issuer's public
key, up the chain, until it reaches a root we hold on disk from cca.gov.in.

Roots live in `corpus/trust/cca/`, fetched from
https://cca.gov.in/root_certificate.html. They are public government artefacts
meant to be distributed, so they are committed rather than fetched at runtime — a
trust store fetched over the network at verification time is a trust store an
attacker can influence.

## Two encodings, one silent failure

CCA publishes some roots as DER, some as bare base64 with no PEM armour
(`MIIDIzCC...`). A loader that only recognises `-----BEGIN` treats the base64 ones
as DER, and the parse *succeeds* — producing a certificate object with no subject,
no issuer and no key. Nothing throws. Three of seven roots loaded as silent
rubbish before this was caught, so `load_roots` verifies that every root it
accepts actually yields a subject and a public key, and raises otherwise.

## What this establishes

A CHAINED result means: this document's signing certificate was issued, through a
verified signature chain, by a CA whose root the Controller of Certifying
Authorities publishes. Combined with a VALID signature, that is strong evidence
the document is genuine.

It still does not establish that the certificate was unrevoked (no CRL/OCSP is
fetched), nor that the signer had authority to sign the document in question.
Those remain out of scope and are reported as such.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from checker import asn1
from checker.asn1 import Asn1Error, Node

TRUST_DIR = Path("corpus/trust/cca")
SOURCE = "https://cca.gov.in/root_certificate.html"

# Chain verdicts
CHAINED = "CHAINED"                  # verified up to a root we hold
UNTRUSTED_ROOT = "UNTRUSTED_ROOT"    # chain is internally valid but ends nowhere we trust
BROKEN_CHAIN = "BROKEN_CHAIN"        # a signature in the chain does not verify
INCOMPLETE = "INCOMPLETE"            # an issuer certificate is missing
NO_ROOTS = "NO_ROOTS"                # we hold no trust store; proves nothing

_SIG_ALG_DIGEST = {
    "1.2.840.113549.1.1.5": "sha1",
    "1.2.840.113549.1.1.11": "sha256",
    "1.2.840.113549.1.1.12": "sha384",
    "1.2.840.113549.1.1.13": "sha512",
    "1.2.840.113549.1.1.4": "md5",
}


class TrustStoreError(RuntimeError):
    """The trust store is unusable. Never swallowed: it would fail open."""


@dataclass
class Cert:
    der: bytes
    node: Node
    subject: dict[str, str]
    issuer: dict[str, str]
    subject_der: bytes
    issuer_der: bytes
    not_before: datetime | None
    not_after: datetime | None
    public_key: tuple[int, int] | None
    path: str = ""

    @property
    def cn(self) -> str:
        return self.subject.get("CN") or self.subject.get("O") or "(unnamed)"

    @property
    def self_signed(self) -> bool:
        return self.subject_der == self.issuer_der

    def valid_at(self, when: datetime) -> bool:
        if self.not_before and when < self.not_before:
            return False
        if self.not_after and when > self.not_after:
            return False
        return True

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.der).hexdigest()


@dataclass
class ChainResult:
    verdict: str
    chain: list[Cert] = field(default_factory=list)
    root: Cert | None = None
    note: str = ""
    expired_in_chain: list[str] = field(default_factory=list)

    @property
    def trusted(self) -> bool:
        return self.verdict == CHAINED

    def describe(self) -> str:
        lines = [f"  chain verdict      : {self.verdict}"]
        for i, c in enumerate(self.chain):
            lines.append(f"    {'  ' * i}{'└─ ' if i else ''}{c.cn}")
        if self.root:
            lines.append(f"  anchored at        : {self.root.cn}")
            lines.append(f"  root fingerprint   : {self.root.fingerprint[:32]}…")
        if self.expired_in_chain:
            lines.append(f"  expired at signing : {', '.join(self.expired_in_chain)}")
        if self.note:
            lines.append(f"  note               : {self.note}")
        return "\n".join(lines)


# --- decoding ---------------------------------------------------------------
def decode_certificate_bytes(raw: bytes) -> bytes:
    """DER bytes from a file that may be DER, PEM, or bare base64.

    The bare-base64 case is the one that matters: it looks enough like binary to
    reach a DER parser and enough like a certificate to come back without an
    error. See the module docstring.
    """
    s = raw.strip()
    if s[:1] == b"\x30":                       # already DER
        return raw
    m = re.search(rb"-----BEGIN [A-Z ]*CERTIFICATE-----(.*?)-----END", s, re.S)
    if m:
        return base64.b64decode(re.sub(rb"\s", b"", m.group(1)))
    # Bare base64 — accept only if it decodes AND the result starts a SEQUENCE.
    try:
        der = base64.b64decode(re.sub(rb"\s", b"", s), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TrustStoreError(f"not DER, PEM, or base64: {exc}") from exc
    if der[:1] != b"\x30":
        raise TrustStoreError("base64 decoded but is not a DER SEQUENCE")
    return der


def _slice(parent: Node, child: Node) -> bytes:
    """The child's exact TLV bytes, as they appear inside the parent."""
    return parent.content[child.start:child.start + child.full]


def load_certificate(der: bytes, path: str = "") -> Cert:
    from checker.pdf_signature import _cert_names, _public_key

    node = asn1.parse(der)
    tbs = node.children[0] if node.children else None
    if tbs is None:
        raise TrustStoreError(f"{path}: no tbsCertificate")
    issuer, subject, nb, na = _cert_names(node)
    seqs = [c for c in tbs.children if c.tag == asn1.SEQUENCE and c.cls == 0]
    if len(seqs) < 4:
        raise TrustStoreError(f"{path}: malformed tbsCertificate")
    return Cert(der=der, node=node, subject=subject, issuer=issuer,
                issuer_der=_slice(tbs, seqs[1]), subject_der=_slice(tbs, seqs[3]),
                not_before=nb, not_after=na, public_key=_public_key(node), path=path)


def load_roots(directory: Path = TRUST_DIR) -> list[Cert]:
    """Every root in the trust store, or an exception. Never a silent empty list."""
    if not directory.exists():
        raise TrustStoreError(f"no trust store at {directory}")
    roots: list[Cert] = []
    problems: list[str] = []
    for p in sorted(directory.glob("*.cer")) + sorted(directory.glob("*.pem")):
        try:
            c = load_certificate(decode_certificate_bytes(p.read_bytes()), str(p))
        except (TrustStoreError, Asn1Error, ValueError) as exc:
            problems.append(f"{p.name}: {exc}")
            continue
        # A root that yields no name or no key is not a root; it is a parse that
        # failed quietly. Refuse it rather than carry it in the store.
        if not c.subject or c.public_key is None:
            problems.append(f"{p.name}: parsed but has no subject or no public key")
            continue
        roots.append(c)
    if not roots:
        raise TrustStoreError(f"no usable roots in {directory}: {problems}")
    if problems:
        raise TrustStoreError(f"unusable certificates in trust store: {problems}")
    return roots


# --- signature verification -------------------------------------------------
def verify_signed_by(child: Cert, issuer: Cert) -> bool:
    """Does `issuer`'s public key actually sign `child`'s tbsCertificate?"""
    from checker.pdf_signature import _pkcs1_digest, _rsa_recover

    if issuer.public_key is None:
        return False
    kids = child.node.children
    if len(kids) < 3:
        return False
    tbs_der = _slice(child.node, kids[0])
    alg_oid = None
    for c in kids[1].children:
        if c.tag == asn1.OID:
            alg_oid = asn1.oid_to_str(c.content)
            break
    digest = _SIG_ALG_DIGEST.get(alg_oid or "")
    if digest is None:
        return False
    sig_bits = kids[2]
    if sig_bits.tag != asn1.BIT_STRING or not sig_bits.content:
        return False
    sig = sig_bits.content[1:]                       # strip unused-bits octet
    block = _rsa_recover(sig, issuer.public_key[0], issuer.public_key[1])
    if block is None:
        return False
    got = _pkcs1_digest(block)
    if got is None:
        return False
    _, want = got
    try:
        return hashlib.new(digest, tbs_der).digest() == want
    except ValueError:
        return False


def build_chain(leaf: Cert, intermediates: list[Cert], roots: list[Cert],
                when: datetime | None = None) -> ChainResult:
    """Walk from `leaf` to a trusted root, verifying every signature on the way."""
    when = when or datetime.now(timezone.utc)
    by_subject: dict[bytes, Cert] = {}
    for c in intermediates:
        by_subject.setdefault(c.subject_der, c)
    roots_by_subject = {c.subject_der: c for c in roots}

    chain = [leaf]
    expired = [] if leaf.valid_at(when) else [leaf.cn]
    current = leaf

    for _ in range(12):                              # depth bound
        if current.subject_der in roots_by_subject and current.self_signed:
            return ChainResult(CHAINED, chain, roots_by_subject[current.subject_der],
                               expired_in_chain=expired)

        root = roots_by_subject.get(current.issuer_der)
        if root is not None:
            if not verify_signed_by(current, root):
                return ChainResult(BROKEN_CHAIN, chain,
                                   note=f"{current.cn} is not signed by {root.cn}",
                                   expired_in_chain=expired)
            chain.append(root)
            if not root.valid_at(when):
                expired.append(root.cn)
            return ChainResult(CHAINED, chain, root, expired_in_chain=expired)

        issuer = by_subject.get(current.issuer_der)
        if issuer is None:
            return ChainResult(INCOMPLETE, chain,
                               note=f"no certificate for issuer of {current.cn}",
                               expired_in_chain=expired)
        if not verify_signed_by(current, issuer):
            return ChainResult(BROKEN_CHAIN, chain,
                               note=f"{current.cn} is not signed by {issuer.cn}",
                               expired_in_chain=expired)
        if not issuer.valid_at(when):
            expired.append(issuer.cn)
        chain.append(issuer)
        current = issuer

    return ChainResult(BROKEN_CHAIN, chain, note="chain too deep",
                       expired_in_chain=expired)


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

    print("trust")

    check(not ChainResult(UNTRUSTED_ROOT).trusted, "UNTRUSTED_ROOT is not trusted")
    check(not ChainResult(BROKEN_CHAIN).trusted, "BROKEN_CHAIN is not trusted")
    check(not ChainResult(INCOMPLETE).trusted, "INCOMPLETE is not trusted")
    check(not ChainResult(NO_ROOTS).trusted, "an empty trust store is not trusted")
    check(ChainResult(CHAINED).trusted, "CHAINED is trusted")

    # Encoding: the silent-failure case that motivated this module.
    der = load_roots()[0].der
    check(decode_certificate_bytes(der) == der, "DER passes through unchanged")
    b64 = base64.b64encode(der)
    check(decode_certificate_bytes(b64) == der, "bare base64 is decoded, not mis-read")
    pem = b"-----BEGIN CERTIFICATE-----\n" + b64 + b"\n-----END CERTIFICATE-----\n"
    check(decode_certificate_bytes(pem) == der, "PEM armour is stripped")
    try:
        decode_certificate_bytes(b"hello world, not a certificate")
        check(False, "garbage input is rejected")
    except TrustStoreError:
        check(True, "garbage input is rejected")

    roots = load_roots()
    check(len(roots) >= 5, f"the CCA trust store loads ({len(roots)} roots)")
    check(all(r.public_key for r in roots), "every root carries a usable public key")
    check(all(r.self_signed for r in roots), "every root is self-signed")
    names = {r.cn for r in roots}
    check(any("2022" in n for n in names), f"the current CCA root is present ({sorted(names)})")

    # Every root must verify its own signature — a cheap check that the loader
    # produced real certificates rather than plausible-looking rubbish.
    selfok = sum(verify_signed_by(r, r) for r in roots)
    check(selfok == len(roots), f"every root verifies its own signature ({selfok}/{len(roots)})")

    # A root must NOT appear to sign an unrelated root.
    if len(roots) >= 2:
        a, b = roots[0], roots[1]
        check(not verify_signed_by(a, b),
              "a root does not verify against an unrelated root's key")

    # An empty directory must raise, never return an empty store.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        try:
            load_roots(Path(d))
            check(False, "an empty trust store raises rather than fails open")
        except TrustStoreError:
            check(True, "an empty trust store raises rather than fails open")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
