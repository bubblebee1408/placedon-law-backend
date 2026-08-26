"""Certificate revocation: CRL retrieval, validation, and the signing-time question.

## Revocation is not retroactive, and that is the whole difficulty

A certificate revoked in 2024 does not invalidate a signature it made in 2023.
RFC 5280 records a `revocationDate`, and the question a verifier must answer is
not "is this certificate revoked now?" but "was it revoked **at the moment of
signing**?" Answering the first and reporting it as the second would condemn
every historical document whose signer later left a firm or replaced a token.

So `check()` returns the revocation date alongside the verdict, and
`NOT_REVOKED_AT_SIGNING` is a distinct outcome from `NOT_REVOKED`. Where no
trusted signing time exists, the honest answer is `UNKNOWN_AT_SIGNING`: the
document's own claimed signing time is asserted by the signer and is not
evidence against them.

## Why the CRL's own signature is checked

CRLs are served over plain HTTP — CCA's own is at `http://cca.gov.in/rw/...`.
That is not a defect: a CRL carries the issuing CA's signature, so its integrity
comes from cryptography rather than from transport. But it means an unverified
CRL is worth nothing, because anyone on the path can serve one. A CRL whose
signature does not verify against the issuing certificate is discarded, not used.

## Freshness

A CRL past its `nextUpdate` is stale. Stale is not the same as clean: the
absence of a serial from an out-of-date list is not evidence it was never
revoked. `STALE_CRL` is reported rather than folded into "not revoked".
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from checker import asn1
from checker.asn1 import Asn1Error, Node
from checker.robots import USER_AGENT

CACHE = Path("corpus/trust/crl")

# Outcomes
NOT_REVOKED = "NOT_REVOKED"                      # absent from a fresh, verified CRL
NOT_REVOKED_AT_SIGNING = "NOT_REVOKED_AT_SIGNING"  # revoked later than the signature
REVOKED = "REVOKED"                              # revoked at or before signing
UNKNOWN_AT_SIGNING = "UNKNOWN_AT_SIGNING"        # revoked, but no trusted signing time
STALE_CRL = "STALE_CRL"                          # list is past nextUpdate
NO_CRL_URL = "NO_CRL_URL"                        # certificate names no distribution point
UNREACHABLE = "UNREACHABLE"                      # could not fetch
UNVERIFIED_CRL = "UNVERIFIED_CRL"                # signature did not verify: discarded
NOT_CHECKED = "NOT_CHECKED"                      # we did not look

CLEAN = (NOT_REVOKED, NOT_REVOKED_AT_SIGNING)

# Extension OIDs
OID_CRL_DP = "2.5.29.31"
OID_AIA = "1.3.6.1.5.5.7.1.1"
OID_OCSP = "1.3.6.1.5.5.7.48.1"
OID_CA_ISSUERS = "1.3.6.1.5.5.7.48.2"


@dataclass
class RevocationResult:
    status: str
    revoked_at: datetime | None = None
    crl_url: str | None = None
    crl_this_update: datetime | None = None
    crl_next_update: datetime | None = None
    crl_entries: int = 0
    crl_signature_verified: bool = False
    note: str = ""

    @property
    def clean(self) -> bool:
        return self.status in CLEAN


def _extensions(cert: Node) -> dict[str, bytes]:
    """OID -> extnValue octets, from the [3] EXPLICIT extensions of a tbsCertificate."""
    tbs = cert.children[0] if cert.children else None
    if tbs is None:
        return {}
    out: dict[str, bytes] = {}
    for c in tbs.children:
        if c.cls != 2 or c.tag != 3:
            continue
        for seq in (c.children[0].children if c.children else []):
            oid = next((k for k in seq.children if k.tag == asn1.OID), None)
            val = next((k for k in seq.children if k.tag == asn1.OCTET_STRING), None)
            if oid is not None and val is not None:
                out[asn1.oid_to_str(oid.content)] = val.content
    return out


def _uris(blob: bytes) -> list[str]:
    """GeneralName uniformResourceIdentifier values, tagged [6] IMPLICIT IA5String."""
    out = []
    i = 0
    while i < len(blob) - 1:
        if blob[i] == 0x86:                       # context [6] primitive
            ln = blob[i + 1]
            if 0 < ln < 0x80 and i + 2 + ln <= len(blob):
                try:
                    s = blob[i + 2:i + 2 + ln].decode("ascii")
                    if s.startswith(("http://", "https://")):
                        out.append(s)
                except UnicodeDecodeError:
                    pass
                i += 2 + ln
                continue
        i += 1
    return out


def crl_urls(cert: Node) -> list[str]:
    v = _extensions(cert).get(OID_CRL_DP)
    return _uris(v) if v else []


def ocsp_urls(cert: Node) -> list[str]:
    v = _extensions(cert).get(OID_AIA)
    if not v:
        return []
    # AIA is a SEQUENCE of AccessDescription {accessMethod OID, accessLocation}.
    # Only the OCSP method's locations are wanted; CA-Issuers URLs point at
    # certificates, and treating them as responders would query the wrong service.
    out = []
    try:
        seq = asn1.parse(v)
    except Asn1Error:
        return []
    for ad in seq.children:
        oid = next((k for k in ad.children if k.tag == asn1.OID), None)
        if oid is None or asn1.oid_to_str(oid.content) != OID_OCSP:
            continue
        out.extend(_uris(ad.content))
    return out


def _parse_time(n: Node) -> datetime | None:
    s = n.content.decode("ascii", "replace").strip()
    fmt = "%y%m%d%H%M%S" if n.tag == asn1.UTC_TIME else "%Y%m%d%H%M%S"
    try:
        base = s[:-1] if s.endswith("Z") else s[:len(fmt) + 2]
        return datetime.strptime(base, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class CRL:
    revoked: dict[int, datetime] = field(default_factory=dict)
    this_update: datetime | None = None
    next_update: datetime | None = None
    der: bytes = b""
    node: Node | None = None

    def fresh_at(self, when: datetime) -> bool:
        if self.next_update is None:
            return False
        return when <= self.next_update


def parse_crl(der: bytes) -> CRL:
    root = asn1.parse(der)
    tbs = root.children[0]
    times = [c for c in tbs.children if c.tag in (asn1.UTC_TIME, asn1.GENERALIZED_TIME)]
    this_u = _parse_time(times[0]) if times else None
    next_u = _parse_time(times[1]) if len(times) > 1 else None

    revoked: dict[int, datetime] = {}
    # revokedCertificates is the SEQUENCE OF whose members are 2-3 element
    # SEQUENCEs starting with an INTEGER serial and a Time. Located by shape
    # rather than by position, because the optional version and extension fields
    # shift the index between CRL profiles.
    for c in tbs.children:
        if c.tag != asn1.SEQUENCE or c.cls != 0:
            continue
        members = [m for m in c.children if m.tag == asn1.SEQUENCE]
        if not members:
            continue
        looks_right = all(
            len(m.children) >= 2 and m.children[0].tag == asn1.INTEGER
            and m.children[1].tag in (asn1.UTC_TIME, asn1.GENERALIZED_TIME)
            for m in members[:5])
        if not looks_right:
            continue
        for m in members:
            serial = int.from_bytes(m.children[0].content, "big")
            when = _parse_time(m.children[1])
            if when:
                revoked[serial] = when
        break
    return CRL(revoked=revoked, this_update=this_u, next_update=next_u,
               der=der, node=root)


def verify_crl_signature(crl: CRL, issuer_der: bytes) -> bool:
    """Does the issuing CA's key sign this CRL? An unverified CRL is discarded."""
    from checker.pdf_signature import _pkcs1_digest, _rsa_recover
    from checker.trust import _SIG_ALG_DIGEST, load_certificate
    import hashlib
    if crl.node is None:
        return False
    try:
        issuer = load_certificate(issuer_der)
    except Exception:
        return False
    if issuer.public_key is None:
        return False
    kids = crl.node.children
    if len(kids) < 3:
        return False
    tbs_der = crl.node.content[kids[0].start:kids[0].start + kids[0].full]
    alg = next((asn1.oid_to_str(c.content) for c in kids[1].children
                if c.tag == asn1.OID), None)
    digest = _SIG_ALG_DIGEST.get(alg or "")
    if digest is None or kids[2].tag != asn1.BIT_STRING or not kids[2].content:
        return False
    block = _rsa_recover(kids[2].content[1:], issuer.public_key[0], issuer.public_key[1])
    got = _pkcs1_digest(block) if block else None
    if got is None:
        return False
    try:
        return hashlib.new(digest, tbs_der).digest() == got[1]
    except ValueError:
        return False


