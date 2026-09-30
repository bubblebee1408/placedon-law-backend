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

from checker.lattice import Lattice
from checker.prescribed_thresholds import Threshold, all_thresholds

# ── currency states, ordered best -> worst so a rollup can take the worst ──────
CURRENT = "CURRENT"                    # servable instrument, in force at the date
NOT_YET_IN_FORCE = "NOT_YET_IN_FORCE"  # the governing instrument commences later
SUPERSEDED = "SUPERSEDED"              # we serve an amount a newer, unacquired instrument may replace
UNACQUIRED = "UNACQUIRED"             # the governing instrument is known but not servable
UNDECLARED = "UNDECLARED"             # the obligation declares no basis here -- a gap in THIS map

# Worse = higher rank. A finding that needs a human wins over one that does not.
# The order lives in the lattice; _SEVERITY is derived from it so there is exactly
# one place this vocabulary can be reordered.
_LATTICE = Lattice("currency",
                   (CURRENT, NOT_YET_IN_FORCE, SUPERSEDED, UNACQUIRED, UNDECLARED))
_SEVERITY = {s: _LATTICE.rank(s) for s in _LATTICE.states}

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
    # Delegated rules this obligation's answer needs that are NOT amounts in the
    # threshold chain. s.177/s.188/s.203 each turn on a Rule we may not hold, and
    # without naming it here the obligation reported CURRENT -- a claim we had
    # read law we had never opened. Same defect class as G.S.R. 880(E).
    rule_ids: tuple[str, ...] = ()


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
    Dependency("CA13-S185-LOANS-DIRECTORS",
               "Companies Act 2013 s.185, held verbatim in corpus"),
    Dependency("CA13-S186-LOAN-INVESTMENT",
               "Companies Act 2013 s.186 (the 60%/100% limit is stated in the Act itself)"),
    Dependency("CA13-S188-RPT",
               "Companies Act 2013 s.188, held verbatim in corpus; the members'-approval "
               "threshold is a delegated rule (S-188-RULES) surfaced on the obligation row",
               rule_ids=("S-188-RULES",)),
    Dependency("CA13-S177-AUDIT-CTTE",
               "Companies Act 2013 s.177, held verbatim; the prescribed class (Rule 6) is a "
               "delegated rule (S-177-RULES) surfaced on the obligation row",
               rule_ids=("S-177-RULES",)),
    Dependency("CA13-S203-KMP",
               "Companies Act 2013 s.203, held verbatim; the prescribed KMP class is a "
               "delegated rule (S-203-RULES) surfaced on the obligation row",
               rule_ids=("S-203-RULES",)),
    Dependency("CA13-S180-BORROWING-LIMIT",
               "Companies Act 2013 s.180(1)(c), held verbatim in corpus; the limit is the "
               "aggregate of paid-up capital, free reserves and securities premium, stated "
               "in the Act itself and not prescribed by rule"),
    Dependency("CA13-S184-DIRECTOR-INTEREST",
               "Companies Act 2013 s.184, held verbatim in corpus; the >2% shareholding and "
               "partner/owner/member limbs are stated in s.184(2) itself, not prescribed by rule"),
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


def _rule_findings(rule_ids: tuple[str, ...]) -> list[Finding]:
    """A delegated rule we cannot use makes the obligation's basis UNACQUIRED."""
    if not rule_ids:
        return []
    from checker.staleness import rule_usable      # lazy: staleness imports us
    out = []
    for rid in rule_ids:
        usable, why = rule_usable(rid)
        if not usable:
            out.append(Finding("", UNACQUIRED, f"{rid}: {why}", rid))
    return out


def currency_of(dep: Dependency, as_of: date) -> Finding:
    """The currency of one obligation: the worst of everything its answer rests on.

    That is its prescribed amounts AND any delegated rule it needs. An obligation
    with neither rests only on Act text we hold verbatim, and is CURRENT.
    """
    findings = [_currency_of_key(k, as_of) for k in dep.threshold_keys]
    findings += _rule_findings(dep.rule_ids)
    if not findings:
        return Finding(dep.obligation_id, CURRENT, dep.basis, None)
    worst = _LATTICE.worst_of(findings, lambda f: f.status).witness
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


