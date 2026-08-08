"""
Document generation. Jinja2 → print-ready HTML.

Three departures from the spec, each with a reason that outlived the preference:

  * **No weasyprint.** It needs cairo and pango — a system install locally, and it does not run
    on Vercel serverless at all, so it breaks in both places we deploy. Print-ready HTML plus the
    browser's own print-to-PDF costs nothing, works everywhere, and produces a real PDF. The
    `@page` rules below are what make it come out right.

  * **No LLM polish.** The spec offers `polish_document()` for grammar. These are legal
    documents whose sentences are quoted verbatim from a statute — a model rewording "not
    exceeding three years" into "up to three years" changes a legal term into a paraphrase, and
    nothing downstream would catch it. The spec itself marks polish optional. It stays off.

  * **Two of the four documents are not built.** `ic_order` and `posh_policy` are compliance
    track: every sentence is derived from ingested statutory text and carries its citation.
    `offer_letter` and `appointment_letter` are operations track, which is blocked on
    BACKLOG O-1/O-2 — there is no confirmed Indian template corpus, and the spec's CTC breakup
    (basic 50%, HRA 20%) is invented. `docs/05` §7 forbids shipping an operations artifact with
    no provenance, and a salary structure is the worst place to start.

Run: python3 checker/documents.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound  # noqa: E402

from checker import board_report  # noqa: E402
from checker.ic_order import MAX_TERM_YEARS, Member, validate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"
CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"

CSS = """
@page { size: A4; margin: 22mm 20mm; }
* { box-sizing: border-box; }
body { margin: 0; background: #eee; }
.doc { max-width: 190mm; margin: 0 auto; padding: 18mm 16mm; background: #fff;
       font: 11.5pt/1.65 Georgia, 'Times New Roman', serif; color: #16150f; }
header { border-bottom: 1.5px solid #16150f; padding-bottom: 10px; margin-bottom: 22px; }
h1 { font-size: 17pt; margin: 0 0 2px; letter-spacing: .01em; }
h2 { font-size: 12pt; margin: 22px 0 6px; }
.sub { margin: 0; font-size: 12.5pt; }
.meta { margin: 4px 0 0; font-size: 9.5pt; color: #555; font-variant-numeric: tabular-nums; }
p { margin: 0 0 11px; }
table { width: 100%; border-collapse: collapse; margin: 14px 0 18px; font-size: 10.5pt; }
th, td { border: 1px solid #cfc9bd; padding: 7px 9px; text-align: left; }
th { background: #f4f1ea; font-weight: 600; }
.cite { font-size: 9pt; color: #555; white-space: nowrap; }
.sign { margin-top: 46px; }
.sign .rule { width: 62mm; border-top: 1px solid #16150f; margin-bottom: 5px; }
.sign p { font-size: 10pt; margin: 0; }
.warn { border: 1px solid #d8c99a; border-left: 3px solid #8a6410; background: #f9f4e6;
        padding: 11px 13px; font-size: 10pt; margin: 20px 0; }
.issues { border: 1px solid #dcc0b8; border-left: 3px solid #8c2f1d; background: #f9efec;
          padding: 11px 13px; font-size: 10pt; margin: 22px 0; }
.issues h2 { margin-top: 0; font-size: 11pt; color: #8c2f1d; }
footer { margin-top: 30px; border-top: 1px solid #cfc9bd; padding-top: 10px;
         font-size: 8.5pt; color: #555; }
footer p { margin: 0 0 3px; }
@media print { body { background: #fff; } .doc { max-width: none; padding: 0; }
                .no-print { display: none; } }
"""

TEMPLATE_INFO: dict[str, dict] = {
    "ic_order": {
        "name": "Internal Committee — constitution order",
        "description": "s.4(1) requires the Committee to be constituted by an order in writing. "
                       "This is that order, and we check your proposed members against s.4(2) "
                       "before drafting it.",
        "track": "compliance",
        "required": ["company_name", "members"],
    },
    "board_report": {
        "name": "PoSH extract for the Board's Report",
        "description": "Rule 8(5)(x) of the Companies (Accounts) Rules has required three "
                       "numbers since 14 July 2025 — complaints received, disposed, and pending "
                       "beyond ninety days. FY 2025-26 is the first year they are due, at AGMs "
                       "by 30 September 2026. We check them against each other and against your "
                       "committee before writing the statement.",
        "track": "compliance",
        "required": ["company_name", "members", "counts"],
    },
    "posh_policy": {
        "name": "PoSH policy for display",
        "description": "s.19(b) requires the penal consequences and the IC order to be displayed "
                       "at a conspicuous place. Deliberately short — it states only what the "
                       "sections we hold actually say.",
        "track": "compliance",
        "required": ["company_name", "members"],
    },
}

# Named so the reason travels with the gap rather than living in a commit message.
BLOCKED: dict[str, str] = {
    "offer_letter":
        "Operations track. There is no confirmed source of Indian offer letters (BACKLOG O-2), "
        "and the CTC breakup in the spec — basic 50%, HRA 20% — is invented. Shipping a salary "
        "structure with no provenance is the failure docs/05 §7 exists to prevent.",
    "appointment_letter":
        "Operations track, same gap. Notice period and probation are legal-adjacent and would "
        "need the lawyer's sign-off, not a template's.",
}


@dataclass(frozen=True)
class Document:
    html: str
    filename: str
    issues: list
    template_type: str


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined,
                       autoescape=True, trim_blocks=True, lstrip_blocks=True)


def _corpus_sha() -> str:
    try:
        return json.loads(CORPUS.read_text())["instrument"]["source_sha256"][:16]
    except (OSError, KeyError, json.JSONDecodeError):
        return "unavailable"


def _verification_line() -> str:
    """States the real verification state. Never claims review that has not happened."""
    try:
        provisions = json.loads(CORPUS.read_text())["provisions"]
    except (OSError, KeyError, json.JSONDecodeError):
        return "Verification state unknown."
    verifiers = {p.get("verified_by") for p in provisions if p.get("verified_by")}
    if not verifiers:
        return ("No lawyer has reviewed our reading of these sections yet — the text is "
                "verbatim, the interpretation is ours.")
    return f"Sections reviewed by {', '.join(sorted(verifiers))}."


def list_available_templates() -> list[dict]:
    out = [{"type": t, **info, "available": True} for t, info in TEMPLATE_INFO.items()]
    out += [{"type": t, "name": t.replace("_", " ").title(), "description": why,
             "track": "operations", "required": [], "available": False}
            for t, why in BLOCKED.items()]
    return out


def company_name_of(company: dict, user_inputs: dict) -> str:
    name = str(company.get("name") or user_inputs.get("company_name") or "").strip()
    if not name:
        raise ValueError("Company name is required.")
    return name


def _board_report(company_name: str, members: list[Member], user_inputs: dict) -> Document:
    """
    Rule 8(5)(x). Separate from the IC documents because its inputs are counts rather than
    people, and because it can refuse for a reason the others cannot — Rule 8(6) exempts a
    One Person Company and a Small Company, and we abstain rather than guess at Rule 8A.
    """
    raw = user_inputs.get("counts") or {}
    try:
        counts = board_report.Counts(
            opening_pending=int(raw.get("opening_pending", 0)),
            received=int(raw.get("received", 0)),
            disposed=int(raw.get("disposed", 0)),
            pending_over_90=int(raw.get("pending_over_90", 0)),
        )
    except (TypeError, ValueError):
        raise ValueError("The four complaint counts must all be whole numbers.") from None

    try:
        extract = board_report.build(
            members, counts,
            is_small_company=bool(user_inputs.get("is_small_company")),
            is_opc=bool(user_inputs.get("is_opc")),
        )
    except board_report.Exempt as e:
        raise ValueError(str(e)) from None

    fy = str(user_inputs.get("financial_year", "")).strip() or "2025-26"
    html = _env().get_template("board_report.html").render(
        css=CSS,
        company_name=company_name,
        financial_year=fy,
        place=str(user_inputs.get("place", "")).strip(),
        counts=extract.counts,
        issues=extract.issues,
        committee_issues=extract.committee_issues,
        may_state_compliance=extract.may_state_compliance,
        corpus_sha=_corpus_sha(),
        verification_line=_verification_line(),
    )
    slug = "".join(c if c.isalnum() else "_" for c in company_name.lower())[:40].strip("_")
    return Document(html, f"placedon_board_report_{fy}_{slug}.html", extract.issues,
                    "board_report")


def generate_document(template_type: str, company: dict, user_inputs: dict) -> Document:
    if template_type in BLOCKED:
        raise ValueError(BLOCKED[template_type])
    if template_type not in TEMPLATE_INFO:
        raise TemplateNotFound(template_type)

    raw_members = user_inputs.get("members") or []
    if not raw_members:
        raise ValueError("At least one committee member is required.")

    members = [
        Member(
            name=str(m.get("name", "")).strip(),
            is_woman=bool(m.get("is_woman")),
            source=("external_ngo" if m.get("source") == "external_ngo" else "employee"),
            designation=str(m.get("designation", "")).strip(),
            senior_level=bool(m.get("senior_level")),
            presiding=bool(m.get("presiding")),
        )
        for m in raw_members
    ]
    if any(not m.name for m in members):
        raise ValueError("Every member needs a name.")

    if template_type == "board_report":
        return _board_report(company_name_of(company, user_inputs), members, user_inputs)

    on = date.today()
    if raw_date := user_inputs.get("date"):
        try:
            on = date.fromisoformat(str(raw_date))
        except ValueError:
            pass

    # The validation runs before the draft, so an unlawful committee is flagged on the page
    # rather than signed and filed.
    verdict = validate(members, term_years=MAX_TERM_YEARS,
                       multi_site=bool(user_inputs.get("multi_site")))

    def role(m: Member) -> str:
        if m.presiding:
            return "Presiding Officer"
        return "Member (external)" if m.source == "external_ngo" else "Member"

    company_name = company_name_of(company, user_inputs)

    html = _env().get_template(f"{template_type}.html").render(
        css=CSS,
        company_name=company_name,
        place=str(user_inputs.get("place", "")).strip(),
        contact_email=str(user_inputs.get("contact_email", "")).strip(),
        date_long=on.strftime("%d %B %Y"),
        until_long=on.replace(year=on.year + MAX_TERM_YEARS).strftime("%d %B %Y"),
        members=[{"name": m.name, "designation": m.designation, "role": role(m)}
                 for m in members],
        issues=[i for i in verdict.issues if i.severity == "blocking"],
        corpus_sha=_corpus_sha(),
        verification_line=_verification_line(),
    )

    slug = "".join(c if c.isalnum() else "_" for c in company_name.lower())[:40].strip("_")
    return Document(html, f"placedon_{template_type}_{slug}.html", verdict.issues, template_type)


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    lawful = [
        {"name": "Ms A. Rao", "is_woman": True, "source": "employee",
         "designation": "VP Engineering", "senior_level": True, "presiding": True},
        {"name": "Ms B. Nair", "is_woman": True, "source": "employee", "designation": "Finance"},
        {"name": "Mr C. Das", "is_woman": False, "source": "employee", "designation": "Design"},
        {"name": "Ms D. Iyer", "is_woman": True, "source": "external_ngo",
         "designation": "Vimochana"},
    ]
    company = {"name": "Acme Software Pvt Ltd"}
    failures = 0

    def check(name: str, got, want) -> None:
        global failures
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  got={got!r}"))

    doc = generate_document("ic_order", company, {"members": lawful, "place": "Bengaluru"})
    check("ic_order renders", "Order constituting the Internal Committee" in doc.html, True)
    check("  quotes s.4(1) verbatim phrase", "by an order in writing" in doc.html, True)
    check("  carries the citation markers", "[s.4(3)]" in doc.html, True)
    check("  states real verification state",
          "No lawyer has reviewed" in doc.html, True)
    check("  pins the corpus hash", "e59776d9ce4300c3" in doc.html, True)
    check("  lawful committee raises no blocking issue",
          [i for i in doc.issues if i.severity == "blocking"], [])

    bad = generate_document("ic_order", company, {"members": lawful[:2]})
    check("unlawful committee is flagged ON the document",
          "Before you sign this" in bad.html, True)

    pol = generate_document("posh_policy", company, {"members": lawful})
    check("posh_policy renders", "Prevention of Sexual Harassment" in pol.html, True)
    check("  quotes s.26 penalty verbatim", "fifty thousand rupees" in pol.html, True)
    check("  admits what it leaves out", "deliberately short" in pol.html, True)

    for blocked in ("offer_letter", "appointment_letter"):
        try:
            generate_document(blocked, company, {"members": lawful})
            check(f"{blocked} refused", False, True)
        except ValueError as e:
            check(f"{blocked} refused with the reason", "Operations track" in str(e), True)

    try:
        generate_document("nonexistent", company, {"members": lawful})
        check("unknown template raises", False, True)
    except TemplateNotFound:
        check("unknown template raises", True, True)

    br = generate_document("board_report", company,
                           {"members": lawful, "financial_year": "2025-26",
                            "counts": {"opening_pending": 1, "received": 4, "disposed": 3,
                                       "pending_over_90": 2}})
    check("board_report renders", "sexual harassment disclosure" in br.html, True)
    check("  states the compliance sentence for a lawful committee",
          "The Company has complied with provisions relating to the constitution" in br.html, True)
    check("  carries all three numbers", ("<td>4</td>" in br.html and "<td>3</td>" in br.html
                                          and "<td>2</td>" in br.html), True)
    check("  derives the closing balance", "Pending at year end: 2" in br.html, True)
    check("  names box (c) as s.11(4) breaches",
          "shall be completed within a period of ninety days" in br.html, True)
    check("  admits the MCA sources are weaker than the PoSH ones",
          "quotation of a quotation" in br.html, True)
    check("  states the s.16 position on complaint contents", "Section 16" in br.html, True)

    bad_ic_br = generate_document("board_report", company,
                                  {"members": lawful[:2],
                                   "counts": {"received": 0, "disposed": 0,
                                              "pending_over_90": 0}})
    check("defective committee → compliance statement withheld",
          "We have not drafted the compliance statement" in bad_ic_br.html, True)
    check("  ...and the true sentence is absent",
          "The Company has complied with provisions" in bad_ic_br.html, False)

    for flag, label in (("is_small_company", "small company"), ("is_opc", "OPC")):
        try:
            generate_document("board_report", company,
                              {"members": lawful, flag: True, "counts": {}})
            check(f"{label} abstains", False, True)
        except ValueError as e:
            check(f"{label} abstains citing Rule 8(6)",
                  "This rule shall not apply" in str(e), True)

    avail = list_available_templates()
    check("5 templates listed, 3 available",
          (len(avail), sum(1 for t in avail if t["available"])), (5, 3))

    (ROOT / "corpus/sample_board_report.html").write_text(br.html, encoding="utf-8")

    out = ROOT / "corpus/sample_ic_order.html"
    out.write_text(doc.html, encoding="utf-8")
    print(f"\nsample → {out.relative_to(ROOT)}")
    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