def fetch_crl(url: str, *, timeout: float = 30.0, cache: Path = CACHE) -> bytes | None:
    """Retrieve a CRL. Plain HTTP is expected and acceptable — see module docstring."""
    cache.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:]
    p = cache / f"{key}.crl"
    if p.exists():
        return p.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return None
            body = r.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if body[:1] != b"\x30":                       # not DER
        return None
    p.write_bytes(body)
    return body


def check(cert: Node, cert_der: bytes, issuer_der: bytes, *,
          serial: int, signing_time: datetime | None,
          offline: bool = False) -> RevocationResult:
    """Was this certificate revoked at the time it signed?"""
    urls = crl_urls(cert)
    if not urls:
        return RevocationResult(NO_CRL_URL,
                                note="certificate names no CRL distribution point")
    if offline:
        return RevocationResult(NOT_CHECKED, crl_url=urls[0],
                                note="offline mode: no CRL fetched")

    der = None
    used = None
    for u in urls:
        der = fetch_crl(u)
        if der:
            used = u
            break
    if der is None:
        return RevocationResult(UNREACHABLE, crl_url=urls[0],
                                note="no CRL could be retrieved")

    try:
        crl = parse_crl(der)
    except (Asn1Error, IndexError, ValueError) as exc:
        return RevocationResult(UNREACHABLE, crl_url=used, note=f"unparseable CRL: {exc}")

    verified = verify_crl_signature(crl, issuer_der)
    base = dict(crl_url=used, crl_this_update=crl.this_update,
                crl_next_update=crl.next_update, crl_entries=len(crl.revoked),
                crl_signature_verified=verified)
    if not verified:
        return RevocationResult(UNVERIFIED_CRL, **base,
                                note="CRL signature did not verify against the issuer; "
                                     "discarded rather than used")

    when = crl.revoked.get(serial)
    if when is None:
        if not crl.fresh_at(datetime.now(timezone.utc)):
            return RevocationResult(STALE_CRL, **base,
                                    note="serial absent, but the CRL is past its "
                                         "nextUpdate; absence is not evidence")
        return RevocationResult(NOT_REVOKED, **base)

    if signing_time is None:
        return RevocationResult(UNKNOWN_AT_SIGNING, revoked_at=when, **base,
                                note="certificate is revoked, but no trusted signing "
                                     "time exists to place the signature before it")
    if signing_time < when:
        return RevocationResult(NOT_REVOKED_AT_SIGNING, revoked_at=when, **base,
                                note=f"revoked {when.date()}, after the signature")
    return RevocationResult(REVOKED, revoked_at=when, **base,
                            note=f"revoked {when.date()}, at or before the signature")


