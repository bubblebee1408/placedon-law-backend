"""
The free PoSH checker — one page, no signup, no database, no LLM.

Run:  uvicorn checker.app:app --reload --port 8000
Then: http://localhost:8000

Nothing is stored. The profile is aggregate-only (headcount, state, district, type) and is
discarded when the response is written. There is no employee-level PII anywhere in this path,
which is deliberate and is one of the few things that makes a student-built compliance tool
defensible to a cautious buyer.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
import os
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from applicability import CompanyProfile

from jinja2 import TemplateNotFound

from . import documents, ratelimit, retrieval, verifier
from .ask_engine import AskEngine
from .assess import assess
from .rules import DISTRICTS, INDUSTRIES, STATES, Finding

# docs/redoc/openapi disabled: this is a public prototype, not an API product, and the
# auto-generated schema pages are surface area with no user.
app = FastAPI(title="placedon — PoSH checker", docs_url=None, redoc_url=None,
              openapi_url=None)

# The Next.js frontend calls /api/diagnose. Same origin in production; localhost for dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://placedon-hr.vercel.app"],
    allow_methods=["GET", "POST"], allow_headers=["*"],
    # Without this the browser RECEIVES both headers and then refuses to let JS read them —
    # a same-origin deploy works, cross-origin dev silently reports zero blocking issues, and
    # the unlawful-committee warning never fires. Response headers are opt-in across origins.
    expose_headers=["X-Blocking-Issues", "Content-Disposition"],
)


class DiagnoseRequest(BaseModel):
    """
    State codes are ISO 3166-2 (`IN-KA`), not bare `KA`. This is load-bearing, not style:
    `jurisdiction.scope_for()` derives the national tier by splitting on the first hyphen, so
    a bare `KA` yields ['KA-BLR', 'KA', 'KA'] and every national provision stops matching.
    """
    employees: int = Field(ge=0, le=5000)
    contractors: int = Field(default=0, ge=0, le=5000)
    state: str = Field(pattern=r"^IN-[A-Z]{2}$|^IN-OTHER$")
    district: str = ""          # required to answer the annual-return question at all
    industry: str = "it_ites"
    has_policy: str = "unsure"
    has_ic: str = "no"
    ic_date: str = ""
    filed_return: str = "unsure"


def _next_steps(findings: list[Finding]) -> list[str]:
    """Ordered actions. Criticals first, then the things we could not answer — because an
    unanswered question is a task for the user, not a gap to hide."""
    steps: list[str] = []
    for f in findings:
        if f.severity == "critical" and f.action:
            steps.append(f"{f.title} — {f.action}")
    for f in findings:
        if f.severity == "unknown" and f.action:
            steps.append(f"{f.title} — {f.action}")
    for f in findings:
        if f.severity == "warning":
            steps.append(f.title)
    return steps


@app.post("/api/diagnose")
def diagnose(req: DiagnoseRequest, request: Request) -> dict:
    """
    JSON twin of POST /check. Same engine, same findings — only the rendering differs.
    No LLM on this path, so it is deterministic and costs ₹0.
    """
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "unknown"))
    allowed, retry_after = ratelimit.check(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="That's a lot of checks in one minute. Give it a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        findings, headline, profile = _run(
            req.employees, req.contractors, req.state, req.district, req.industry,
            req.has_policy, req.has_ic, req.ic_date, req.filed_return)
    except Exception:                                    # noqa: BLE001 — deliberate boundary
        logging.exception("diagnose.engine_failed state=%s employees=%s",
                          req.state, req.employees)
        raise HTTPException(
            status_code=500,
            detail="Unable to generate report. Please try again.",
        ) from None

    payload = {
        "headline": headline,
        "as_of": profile.as_of.isoformat(),
        "verified": False,  # nothing is lawyer-verified yet; the UI must not claim otherwise
        "company_profile": {
            "state": dict(STATES).get(req.state, req.state),
            "state_code": req.state,
            "district": req.district,
            "industry": dict(INDUSTRIES).get(req.industry, req.industry),
            "employee_count": profile.employee_count,
            "contractor_count": profile.contractor_count,
            "has_ic": req.has_ic == "yes",
            "has_policy": req.has_policy == "yes",
            "has_return_filed": req.filed_return == "yes",
        },
        "summary": {
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "warning": sum(1 for f in findings if f.severity == "warning"),
            "good": sum(1 for f in findings if f.severity == "good"),
            "unknown": sum(1 for f in findings if f.severity == "unknown"),
        },
        "next_steps": _next_steps(findings),
        "findings": [
            {"title": f.title, "severity": f.severity, "detail": f.detail,
             "citation": f.citation, "source": f.source, "action": f.action}
            for f in findings
        ],
    }

    _log_check(req, payload)
    return payload


def _log_check(req: DiagnoseRequest, payload: dict) -> None:
    """
    Best effort, never fails the request.

    Aggregate only — headcount, state, district, type. No names, no IDs, no IP. What makes this
    worth keeping is the abstention count: every question we could not answer is a ranked vote
    for which instrument to ingest next (`docs/06` §3).
    """
    try:
        line = json.dumps({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "state": req.state, "district": req.district,
            "employees": req.employees, "contractors": req.contractors,
            "industry": req.industry,
            "summary": payload["summary"],
            "abstained_on": [f["title"] for f in payload["findings"]
                             if f["severity"] == "unknown"],
        })
        path = Path(os.getenv("CHECK_LOG", "corpus/.checks.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(line + "\n")
    except Exception:                                    # noqa: BLE001
        logging.warning("diagnose.log_failed", exc_info=True)

CSS = """
:root{
  --paper:#faf8f4; --ink:#16150f; --muted:#6a675c; --rule:#e0dbd0;
  --crit:#8c2f1d; --warn:#8a6410; --good:#2f5d3a; --unknown:#3d4c66;
  --crit-bg:#f7ece8; --warn-bg:#f8f2e4; --good-bg:#edf3ed; --unknown-bg:#eceff5;
  --serif:Georgia,"Iowan Old Style",'Times New Roman',serif;
  --sans:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  --measure:34rem;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:17px;line-height:1.6;-webkit-font-smoothing:antialiased}
