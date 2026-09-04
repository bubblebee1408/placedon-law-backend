"""The pre-diligence evidence pack — the matrix as a dated, cited document.

This is the artifact that lives inside the discipline rather than trading it
away. A compliance matrix that only says "you are in breach" is worth less than
one that a CFO can hand to diligence counsel, and this renders exactly that:
a company's Companies Act position on a stated date, with the provision behind
every line and an explicit account of what could not be verified.

## What it is, and firmly is not

It IS a record: every row carries its provision, its state, the basis for that
state, and — where the row could not be decided — the fact or the source that is
missing. It carries a provenance block so a reader can reproduce it: which
corpus, which code, which date.

It is NOT any of the following, and the rendered pack says so on its face:

  * It does not generate a resolution, notice, or any operative instrument. It
    reports on obligations; it does not draft the documents that discharge them.
    Drafting a legally operative document is a different liability surface and a
    governance decision this pack does not take.
  * It does not guarantee zero defects. It covers a named set of obligations, not
    the whole Act, against a corpus that holds the Act but almost none of the
    subordinate rules. It can say it did not contradict itself. It cannot say
    nothing is wrong.
  * It is not legal advice, and it is not reviewed by a lawyer.

Stating those limits is not throat-clearing. A pack that overstated what it
established would be the exact failure the whole system is built to avoid, and
it would carry that failure into a due-diligence room where the stakes are real.

## No model, and no operative text

`build()` runs the deterministic obligation register and nothing else. No
language model is consulted, and per s.52(1)(q)(ii) the pack never reproduces
bare statutory text as its own content — it cites provisions and states our
analysis, it does not republish the Act.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from checker.company_profile import CompanyProfile
from checker import currency
from checker.obligation_citations import structural_cites
from checker.obligations import (APPLIES_NOT_SATISFIED, APPLIES_SATISFIED,
                                 APPLIES_UNDETERMINED, CANNOT_DETERMINE,
                                 DOES_NOT_APPLY, Evidence, REGISTER, Row, build)

# What the pack establishes, and what it does not — carried in the artifact
# itself so the statement travels with the document, not in a doc beside it.
ESTABLISHES = (
    "A record of this company's position on the obligations below, as of the "
    "stated date, with the provision behind each line and an explicit list of "
    "what could not be verified. Every line is a provision, a fact supplied, or "
    "arithmetic on the two."
)

DOES_NOT_ESTABLISH = (
    "This is not a certificate of compliance and not legal advice. It covers "
    f"{len(REGISTER)} obligations, not the whole Companies Act, against a corpus "
    "that holds the Act but almost none of the subordinate rules — so some rows "
    "refuse rather than answer, and name the instrument they are waiting on. It "
    "generates no resolution, notice, or other operative document. No lawyer has "
    "reviewed it. It can say the analysis did not contradict itself; it cannot "
    "say nothing is wrong."
)


@dataclass
class DiligencePack:
    company_class: str
    cin: str | None
    as_of: date
    financial_year: str | None
    generated_at: str
    provenance: dict
    rows: list[Row] = field(default_factory=list)
    # Obligations resting on law we cannot yet show is current (currency.stale).
    currency_flags: list = field(default_factory=list)

    # Derived groupings, so a reader sees the shape before the detail.
    @property
    def not_satisfied(self) -> list[Row]:
        return [r for r in self.rows if r.state == APPLIES_NOT_SATISFIED]

    @property
    def undetermined(self) -> list[Row]:
        return [r for r in self.rows if r.state == APPLIES_UNDETERMINED]

    @property
    def cannot_determine(self) -> list[Row]:
        return [r for r in self.rows if r.state == CANNOT_DETERMINE]

    @property
    def satisfied(self) -> list[Row]:
        return [r for r in self.rows if r.state == APPLIES_SATISFIED]

    @property
    def not_applicable(self) -> list[Row]:
        return [r for r in self.rows if r.state == DOES_NOT_APPLY]

    @property
    def blocked_on_sources(self) -> list[Row]:
        return [r for r in self.rows if r.blocked_by]

    def unverified(self) -> list[tuple[str, str]]:
        """Every row we could not settle, and what would settle it. This is the
        section a diligence reader values most: an honest map of the gaps."""
        out = []
        for r in self.rows:
            if r.state in (APPLIES_UNDETERMINED, CANNOT_DETERMINE):
                need = ("; ".join(r.missing_facts) if r.missing_facts
                        else (r.blocked_by or "see basis"))
                out.append((r.obligation_id, need))
        return out


def build_pack(profile: CompanyProfile,
               evidence: Evidence | None = None,
               *, generated_at: str) -> DiligencePack:
    """Build the pack. Deterministic; no model. `generated_at` is passed in so
    the result is reproducible rather than stamped from a wall clock."""
    from checker.release_record import provenance, ProvenanceError
    try:
        prov = provenance("v3", law_effective_date=profile.as_of.isoformat())
        prov_block = {
            "benchmark_version": prov.benchmark_version,
            "corpus_version": prov.corpus_version,
            "checker_commit": prov.checker_commit,
            "working_tree_dirty": prov.working_tree_dirty,
            "law_as_of": prov.law_effective_date,
        }
    except ProvenanceError as e:
        prov_block = {"error": str(e),
                      "note": "provenance could not be fully named; treat this "
                              "pack as non-reproducible"}

    return DiligencePack(
        company_class=profile.company_class,
        cin=profile.cin,
        as_of=profile.as_of,
        financial_year=profile.latest_financial_year,
        generated_at=generated_at,
        provenance=prov_block,
        rows=build(profile, evidence=evidence or Evidence()),
        currency_flags=currency.stale(profile.as_of))


_STATE_LABEL = {
    APPLIES_SATISFIED: "SATISFIED",
    APPLIES_NOT_SATISFIED: "NOT SATISFIED",
    APPLIES_UNDETERMINED: "UNDETERMINED",
    CANNOT_DETERMINE: "CANNOT DETERMINE",
    DOES_NOT_APPLY: "DOES NOT APPLY",
}


def render(pack: DiligencePack) -> str:
    L = ["=" * 78,
         "PRE-DILIGENCE EVIDENCE PACK — Companies Act 2013",
         "=" * 78,
         f"  company class   : {pack.company_class}",
         f"  CIN             : {pack.cin or 'not supplied'}",
         f"  position as of  : {pack.as_of}",
         f"  financial year  : {pack.financial_year or 'not supplied'}",
         f"  generated at    : {pack.generated_at}",
         "",
         "  Provenance (so this pack can be reproduced):"]
    for k, v in pack.provenance.items():
        L.append(f"    {k:<20} {v}")

    L += ["",
          f"  SUMMARY  {len(pack.not_satisfied)} not satisfied · "
          f"{len(pack.undetermined)} undetermined · "
          f"{len(pack.cannot_determine)} cannot determine · "
          f"{len(pack.satisfied)} satisfied · "
          f"{len(pack.not_applicable)} not applicable",
          "=" * 78, ""]

    # Order the rows most-urgent first: a diligence reader wants the breaches
    # and the gaps before the clean rows.
    order = [APPLIES_NOT_SATISFIED, CANNOT_DETERMINE, APPLIES_UNDETERMINED,
             APPLIES_SATISFIED, DOES_NOT_APPLY]
    for state in order:
        for r in [x for x in pack.rows if x.state == state]:
            flag = "!" if r.needs_attention else " "
            L.append(f" {flag} [{_STATE_LABEL[r.state]}] {r.obligation_id}")
            L.append(f"     duty      : {r.duty}")
            L.append(f"     provision : {r.provision}")
            _cites = structural_cites(r.obligation_id)
            if _cites:
                L.append("     spans     : "
                         + " · ".join(str(_c) for _c in _cites))
            L.append(f"     basis     : {r.basis}")
            if r.missing_facts:
                L.append(f"     to settle : {'; '.join(r.missing_facts)}")
            if r.blocked_by:
                L.append(f"     BLOCKED   : {r.blocked_by} — a source not yet "
                         f"properly acquired")
            L.append("")

    unv = pack.unverified()
    if unv:
        L += ["-" * 78,
              f"  WHAT COULD NOT BE VERIFIED ({len(unv)}) — supply these to close them",
              ""]
        for oid, need in unv:
            L.append(f"    {oid:<22} {need[:90]}")
        L.append("")

    if pack.currency_flags:
        L += ["-" * 78,
              f"  LAW-CURRENCY WATCH ({len(pack.currency_flags)}) — rows resting on law "
              "not yet shown current",
              ""]
        for f in pack.currency_flags:
            L.append(f"    [{f.status}] {f.obligation_id}")
            if f.instrument:
                L.append(f"       acquire : {f.instrument}")
            L.append(f"       why     : {f.detail[:110]}")
        L.append("")

    L += ["=" * 78,
          "  WHAT THIS PACK IS",
          f"  {ESTABLISHES}",
          "",
          "  WHAT IT IS NOT",
          f"  {DOES_NOT_ESTABLISH}",
          "=" * 78]
    return "\n".join(L)


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

    print("diligence_pack")
    from checker.company_profile import Figure, Money

    common = dict(incorporation_date=date(2019, 6, 1), as_of=date(2026, 8, 31),
                  latest_financial_year="2024-25", is_holding_company=False,
                  is_subsidiary_company=False, is_section_8=False,
                  governed_by_special_act=False, cin="U74999KA2019PTC000000")
    prof = CompanyProfile(company_class="private", director_count=2, **common,
                          paid_up_capital=Figure(Money.crore(2), "2024-25"),
                          turnover=Figure(Money.crore(30), "2024-25"))
    ev = Evidence(agm_dates=(date(2024, 8, 20), date(2025, 12, 30)),
                  financial_year_end=date(2025, 3, 31),
                  board_meetings=(date(2025, 3, 1),), calendar_year=2025,
                  resident_director_days=90)

    pack = build_pack(prof, ev, generated_at="2026-09-04T00:00:00Z")

    check(len(pack.rows) == len(REGISTER),
          f"the pack covers every registered obligation ({len(pack.rows)})")
    check(pack.cin == "U74999KA2019PTC000000", "the pack carries the CIN")
    check(pack.generated_at == "2026-09-04T00:00:00Z",
          "generated_at is passed in, not stamped from a clock")

    # Provenance must be present and name the corpus and the law-as-of date.
    check("corpus_version" in pack.provenance or "error" in pack.provenance,
          "the pack carries a provenance block")
    check(pack.provenance.get("law_as_of") == "2026-08-31"
          or "error" in pack.provenance,
          "the law-as-of date is the profile date, kept distinct from the corpus")

    # The unverified section is the diligence value: every open row, named.
    unv_ids = {oid for oid, _ in pack.unverified()}
    open_rows = {r.obligation_id for r in pack.rows
                 if r.state in (APPLIES_UNDETERMINED, CANNOT_DETERMINE)}
    check(unv_ids == open_rows,
          "every undetermined or unresolvable row appears in the unverified list")
    check(all(need for _, need in pack.unverified()),
          "each unverified row names what would settle it")

    # A blocked row surfaces its source, not a bare refusal.
    check(any("S-002" in (r.blocked_by or "") for r in pack.rows),
          "the small-company row names the instrument it waits on")

    text = render(pack)

    # Currency: the small-company row rests on G.S.R. 700(E), unacquired, so the
    # pack must carry a LAW-CURRENCY WATCH naming the instrument to acquire.
    cf_ids = {f.obligation_id for f in pack.currency_flags}
    check("CA13-S2-85-SMALL" in cf_ids,
          f"the small-company row is flagged as resting on non-current law ({cf_ids})")
    check("LAW-CURRENCY WATCH" in text,
          "the rendered pack carries a law-currency watch section")
    check("G.S.R. 700(E)" in text,
          "...naming the exact instrument to acquire")

    # Structural citations: the small-company row cites its sub-clause limbs
    # by path + hash (T6), never reproducing the statutory text.
    check("s.2(85)(i)" in text,
          "the small-company row cites the sub-clause limb 2(85)(i)")
    check("sha256" in text.split("s.2(85)(i)")[1][:40],
          "...with the limb's content hash beside it")

    # NOT a certificate, and it says so on its face.
    check("not a certificate of compliance" in text.lower(),
          "the rendered pack states it is not a compliance certificate")
    check("generates no resolution" in text.lower()
          or "operative document" in text.lower(),
          "...and that it drafts no operative instrument")
    check("cannot say nothing is wrong" in text.lower(),
          "...and does not claim zero defects")
    check("provenance" in text.lower() and "reproduced" in text.lower(),
          "the pack presents its provenance for reproduction")

    # No bare statutory text — the same s.52(1)(q)(ii) check the matrix passes.
    for phrase in ("Every company shall hold", "not less than clear twenty-one",
                   "shall be the quorum"):
        if phrase in text:
            check(False, f"the pack served bare statutory text: {phrase!r}")
            break
    else:
        check(True, "the pack cites provisions but serves no bare statutory text")

    # No model, no operative-drafting import. Parsed from the module's own
    # import statements rather than grepped for strings -- a string search finds
    # the guard strings themselves, which is a false positive I have hit before.
    import ast, sys
    import checker.diligence_pack as mod
    tree = ast.parse(open(mod.__file__).read())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    banned = {"openai", "anthropic", "docx", "jinja2"}
    check(not (roots & banned),
          f"the pack imports no model or document-drafting library ({roots & banned or 'clean'})")
    # And it does not import the one internal module that talks to a model.
    fromlist = {n.module for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module}
    check(not any("model_adapter" in m for m in fromlist),
          "...and does not reach the model adapter")

    # Most-urgent-first ordering: a NOT SATISFIED row precedes a SATISFIED one.
    ns = text.find("[NOT SATISFIED]")
    sat = text.find("[SATISFIED]")
    check(ns != -1 and (sat == -1 or ns < sat),
          "breaches are ordered before clean rows")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
