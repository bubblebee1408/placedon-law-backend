"""Dated statutory thresholds, each carrying how well we actually know it.

s.2(85) does not state the small-company thresholds operatively. It states a
floor and a ceiling and then delegates:

    "(i) paid-up share capital of which does not exceed fifty lakh rupees or
     such higher amount AS MAY BE PRESCRIBED which shall not be more than
     [ten crore rupees]; [and] (ii) turnover of which [as per profit and loss
     account for the immediately preceding financial year] does not exceed two
     crore rupees or such higher amount as may be prescribed which shall not be
     more than [one hundred crore rupees]"

    -- quoted from our own corpus of the Act, not from recollection.

So the number that decides a real company is in a delegated rule, and the
widely-cited ₹4 crore / ₹40 crore appear nowhere in the Act. A classifier that
hardcoded them would be asserting a Rule it has never read.

## Why this file refuses rather than answers

Every threshold carries a provenance state from checker.provenance. `lookup()`
returns only what is SERVABLE. The prescribed amounts are NOT servable today:

  * India Code lists the operative instrument -- G.S.R. 700(E) of 15-09-2022,
    handle 123456789/508916 -- and its text bitstream is reachable.
  * But indiacode.gov.in/robots.txt has been answering **HTTP 502** on every
    attempt, and checker.robots fails closed on a 5xx: a 4xx means "no rules
    exist", a 5xx means "we cannot know what the rules are". So the compliant
    fetcher declines, correctly.
  * The reading recorded below was obtained OUTSIDE that gate and came back
    paraphrased rather than verbatim. It is a lead, not an acquisition. It is
    recorded so the work is not repeated, and marked so it cannot be served.

The consequence is deliberate: a small-company classification is
INSUFFICIENT_DATA until the instrument is acquired properly. That is the correct
answer today, and it is a better one than a confident number nobody verified.
"""
from __future__ import annotations

from contextlib import contextmanager as _contextmanager
from dataclasses import dataclass
from datetime import date, timedelta

from checker.company_profile import Money
from checker.provenance import CORROBORATED, SERVABLE, UNRESOLVED, VERIFIED


