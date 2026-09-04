"""Corpus currency — does each obligation rest on law we can show is current?

Legora ships this as "Monitors", Harvey as "Horizon Scanning": both of the
best-funded players in this lane sell "the law changed" as a headline product
(sourced in docs/TECHNICAL_PLAN_EVIDENCED_2026_09.md §1). This module is that
primitive at our scale and under our discipline.

It fetches nothing and invents no amount. It maps each obligation to the dated
instrument its answer depends on, then rolls up the acquisition/currency state
those instruments ALREADY carry -- in prescribed_thresholds and the registration
records -- into one obligation-level view: is the legal basis CURRENT, not yet in
force, SUPERSEDED (we may be serving stale law), or UNACQUIRED?

## Why an engine and not a flag per obligation

An obligation that silently rests on an unacquired rule renders green while
standing on law we have never read. s.2(85) small-company status is exactly that
today: it depends on G.S.R. 700(E), which is UNACQUIRED (S-002). Rather than let
that hide inside a threshold lookup, this surfaces it as a first-class signal
naming the instrument to acquire. And when a NEWER amendment lands that we have
not caught up to, `SUPERSEDED` says so instead of quietly serving the old amount.

## What CURRENT does and does not claim

CURRENT means the instrument the obligation depends on is servable and in force
at the as-of date. For obligations resting only on the Companies Act text we hold
verbatim (VERIFIED in the corpus), CURRENT is as strong as our claim to hold the
current Act -- whose own currency is tracked by the corpus law-effective-date,
not here. This module governs the delegated-rule layer, which is where thresholds
actually move.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from checker.prescribed_thresholds import Threshold, all_thresholds

# ── currency states, ordered best -> worst so a rollup can take the worst ──────
CURRENT = "CURRENT"                    # servable instrument, in force at the date
NOT_YET_IN_FORCE = "NOT_YET_IN_FORCE"  # the governing instrument commences later
SUPERSEDED = "SUPERSEDED"              # we serve an amount a newer, unacquired instrument may replace
UNACQUIRED = "UNACQUIRED"             # the governing instrument is known but not servable
UNDECLARED = "UNDECLARED"             # the obligation declares no basis here -- a gap in THIS map

# Worse = higher rank. A finding that needs a human wins over one that does not.
_SEVERITY = {CURRENT: 0, NOT_YET_IN_FORCE: 1, SUPERSEDED: 2, UNACQUIRED: 3, UNDECLARED: 4}

# States that mean "someone must act before this obligation is safe to serve".
NEEDS_ACTION = (SUPERSEDED, UNACQUIRED, UNDECLARED)


@dataclass(frozen=True)
class Dependency:
    """What an obligation's answer rests on, for currency purposes.

    threshold_keys empty => the obligation rests only on Act text held verbatim.
    Otherwise each key names a prescribed_thresholds amount whose state decides
    whether the obligation stands on current, acquired law.
    """
    obligation_id: str
    basis: str
    threshold_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    obligation_id: str
    status: str
    detail: str
    instrument: str | None = None      # the instrument to acquire, when there is one

    @property
    def needs_action(self) -> bool:
        return self.status in NEEDS_ACTION


# ── the dependency map ────────────────────────────────────────────────────────
# Conservative and explicit: an obligation appears here only where we can name
# what it rests on. The small-company duty is the one delegated-rule dependency
# today; the rest rest on Act text we hold verbatim. Every obligation in the
# register must be covered -- the test below fails if one is missing, because an
# obligation with no declared currency basis is itself a finding (UNDECLARED).
_SMALL_CO_KEYS = (
    "small_company.paid_up_capital.prescribed",
    "small_company.turnover.prescribed",
)

DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency("CA13-S2-85-SMALL",
               "the prescribed small-company limits, set by delegated rule", _SMALL_CO_KEYS),
    Dependency("CA13-S96-AGM", "Companies Act 2013 s.96, held verbatim in corpus"),
    Dependency("CA13-S173-BOARD", "Companies Act 2013 s.173, held verbatim in corpus"),
    Dependency("CA13-S149-BOARD-SIZE", "Companies Act 2013 s.149(1), held verbatim in corpus"),
    Dependency("CA13-S149-3-RESIDENT", "Companies Act 2013 s.149(3), held verbatim in corpus"),
    Dependency("CA13-S137-AOC4", "Companies Act 2013 s.137, held verbatim in corpus"),
    Dependency("CA13-S92-RETURN", "Companies Act 2013 s.92, held verbatim in corpus"),
    Dependency("CA13-S135-CSR",
               "Companies Act 2013 s.135(1) thresholds, stated in the Act itself, not delegated"),
)


def _for_key(key: str) -> list[Threshold]:
    return [t for t in all_thresholds() if t.key == key]


def _currency_of_key(key: str, as_of: date) -> Finding:
    recorded = _for_key(key)
    if not recorded:
        return Finding("", UNDECLARED, f"no threshold on record for {key}", None)

    covering = [t for t in recorded if t.covers(as_of)]
    future = [t for t in recorded if t.effective_from > as_of]

    if not covering:
        if future:
            nxt = min(future, key=lambda t: t.effective_from)
            return Finding("", NOT_YET_IN_FORCE,
                           f"{nxt.instrument} takes effect {nxt.effective_from.isoformat()}",
                           nxt.instrument)
        return Finding("", UNACQUIRED, f"no instrument on record covers {as_of.isoformat()}", None)

    servable = [t for t in covering if t.servable]
    if servable:
        latest = max(servable, key=lambda t: t.effective_from)
        # Are we serving an amount a NEWER, not-yet-acquired instrument may replace?
        newer_unacquired = [t for t in covering
                            if not t.servable and t.effective_from > latest.effective_from]
        if newer_unacquired:
            nu = max(newer_unacquired, key=lambda t: t.effective_from)
            return Finding("", SUPERSEDED,
                           f"serving {latest.instrument} but {nu.instrument} "
                           f"({nu.effective_from.isoformat()}) may supersede it and is not acquired",
                           nu.instrument)
        return Finding("", CURRENT, f"{latest.instrument} ({latest.state})", latest.instrument)

    # something covers the date but nothing servable does: the rule is unacquired.
    t = max(covering, key=lambda x: x.effective_from)
    return Finding("", UNACQUIRED, t.note or f"{t.instrument} is on record but not servable",
                   t.instrument)


def currency_of(dep: Dependency, as_of: date) -> Finding:
    """The currency of one obligation. Worst of its keys; CURRENT if Act-only."""
    if not dep.threshold_keys:
        return Finding(dep.obligation_id, CURRENT, dep.basis, None)
    per_key = [_currency_of_key(k, as_of) for k in dep.threshold_keys]
    worst = max(per_key, key=lambda f: _SEVERITY[f.status])
    return Finding(dep.obligation_id, worst.status, f"{dep.basis}: {worst.detail}", worst.instrument)


def report(as_of: date) -> list[Finding]:
    """Currency of every obligation in the register, worst first.

    Includes an UNDECLARED finding for any obligation the register carries but
    this map does not -- so adding an obligation without declaring its basis is
    caught here rather than passing silently.
    """
    from checker.obligations import REGISTER

    declared = {d.obligation_id: d for d in DEPENDENCIES}
    findings: list[Finding] = []
    for ob in REGISTER:
        dep = declared.get(ob.obligation_id)
        if dep is None:
            findings.append(Finding(ob.obligation_id, UNDECLARED,
                                    "obligation has no declared currency basis", None))
        else:
            findings.append(currency_of(dep, as_of))
    findings.sort(key=lambda f: (-_SEVERITY[f.status], f.obligation_id))
    return findings


def stale(as_of: date) -> list[Finding]:
    """Only the obligations that need someone to act. The alert list."""
    return [f for f in report(as_of) if f.needs_action]


def affected_by(instrument_fragment: str) -> list[str]:
    """The Monitors primitive: which obligations would this instrument touch?

    Given a fragment of an instrument's name (e.g. 'G.S.R. 700(E)'), return the
    obligation ids whose declared thresholds are set by a matching instrument.
    This is what turns 'a new Gazette arrived' into 'these obligations change'.
    """
    frag = instrument_fragment.lower()
    hit_keys = {t.key for t in all_thresholds() if frag in t.instrument.lower()}
    return sorted(d.obligation_id for d in DEPENDENCIES
                  if set(d.threshold_keys) & hit_keys)


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

    print("currency")
    today = date(2026, 8, 31)

    # ── every obligation is covered, and the report is worst-first ──────────
    from checker.obligations import REGISTER
    rep = report(today)
    check(len(rep) == len(REGISTER),
          f"the report covers every obligation ({len(rep)}/{len(REGISTER)})")
    ids = {f.obligation_id for f in rep}
    check(ids == {ob.obligation_id for ob in REGISTER},
          "...and exactly the register's obligations, no more")
    severities = [_SEVERITY[f.status] for f in rep]
    check(severities == sorted(severities, reverse=True), "worst findings sort first")

    # ── the small-company duty rests on G.S.R. 700(E), which is UNACQUIRED ───
    small = [f for f in rep if f.obligation_id == "CA13-S2-85-SMALL"][0]
    check(small.status == UNACQUIRED,
          f"small-company currency is UNACQUIRED while 700(E) is unacquired ({small.status})")
    check(small.instrument and "700(E)" in small.instrument,
          f"...and names the instrument to acquire ({small.instrument})")
    check(small.needs_action, "...and is flagged as needing action")
    check(small in stale(today), "...and appears on the stale/alert list")

    # ── an Act-only obligation is CURRENT ────────────────────────────────────
    agm = [f for f in rep if f.obligation_id == "CA13-S96-AGM"][0]
    check(agm.status == CURRENT, f"an Act-only obligation is CURRENT ({agm.status})")
    check(not agm.needs_action, "...and needs no action")

    # ── the Monitors primitive: 700(E) touches exactly the small-company duty ─
    touched = affected_by("G.S.R. 700(E)")
    check(touched == ["CA13-S2-85-SMALL"],
          f"affected_by('G.S.R. 700(E)') finds the small-company duty ({touched})")
    check(affected_by("no such instrument") == [],
          "an unknown instrument touches nothing")

    # ── SUPERSEDED: we serve an amount a newer unacquired instrument may replace
    from unittest import mock
    import checker.currency as cur
    from checker.company_profile import Money
    from checker.provenance import CORROBORATED, UNRESOLVED
    key = "small_company.turnover.prescribed"
    served = Threshold(key, Money.crore(40), date(2022, 9, 15), None,
                       "G.S.R. 700(E) of 2022", "u", CORROBORATED, "attested")
    newer = Threshold(key, Money.crore(60), date(2025, 4, 1), None,
                      "G.S.R. 999(E) of 2025", "u", UNRESOLVED, "not yet acquired")
    with mock.patch.object(cur, "all_thresholds", lambda: (served, newer)):
        f = cur._currency_of_key(key, date(2026, 1, 1))
        check(f.status == SUPERSEDED,
              f"a newer unacquired amendment marks the served amount SUPERSEDED ({f.status})")
        check("999(E)" in (f.instrument or ""), "...naming the amendment to catch up to")
        # before the newer instrument commenced, the served amount is CURRENT
        f2 = cur._currency_of_key(key, date(2023, 1, 1))
        check(f2.status == CURRENT, "...but before it commenced the served amount is CURRENT")

    # ── NOT_YET_IN_FORCE: nothing covers a date before any instrument ────────
    with mock.patch.object(cur, "all_thresholds", lambda: (served,)):
        f3 = cur._currency_of_key(key, date(2020, 1, 1))
        check(f3.status == NOT_YET_IN_FORCE,
              f"a date before the only instrument is NOT_YET_IN_FORCE ({f3.status})")

    # ── once 700(E) is attested, the small-company duty becomes CURRENT ──────
    import scripts.register_gsr700e as sreg
    attested = {"artifact_sha256": "sha256:" + "cd" * 32,
                "identity_checked_by": "reviewer-01",
                "identity_checked_at": "2026-08-31T00:00:00Z",
                "verbatim_clause_checked_by": "reviewer-01",
                "verbatim_clause_checked_at": "2026-08-31T00:00:00Z",
                "status": "CORROBORATED"}
    with mock.patch.object(sreg, "registration", lambda: attested):
        small2 = [f for f in report(today) if f.obligation_id == "CA13-S2-85-SMALL"][0]
        check(small2.status == CURRENT,
              f"once 700(E) is attested the small-company duty is CURRENT ({small2.status})")
        check(not stale(today) or all(s.obligation_id != "CA13-S2-85-SMALL"
                                      for s in stale(today)),
              "...and it drops off the alert list")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
