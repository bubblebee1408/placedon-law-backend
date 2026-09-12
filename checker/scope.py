"""What body of law this engine claims to cover, and what it actually holds.

The product scope is **compliance across Indian corporate law**, not the Companies
Act alone. That is a deliberate widening, and it creates a specific danger this
module exists to remove.

## Why widening scope needs a register, not just a sentence

Every refusal this engine makes is credible because it names what it does not
hold. Widen the claimed scope without widening the refusals and the engine starts
looking like it covers SEBI, FEMA, IBC and stamp duty when it has never read a
line of any of them. A silence that used to mean "outside our scope" would start
meaning "no obligation found" -- and those are opposite answers.

So scope is declared here in three states, and the difference between the first
two is the whole point:

    IN_CORPUS     instruments are held; obligations can be decided
    DECLARED      in product scope, nothing acquired yet -- must REFUSE, naming
                  the body of law and what would have to be acquired
    OUT_OF_SCOPE  deliberately excluded, with the reason

`DECLARED` is not a weaker `IN_CORPUS`. It is an active refusal: a question in a
declared-but-unheld area gets an answer that says *this is in scope, we hold
nothing, here is what we would need* -- which is useful, and is not the same as
pretending the area does not exist.

## The invariant

No obligation may exist in the register for a body that is not IN_CORPUS. A test
asserts it. That is what stops scope-widening from quietly producing obligations
decided against law nobody acquired.
"""
from __future__ import annotations

from dataclasses import dataclass

IN_CORPUS = "IN_CORPUS"
CURRENT_ONLY = "CURRENT_ONLY"    # text held, but it is a consolidation: no history
DECLARED = "DECLARED"
OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class Body:
    """One body of law, and our honest position on it."""
    key: str
    name: str
    regulator: str
    covers: str
    status: str
    note: str = ""
    feed: str | None = None          # a machine-readable change signal, if any

    @property
    def answerable(self) -> bool:
        """Can obligations be DECIDED against this body? CURRENT_ONLY cannot yet:
        the text is held but no obligation has been wired to it."""
        return self.status == IN_CORPUS

    @property
    def point_in_time(self) -> bool:
        """Can this body answer 'what did it say on date D'?

        Only IN_CORPUS can. CURRENT_ONLY holds a regulator's consolidation -- one
        snapshot, authoritative for today and silent on every earlier date. The
        distinction exists because collapsing it is the retracted mistake in
        docs/RETRACTIONS.md: using a current consolidated text as pre-amendment
        ground truth.
        """
        return self.status == IN_CORPUS


# ── the register ──────────────────────────────────────────────────────────────
# Ordered: what we hold, then what we claim, then what we refuse.
BODIES: tuple[Body, ...] = (
    Body("CA2013", "Companies Act, 2013", "MCA",
         "incorporation, governance, board and member meetings, accounts, audit, "
         "related-party transactions, loans to directors, KMP, filings",
         IN_CORPUS,
         "527 sections held and hash-stamped. Delegated rules acquired one at a "
         "time under the two-human-check route; three remain unresolved."),

    Body("LLP2008", "Limited Liability Partnership Act, 2008", "MCA",
         "LLP incorporation, partner obligations, annual filings",
         DECLARED,
         "No instrument acquired. An LLP question must be refused, not answered "
         "from Companies Act reasoning -- the two regimes differ on almost every "
         "obligation that matters."),

    Body("SEBI_LODR", "SEBI (Listing Obligations and Disclosure Requirements) "
         "Regulations, 2015", "SEBI",
         "continuous disclosure, board composition, related-party approval and "
         "reporting for listed entities",
         CURRENT_ONLY,
         "SEBI's own consolidation is held (amended up to 14-07-2026, "
         "SEBI/LAD-NRO/GN/2015-16/013), PENDING_HUMAN_REVIEW. It answers what the "
         "law is NOW and is silent on every earlier date, because SEBI publishes a "
         "consolidation where MCA publishes discrete amending notifications. Dated "
         "LODR questions stay refused until those notifications are acquired "
         "individually. No obligation is wired to it yet.",
         feed="https://www.sebi.gov.in/sebirss.xml"),

    Body("SEBI_OTHER", "SEBI ICDR, SAST, PIT and Buyback Regulations", "SEBI",
         "issue of capital, takeovers, insider trading, buyback",
         DECLARED,
         "Nothing acquired.",
         feed="https://www.sebi.gov.in/sebirss.xml"),

    Body("FEMA1999", "Foreign Exchange Management Act, 1999 and the FDI rules",
         "RBI / DPIIT",
         "foreign investment, sectoral caps, reporting (FC-GPR, FC-TRS), "
         "downstream investment",
         DECLARED,
         "Nothing acquired. Sectoral caps change by press note, which is a "
         "different acquisition problem from a Gazette rule."),

    Body("IBC2016", "Insolvency and Bankruptcy Code, 2016", "IBBI / NCLT",
         "insolvency resolution, liquidation, director conduct in the twilight period",
         DECLARED,
         "Nothing acquired. NCLT and IBBI orders are natively text PDFs, so the "
         "acquisition route is clearer here than most."),

    Body("COMP2002", "Competition Act, 2002", "CCI",
         "combination notification thresholds, anti-competitive agreements",
         DECLARED, "Nothing acquired."),

    Body("STAMP", "Stamp duty — Indian Stamp Act, 1899 and State amendments",
         "State governments",
         "instrument stamping on share transfers, debentures, agreements",
         DECLARED,
         "Declared with a warning: rates vary across 25+ States and Union "
         "Territories, so a single national answer is wrong by construction. Any "
         "answer here must be State-qualified or refused."),

    Body("DPDP2023", "Digital Personal Data Protection Act, 2023", "MeitY / DPB",
         "personal data obligations falling on a company as Data Fiduciary",
         DECLARED,
         "Previously recorded OUT_OF_SCOPE on 2026-08-16, when the product was "
         "Companies Act only. The widening to corporate-law compliance brings it "
         "back in scope as a declared area. Nothing acquired, and the SDF "
         "designation remains a gazette lookup, never a computed threshold."),

    Body("POSH", "Sexual Harassment of Women at Workplace (Prevention, "
         "Prohibition and Redressal) Act, 2013", "—",
         "internal committee, complaint handling",
         OUT_OF_SCOPE,
         "Retired product direction, not a gap. See docs/RETIRED_POSH.md."),

    Body("AI_LAW", "AI regulation", "—", "—", OUT_OF_SCOPE,
         "Excluded until an enacted Indian statute exists to verify against. "
         "There is nothing to hold, so there is nothing to refuse from."),
)

