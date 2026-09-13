"""Axis D — may we show this to a paying customer?

`provenance` grades whether evidence is good (Axis A) and how a source behaved
when asked (Axis B). `event_log` grades what kind of statement we are serving
(Axis C). None of them records whether we are ALLOWED to render a value.

That was safe while statute was the only corpus: the Gazette is public, and the
question never arose. It is fatal for any market or register feed. Platts, Argus,
ICE/CME settlement and MCX are licensed IP -- Argus's terms read "you may not
conduct text or data mining or web scraping ... for any purpose" -- and
SOURCE_POLICY.md already records that RBI prohibits commercial use AND caching.
Bloomberg's actual business is licence compliance. A product that renders a
licensed print to a customer is one contract breach from zero, and the compliance
buyer it is sold to is precisely the buyer who cannot tolerate that.

## Capabilities are a SET, not a ladder

A feed may be showable but not storable (a display-only quote), or storable but
not showable (a licensed input usable only to compute a derived figure). There is
no ordering in which those are two points on one scale. Modelling them as a
ladder would repeat the mistake `provenance.py:38-40` documents about conflating
evidence state with accessibility -- two axes that need opposite responses.

## Nothing here is a fact until a person reads the contract

The candidates below come from a source audit dated 2026-09-11. An audit is
secondary reporting. It is a lead to CHECK, never a right to rely on -- the same
status `prescribed_thresholds` gave Rs 10 crore before a human read G.S.R. 880(E).

So `capabilities_of()` returns the EMPTY frozenset for every feed until a
registration record on disk says a person checked its contract. An unregistered
or unattested feed may not even be computed with, and `release.may_release`
refuses it. Fail closed, as `robots.py:11-13` does for an unparseable robots.txt.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "corpus" / "licences"

# ── the capabilities (Axis D) ─────────────────────────────────────────────────
MAY_SHOW = "MAY_SHOW"        # may render the value to an entitled customer
MAY_STORE = "MAY_STORE"      # may persist beyond the session
MAY_DERIVE = "MAY_DERIVE"    # may publish a figure derived from it
INTERNAL_ONLY = "INTERNAL_ONLY"   # may compute with it; may never render it
EMBARGOED = "EMBARGOED"      # held, not releasable until a stated datetime
CAPABILITIES = (MAY_SHOW, MAY_STORE, MAY_DERIVE, INTERNAL_ONLY, EMBARGOED)

NONE_AT_ALL: frozenset[str] = frozenset()


class LicenceError(ValueError):
    """A licence claim that cannot be relied on. Never downgraded to a warning."""


@dataclass(frozen=True)
class Candidate:
    """What the source audit REPORTED. A lead to check, never a right to rely on."""
    feed_id: str
    operator: str
    reported: tuple[str, ...]    # capabilities the audit believed apply
    evidence: str                # what the audit actually read
    must_check: str              # what a person must confirm before attesting

    def __post_init__(self) -> None:
        unknown = [c for c in self.reported if c not in CAPABILITIES]
        if unknown:
            raise LicenceError(f"{self.feed_id}: unknown capability {unknown}")


# Recorded so the work is not repeated, and so nobody "remembers" a term wrongly.
# NONE of this is relied on. Every entry needs a human to read the contract.
CANDIDATES = (
    Candidate("OFAC_SDN", "US Treasury OFAC", (MAY_SHOW, MAY_STORE, MAY_DERIVE),
              "audit 2026-09-11: reported US-government public domain",
              "confirm the publication terms on the Treasury site itself"),
    Candidate("EIA_API", "US Energy Information Administration",
              (MAY_SHOW, MAY_STORE, MAY_DERIVE),
              "audit 2026-09-11: reported public domain, free API key",
              "confirm the API terms of service and any attribution requirement"),
    Candidate("WORLD_BANK_PINK", "World Bank", (MAY_SHOW, MAY_STORE, MAY_DERIVE),
              "audit 2026-09-11: reported LIKELY CC BY -- the audit said likely",
              "confirm the licence is CC BY and not CC BY-NC before any commercial use"),
    Candidate("OPENSANCTIONS", "OpenSanctions", (MAY_SHOW, MAY_STORE, MAY_DERIVE),
              "audit 2026-09-11: published metered pricing with an explicit reseller tier",
              "sign the reseller tier; confirm what the base tier does NOT permit"),
    Candidate("GFW_AIS", "Global Fishing Watch", (INTERNAL_ONLY,),
              "audit 2026-09-11: CC BY-NC per their own FAQ -- NON-COMMERCIAL",
              "NC almost certainly bars our use entirely; confirm before computing with it"),
    Candidate("BALTIC_EXCHANGE", "Baltic Exchange", (MAY_STORE, INTERNAL_ONLY),
              "audit 2026-09-11: subscription ~GBP2,000/yr, customer redistribution "
              "is a SEPARATE and unpriced tier",
              "confirm internal-use scope; do NOT assume display rights are included"),
    Candidate("PLATTS", "S&P Global Platts", (),
              "audit 2026-09-11: licensed IP, anti-scraping and anti-redistribution",
              "no use at all without a negotiated licence"),
    Candidate("ARGUS", "Argus Media", (),
              "audit 2026-09-11: terms state text/data mining and scraping are barred "
              "'for any purpose'",
              "no use at all without a negotiated licence"),
    Candidate("VESSELFINDER", "VesselFinder", (),
              "audit 2026-09-11: terms bar resale, redistribution, sublicensing, and "
              "building substitute analytics",
              "prohibited at the accessible price point; do not design against it"),
    Candidate("AISSTREAM", "AISStream.io", (),
              "audit 2026-09-11: an open, UNANSWERED question about commercial "
              "licensing -- so no documented permission exists",
              "obtain written permission or treat as prohibited"),
)

_BY_ID = {c.feed_id: c for c in CANDIDATES}


@dataclass(frozen=True)
class Attestation:
    """A person read the contract and recorded what it permits."""
    feed_id: str
    capabilities: frozenset[str]
    contract_ref: str
    contract_date: str
    checked_by: str
    checked_at: str


def _record_path(feed_id: str) -> Path:
    return RECORDS / f"{feed_id.lower()}.json"


def attestation(feed_id: str) -> Attestation | None:
    """The registration record, if a person made one. Read from disk, never cached."""
    p = _record_path(feed_id)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    required = ("capabilities", "contract_ref", "contract_date", "checked_by", "checked_at")
    if not all(d.get(k) for k in required):
        return None            # a half-filled record is not an attestation
    caps = frozenset(d["capabilities"])
    if not caps <= set(CAPABILITIES):
        return None            # an unknown capability voids the record
    return Attestation(feed_id, caps, d["contract_ref"], d["contract_date"],
                       d["checked_by"], d["checked_at"])


def capabilities_of(feed_id: str) -> frozenset[str]:
    """What we may do with this feed. EMPTY unless a person attested it.

    Deliberately returns the empty set rather than raising, so a caller that
    forgets to check still gets the fail-closed answer from release.may_release.
    """
    att = attestation(feed_id)
    return att.capabilities if att else NONE_AT_ALL


def why_refused(feed_id: str) -> str:
    """The sentence to show when a feed is not usable. Never a blank."""
    if attestation(feed_id):
        return ""
    cand = _BY_ID.get(feed_id)
    if cand is None:
        return (f"{feed_id}: no licence record and no audited candidate. An "
                "unregistered feed carries no rights at all.")
    return (f"{feed_id} ({cand.operator}): not attested. The audit reported "
            f"{list(cand.reported) or 'no usable rights'} on the basis of "
            f"'{cand.evidence}', which is secondary reporting and may not be relied "
            f"on. Before use, a person must: {cand.must_check}.")


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

    print("licence")

    from checker import release

    # ── the whole point: NOTHING is usable until a person attests it ─────────
    unattested = [c.feed_id for c in CANDIDATES if capabilities_of(c.feed_id)]
    check(not unattested,
          f"no audited candidate is usable without attestation ({unattested or 'none'})")
    check(capabilities_of("OFAC_SDN") == NONE_AT_ALL,
          "even a public-domain feed carries no rights until checked")
    check(capabilities_of("NOT_A_FEED") == NONE_AT_ALL,
          "an entirely unknown feed carries no rights")

    # ── and the gate refuses it, with something a user can read ─────────────
    r = release.may_release(evidence_state="VERIFIED",
                            licence=capabilities_of("PLATTS"), what="a Platts assessment")
    check(not r.allowed, "release refuses an unattested feed even at VERIFIED evidence")
    check("does not permit display" in r.reason, f"...readably ({r.reason[:48]}…)")

    # ── the refusal names what a person must do ─────────────────────────────
    w = why_refused("WORLD_BANK_PINK")
    check("not attested" in w and "confirm the licence" in w,
          "the refusal names the specific check a person must perform")
    check("likely" in w,
          "...and preserves the audit's own hedge rather than hardening it into a fact")
    check("no licence record" in why_refused("NOT_A_FEED"),
          "an unknown feed's refusal says so plainly")

    # ── capabilities are a SET, not a ladder ────────────────────────────────
    store_only = frozenset({MAY_STORE})
    check(not release.may_release(evidence_state="VERIFIED", licence=store_only).allowed,
          "MAY_STORE does not imply MAY_SHOW")
    show_only = frozenset({MAY_SHOW})
    check(release.may_release(evidence_state="VERIFIED", licence=show_only).allowed,
          "...and MAY_SHOW does not require MAY_STORE")

    # ── a malformed capability is refused at construction ───────────────────
    try:
        Candidate("X", "op", ("NONSENSE",), "e", "m")
        check(False, "an unknown capability is refused at construction")
    except LicenceError:
        check(True, "an unknown capability is refused at construction")

    # ── the audit's prohibitions are recorded as prohibitions ───────────────
    for fid in ("PLATTS", "ARGUS", "VESSELFINDER", "AISSTREAM"):
        check(_BY_ID[fid].reported == (),
              f"{fid} is recorded as carrying no usable rights")

    # ── a half-filled record is not an attestation ──────────────────────────
    check(attestation("OFAC_SDN") is None,
          "no attestation record exists on disk yet, and none is invented")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