main{max-width:var(--measure);margin:0 auto;padding:4rem 1.5rem 6rem}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(2rem,1.2rem+3vw,3rem);
  line-height:1.1;letter-spacing:-.02em;margin:0 0 1rem}
h2{font-family:var(--serif);font-weight:400;font-size:1.4rem;margin:2.5rem 0 .5rem}
.lede{font-size:1.15rem;color:var(--muted);margin:0 0 2.5rem}
.rule{border:0;border-top:1px solid var(--rule);margin:3rem 0}
label{display:block;font-weight:600;margin:1.75rem 0 .4rem;font-size:.95rem}
.hint{font-weight:400;color:var(--muted);font-size:.85rem;margin:.1rem 0 .5rem}
input[type=number],input[type=date],select{width:100%;padding:.6rem .7rem;font:inherit;
  font-variant-numeric:tabular-nums;background:#fff;border:1px solid var(--rule);border-radius:2px}
input:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid var(--ink);
  outline-offset:2px}
.choices{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.4rem}
.choices label{margin:0;font-weight:400}
.choices input{position:absolute;opacity:0;width:0}
.choices span{display:inline-block;padding:.45rem .9rem;border:1px solid var(--rule);
  border-radius:2px;background:#fff;cursor:pointer;font-size:.9rem}
.choices input:checked+span{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.choices input:focus-visible+span{outline:2px solid var(--ink);outline-offset:2px}
button{margin-top:2.5rem;width:100%;padding:.9rem;font:inherit;font-weight:600;
  background:var(--ink);color:var(--paper);border:0;border-radius:2px;cursor:pointer}
button:hover{background:#000}
.banner{border:1px solid var(--rule);border-left:3px solid var(--warn);background:var(--warn-bg);
  padding:1rem 1.1rem;margin:0 0 2.5rem;font-size:.9rem;line-height:1.5}
.banner strong{display:block;margin-bottom:.2rem}
.finding{border:1px solid var(--rule);border-left:3px solid var(--rule);border-radius:2px;
  padding:1.1rem 1.2rem;margin:1rem 0}
.finding.critical{border-left-color:var(--crit);background:var(--crit-bg)}
.finding.warning{border-left-color:var(--warn);background:var(--warn-bg)}
.finding.good{border-left-color:var(--good);background:var(--good-bg)}
.finding.unknown{border-left-color:var(--unknown);background:var(--unknown-bg)}
.tag{font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;font-weight:700}
.critical .tag{color:var(--crit)} .warning .tag{color:var(--warn)}
.good .tag{color:var(--good)} .unknown .tag{color:var(--unknown)}
.finding h3{font-size:1.05rem;margin:.3rem 0 .5rem;font-weight:600}
.finding p{margin:0 0 .6rem}
.cite{font-size:.8rem;color:var(--muted);font-variant-numeric:tabular-nums;
  border-top:1px solid var(--rule);padding-top:.55rem;margin-top:.8rem}
.act{font-size:.9rem;font-weight:600;margin:.6rem 0 0}
.stamp{font-size:.8rem;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2.5rem}
a{color:var(--ink)}
footer{margin-top:3rem;font-size:.85rem;color:var(--muted)}
"""

SEV_LABEL = {"critical": "Fix first", "warning": "Needs attention",
             "good": "Looks fine", "unknown": "We don't know"}


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"
    )


BANNER = (
    "<div class=banner><strong>This is a prototype, and none of these rules have been "
    "checked by a lawyer yet.</strong>We are showing it to you anyway, because we would "
    "rather be told we are wrong than find out later. If something here does not match what "
    "you have been advised, that is the most useful thing you can tell us.</div>"
)


def _radio(name: str, options: list[tuple[str, str]], checked: str | None = None) -> str:
    out = ["<div class=choices>"]
    for value, label in options:
        c = " checked" if value == checked else ""
        out.append(
            f"<label><input type=radio name={name} value='{value}'{c}><span>{label}</span></label>"
        )
    out.append("</div>")
    return "".join(out)


@app.get("/", response_class=HTMLResponse)
def form() -> str:
    states = "".join(f"<option value='{c}'>{n}</option>" for c, n in STATES)
    districts = ["<option value=''>Not sure / not listed</option>"]
    for code, names in DISTRICTS.items():
        state_name = dict(STATES)[code]
        districts.append(f"<optgroup label='{state_name}'>")
        districts += [f"<option value='{c}'>{n}</option>" for c, n in names if c]
        districts.append("</optgroup>")
    industries = "".join(f"<option value='{c}'>{n}</option>" for c, n in INDUSTRIES)

    yn = [("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")]

    return _page("Does PoSH apply to you? — placedon", f"""
      <h1>Does PoSH apply to&nbsp;you?</h1>
      <p class=lede>Eight questions. No signup, no email. We show you the section of the Act
      behind every answer — and we tell you when we don't know.</p>
      {BANNER}
      <form method=post action=/check>
        <label for=emp>1 &nbsp;How many employees?</label>
        <p class=hint>People on your payroll, all locations.</p>
        <input id=emp type=number name=employees min=0 max=5000 value=14 required>

        <label for=con>2 &nbsp;How many contract workers?</label>
        <p class=hint>Agency staff, housekeeping, security. Zero is a fine answer.</p>
        <input id=con type=number name=contractors min=0 max=5000 value=0 required>

        <label for=st>3 &nbsp;Which state?</label>
        <select id=st name=state>{states}</select>

        <label for=di>4 &nbsp;Which district?</label>
        <p class=hint>This matters more than you'd think — the annual-return deadline is set
        district by district, not nationally.</p>
        <select id=di name=district>{"".join(districts)}</select>

        <label for=ind>5 &nbsp;What kind of workplace?</label>
        <select id=ind name=industry>{industries}</select>

        <label>6 &nbsp;Do you have a written PoSH policy?</label>
        {_radio("has_policy", yn, "unsure")}

        <label>7 &nbsp;Have you constituted an Internal Committee?</label>
        {_radio("has_ic", [("yes", "Yes"), ("no", "No")], "no")}

        <label for=icd>&nbsp;&nbsp;&nbsp;If yes, roughly when?</label>
        <p class=hint>Leave blank if you don't remember.</p>
        <input id=icd type=date name=ic_date>

        <label>8 &nbsp;Have you filed the annual return?</label>
        {_radio("filed_return", yn, "unsure")}

        <button type=submit>Show me where I stand</button>
      </form>
      <footer>Nothing you type is stored. We never ask for employee names, salaries, or IDs —
      the answer only needs counts.</footer>
    """)


def _tri(v: str) -> bool | None:
    return {"yes": True, "no": False}.get(v)


def _run(employees: int, contractors: int, state: str, district: str, industry: str,
         has_policy: str, has_ic: str, ic_date: str, filed_return: str):
    """One assessment path. The HTML form and the JSON API both come through here."""
    today = date.today()
    constituted = None
    if ic_date:
        try:
            constituted = datetime.strptime(ic_date, "%Y-%m-%d").date()
        except ValueError:
            constituted = None

    profile = CompanyProfile(
        state=state,
        employee_count=max(0, employees),
        contractor_count=max(0, contractors),
        establishment_type=industry,          # type: ignore[arg-type]
        entity_type="pvt_ltd",
        as_of=today,
        districts=[district] if district else [],
    )
    findings, headline = assess(
        profile,
        has_ic=_tri(has_ic),
        ic_constituted_on=constituted,
        has_policy=_tri(has_policy),
        filed_return=_tri(filed_return),
    )
    return findings, headline, profile


@app.post("/check", response_class=HTMLResponse)
def check(
    employees: int = Form(...),
    contractors: int = Form(0),
    state: str = Form("IN-KA"),
    district: str = Form(""),
    industry: str = Form("it_ites"),
    has_policy: str = Form("unsure"),
    has_ic: str = Form("no"),
    ic_date: str = Form(""),
    filed_return: str = Form("unsure"),
) -> str:
    findings, headline, profile = _run(employees, contractors, state, district, industry,
                                       has_policy, has_ic, ic_date, filed_return)
    today = profile.as_of
    state_name = dict(STATES).get(state, state)
    cards = "".join(_card(f) for f in findings)

    return _page("Where you stand — placedon", f"""
      <h1>Where you stand</h1>
      <p class=lede>{headline}</p>
      {BANNER}
      {cards}
      <p class=stamp>{state_name} · {profile.employee_count} employees ·
      as of {today:%d %b %Y}</p>
      <hr class=rule>
      <h2>Tell us what's wrong with this</h2>
      <p>Genuinely — a wrong line here is worth more to us than a compliment. If your CA or
      lawyer has told you something different, that is the thing we want to hear.</p>
      <p><a href="/">Run it again</a></p>
    """)


def _card(f: Finding) -> str:
    cite = f"<p class=cite>{f.citation}" + (f" · {f.source}" if f.source else "") + "</p>"
    act = f"<p class=act>{f.action}</p>" if f.action else ""
    return (
        f"<section class='finding {f.severity}'>"
        f"<div class=tag>{SEV_LABEL[f.severity]}</div>"
        f"<h3>{f.title}</h3><p>{f.detail}</p>{act}{cite}</section>"
    )


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    state: str = Field(default="IN-KA", pattern=r"^IN-[A-Z]{2}$|^IN-OTHER$")
    employees: int = Field(default=0, ge=0, le=5000)


@lru_cache(maxsize=1)
def _ask_engine() -> AskEngine:
    """One instance. Building it parses the corpus and derives the provision graph."""
    return AskEngine()


@app.post("/api/ask")
def ask(req: AskRequest, request: Request) -> dict:
    """
    Cited Q&A, routed through `checker.ask_engine`.

    The endpoint used to inline the pipeline. It now delegates, which buys three things the
    inline version could not have:

      * **Deductions never reach a model.** "Do I need an IC?" is computed by the rules engine
        from the Act and the company's own headcount. The old path would have sent it to be
        explained; the engine routes it to code before retrieval.
      * **The epistemic chain is exposed.** Abstention names the weakest link — "s.4 rests on
        unverified s.16" — instead of restating that nothing is verified.
      * **One pipeline, one set of tests.** ask_engine carries 24 of its own; the inline version
        had none.

    Still ₹0. Every provision carries `verified_by: null`, so the gate closes before any call.
    """
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "unknown"))
    allowed, retry_after = ratelimit.check(client_ip, limit=10)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many questions in one minute.",
                            headers={"Retry-After": str(retry_after)})

    try:
        result = _ask_engine().ask(req.question,
                                   {"employee_count": req.employees, "state": req.state})
    except Exception:                                    # noqa: BLE001
        logging.exception("ask.failed")
        raise HTTPException(500, "Unable to answer right now. Please try again.") from None

    payload = {
        "abstained": result.abstained,
        "answer": result.reason if result.abstained else result.answer,
        # The ordinal epistemic status, not a confidence tier. Calibrating a tier needs a
        # labelled validation set we do not have; this is a fact about the corpus.
        "status": result.status,
        "route": result.route,
        "epistemic_chain": result.epistemic_chain,
        "cost_inr": result.cost_inr,
        "citations": [
            {"citation": src["section"], "heading": src["heading"],
             "verified_by": src["verified_by"]}
            for src in result.sources
        ],
        # Kept so existing clients do not break on a renamed field.
        "confidence": "abstain" if result.abstained else "answer",
        "retrieval_stage": result.route,
    }
    _log_ask(req, payload)
    return payload


def _log_ask(req: AskRequest, payload: dict) -> None:
    """Abstentions are the roadmap — every unanswered question ranks the next instrument."""
    try:
        path = Path(os.getenv("ASK_LOG", "corpus/.asks.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "question": req.question, "state": req.state,
                "abstained": payload["abstained"], "stage": payload["retrieval_stage"],
                "cost_inr": payload["cost_inr"],
                "cited": [c["citation"] for c in payload["citations"]],
            }) + "\n")
    except Exception:                                    # noqa: BLE001
        logging.warning("ask.log_failed", exc_info=True)


@app.get("/api/generate/templates")
def list_templates() -> dict:
    """Free tier, no auth. Unavailable templates are listed WITH the reason, not hidden."""
    return {"templates": documents.list_available_templates()}


class GenerateRequest(BaseModel):
    company: dict = Field(default_factory=dict)
    inputs: dict = Field(default_factory=dict)


@app.post("/api/generate/{template_type}")
def generate(template_type: str, req: GenerateRequest, request: Request) -> Response:
    """
    Returns print-ready HTML, not a PDF blob.

    weasyprint needs cairo/pango — a system install locally and unavailable on Vercel
    serverless, so it breaks in both places we deploy. The document carries @page rules and
    a print stylesheet; the browser's own print-to-PDF produces a proper A4 file with no
    dependency at all.
    """
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "unknown"))
    allowed, retry_after = ratelimit.check(client_ip, limit=5)
    if not allowed:
        raise HTTPException(429, "Too many documents in one minute.",
                            headers={"Retry-After": str(retry_after)})

    try:
        doc = documents.generate_document(template_type, req.company, req.inputs)
    except TemplateNotFound:
        raise HTTPException(404, f"No template called {template_type!r}.") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except Exception:                                    # noqa: BLE001
        logging.exception("generate.failed type=%s", template_type)
        raise HTTPException(500, "Could not generate that document. Please try again.") from None

    return Response(
        content=doc.html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="{doc.filename}"',
            "X-Blocking-Issues": str(sum(1 for i in doc.issues if i.severity == "blocking")),
        },
    )