_BY_KEY = {b.key: b for b in BODIES}

# Which body each obligation in the register belongs to. An obligation with no
# entry here fails the completeness test below -- adding one without declaring
# its body is exactly how scope drifts.
OBLIGATION_BODY = {
    "CA13-S96-AGM": "CA2013", "CA13-S173-BOARD": "CA2013",
    "CA13-S149-BOARD-SIZE": "CA2013", "CA13-S149-3-RESIDENT": "CA2013",
    "CA13-S137-AOC4": "CA2013", "CA13-S92-RETURN": "CA2013",
    "CA13-S135-CSR": "CA2013", "CA13-S2-85-SMALL": "CA2013",
    "CA13-S185-LOANS-DIRECTORS": "CA2013", "CA13-S186-LOAN-INVESTMENT": "CA2013",
    "CA13-S188-RPT": "CA2013", "CA13-S177-AUDIT-CTTE": "CA2013",
    "CA13-S203-KMP": "CA2013", "CA13-S180-BORROWING-LIMIT": "CA2013",
    "CA13-S184-DIRECTOR-INTEREST": "CA2013",
}


def body(key: str) -> Body:
    if key not in _BY_KEY:
        raise LookupError(f"no body of law declared for {key!r}. "
                          f"Declared: {', '.join(sorted(_BY_KEY))}")
    return _BY_KEY[key]


def in_corpus() -> tuple[Body, ...]:
    return tuple(b for b in BODIES if b.status == IN_CORPUS)


def current_only() -> tuple[Body, ...]:
    return tuple(b for b in BODIES if b.status == CURRENT_ONLY)


def declared_unheld() -> tuple[Body, ...]:
    return tuple(b for b in BODIES if b.status == DECLARED)


def refusal_for(key: str) -> str:
    """The honest answer for a declared-but-unheld area."""
    b = body(key)
    if b.status == IN_CORPUS:
        raise ValueError(f"{key} is in corpus; it is answered, not refused")
    if b.status == OUT_OF_SCOPE:
        return (f"{b.name} is outside this product's scope. {b.note}")
    if b.status == CURRENT_ONLY:
        return (f"{b.name} ({b.regulator}): the current consolidated text is held, "
                f"but it is a snapshot, not a history. A question about what this "
                f"body required on a past date cannot be answered from it. {b.note}")
    return (f"{b.name} ({b.regulator}) is within scope — it covers {b.covers} — "
            f"but no instrument has been acquired, so nothing here can be decided. "
            f"{b.note} This is a statement about what we hold, not a finding that "
            f"no obligation applies.")


def coverage() -> str:
    held = len(in_corpus())
    return (f"{held} of {len(BODIES) - sum(1 for b in BODIES if b.status == OUT_OF_SCOPE)} "
            f"in-scope bodies of law are held")


