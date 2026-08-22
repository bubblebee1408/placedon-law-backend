"""Minimal DER decoder, enough to read a PKCS#7 signature and an X.509 certificate.

Written rather than imported because this file sits on the trust path. A document
authenticity check that depends on a package a developer can silently upgrade is a
check whose meaning can change without anyone reading a diff. The repo has no
third-party dependencies and this is the one place where that is a security
property rather than a preference.

Scope is deliberately small: definite-length DER, which is what PDF signatures and
X.509 use. BER's indefinite lengths are rejected rather than guessed at, because a
parser that accepts more than the standard permits is a parser an attacker can
disagree with the verifier about.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Tag numbers we care about
BOOLEAN = 0x01
INTEGER = 0x02
BIT_STRING = 0x03
OCTET_STRING = 0x04
NULL = 0x05
OID = 0x06
UTF8_STRING = 0x0C
SEQUENCE = 0x10
SET = 0x11
PRINTABLE_STRING = 0x13
T61_STRING = 0x14
IA5_STRING = 0x16
UTC_TIME = 0x17
GENERALIZED_TIME = 0x18
BMP_STRING = 0x1E

_STRING_TAGS = {UTF8_STRING, PRINTABLE_STRING, T61_STRING, IA5_STRING, BMP_STRING}


class Asn1Error(ValueError):
    """Malformed input. Never recovered from — a guess here is a forged document."""


@dataclass
class Node:
    tag: int
    cls: int                 # 0 universal, 1 application, 2 context, 3 private
    constructed: bool
    start: int               # offset of the identifier octet
    header_len: int
    content: bytes
    children: list["Node"] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.start + self.header_len + len(self.content)

    @property
    def full(self) -> int:
        """Length of the complete TLV — needed to re-serialise SignedAttrs."""
        return self.header_len + len(self.content)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Node cls={self.cls} tag=0x{self.tag:02x} len={len(self.content)}>"


def _parse_one(data: bytes, i: int, depth: int) -> Node:
    if depth > 40:
        raise Asn1Error("nesting too deep")
    if i >= len(data):
        raise Asn1Error("truncated at identifier")

    ident = data[i]
    cls = ident >> 6
    constructed = bool(ident & 0x20)
    tag = ident & 0x1F
    j = i + 1
    if tag == 0x1F:                       # high-tag-number form
        tag = 0
        while True:
            if j >= len(data):
                raise Asn1Error("truncated in high tag")
            b = data[j]
            j += 1
            tag = (tag << 7) | (b & 0x7F)
            if not b & 0x80:
                break

    if j >= len(data):
        raise Asn1Error("truncated at length")
    n = data[j]
    j += 1
    if n == 0x80:
        # Indefinite length is legal BER but not DER. Accepting it would let a
        # document be parsed one way here and another way by a real verifier.
        raise Asn1Error("indefinite length is not DER")
    if n & 0x80:
        k = n & 0x7F
        if k == 0 or k > 6:
            raise Asn1Error(f"unreasonable length-of-length {k}")
        if j + k > len(data):
            raise Asn1Error("truncated in long length")
        length = int.from_bytes(data[j:j + k], "big")
        j += k
    else:
        length = n

    if j + length > len(data):
        raise Asn1Error("length exceeds buffer")

    node = Node(tag=tag, cls=cls, constructed=constructed, start=i,
                header_len=j - i, content=data[j:j + length])

    if constructed:
        k = 0
        while k < len(node.content):
            child = _parse_one(node.content, k, depth + 1)
            node.children.append(child)
            k = child.end
    return node


def parse(data: bytes) -> Node:
    """Parse a single DER TLV from the start of `data`."""
    return _parse_one(data, 0, 0)


def oid_to_str(content: bytes) -> str:
    """Decode an OBJECT IDENTIFIER's content octets to dotted form."""
    if not content:
        raise Asn1Error("empty OID")
    first = content[0]
    parts = [str(first // 40), str(first % 40)]
    val = 0
    for b in content[1:]:
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            parts.append(str(val))
            val = 0
    return ".".join(parts)


def find(node: Node, tag: int, cls: int = 0) -> list[Node]:
    """Every descendant with this tag and class, depth-first."""
    out: list[Node] = []
    for c in node.children:
        if c.tag == tag and c.cls == cls:
            out.append(c)
        out.extend(find(c, tag, cls))
    return out


def text_of(node: Node) -> str:
    """Decode a string node. BMPString is UTF-16BE, which trips naive readers."""
    if node.tag == BMP_STRING:
        return node.content.decode("utf-16-be", "replace")
    return node.content.decode("utf-8", "replace")


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

    print("asn1")

    n = parse(bytes([0x02, 0x01, 0x05]))
    check(n.tag == INTEGER and n.content == b"\x05", "a short INTEGER parses")

    seq = parse(bytes([0x30, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x02]))
    check(seq.tag == SEQUENCE and len(seq.children) == 2,
          "a SEQUENCE exposes its children")

    long = parse(bytes([0x04, 0x82, 0x01, 0x00]) + b"A" * 256)
    check(len(long.content) == 256, "a long-form length parses")

    check(oid_to_str(bytes([0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x07, 0x02]))
          == "1.2.840.113549.1.7.2", "the signedData OID decodes correctly")
    check(oid_to_str(bytes([0x55, 0x04, 0x03])) == "2.5.4.3",
          "the commonName OID decodes correctly")

    # Rejections. Each of these, if accepted, is a way to disagree with a real
    # verifier about what a document says.
    for bad, why in [
        (bytes([0x30, 0x80, 0x00, 0x00]), "indefinite length is rejected"),
        (bytes([0x04, 0x05, 0x01]), "a length past the buffer is rejected"),
        (bytes([0x02]), "a truncated header is rejected"),
        (bytes([0x04, 0x88] + [0xff] * 8), "an absurd length-of-length is rejected"),
    ]:
        try:
            parse(bad)
            check(False, why)
        except Asn1Error:
            check(True, why)

    check(text_of(Node(BMP_STRING, 0, False, 0, 2, "hi".encode("utf-16-be"))) == "hi",
          "BMPString decodes as UTF-16BE")

    deep = b""
    for _ in range(60):
        deep = bytes([0x30, len(deep)]) + deep
    try:
        parse(deep)
        check(False, "deeply nested input is rejected")
    except Asn1Error:
        check(True, "deeply nested input is rejected")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
