"""Firm-ready document templates — research memo and client email from CUAD pipeline output.

Consumes structured CUADResult / audit findings. Never sends anything automatically.
Every output is DRAFT / PENDING_REVIEW until a lawyer approves.

Run: PYTHONPATH=. python3 checker/firm_templates.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from jinja2 import Environment

from checker.cuad_pipeline import CUADResult
from checker.obligation_extractor import Obligation

__all__ = ["TemplateInput", "TemplateOutput", "render_memo", "render_email"]

TEMPLATE_VERSION = "1.0"


@dataclass(frozen=True)
class TemplateInput:
    template_id: str
    template_version: str
    firm_name: str
    matter_id: str
    matter_name: str
    client_name: str
    document_name: str
    cuad_result: CUADResult | None = None
    audit_findings: tuple[dict[str, Any], ...] = ()
    additional_context: dict[str, Any] = field(default_factory=dict)
    preparer_name: str = ""
    date: date = field(default_factory=date.today)


@dataclass(frozen=True)
class TemplateOutput:
    template_id: str
    template_version: str
    content_markdown: str
    content_html: str
    missing_fields: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    draft_status: str = "DRAFT"
    approval_status: str = "PENDING_REVIEW"


# ── template strings ─────────────────────────────────────────────────────────
# ponytail: inline strings; move to files when template count > 5

_MEMO_MD = """\
# Legal Research Memo

**Firm:** {{ firm_name }}
**Matter:** {{ matter_name }} ({{ matter_id }})
**Client:** {{ client_name }}
**Document:** {{ document_name }}
**Prepared by:** {{ preparer_name or "[Not specified]" }}
**Date:** {{ date }}
**Status:** DRAFT — PENDING LAWYER REVIEW

---

## 1. Matter Details

{{ matter_name }} (ID: {{ matter_id }}) for client {{ client_name }}.
{{ additional_notes }}

## 2. Document Reviewed

- **Name:** {{ document_name }}
- **Classification:** {{ doc_class or "[Not classified]" }}
- **Tags:** {{ tags_display or "[None]" }}

## 3. Executive Summary

{% if extraction_count > 0 -%}
{{ extraction_count }} clause extraction(s) found across {{ categories_found_count }} categories.
{{ obligation_count }} obligation(s) identified.
{%- else -%}
Extraction not available for this document. Manual review required.
{%- endif %}
{% if finding_count > 0 -%}
{{ finding_count }} audit finding(s) flagged for review.
{%- endif %}

## 4. Key Contractual Provisions

{% if extractions -%}
{% for e in extractions -%}
- **{{ e.category }}**: {{ e.answer_text }} *({{ e.verification_status }})*
{% endfor -%}
{% else -%}
No verified extractions available.
{% endif %}

## 5. Obligations and Rights by Party

{% if obligations_by_party -%}
{% for party, obls in obligations_by_party.items() -%}
### {{ party or "Unidentified Party" }}

{% for o in obls -%}
- **{{ o.modality | capitalize }}**: {{ o.action }}{% if o.deadline %} — Deadline: {{ o.deadline }}{% endif %}{% if o.condition %} — Condition: {{ o.condition }}{% endif %}

{% endfor -%}
{% endfor -%}
{% else -%}
No party-specific obligations extracted.
{% endif %}

## 6. Material Audit Findings

{% if audit_findings -%}
{% for f in audit_findings -%}
- **[{{ f.get("severity", "UNKNOWN") }}]** {{ f.get("title", f.get("category", "Finding")) }}: {{ f.get("explanation", f.get("description", "No detail")) }}{% if f.get("verification_status") %} *({{ f.get("verification_status") }})*{% endif %}

{% endfor -%}
{% else -%}
No audit findings recorded.
{% endif %}

## 7. Supporting Evidence

{% if evidence_refs -%}
{% for ref in evidence_refs -%}
{{ loop.index }}. {{ ref }}
{% endfor -%}
{% else -%}
No supporting evidence references collected.
{% endif %}

## 8. Outstanding Questions

{% if missing_fields -%}
The following information was not available:
{% for m in missing_fields -%}
- {{ m }}
{% endfor -%}
{% else -%}
No outstanding data gaps identified.
{% endif %}