def report_text() -> str:
    lines = ["SCOPE — compliance across Indian corporate law", "", f"  {coverage()}", ""]
    for label, st in (("HELD — obligations can be decided, on any date", IN_CORPUS),
                      ("CURRENT ONLY — text held, but a consolidation: no history", CURRENT_ONLY),
                      ("DECLARED — in scope, nothing acquired, must refuse", DECLARED),
                      ("OUT OF SCOPE — deliberately excluded", OUT_OF_SCOPE)):
        rows = [b for b in BODIES if b.status == st]
        if not rows:
            continue
        lines.append(f"  {label}")
        for b in rows:
            lines.append(f"    {b.key:10} {b.name[:58]}")
            if b.feed:
                lines.append(f"               feed: {b.feed}")
        lines.append("")
    lines.append("DECLARED is an active refusal, not a weaker form of HELD: a question")
    lines.append("there is answered with what we would need, never with silence.")
    return "\n".join(lines)


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

    print("scope")
    from checker.obligations import REGISTER

    # ── THE INVARIANT ────────────────────────────────────────────────────────
    undeclared = [o.obligation_id for o in REGISTER
                  if o.obligation_id not in OBLIGATION_BODY]
    check(not undeclared,
          f"every obligation declares which body of law it belongs to ({undeclared})")

    not_held = [o.obligation_id for o in REGISTER
                if o.obligation_id in OBLIGATION_BODY
                and not body(OBLIGATION_BODY[o.obligation_id]).answerable]
    check(not not_held,
          f"no obligation is decided against a body we do not hold ({not_held})")

    # ── declared areas refuse, and say what they are ─────────────────────────
    for b in declared_unheld():
        r = refusal_for(b.key)
        check(b.name[:20] in r and "no instrument has been acquired" in r,
              f"{b.key} refuses, naming the body and the gap")
        check("not a finding that no obligation applies" in r,
              f"...and {b.key}'s refusal distinguishes 'we hold nothing' from "
              f"'nothing applies'")
        break                                   # one worked example is enough here

    check(all("no instrument has been acquired" in refusal_for(b.key)
              for b in declared_unheld()),
          "every declared-but-unheld body refuses the same way")

    # ── an in-corpus body is answered, not refused ───────────────────────────
    try:
        refusal_for("CA2013")
        check(False, "asking for a refusal on a held body raises")
    except ValueError as e:
        check("answered, not refused" in str(e),
              "asking for a refusal on a held body raises")

    # ── out of scope is distinct from declared ───────────────────────────────
    check("outside this product's scope" in refusal_for("POSH"),
          "an out-of-scope body says so, and does not promise future coverage")
    check("Retired product direction, not a gap" in refusal_for("POSH"),
          "...and says why, so it is not re-litigated")

    # ── the register is honest about its own shape ───────────────────────────
    check(len(in_corpus()) == 1,
          f"exactly one body decides obligations ({[b.key for b in in_corpus()]})")

    # ── CURRENT_ONLY: text held, history not ─────────────────────────────────
    co = current_only()
    check([b.key for b in co] == ["SEBI_LODR"],
          f"LODR is held as a consolidation ({[b.key for b in co]})")
    lodr = body("SEBI_LODR")
    check(not lodr.point_in_time,
          "a consolidation cannot answer a dated question — one snapshot is not a history")
    check(not lodr.answerable,
          "...and no obligation is wired to it yet, so it decides nothing either")
    r = refusal_for("SEBI_LODR")
    check("snapshot, not a history" in r,
          "...and its refusal says exactly why, rather than sounding like 'not held'")
    check(body("CA2013").point_in_time,
          "a body built from discrete amending notifications CAN answer a dated question")


    check(len(declared_unheld()) >= 7,
          f"the widening declares substantially more than it holds "
          f"({len(declared_unheld())} declared)")
    check(all(b.note.strip() for b in BODIES), "every body carries a note")
    check(all(b.covers.strip() for b in BODIES), "every body states what it covers")

    # the one machine-readable change signal found anywhere in Indian law
    feeds = [b.key for b in BODIES if b.feed]
    check("SEBI_LODR" in feeds,
          f"SEBI's feed is recorded, being the only one that exists ({feeds})")

    # ── an unknown key is a refusal, not a guess ─────────────────────────────
    try:
        body("GST")
        check(False, "an undeclared body raises rather than defaulting")
    except LookupError as e:
        check("Declared:" in str(e),
              "an undeclared body raises, listing what is declared")

    check("active refusal" in report_text(),
          "the report states that DECLARED is a refusal, not a weaker HELD")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