@dataclass(frozen=True)
class Threshold:
    """One dated amount, with where it came from and how well we know it."""
    key: str
    amount: Money
    effective_from: date
    effective_to: date | None          # None = still in force so far as we know
    instrument: str                    # the instrument that sets it
    source_url: str
    state: str                         # a checker.provenance evidence state
    note: str = ""                     # reader-facing: what a lawyer needs to know
    # Operator-facing: the acquisition route. Kept OUT of `note` because `note`
    # reaches a page a lawyer reads, and a script path in a compliance report is
    # noise at best and a credibility cost at worst. Same fact, two audiences.
    operator_note: str = ""

    @property
    def servable(self) -> bool:
        return self.state in SERVABLE

    def covers(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        return self.effective_to is None or as_of <= self.effective_to


class ThresholdUnavailable(LookupError):
    """No threshold we are willing to serve covers this date."""

    def __init__(self, key: str, as_of: date, held: list[Threshold]) -> None:
        self.key, self.as_of, self.held = key, as_of, held
        if held:
            detail = "; ".join(
                f"{t.instrument} — {t.note or 'not available'}" for t in held)
            # "cannot rely on" rather than "do not hold": once an artifact is
            # downloaded but not yet reviewed we DO hold it, and saying otherwise
            # contradicted the note that followed in the same sentence.
            msg = (f"the prescribed limit in force on {as_of.isoformat()} is set by "
                   f"an instrument we cannot yet rely on: {detail}")
        else:
            msg = (f"no instrument on record sets this prescribed limit on "
                   f"{as_of.isoformat()}")
        super().__init__(msg)

    @property
    def operator_detail(self) -> str:
        """The acquisition route. For an operator or a log, never a report."""
        return "; ".join(t.operator_note for t in self.held if t.operator_note)


_INDIA_CODE = "https://indiacode.gov.in/handle/123456789"
# The India Code handle for 880(E) is UNRESOLVED -- not looked up from a primary
# host, and inventing one would be a fabricated citation. The person who
# downloads it records the real source in the registration record.
SOURCE_880 = "UNRESOLVED — see scripts/register_gsr880e.py"

# The Act's own limbs. These ARE in our corpus verbatim, so they are usable --
# but note what they are: the floor below which no prescription is needed, and
# the ceiling above which none may go. Neither is the operative number once a
# Rule has been made.
_ACT_BOUNDS: tuple[Threshold, ...] = (
    Threshold("small_company.paid_up_capital.statutory_floor", Money.lakh(50),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(i)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "the amount that applies absent any prescription; held verbatim "
              "in our corpus of the Act"),
    Threshold("small_company.paid_up_capital.prescription_ceiling", Money.crore(10),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(i)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "no prescribed amount may exceed this"),
    Threshold("small_company.turnover.statutory_floor", Money.crore(2),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(ii)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "turnover as per the profit and loss account for the immediately "
              "preceding financial year"),
    Threshold("small_company.turnover.prescription_ceiling", Money.crore(100),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(ii)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "no prescribed amount may exceed this"),
)

def _prescribed_state() -> tuple[str, str, str]:
    """(evidence state, note) for the prescribed amounts, derived from evidence.

    Not a hand-edited constant. A constant saying CORROBORATED can outlive the
    artifact it was asserting, and the whole point of the registration record is
    that the state follows the evidence rather than someone's memory of it.
    """
    try:
        from scripts.register_gsr700e import registration, is_attested
    except ImportError:                                     # pragma: no cover
        return UNRESOLVED, "this instrument has not been acquired", ""

    rec = registration()
    if rec is None:
        return UNRESOLVED, "this instrument has not been acquired (reference S-002)", (
            "no registration on record. India Code lists the instrument and its "
            "text bitstream is reachable, but indiacode.gov.in/robots.txt answers "
            "HTTP 502 so checker.robots declines, and egazette chains to a root "
            "absent from this machine's trust store. Acquire under S-002: "
            "download in a browser, then scripts/register_gsr700e.py.")
    if not is_attested(rec):
        missing = [k for k in ("identity_checked_by", "verbatim_clause_checked_by")
                   if not rec.get(k)]
        return UNRESOLVED, (
            "the instrument is held but no reviewer has confirmed it is the right "
            "one and that its clause is reproduced verbatim (reference S-002)"), (
            f"artifact registered ({rec.get('artifact_sha256', '?')[:23]}…) but not "
            f"attested: {', '.join(missing) or 'status is not CORROBORATED'}. "
            "Hashing proves the bytes did not change, not that they are the right "
            "instrument or that the clause survived extraction. Run "
            "scripts/register_gsr700e.py --attest <reviewer-id>.")
    return CORROBORATED, (
        f"held and confirmed by a named reviewer on "
        f"{rec['identity_checked_at'][:10]}"), (
        f"registered and attested by {rec['identity_checked_by']} at "
        f"{rec['identity_checked_at']}; artifact "
        f"{rec.get('artifact_sha256', '?')[:23]}…")


def _prescribed_state_880() -> tuple[str, str, str]:
    """(evidence state, note) for the 2025 amounts. Derived, never asserted.

    Same shape as _prescribed_state, for the instrument that SUPERSEDED 700(E).
    """
    try:
        from scripts.register_gsr880e import registration, is_attested
    except ImportError:                                     # pragma: no cover
        return UNRESOLVED, "this instrument has not been acquired", ""

    rec = registration()
    if rec is None:
        return UNRESOLVED, (
            "it raises the small-company limits with effect from 01-12-2025, and we "
            "do not hold it. What it says is known to us only from secondary "
            "reporting, and this system does not state a statutory amount it has "
            "not read in the Gazette (reference S-003)"), (
            "no registration on record. Acquire under S-003: download the Gazette "
            "artifact in a browser, then scripts/register_gsr880e.py.")
    if not is_attested(rec):
        missing = [k for k in ("identity_checked_by", "verbatim_clause_checked_by")
                   if not rec.get(k)]
        return UNRESOLVED, (
            "the instrument is held but no reviewer has confirmed it is the right "
            "one and that its clause is reproduced verbatim (reference S-003)"), (
            f"artifact registered ({rec.get('artifact_sha256', '?')[:23]}…) but not "
            f"attested: {', '.join(missing) or 'status is not CORROBORATED'}. Run "
            "scripts/register_gsr880e.py --attest <reviewer-id>.")
    return CORROBORATED, (
        f"held and confirmed by a named reviewer on "
        f"{rec['identity_checked_at'][:10]}"), (
        f"registered and attested by {rec['identity_checked_by']} at "
        f"{rec['identity_checked_at']}; artifact "
        f"{rec.get('artifact_sha256', '?')[:23]}…")


# The date G.S.R. 880(E) took effect, and therefore the day after which the 2022
# amounts are no longer the operative prescription. Recording this is what stops
# the engine serving a superseded figure as current -- see the note below.
_GSR880_FROM = date(2025, 12, 1)


# The prescribed amounts. Their state is DERIVED, never asserted here.
#
# Two instruments, in sequence, and the boundary between them is load-bearing.
# 700(E)'s records once carried effective_to=None, which asserts "still in force
# so far as we know". That stopped being true on 01-12-2025 and the engine went
# on serving Rs 4 crore as CURRENT -- the exact failure this system exists to
# prevent. effective_to now closes the 2022 window, so for any date from
# 01-12-2025 the only record covering it is 880(E), which is not servable until a
# person acquires and attests it. The engine therefore REFUSES rather than
# serving either the superseded figure or an unverified new one.
def _prescribed() -> tuple[Threshold, ...]:
    state, note, op_note = _prescribed_state()
    state880, note880, op_note880 = _prescribed_state_880()
    _2022 = ("G.S.R. 700(E), Companies (Specification of Definition Details) "
             "Amendment Rules, 2022, dated 15-09-2022")
    _2025 = ("G.S.R. 880(E), Companies (Specification of Definition Details) "
             "Amendment Rules, 2025, dated 01-12-2025")
    superseded = " Superseded by G.S.R. 880(E) with effect from 01-12-2025."
    return (
        Threshold("small_company.paid_up_capital.prescribed", Money.crore(4),
                  date(2022, 9, 15), _GSR880_FROM - timedelta(days=1),
                  _2022, f"{_INDIA_CODE}/508916", state, note + superseded, op_note),
        Threshold("small_company.turnover.prescribed", Money.crore(40),
                  date(2022, 9, 15), _GSR880_FROM - timedelta(days=1),
                  _2022, f"{_INDIA_CODE}/508916", state, note + superseded, op_note),
        # The 2025 amounts are a CLAIM PENDING ATTESTATION, not a fact. They are
        # here so the artifact can be checked against them (register_gsr880e's
        # clause regex requires these words), and they are unservable until it is.
        Threshold("small_company.paid_up_capital.prescribed", Money.crore(10),
                  _GSR880_FROM, None, _2025, SOURCE_880, state880, note880, op_note880),
        Threshold("small_company.turnover.prescribed", Money.crore(100),
                  _GSR880_FROM, None, _2025, SOURCE_880, state880, note880, op_note880),
    )


def all_thresholds() -> tuple[Threshold, ...]:
    return _ACT_BOUNDS + _prescribed()


def held(key: str, as_of: date) -> list[Threshold]:
    """Every recorded amount for this key covering that date, servable or not."""
    return [t for t in all_thresholds() if t.key == key and t.covers(as_of)]


def lookup(key: str, as_of: date) -> Threshold:
    """The amount we are willing to serve. Raises rather than guessing."""
    candidates = held(key, as_of)
    servable = [t for t in candidates if t.servable]
    if not servable:
        raise ThresholdUnavailable(key, as_of, candidates)
    # Latest in force wins if several cover the date.
    return max(servable, key=lambda t: t.effective_from)


def operative_small_company_limits(as_of: date) -> tuple[Money, Money]:
    """Paid-up capital and turnover limits actually in force. Raises if unknown.

    Deliberately does NOT fall back to the statutory floor when the prescribed
    amount is unavailable. The floor is ₹50 lakh against a prescribed ₹4 crore,
    so falling back would classify most small companies as not small -- a wrong
    answer wearing the costume of a conservative one.
    """
    cap = lookup("small_company.paid_up_capital.prescribed", as_of)
    turn = lookup("small_company.turnover.prescribed", as_of)
    return cap.amount, turn.amount


# ── test support ──────────────────────────────────────────────────────────────
@_contextmanager
def all_acquired():
    """Stub EVERY instrument in the prescribed chain as acquired and attested.

    Tests that mean "the thresholds are available" must control the whole chain,
    not one instrument. Stubbing only 700(E) used to be enough; once 880(E)
    superseded it on 01-12-2025, a test that stubbed 700(E) and asked about a
    2026 date was asking about an instrument it had not stubbed -- which is how
    the supersession bug hid. One helper, so the next amendment updates one place.
    """
    import scripts.register_gsr700e as _r700
    import scripts.register_gsr880e as _r880
    with _r700.stub_registration(_r700.attested_stub()), \
         _r880.stub_registration(_r880.attested_stub()):
        yield


@_contextmanager
def none_acquired():
    """Stub EVERY instrument in the prescribed chain as NOT acquired.

    The mirror of all_acquired(), and needed for the same reason. A test meaning
    "the engine refuses while the law is unheld" must control the whole chain: on
    2026-09-10, stubbing only 700(E) leaves 880(E) attested on disk, so the row
    resolves and the test asserts the opposite of what it says. That is not
    hypothetical -- it is what happened to nine suites the moment 880(E) was
    attested, exactly as it happened when 700(E) was.

    Two helpers, one for each direction, so the next amendment updates one place.
    """
    import scripts.register_gsr700e as _r700
    import scripts.register_gsr880e as _r880
    with _r700.stub_registration(None), _r880.stub_registration(None):
        yield


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

    print("prescribed_thresholds")
    today = date(2026, 8, 31)

    # The Act's own limbs are held and usable.
    floor = lookup("small_company.paid_up_capital.statutory_floor", today)
    check(floor.amount == Money.lakh(50), f"the statutory floor is ₹50 lakh ({floor.amount})")
    ceil = lookup("small_company.turnover.prescription_ceiling", today)
    check(ceil.amount == Money.crore(100), f"the turnover ceiling is ₹100 crore ({ceil.amount})")

    # The prescribed amounts are on record. Their SERVABILITY depends on the live
    # registration/attestation state on disk, which the mocked blocks below
    # exercise deterministically. Here assert what holds in every state, then the
    # behaviour that matches the ACTUAL current state -- so this test stays green
    # both before the artifact is acquired and after it is attested, rather than
    # pinning to a transient "robots 502 / not yet acquired" moment.
    # Two instruments in sequence. Inside the 2022 window the 700(E) amounts are
    # the record; from 01-12-2025 they are superseded by 880(E).
    in_2022 = date(2024, 6, 1)
    rec = held("small_company.paid_up_capital.prescribed", in_2022)
    check(len(rec) == 1, "one prescribed capital amount covers a 2024 date")
    check(rec[0].amount == Money.crore(4), f"...as ₹4 crore ({rec[0].amount})")
    check(bool(rec[0].note.strip()),
          "...with its current acquisition status stated in the note")

    from scripts.register_gsr700e import registration as _live_reg, is_attested as _live_att
    if _live_att(_live_reg()):
        cap, turn = operative_small_company_limits(in_2022)
        check(cap == Money.crore(4) and turn == Money.crore(40),
              "700(E) is attested, so the 2022-window limits are servable")
    else:
        check(not rec[0].servable,
              "the live artifact is not yet attested, so the amount is not servable")
        try:
            operative_small_company_limits(in_2022)
            check(False, "small-company limits are refused while unattested")
        except ThresholdUnavailable:
            check(True, "small-company limits are refused while unattested")

    # ── the supersession boundary. This is the one correctness property: never
    # serve a figure a later instrument replaced. Before 880(E) commenced the
    # 2022 amounts stand; on and after it, NOTHING is served until a person
    # acquires and attests the new instrument. It must not fall back to ₹4 crore.
    day_before = _GSR880_FROM - timedelta(days=1)
    covering_before = held("small_company.paid_up_capital.prescribed", day_before)
    check([t.amount for t in covering_before] == [Money.crore(4)],
          f"the day before 880(E), ₹4 crore is the only record ({covering_before and covering_before[0].amount})")

    covering_after = held("small_company.paid_up_capital.prescribed", _GSR880_FROM)
    check([t.instrument for t in covering_after] and
          all("880(E)" in t.instrument for t in covering_after),
          "from 01-12-2025 only G.S.R. 880(E) covers the date")
    # These two are about what happens while the instrument is UNHELD, so they
    # must control that state. Asserting it against the ambient record made them
    # flip red the moment 880(E) was attested -- the same way the 700(E) tests
    # flipped when it was attested, and for the same reason.
    with none_acquired():
        covering_unheld = held("small_company.paid_up_capital.prescribed", _GSR880_FROM)
        check(not any(t.servable for t in covering_unheld),
              "...and while unheld it is not servable")
        try:
            operative_small_company_limits(_GSR880_FROM)
            check(False, "while unheld, the limits are REFUSED, not guessed")
        except ThresholdUnavailable as e:
            check("880(E)" in str(e),
                  "while unheld, the limits are refused, naming the instrument to acquire")
    # ...and now that it IS attested, the same date answers.
    check(operative_small_company_limits(_GSR880_FROM)[0] == Money.crore(10),
          "once attested, 880(E)'s commencement date serves ₹10 crore")
    # the failure mode this whole change exists to prevent
    check(not any(t.amount == Money.crore(4) and t.servable
                  for t in held("small_company.paid_up_capital.prescribed", date(2026, 9, 9))),
          "the superseded ₹4 crore figure is never servable on a 2026 date")

    # It must not silently fall back to the Act's floor.
    import inspect
    src = inspect.getsource(operative_small_company_limits)
    check("statutory_floor" not in src.split('"""')[2],
          "no fallback to the statutory floor in the code path")

    # Dates matter: nothing prescribed applies before the instrument existed.
    before = date(2022, 9, 14)
    check(not held("small_company.turnover.prescribed", before),
          "the 2022 prescription does not reach a date before it was made")
    check(held("small_company.turnover.prescribed", date(2022, 9, 15)),
          "...and does reach its own commencement date")

    # An unknown key is a refusal, not an empty answer.
    try:
        lookup("small_company.net_worth.prescribed", today)
        check(False, "an unknown key raises")
    except ThresholdUnavailable as e:
        check("no instrument on record" in str(e), f"an unknown key raises ({e})")

    # Every record names an instrument and a source.
    check(all(t.instrument and t.source_url for t in all_thresholds()),
          "every threshold names its instrument and source")
    check(all(t.state in (VERIFIED, UNRESOLVED, CORROBORATED) for t in all_thresholds()),
          "every threshold carries a provenance state")

    # The Act figures must never be confused for the operative ones.
    check(all("floor" in t.key or "ceiling" in t.key
              for t in _ACT_BOUNDS),
          "the Act's limbs are keyed as floor/ceiling, never as the operative amount")

    # The whole acquisition gate, exercised end to end against a temporary
    # record. Registration alone must NOT unlock the thresholds; only a
    # registration carrying both human attestations may.
    import json, tempfile
    from unittest import mock
    import scripts.register_gsr700e as reg

    unattested = {"artifact_sha256": "sha256:" + "ab" * 32,
                  "identity_checked_by": None, "identity_checked_at": None,
                  "verbatim_clause_checked_by": None,
                  "verbatim_clause_checked_at": None,
                  "status": "PENDING_HUMAN_REVIEW"}
    with mock.patch.object(reg, "registration", lambda: unattested):
        st, note, _op = _prescribed_state()
        check(st == UNRESOLVED, f"a registered but unattested artifact stays refused ({st})")
        check("no reviewer has confirmed" in note,
              f"...and the READER note says why, without a script path ({note[:60]}…)")
        check("not attested" in _op and "register_gsr700e.py" in _op,
              "...and the OPERATOR note carries the acquisition route")
        try:
            operative_small_company_limits(in_2022)
            check(False, "...and the limits are still unavailable")
        except ThresholdUnavailable:
            check(True, "...and the limits are still unavailable")

    attested = dict(unattested, identity_checked_by="reviewer-01",
                    identity_checked_at="2026-08-31T00:00:00Z",
                    verbatim_clause_checked_by="reviewer-01",
                    verbatim_clause_checked_at="2026-08-31T00:00:00Z",
                    status="CORROBORATED")
    with mock.patch.object(reg, "registration", lambda: attested):
        st2, note2, _op2b = _prescribed_state()
        check(st2 == CORROBORATED, f"an attested artifact makes them servable ({st2})")
        check("named reviewer" in note2,
              "...the reader note says a reviewer confirmed it, without naming them")
        check("reviewer-01" in _op2b, "...and the operator note names the reviewer")
        cap, turn = operative_small_company_limits(in_2022)
        check(cap == Money.crore(4) and turn == Money.crore(40),
              f"...and the limits come through, inside 700(E)'s window ({cap} / {turn})")

    # A partial attestation is not an attestation.
    half = dict(attested, verbatim_clause_checked_by=None)
    with mock.patch.object(reg, "registration", lambda: half):
        st3, _, _ = _prescribed_state()
        check(st3 == UNRESOLVED, "one of the two checks alone is not enough")

    # And with no record at all we are back to the real state.
    with mock.patch.object(reg, "registration", lambda: None):
        st4, note4, _op4 = _prescribed_state()
        check(st4 == UNRESOLVED, "no registration means no servable threshold")
        check("S-002" in note4, "...and the note names the open task")

    # ── the 2025 instrument is gated exactly the same way ────────────────────
    import scripts.register_gsr880e as reg880
    with reg880.stub_registration(None):
        st5, note5, _op5 = _prescribed_state_880()
        check(st5 == UNRESOLVED, f"880(E) unacquired is UNRESOLVED ({st5})")
        check("S-003" in note5, "...and the note names the open acquisition task")
        try:
            operative_small_company_limits(date(2026, 9, 9))
            check(False, "a 2026 date is refused while 880(E) is unacquired")
        except ThresholdUnavailable:
            check(True, "a 2026 date is refused while 880(E) is unacquired")

    with reg880.stub_registration(reg880.registered_unattested_stub()):
        st6, _, _ = _prescribed_state_880()
        check(st6 == UNRESOLVED, "downloading 880(E) without attesting is not enough")

    with reg880.stub_registration(reg880.attested_stub("reviewer-880")):
        st7, note7, _op7 = _prescribed_state_880()
        check(st7 == CORROBORATED, f"an attested 880(E) becomes servable ({st7})")
        check("named reviewer" in note7,
              "...the reader note says a reviewer confirmed it")
        check("reviewer-880" in _op7, "...and the operator note names the reviewer")
        cap25, turn25 = operative_small_company_limits(date(2026, 9, 9))
        check(cap25 == Money.crore(10) and turn25 == Money.crore(100),
              f"...and the 2025 limits then come through ({cap25} / {turn25})")
        # and the old figure still governs its own past
        cap22, _ = operative_small_company_limits(in_2022)
        check(cap22 == Money.crore(4),
              f"...while a 2024 date still gets the 2022 figure ({cap22})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