def _matches(fragment: str, instrument_name: str) -> bool:
    """Does `fragment` name `instrument_name`? The ONLY containment test in this module.

    Extracted 2026-09-26 (PLAN_19 G0.1) because `affected_by` and `acquisition_for`
    each had their own copy and they had already drifted: `affected_by` did not strip
    and did not refuse an empty fragment, so **`affected_by("")` returned
    `['CA13-S2-85-SMALL']`** while `acquisition_for("")` returned `None`.
    `acquisition_for`'s docstring claimed "Matched exactly as `affected_by` matches",
    and that was false the day it was written.

    The empty case is not a tidy-up. `operations.py` feeds a Gazette trigger straight
    in, so an empty or whitespace trigger was manufacturing an operation against the
    small-company threshold -- work created by a source that named nothing.

    Deliberately NOT anchored. PLAN_19 G0.1 asked for anchoring to whole registered
    instrument ids; the decision doc records why that was refused (§6.2): every live
    caller passes a Gazette-style NAME fragment, no caller holds an id, and anchoring
    would have reinstated the false "Nobody has read the instrument yet" sentence
    removed in 8d578f3.
    """
    frag = fragment.strip().lower()
    if not frag:
        return False
    # RT: a punctuation-only fragment named nothing, and got a substantive answer.
    # Found 2026-09-26 red-teaming this module: "." , "-" and "(" each matched several
    # instrument titles by substring and came back AMBIGUOUS -- literally true and
    # useless, because a caller passing "." asked no question. The same shape as the
    # one-character SOURCE that closed a requirement in operation_store (RT-12): a
    # check for "non-empty" is not a check for "means something".
    if not any(c.isalnum() for c in frag):
        return False
    return frag in instrument_name.lower()


def affected_by(instrument_fragment: str) -> list[str]:
    """The Monitors primitive: which obligations would this instrument touch?

    Given a fragment of an instrument's name (e.g. 'G.S.R. 700(E)'), return the
    obligation ids whose declared thresholds are set by a matching instrument.
    This is what turns 'a new Gazette arrived' into 'these obligations change'.
    """
    hit_keys = {t.key for t in all_thresholds()
                if _matches(instrument_fragment, t.instrument)}
    return sorted(d.obligation_id for d in DEPENDENCIES
                  if set(d.threshold_keys) & hit_keys)


ACQUIRED = "ACQUIRED"   # attested, and the deciding module permits reliance on it
PENDING = "PENDING"     # a registration record exists; no person has attested it
# A fragment that names SEVERAL instruments names none of them. Measured 2026-09-26:
# "G.S.R." matches five distinct instruments and "Companies Act 2013" matches two, and
# both used to come back read=True off whichever row sorted first -- an answer about an
# instrument the caller never asked about. This is NOT `None`: something is on record,
# and saying "no record" would be the same conflation G0.1 exists to remove. `read` is
# False, so both callers' existing `not acq.read` branch handles it conservatively.
AMBIGUOUS = "AMBIGUOUS"
ACQUISITION_STATUS = (ACQUIRED, PENDING, AMBIGUOUS)


@dataclass(frozen=True)
class Acquisition:
    """Whether a named instrument has in fact been read, and on what evidence.

    The companion to `affected_by`. That function answers "what would this
    instrument touch"; this one answers the question a lawyer asks immediately
    afterwards -- **has anyone actually opened it** -- and it exists because the
    answer was being asserted rather than looked up.

    `themis.get_instrument_impact("880")` told every caller "Nobody has read the
    instrument yet, so nothing follows from it until someone acquires and attests
    it" as a CONSTANT, with no branch. G.S.R. 880(E) was registered on 2026-09-10,
    identity and verbatim clause both checked by a named reviewer, status
    CORROBORATED. The product was telling lawyers nobody had read an instrument a
    person had read a fortnight earlier -- wrong in the direction that makes an
    honest system look like it holds nothing (PLAN_17 M1.3).
    """

    instrument: str            # the full name the record holds, not the fragment asked for
    read: bool                 # == (status == ACQUIRED). Derived, never independent.
    state: str                 # the answering record's OWN evidence word, verbatim
    source_url: str            # "" when the record names none -- never invented
    # None when nothing dated is on record. A registration record carries no
    # commencement date in general, and inventing one would be a fabricated legal
    # date -- the thing this repository refuses most consistently.
    effective_from: date | None
    note: str = ""
    # PLAN_19 G0.1. `None` used to mean two different things: "never heard of it" and
    # "downloaded, hashed, and waiting for a reviewer". The second was being reported
    # as the first, so an operation demanded someone acquire a file already on disk.
    status: str = ACQUIRED
    # Which record answered. The states come from two vocabularies -- provenance
    # states on the threshold path, `PENDING_HUMAN_REVIEW` and the like on the
    # registry path -- and a reader who cannot tell which they are looking at cannot
    # use either. A verdict with no witness is unusable.
    answered_from: str = ""