## 9. Recommended Next Steps

{% if has_unverified -%}
- Review unverified or fuzzy-matched extractions manually.
{% endif -%}
{% if finding_count > 0 -%}
- Address flagged audit findings before finalisation.
{% endif -%}
{% if obligation_count > 0 -%}
- Confirm party-specific obligations with the client.
{% endif -%}
- Obtain lawyer sign-off before releasing this memo.
"""


_EMAIL_MD = """\
**Subject:** {{ subject }}

Dear {{ client_name }},

### Matter Context

We are writing regarding {{ matter_name }} (Ref: {{ matter_id }}). We have completed our review of {{ document_name }}.

### Key Findings

{% if extractions -%}
Our review identified the following key provisions:
{% for e in extractions -%}
- **{{ e.category }}**: {{ e.answer_text }}
{% endfor -%}
{% else -%}
Detailed clause extraction was not performed for this document. A summary follows based on available information.
{% endif %}

{% if audit_findings -%}
**Flagged items requiring attention:**
{% for f in audit_findings -%}
- {{ f.get("title", f.get("category", "Item")) }}: {{ f.get("explanation", f.get("description", "")) }}
{% endfor -%}
{% endif %}

### Required Client Actions

{% if deadlines -%}
Please note the following deadlines:
{% for d in deadlines -%}
- {{ d.party or "Party" }}: {{ d.action }} — {{ d.deadline }}
{% endfor -%}
{% else -%}
No immediate client actions identified at this time.
{% endif %}

### Important Deadlines

{% if deadlines -%}
{% for d in deadlines -%}
- {{ d.deadline }}{% if d.party %} ({{ d.party }}){% endif %}: {{ d.action }}
{% endfor -%}
{% else -%}
No contractual deadlines extracted.
{% endif %}

### Outstanding Clarifications

{% if missing_fields -%}
We require clarification on the following:
{% for m in missing_fields -%}
- {{ m }}
{% endfor -%}
{% else -%}
No clarifications required at this stage.
{% endif %}

### Next Steps

{% if obligation_count > 0 -%}
- We recommend reviewing the {{ obligation_count }} identified obligation(s) in the attached memo.
{% endif -%}
- Please confirm the above at your earliest convenience.
- We remain available for any questions.

Kind regards,
{{ preparer_name or "[Lawyer name]" }}
{{ firm_name }}