def _test() -> None:
    ok = fail = 0

    def check_(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("revocation")

    check_(not RevocationResult(NOT_CHECKED).clean, "NOT_CHECKED is not clean")
    check_(not RevocationResult(UNREACHABLE).clean, "UNREACHABLE is not clean")
    check_(not RevocationResult(STALE_CRL).clean,
           "a stale CRL is not clean — absence from an old list proves nothing")
    check_(not RevocationResult(UNVERIFIED_CRL).clean,
           "an unverified CRL is not clean")
    check_(not RevocationResult(UNKNOWN_AT_SIGNING).clean,
           "revoked-with-no-signing-time is not clean")
    check_(not RevocationResult(REVOKED).clean, "REVOKED is not clean")
    check_(RevocationResult(NOT_REVOKED).clean and
           RevocationResult(NOT_REVOKED_AT_SIGNING).clean,
           "only NOT_REVOKED and NOT_REVOKED_AT_SIGNING are clean")

    # Extension extraction from the real chain.
    import re as _re
    from checker.pdf_signature import _certificates, _der_of, _cert_names
    data = Path("corpus/testdocs/_raw/rm_bm_20260507.pdf").read_bytes()
    blob = bytes.fromhex(_re.sub(rb"\s", b"",
                                 _re.findall(rb"/Contents\s*<([0-9A-Fa-f\s]+)>",
                                             data)[-1]).decode())
    ci = asn1.parse(blob)
    ex = next(c for c in ci.children if c.cls == 2 and c.tag == 0)
    certs = _certificates(ex.children[0])
    with_crl = [c for c in certs if crl_urls(c)]
    check_(len(with_crl) >= 2, f"CRL distribution points are extracted ({len(with_crl)})")
    urls = [u for c in certs for u in crl_urls(c)]
    check_(all(u.startswith("http") and not u.endswith(("0", "0I", "0P")) for u in urls),
           f"URLs are cleanly delimited, not regex-scraped ({urls[:2]})")
    check_(any("cca.gov.in" in u for u in urls),
           "CCA's own CRL endpoint is among them")
    oc = [u for c in certs for u in ocsp_urls(c)]
    check_(oc and all("ocsp" in u or "ocvs" in u for u in oc),
           f"OCSP responders are extracted and CA-Issuers URLs excluded ({oc})")

    # Freshness semantics.
    now = datetime.now(timezone.utc)
    past = CRL(next_update=now.replace(year=now.year - 1))
    future = CRL(next_update=now.replace(year=now.year + 1))
    check_(not past.fresh_at(now) and future.fresh_at(now),
           "freshness is decided by nextUpdate")
    check_(not CRL().fresh_at(now), "a CRL with no nextUpdate is never fresh")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
