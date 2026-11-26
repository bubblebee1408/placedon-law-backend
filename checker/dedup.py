#!/usr/bin/env python3
"""Near-duplicate document detection via MinHash (Broder, IEEE 1997).

Jaccard similarity estimated from signature overlap. No model, no dependencies
beyond stdlib. The hash family is a set of random linear functions over a
Mersenne prime — the same construction `datasketch` uses, but in ~80 lines.

The algorithm:
  1. Shingle each document into overlapping k-grams of words.
  2. For each shingle set, compute a MinHash signature: for each of `num_perm`
     hash functions h_i, record min(h_i(shingle) for shingle in set).
  3. Estimate Jaccard similarity as the fraction of signature positions that agree.

Two documents with Jaccard >= threshold are near-duplicates.

Reference:
  Broder A. Z. "On the Resemblance and Containment of Documents."
  Compression and Complexity of Sequences, IEEE, 1997, pp. 21–29.

Run: PYTHONPATH=. python3 checker/dedup.py --test
"""
from __future__ import annotations

import hashlib
import struct

__all__ = ["MinHashSignature", "minhash", "jaccard_estimate", "find_duplicates"]

_MERSENNE = (1 << 61) - 1
_MAX_HASH = (1 << 32) - 1
NUM_PERM = 128
SHINGLE_K = 5
THRESHOLD = 0.6


def _word_shingles(text: str, k: int = SHINGLE_K) -> set[str]:
    words = text.lower().split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _hash_family(num_perm: int = NUM_PERM, seed: int = 42) -> list[tuple[int, int]]:
    """Deterministic hash family: (a, b) pairs for h(x) = (a*x + b) mod p."""
    rng_state = hashlib.sha256(seed.to_bytes(8, "big")).digest()
    pairs = []
    for i in range(num_perm):
        h = hashlib.sha256(rng_state + i.to_bytes(4, "big")).digest()
        a = int.from_bytes(h[:8], "big") % _MERSENNE
        b = int.from_bytes(h[8:16], "big") % _MERSENNE
        if a == 0:
            a = 1
        pairs.append((a, b))
    return pairs


_FAMILY = _hash_family()

MinHashSignature = tuple[int, ...]


def _shingle_hash(shingle: str) -> int:
    return struct.unpack("<I", hashlib.md5(shingle.encode()).digest()[:4])[0]


def minhash(text: str, *, num_perm: int = NUM_PERM) -> MinHashSignature:
    """Compute a MinHash signature for `text`."""
    shingles = _word_shingles(text)
    if not shingles:
        return tuple(_MAX_HASH for _ in range(num_perm))
    hashes = [_shingle_hash(s) for s in shingles]
    sig = []
    for a, b in _FAMILY[:num_perm]:
        min_val = _MAX_HASH
        for h in hashes:
            val = ((a * h + b) % _MERSENNE) & _MAX_HASH
            if val < min_val:
                min_val = val
        sig.append(min_val)
    return tuple(sig)


def jaccard_estimate(sig_a: MinHashSignature, sig_b: MinHashSignature) -> float:
    """Estimate Jaccard similarity from two MinHash signatures."""
    if len(sig_a) != len(sig_b):
        raise ValueError("signatures must have the same length")
    if not sig_a:
        return 0.0
    return sum(a == b for a, b in zip(sig_a, sig_b)) / len(sig_a)


def find_duplicates(
    documents: dict[str, str],
    *,
    threshold: float = THRESHOLD,
) -> list[tuple[str, str, float]]:
    """Return pairs of near-duplicate document ids with their similarity.

    `documents` maps id → text. Returns [(id_a, id_b, similarity), ...]
    sorted by similarity descending.
    """
    sigs = {doc_id: minhash(text) for doc_id, text in documents.items()}
    ids = list(sigs)
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = jaccard_estimate(sigs[ids[i]], sigs[ids[j]])
            if sim >= threshold:
                pairs.append((ids[i], ids[j], sim))
    return sorted(pairs, key=lambda t: -t[2])


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("dedup")

    # ── identical documents have similarity ~1.0 ──────────────────────────
    text = ("This Non-Disclosure Agreement is entered into between Acme Corp "
            "and Beta Ltd for the purpose of protecting confidential information "
            "shared between the parties during the course of their business.")
    sig_a = minhash(text)
    sig_b = minhash(text)
    check(sig_a == sig_b, "identical text produces identical signatures")
    check(jaccard_estimate(sig_a, sig_b) == 1.0, "self-similarity is 1.0")

    # ── near-duplicates score high ────────────────────────────────────────
    text_variant = text.replace("Acme Corp", "Acme Corporation").replace(
        "Beta Ltd", "Beta Limited")
    sig_c = minhash(text_variant)
    sim = jaccard_estimate(sig_a, sig_c)
    check(sim > 0.5, f"near-duplicate similarity is high ({sim:.3f})")

    # ── unrelated documents score low ─────────────────────────────────────
    unrelated = ("The board of directors met on 15 March 2024 to discuss the "
                 "annual financial results and approve the dividend distribution "
                 "for the fiscal year ending 31 March 2024.")
    sig_d = minhash(unrelated)
    sim_unrel = jaccard_estimate(sig_a, sig_d)
    check(sim_unrel < 0.3, f"unrelated documents score low ({sim_unrel:.3f})")

    # ── find_duplicates returns correct pairs ─────────────────────────────
    docs = {"nda_v1": text, "nda_v2": text_variant, "minutes": unrelated}
    pairs = find_duplicates(docs, threshold=0.4)
    check(len(pairs) >= 1, f"finds at least one duplicate pair ({len(pairs)})")
    check(pairs[0][0] == "nda_v1" and pairs[0][1] == "nda_v2",
          "the NDA variants are the top pair")

    # ── empty text ────────────────────────────────────────────────────────
    sig_empty = minhash("")
    check(len(sig_empty) == NUM_PERM, "empty text produces a valid signature")

    # ── deterministic ─────────────────────────────────────────────────────
    check(minhash(text) == sig_a, "signatures are deterministic across calls")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