def _ambiguous(fragment: str, names: list[str], answered_from: str) -> Acquisition:
    """The answer when a fragment names more than one instrument.

    It names them all, in `note`, rather than picking one. A caller that silently got
    the first of five would have no way to know it had asked a question with several
    answers.
    """
    return Acquisition(
        instrument=f"{len(names)} instruments match {fragment.strip()!r}",
        read=False, state="", source_url="", effective_from=None,
        note=("this fragment does not name one instrument; it matches: "
              + "; ".join(n[:70] for n in names)),
        status=AMBIGUOUS, answered_from=answered_from)


def acquisition_for(instrument_fragment: str) -> Acquisition | None:
    """Has anyone read the instrument this fragment names? `None` if none is on record.

    Matched exactly as `affected_by` matches, so the two can never disagree about
    which instrument a fragment means.

    `read` is deliberately NOT a state comparison written here. It is
    `Threshold.servable`, which routes through `release.may_release` -- the single
    gate that decides whether evidence may reach a user as a legal statement. A
    fourth opinion about what "attested" means is exactly what `CLAUDE.md` forbids,
    and there are already three modules entitled to hold one.

    When several thresholds rest on the same instrument, the WORST governs: an
    instrument is read only if every amount resting on it may be served. Taking the
    best would let one corroborated amount vouch for an unacquired sibling.
    """
    hits = [t for t in all_thresholds() if _matches(instrument_fragment, t.instrument)]
    if hits:
        names = {t.instrument for t in hits}
        if len(names) > 1:
            return _ambiguous(instrument_fragment, sorted(names),
                              "checker.prescribed_thresholds")
        # Threshold path FIRST and unchanged, so 700(E) and 880(E) cannot regress.
        worst = min(hits, key=lambda t: (t.servable, t.effective_from))
        servable = all(t.servable for t in hits)
        if servable:
            status = ACQUIRED
        else:
            # A non-servable threshold does NOT tell us which of two things is true:
            # a record exists and no person has attested it, or nothing was ever
            # acquired. Mapping both to PENDING would be the very conflation G0.1
            # removes, committed on the other path -- caught 2026-09-26 by the
            # `none_acquired()` tests written for M1.3, which stub the registration
            # away and correctly expect "nobody has read it".
            from checker import instrument_registry as _ir
            on_record = any(_matches(instrument_fragment, r.title)
                            for r in _ir.records())
            if not on_record:
                return None
            status = PENDING
        return Acquisition(instrument=worst.instrument, read=servable,
                           state=worst.state, source_url=worst.source_url,
                           effective_from=worst.effective_from, note=worst.note,
                           status=status,
                           answered_from="checker.prescribed_thresholds")

    # Registry SECOND: an instrument may be on record without setting any threshold
    # this system declares. KMP, PAS, SEBI LODR and Rule 15 are all in that position,
    # and every one of them used to come back as `None` -- indistinguishable from an
    # instrument nobody has ever downloaded.
    from checker import instrument_registry          # lazy: it imports scripts.*
    reg = [r for r in instrument_registry.records()
           if _matches(instrument_fragment, r.title)]
    if not reg:
        return None
    titles = {r.title for r in reg}
    if len(titles) > 1:
        return _ambiguous(instrument_fragment, sorted(titles),
                          ", ".join(sorted(r.module for r in reg)))
    # The WORST governs, as on the threshold path: one attested record must not vouch
    # for an unattested sibling matched by the same fragment.
    worst_r = min(reg, key=lambda r: r.attested)
    return Acquisition(instrument=worst_r.title,
                       read=all(r.attested for r in reg),
                       state=worst_r.state, source_url=worst_r.source_url,
                       effective_from=None,
                       note="", status=ACQUIRED if worst_r.attested else PENDING,
                       answered_from=worst_r.module)


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

    # ── every obligation DECLARES a basis. An obligation added to the register
    # without a Dependency here reports UNDECLARED: the map catching its own gap.
    # That is the right behaviour, but it must never be the resting state -- an
    # UNDECLARED row is a hole in our map, not a finding about a company.
    undeclared = [f.obligation_id for f in rep if f.status == UNDECLARED]
    check(not undeclared,
          f"every obligation declares a currency basis (undeclared: {undeclared})")

    # ── the small-company duty rests on G.S.R. 700(E): UNACQUIRED when the Rule
    # is not attested. Forced via the stub so this does not depend on the live
    # on-disk attestation state (which flips once a reviewer attests 700(E)).
    import scripts.register_gsr700e as _reg
    from checker.prescribed_thresholds import none_acquired as _none_acquired
    with _none_acquired():
        rep_unacq = report(today)
        small = [f for f in rep_unacq if f.obligation_id == "CA13-S2-85-SMALL"][0]
        check(small.status == UNACQUIRED,
              f"small-company currency is UNACQUIRED while 700(E) is unacquired ({small.status})")
        check(small.instrument and "880(E)" in small.instrument,
              f"...and names the instrument to acquire — the one governing THIS "
              f"date, not the one it superseded ({small.instrument})")
        check(small.needs_action, "...and is flagged as needing action")
        check(small in stale(today), "...and appears on the stale/alert list")

    # ── and CURRENT once the whole chain is attested ────────────────────────
    from checker.prescribed_thresholds import all_acquired as _all_acquired
    with _all_acquired():
        small_c = [f for f in report(today)
                   if f.obligation_id == "CA13-S2-85-SMALL"][0]
        check(small_c.status == CURRENT,
              f"small-company currency is CURRENT once 700(E) is attested ({small_c.status})")
        check(not small_c.needs_action, "...and no longer needs action")

    # ── REGRESSION GUARD: attesting the SUPERSEDED instrument must not make a
    # later date current. This is the bug that shipped: 700(E) was attested, its
    # record said effective_to=None, and the engine reported CURRENT on a 2026
    # date while G.S.R. 880(E) had governed since 01-12-2025. Serving superseded
    # law as current is the one failure this system exists to prevent.
    import scripts.register_gsr880e as _reg880
    with _reg.stub_registration(_reg.attested_stub()), _reg880.stub_registration(None):
        f2026 = [f for f in report(date(2026, 9, 9))
                 if f.obligation_id == "CA13-S2-85-SMALL"][0]
        check(f2026.status != CURRENT,
              f"an attested 700(E) does NOT make a 2026 date current ({f2026.status})")
        check("880(E)" in (f2026.instrument or ""),
              f"...and the finding names 880(E) as what must be acquired ({f2026.instrument})")
        # The status alone is too weak to be a guard: with the bug present the
        # status reads SUPERSEDED, which is != CURRENT and would let this pass
        # while the engine went on SERVING ₹4 crore. What must be true is that
        # the superseded amount is not served at all. A company with ₹6 crore
        # capital is small under 880(E) and not small under 700(E) -- serving the
        # old figure is a wrong answer, not a cautious one.
        from checker.prescribed_thresholds import (
            operative_small_company_limits as _limits, ThresholdUnavailable as _TU)
        try:
            served = _limits(date(2026, 9, 9))
            check(False, f"the superseded limits must not be served ({served})")
        except _TU as e:
            check("880(E)" in str(e),
                  "the superseded limits are refused, naming the instrument to acquire")
        # while its own window is still answered correctly
        f2024 = [f for f in report(date(2024, 6, 1))
                 if f.obligation_id == "CA13-S2-85-SMALL"][0]
        check(f2024.status == CURRENT,
              f"...and 700(E) still makes its OWN window current ({f2024.status})")

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
    with mock.patch.object(sreg, "registration", lambda: attested), _all_acquired():
        small2 = [f for f in report(today) if f.obligation_id == "CA13-S2-85-SMALL"][0]
        check(small2.status == CURRENT,
              f"once 700(E) is attested the small-company duty is CURRENT ({small2.status})")
        check(not stale(today) or all(s.obligation_id != "CA13-S2-85-SMALL"
                                      for s in stale(today)),
              "...and it drops off the alert list")


    # ---- acquisition_for: both branches, and the gate behind them ---------------
    # PLAN_17 M1.3. The bug was a CONSTANT where a question belonged, so the test
    # that matters is the one proving the answer can be either.
    from checker.prescribed_thresholds import all_acquired, none_acquired

    with all_acquired():
        a = acquisition_for("880")
        check(a is not None and a.read,
              "an attested instrument reads as read")
        check(a.instrument.startswith("G.S.R. 880(E)") and a.effective_from == date(2025, 12, 1),
              f"...and names itself and its commencement ({a.instrument[:24]}, {a.effective_from})")
        check(a.state in ("CORROBORATED", "VERIFIED"),
              f"...on a servable evidence state ({a.state})")

    with none_acquired():
        # With the registration stubbed away there is no record at all, so `None` is
        # the honest answer -- not PENDING. This assertion changed on 2026-09-26: it
        # used to demand an Acquisition here, and G0.1 made "no record" and
        # "record, unattested" different answers.
        check(acquisition_for("880") is None,
              "with no registration on record at all, the answer is None, not PENDING")

    # ---- G0.1: three states, and none of them is the other ----------------------
    check(acquisition_for("nonexistent-instrument-xyz") is None,
          "an instrument nothing holds is None")
    for frag, mod in (("Managerial Personnel", "register_kmp_rules"),
                      ("Prospectus and Allotment", "register_pas_rules"),
                      ("SEBI", "register_sebi_lodr")):
        a = acquisition_for(frag)
        if a is None or a.status != PENDING or mod not in a.answered_from:
            check(False, f"{frag!r} should be PENDING via {mod} (got "
                         f"{None if a is None else (a.status, a.answered_from)})")
            break
    else:
        check(True, "an instrument registered but NOT attested is PENDING, naming the "
                    "module that said so -- KMP, PAS and SEBI LODR")
    a = acquisition_for("Managerial Personnel")
    check(a.read is False and a.effective_from is None,
          "...not read, and with no invented commencement date")

    # An over-broad fragment names several instruments, so it names none of them.
    for frag, n in (("Companies Act 2013", 2), ("G.S.R.", 2)):
        a = acquisition_for(frag)
        if a is None or a.status != AMBIGUOUS or a.read:
            check(False, f"{frag!r} must be AMBIGUOUS and not read "
                         f"(got {None if a is None else (a.status, a.read)})")
            break
    else:
        check(True, "a fragment matching several instruments is AMBIGUOUS, never "
                    "read=True off whichever row sorted first")
    check("matches:" in acquisition_for("G.S.R.").note,
          "...and it names the candidates rather than silently picking one")
    check(acquisition_for("880").status == ACQUIRED and acquisition_for("880").read,
          "880(E) is still ACQUIRED -- the threshold path is unchanged")

    # ---- the shared matcher, and the bug it closed -------------------------------
    check(affected_by("") == [] and affected_by("   ") == [],
          "affected_by('') is empty: an empty Gazette trigger manufactured work until "
          "2026-09-26, matching the small-company threshold on a fragment naming nothing")
    check(_matches("880", "G.S.R. 880(E), x") and not _matches("", "anything"),
          "_matches is the one containment test, and it refuses an empty fragment")
    # RT 2026-09-26: punctuation matched many titles and answered AMBIGUOUS.
    for junk in (".", "-", "(", ",", "()", "--", " . "):
        if acquisition_for(junk) is not None:
            check(False, f"a punctuation-only fragment {junk!r} got a substantive answer")
            break
    else:
        check(True, "a fragment with no alphanumeric character names nothing -- "
                    "'non-empty' is not 'means something' (RT-12's shape, one layer up)")
    check(not _matches("...", "G.S.R. 880(E)") and _matches("880", "G.S.R. 880(E)"),
          "...and a real fragment still matches")

    check(acquisition_for("G.S.R. 9999(E)") is None,
          "an instrument no threshold rests on is None, not a false negative dressed as one")
    check(acquisition_for("") is None and acquisition_for("   ") is None,
          "an empty fragment matches nothing rather than everything")
    check(acquisition_for("880").instrument == acquisition_for("880").instrument,
          "the same fragment resolves the same way every time")
    # The match must be the SAME match affected_by uses, or the two can disagree
    # about which instrument a fragment means.
    check(bool(affected_by("880")) == (acquisition_for("880") is not None),
          "acquisition_for and affected_by agree on whether a fragment names anything")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