---
*This is a draft communication prepared by {{ firm_name }}. It has not been reviewed or approved for sending.*
*Template version: {{ template_version }}*
"""


# ── rendering ─────────────────────────────────────────────────────────────────

_md_env = Environment(autoescape=False)
_html_env = Environment(autoescape=True)


def _build_context(inp: TemplateInput) -> tuple[dict[str, Any], list[str], list[str]]:
    """Build the shared template context, missing fields list, and evidence refs."""
    missing: list[str] = []
    evidence_refs: list[str] = []
    extractions: list[Any] = []
    obligations: list[Obligation] = []

    if inp.cuad_result and inp.cuad_result.extraction:
        extractions = list(inp.cuad_result.extraction.extractions)
        for e in extractions:
            if e.evidence_text:
                evidence_refs.append(
                    f"[{e.category}] \"{e.evidence_text[:120]}\" ({e.verification_status})")
    else:
        missing.append("Clause extraction not available")

    if inp.cuad_result:
        obligations = list(inp.cuad_result.obligations)
    else:
        missing.append("CUAD pipeline result not available")

    if not inp.audit_findings:
        missing.append("No audit findings provided")

    if not inp.preparer_name:
        missing.append("Preparer name not specified")

    # Group obligations by party.
    obls_by_party: dict[str, list[Obligation]] = {}
    for o in obligations:
        key = o.party or "Unidentified Party"
        obls_by_party.setdefault(key, []).append(o)

    deadlines = [o for o in obligations if o.deadline]

    has_unverified = any(
        getattr(e, "verification_status", "") in ("FUZZY_MATCH", "UNVERIFIED")
        for e in extractions)

    ctx = {
        "firm_name": inp.firm_name,
        "matter_name": inp.matter_name,
        "matter_id": inp.matter_id,
        "client_name": inp.client_name,
        "document_name": inp.document_name,
        "preparer_name": inp.preparer_name,
        "date": str(inp.date),
        "template_version": inp.template_version,
        "additional_notes": inp.additional_context.get("notes", ""),
        "doc_class": inp.cuad_result.doc_class if inp.cuad_result else "",
        "tags_display": ", ".join(inp.cuad_result.tags) if inp.cuad_result else "",
        "extractions": extractions,
        "extraction_count": len(extractions),
        "categories_found_count": len(set(e.category for e in extractions)),
        "obligations_by_party": obls_by_party,
        "obligation_count": len(obligations),
        "deadlines": deadlines,
        "audit_findings": list(inp.audit_findings),
        "finding_count": len(inp.audit_findings),
        "evidence_refs": evidence_refs,
        "missing_fields": missing,
        "has_unverified": has_unverified,
        "subject": f"Review of {inp.document_name} — {inp.matter_name}",
    }
    return ctx, missing, evidence_refs


def render_memo(inp: TemplateInput) -> TemplateOutput:
    ctx, missing, evidence_refs = _build_context(inp)
    md = _md_env.from_string(_MEMO_MD).render(ctx)
    html = _html_env.from_string(_MEMO_MD).render(ctx)
    return TemplateOutput(
        template_id=inp.template_id,
        template_version=inp.template_version,
        content_markdown=md,
        content_html=html,
        missing_fields=tuple(missing),
        evidence_refs=tuple(evidence_refs),
    )


def render_email(inp: TemplateInput) -> TemplateOutput:
    ctx, missing, evidence_refs = _build_context(inp)
    md = _md_env.from_string(_EMAIL_MD).render(ctx)
    html = _html_env.from_string(_EMAIL_MD).render(ctx)
    return TemplateOutput(
        template_id=inp.template_id,
        template_version=inp.template_version,
        content_markdown=md,
        content_html=html,
        missing_fields=tuple(missing),
        evidence_refs=tuple(evidence_refs),
    )


# ── self-tests ─────────────────────────────────────────────────────────────────

def _test() -> int:
    import json
    from checker.cuad_extractor import Extraction, ExtractionResult

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("firm_templates")

    # ── build a full CUADResult ──────────────────────────────────────────
    ext1 = Extraction(
        category="Governing Law", answer_text="India",
        evidence_text="governed by the laws of India",
        normalized_value="India", start_offset=100, end_offset=130,
        page_number=1, verification_status="VERIFIED",
        review_status="PENDING", model_provider="test",
        model_version="mock-1", prompt_version="1.0", schema_version="1.0")
    ext2 = Extraction(
        category="Indemnification", answer_text="indemnify",
        evidence_text="The Supplier shall indemnify the Customer",
        normalized_value="indemnify", start_offset=200, end_offset=240,
        page_number=2, verification_status="FUZZY_MATCH",
        review_status="PENDING", model_provider="test",
        model_version="mock-1", prompt_version="1.0", schema_version="1.0")
    extraction_result = ExtractionResult(
        extractions=(ext1, ext2), model_provider="test",
        model_version="mock-1",
        categories_asked=("Governing Law", "Indemnification"),
        categories_found=("Governing Law", "Indemnification"),
        categories_absent=(), errors=())
    obl1 = Obligation(
        party="the Supplier", action="indemnify the Customer",
        modality="obligation", object_="indemnify",
        condition="", deadline="within 30 days", exception="",
        evidence="The Supplier shall indemnify the Customer",
        source_category="Indemnification")
    obl2 = Obligation(
        party="Either party", action="terminate this agreement",
        modality="permission", object_="terminate",
        condition="", deadline="", exception="",
        evidence="Either party may terminate this agreement",
        source_category="Termination")
    cuad = CUADResult(
        document_id="doc-001", name="NDA.pdf", doc_class="nda",
        tags=("confidentiality", "governing_law", "indemnification"),
        extraction=extraction_result,
        obligations=(obl1, obl2),
        injection_markers=(), sensitive_hits=0,
        sanitization_applied=False, errors=())

    # ── 1. Complete memo ─────────────────────────────────────────────────
    inp = TemplateInput(
        template_id="memo", template_version=TEMPLATE_VERSION,
        firm_name="TestLaw LLP", matter_id="M-2024-001",
        matter_name="Acme-Beta NDA Review", client_name="Acme Corp",
        document_name="NDA.pdf", cuad_result=cuad,
        audit_findings=(
            {"severity": "HIGH", "title": "Missing limitation clause",
             "explanation": "No limitation of liability found",
             "verification_status": "VERIFIED"},
        ),
        preparer_name="A. Lawyer", date=date(2026, 1, 15))
    out = render_memo(inp)
    check("Legal Research Memo" in out.content_markdown, "memo has title")
    check("TestLaw LLP" in out.content_markdown, "memo has firm name")
    check("Governing Law" in out.content_markdown, "memo has extraction")
    check("the Supplier" in out.content_markdown, "memo has party obligations")
    check("Missing limitation clause" in out.content_markdown, "memo has audit finding")
    check("within 30 days" in out.content_markdown, "memo has deadline")
    check(len(out.evidence_refs) == 2, f"memo evidence refs ({len(out.evidence_refs)})")
    check(out.draft_status == "DRAFT", "memo is DRAFT")
    check(out.approval_status == "PENDING_REVIEW", "memo is PENDING_REVIEW")
    check(out.template_version == TEMPLATE_VERSION, "memo version preserved")
    check("unverified" not in out.missing_fields, "complete memo has no missing extraction")

    # ── 2. Memo with missing fields ──────────────────────────────────────
    inp2 = TemplateInput(
        template_id="memo", template_version=TEMPLATE_VERSION,
        firm_name="TestLaw LLP", matter_id="M-2024-002",
        matter_name="Empty Review", client_name="Beta Ltd",
        document_name="Unknown.pdf", cuad_result=None)
    out2 = render_memo(inp2)
    check("CUAD pipeline result not available" in out2.missing_fields,
          "missing CUAD result noted")
    check("Preparer name not specified" in out2.missing_fields,
          "missing preparer noted")
    check("No audit findings provided" in out2.missing_fields,
          "missing findings noted")
    check(len(out2.evidence_refs) == 0, "no evidence refs when no extraction")

    # ── 3. Multiple parties ──────────────────────────────────────────────
    check("the Supplier" in out.content_markdown, "party 1 in memo")
    check("Either party" in out.content_markdown, "party 2 in memo")

    # ── 4. Unverified findings ───────────────────────────────────────────
    check("unverified" in out.content_markdown.lower() or "fuzzy" in out.content_markdown.lower(),
          "memo mentions fuzzy/unverified status")

    # ── 5. Empty extraction ──────────────────────────────────────────────
    check("not available" in out2.content_markdown.lower() or "not performed" in out2.content_markdown.lower(),
          "empty extraction noted in memo")

    # ── 6. HTML escaping ─────────────────────────────────────────────────
    xss_finding = {"severity": "HIGH", "title": "<script>alert('xss')</script>",
                   "explanation": "test <b>bold</b>"}
    inp3 = TemplateInput(
        template_id="memo", template_version=TEMPLATE_VERSION,
        firm_name="TestLaw LLP", matter_id="M-XSS",
        matter_name="XSS Test", client_name="Evil Corp",
        document_name="bad.pdf", audit_findings=(xss_finding,))
    out3 = render_memo(inp3)
    check("<script>" not in out3.content_html, "HTML escapes script tags")
    check("&lt;script&gt;" in out3.content_html, "script tag escaped in HTML")

    # ── 7. Client email ──────────────────────────────────────────────────
    email_out = render_email(inp)
    check("Subject:" in email_out.content_markdown, "email has subject")
    check("Dear Acme Corp" in email_out.content_markdown, "email has greeting")
    check("Governing Law" in email_out.content_markdown, "email has extraction")
    check("within 30 days" in email_out.content_markdown, "email has deadline")
    check("draft communication" in email_out.content_markdown.lower(), "email marked as draft")
    check(email_out.draft_status == "DRAFT", "email is DRAFT")
    check(email_out.template_version == TEMPLATE_VERSION, "email version preserved")

    # ── 8. Email with no data ────────────────────────────────────────────
    email_out2 = render_email(inp2)
    check("not performed" in email_out2.content_markdown.lower()
          or "not available" in email_out2.content_markdown.lower(),
          "empty email notes missing extraction")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
