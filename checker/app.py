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

import html
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

from . import documents, ratelimit, register, retrieval, verifier
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
    # The frontend is a SEPARATE Vercel project, so every browser call to this API is
    # cross-origin and an omitted origin is a silent, total failure of the paid features.
    # It failed exactly that way once: the /generate grid loaded fine — it is a server
    # component, so its fetch never leaves the server and CORS does not apply — while every
    # document POST from the same page was blocked. A page that half-works is harder to
    # diagnose than one that does not load.
    #
    # Preview deployments get their own hostname per build, so the regex covers them; the
    # explicit list stays for the stable aliases.
    allow_origins=["http://localhost:3000", "https://placedon-hr.vercel.app",
                   "https://placedon-hr-app.vercel.app"],
    allow_origin_regex=r"https://placedon-hr-app-[a-z0-9]+-placeon\.vercel\.app",
    allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"],
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
  --rule-strong:#c9c2b0; --crit:#8c2f1d; --warn:#8a6410; --good:#2f5d3a; --unknown:#3d4c66;
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

/* ── Epistemic status badge ──────────────────────────────────────────────
   The ordinal lattice, made visible. It has existed in code for two days and
   no user could see it. The dot carries the state; the word carries the
   meaning; neither alone is enough at 390px in sunlight. */
/* The seven states are an ORDER, not a palette.
   Hue-coding them green/amber/red — which this first did — collapses an ordinal ladder into
   three categories and implies "compliant/at-risk" buckets the corpus cannot support. The
   ancestor here is Bluebook's introductory signals (see / see also / cf. / but see): a graded
   scale of how strongly an authority supports a proposition, and it is typeset as a sequence.
   So the ramp is carried by BORDER STYLE and FILL, not colour: dashed -> dotted -> solid
   outline -> solid fill -> sealed. Pencil draft, then ink, then notarised. Adjacent states
   differ by exactly one property, so the order is legible before the label is read.
   Colour is spent once, on QUOTED, so that when it appears it means something. */
/* The public register. Rows with no reply must read as prominently as rows with one — they are
   the evidence that we asked rather than guessed, so they get the same weight and the same rule. */
.tally{font-family:var(--mono);font-size:.82rem;color:var(--muted);
       border-top:2px solid var(--ink);border-bottom:1px solid var(--rule-strong);
       padding:.7rem 0;margin:1.4rem 0 0}
.reg{border-collapse:collapse;width:100%;margin:1.6rem 0;font-size:.94rem}
.reg th{text-align:left;font-family:var(--mono);font-size:.64rem;letter-spacing:.09em;
        text-transform:uppercase;color:var(--muted);font-weight:600;
        border-bottom:1px solid var(--ink);padding:0 .8rem .45rem 0}
.reg td{padding:.6rem .8rem .6rem 0;border-bottom:1px solid var(--rule);vertical-align:baseline}
.reg td.date,.reg td.when{font-family:var(--mono);font-size:.84rem;font-variant-numeric:tabular-nums;
        white-space:nowrap}
.reg td.when{color:var(--muted)}
.reg tr.q td{border-bottom:1px solid var(--rule);padding-top:0}
.reg blockquote{margin:0 0 .3rem;padding:.15rem 0 .15rem .9rem;border-left:3px solid var(--crit);
        font-family:var(--serif);font-style:italic;color:var(--ink);max-width:44rem}
.reg blockquote cite{display:block;margin-top:.35rem;font-style:normal;font-family:var(--mono);
        font-size:.7rem;color:var(--muted)}
.note{font-size:.9rem;color:var(--muted);max-width:var(--measure);margin:1.2rem 0}
.note b{color:var(--ink)}

.status{display:inline-flex;align-items:center;gap:.3em;padding:.18em .55em;border-radius:2px;
  font-family:ui-monospace,Menlo,monospace;font-size:.68rem;font-weight:600;letter-spacing:.04em;
  white-space:nowrap;background:transparent;color:var(--muted)}
.status.silent{border:1px dashed var(--rule-strong)}
.status.unsupported{border:1px dashed var(--rule-strong);text-decoration:line-through;
  text-decoration-color:var(--rule-strong)}
.status.unchecked{border:1px dotted var(--muted)}
.status.secondary{border:1px solid var(--muted);color:var(--ink)}
.status.inferred{border:1.5px solid var(--ink);color:var(--ink)}
/* The dagger is borrowed from critical-edition sigla, where it marks a reading restored or
   doubtful. It says "this is our reading" in one character. */
/* The dagger literally, not as a CSS hex escape. `content:"\2020 "` looks right but
   the CSS constant is a plain Python string, so Python read \202 as an OCTAL escape
   and the browser received U+0082 followed by "0" — the badge rendered a zero. The
   character costs two bytes and cannot be misparsed by anything in the chain. */
.status.inferred::after{content:"†";margin-left:.15em;opacity:.7}
.status.verified{border:1.5px solid var(--ink);background:var(--ink);color:var(--paper)}
.status.quoted{border:1px solid var(--crit);border-left-width:3px;background:var(--crit-bg);
  color:var(--ink);font-family:var(--serif);font-style:italic;font-weight:400}

/* ── Citation pin ────────────────────────────────────────────────────────
   Every claim names its source. Making that a pin rather than a trailing line
   means the eye can find it without reading the sentence, which is what a
   sceptical reader does first. Monospace because a citation is an address. */
.pin{display:inline-block;padding:.05em .4em;border:1px solid var(--rule);
  border-radius:2px;background:#fff;font-family:ui-monospace,Menlo,monospace;
  font-size:.78em;color:var(--muted);text-decoration:none;white-space:nowrap}
a.pin:hover,a.pin:focus-visible{color:var(--ink);border-color:var(--ink)}

/* ── Cascade block ───────────────────────────────────────────────────────
   The dependency chain, rendered as a chain. This is the one output nothing
   else in this market produces, and it was being flattened into a comma list:
   "s.2 rests on unverified s.4, s.5, s.6, s.7, s.9, s.16."
   Indentation carries the derivation; the rule down the left carries the fact
   that these are steps rather than bullets. */
.cascade{margin:1rem 0 0;padding:.1rem 0 .1rem 1.1rem;border-left:2px solid var(--rule);
  list-style:none;font-size:.9rem}
.cascade li{position:relative;margin:0 0 .7rem;color:var(--muted)}
.cascade li:last-child{margin-bottom:0}
.cascade li::before{content:"↳";position:absolute;left:-1.55rem;color:var(--rule)}
.cascade .ground{color:var(--ink)}
.note{color:var(--muted);font-size:.82rem;font-style:italic}

/* ── Motion ──────────────────────────────────────────────────────────────
   One curve, a pure decelerate with no overshoot: a stamp coming down and
   staying, not a card popping in. Bounce reads as playful and this is a legal
   instrument.

   Nothing here is a LOADING state. No spinner, no shimmer, no pulse — because
   UNCHECKED is a permanent fact about the corpus, not a value in flight, and
   animating it as "loading" would promise it resolves on its own. It does not.

   The cascade staggers so it reads as tracing an argument rather than a list
   rendering. Only the nodes move; the spine is static, so attention stays on
   the content. */
@keyframes settle{to{opacity:1;transform:none}}
.finding.critical,.finding.unknown{opacity:0;transform:translateY(6px);
  animation:settle 420ms cubic-bezier(.16,1,.3,1) forwards}
.finding.critical{animation-delay:60ms}
.cascade li{opacity:0;transform:translateY(4px);
  animation:settle 280ms cubic-bezier(.16,1,.3,1) forwards}
.cascade li:nth-child(1){animation-delay:120ms}
.cascade li:nth-child(2){animation-delay:210ms}
.cascade li:nth-child(3){animation-delay:300ms}
@media (prefers-reduced-motion:reduce){
  .finding.critical,.finding.unknown,.cascade li{animation:none;opacity:1;transform:none}
}

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


# Where a citation points. The Act is the only instrument we hold at primary grade, so it is
# the only one we deep-link; sending someone to a page we have not verified would be worse than
# sending them nowhere.
INDIA_CODE = "https://www.indiacode.nic.in/handle/123456789/2104"


def _pins(citation: str) -> str:
    """
    Citations as pins rather than a trailing grey line.

    A sceptical reader looks for the source before reading the claim, and a comma-separated
    sentence makes them read to find it. Each section becomes its own pin so the eye can count
    them. Only PoSH Act citations link out — we hold that text at primary grade.
    """
    import re as _re                                          # noqa: PLC0415

    out, seen = [], set()
    # Pull the section references out wherever they sit. Splitting on punctuation produced
    # "penalty s.26, PoSH Act 2013" as one pin, which is a sentence, not an address.
    for m in _re.finditer(r"s\.\s?(\d+(?:\(\w+\))?(?:/\d+)?)", citation):
        ref = m.group(1)
        if ref in seen:
            continue
        seen.add(ref)
        out.append(f'<a class=pin href="{INDIA_CODE}" target=_blank rel=noopener>'
                   f'§&nbsp;{ref}</a>')
    # Anything that is not a section reference is a qualification, and it matters — "deadline
    # fixed by the District Officer" is the whole point of that finding. Kept as plain text.
    rest = _re.sub(r"s\.\s?\d+(?:\(\w+\))?(?:/\d+)?", "", citation)
    rest = _re.sub(r"PoSH Act 2013", "", rest)
    rest = " ".join(w for w in _re.split(r"[;,·]", rest) if w.strip())
    if rest.strip():
        out.append(f'<span class=note>{rest.strip()}</span>')
    return " ".join(out)


def _cascade(f: Finding) -> str:
    """
    The dependency chain, rendered as a chain.

    `epistemic_status` computes which provisions a claim rests on and which of those nobody has
    verified, each with the corpus field that established it. That was being flattened into one
    sentence — "s.2 rests on unverified s.4, s.5, s.6, s.7, s.9, s.16" — which reads as an error
    string rather than as a derivation. It is the one output nothing else in this market
    produces, so it gets the space.
    """
    try:
        from checker.epistemic_status import EpistemicState   # noqa: PLC0415
        import re as _re                                      # noqa: PLC0415
        nums = [int(n) for n in _re.findall(r"s\.(\d+)", f.citation)]
        if not nums:
            return ""
        claim = EpistemicState().assess(f.title, sections=nums, citation=f.citation)
    except Exception:                                         # noqa: BLE001
        return ""

    grounds = sorted(claim.grounds, key=lambda g: g.status)[:3]
    if not grounds:
        return ""
    # No `g.source` here. It reads "provision_graph.blocked_by" and "provision.verified_by is
    # null" — the corpus fields that produced the status. That is exactly right in the JSON API,
    # where a developer or a reviewer wants the provenance, and exactly wrong on a page read by
    # an HR generalist at 11pm who is worried about a fine. The status badge already carries the
    # claim; the field name only carries our implementation.
    items = "".join(
        f"<li><span class='status {g.status.name.lower()}'>{g.status.name}</span> "
        f"<span class=ground>{g.reason}</span></li>"
        for g in grounds
    )
    return f"<ul class=cascade>{items}</ul>"


def _card(f: Finding) -> str:
    cite = f"<p class=cite>{_pins(f.citation)}</p>"
    act = f"<p class=act>{f.action}</p>" if f.action else ""
    # The chain is shown where it changes the reading: on a refusal, and on the finding we tell
    # people to fix first. Everywhere else it is noise.
    chain = _cascade(f) if f.severity in ("unknown", "critical") else ""
    return (
        f"<section class='finding {f.severity}'>"
        f"<div class=tag>{SEV_LABEL[f.severity]}</div>"
        f"<h3>{f.title}</h3><p>{f.detail}</p>{act}{chain}{cite}</section>"
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


@app.get("/api/register")
def register_json() -> dict:
    """The whole register, unauthenticated. Meant to be cited, scraped and disagreed with."""
    rows = sorted(register._rows().values(), key=lambda x: x.district)
    return {
        "what_this_is": ("What each District Officer told us, in their own words, about the date "
                         "for submitting the annual report under s.21 of the PoSH Act."),
        "what_this_is_not": ("Not a national deadline. There is none: s.21 delegates timing to "
                             "what 'may be prescribed' and the PoSH Rules prescribe no date."),
        "districts": [{"code": r.jurisdiction, "district": r.district, "status": r.status,
                       "asked_on": r.asked_on, "replied_on": r.replied_on,
                       "notified_date": r.notified_date, "reply": r.reply_verbatim}
                      for r in rows],
        "count": len(rows),
    }


@app.get("/register", response_class=HTMLResponse)
def register_page() -> str:
    """
    The register, in public.

    Every district appears, including — especially — the ones nobody has answered. Filtering to
    the 'interesting' rows would hide the non-answers, and the non-answers are the evidence that
    we asked rather than guessed. They are also the only part of this nobody else has.

    A date never appears without the officer's words beneath it. That rule is enforced in three
    places now: the CLI refuses to record one, register.py refuses to describe one, and
    verify.py refuses to let this page render one.
    """
    rows = sorted(register._rows().values(), key=lambda x: x.district)
    asked = sum(1 for r in rows if r.status != "UNASKED")
    answered = sum(1 for r in rows if r.has_answer)

    LABEL = {"DATE_NOTIFIED": "notified", "NONE_NOTIFIED": "none notified",
             "NO_REPLY": "no reply", "ASKED": "asked", "UNASKED": "not yet asked"}

    items = []
    for r in rows:
        cls = "verified" if r.status == "DATE_NOTIFIED" else (
              "secondary" if r.status == "NONE_NOTIFIED" else
              "unchecked" if r.status in {"ASKED", "NO_REPLY"} else "silent")
        date = f"<td class=date>{html.escape(r.notified_date)}</td>" if r.notified_date \
               else "<td class=date>&mdash;</td>"
        when = r.replied_on or r.asked_on or ""
        quote = ""
        if r.reply_verbatim:
            quote = (f"<tr class=q><td></td><td colspan=3><blockquote>"
                     f"{html.escape(r.reply_verbatim)}"
                     f"<cite>— District Officer, {html.escape(r.district)}"
                     f"{', ' + html.escape(r.replied_on) if r.replied_on else ''}</cite>"
                     f"</blockquote></td></tr>")
        items.append(
            f"<tr><td>{html.escape(r.district)}</td>"
            f"<td><span class='status {cls}'>{LABEL[r.status]}</span></td>"
            f"{date}<td class=when>{html.escape(when)}</td></tr>{quote}")

    body = f"""
<h1>Notified dates for the PoSH annual report</h1>
<p class=lede>Section 21 of the PoSH Act says the Committee shall prepare an annual report
&ldquo;in such form and <b>at such time as may be prescribed</b>&rdquo;. The Rules prescribe no
time. The District Officer sets it, and every guide we can find tells you to go and ask yours.</p>
<p class=lede>So we asked. This is what came back, verbatim, including the districts that have
not replied.</p>

<p class=tally><b>{len(rows)}</b> districts &middot; <b>{asked}</b> asked &middot;
<b>{answered}</b> answered</p>

<table class=reg>
<tr><th>District</th><th>Status</th><th>Notified date</th><th>Asked / replied</th></tr>
{''.join(items)}
</table>

<p class=note><b>What this is not.</b> It is not a national deadline, because there is no national
deadline. &ldquo;31 January&rdquo; is widely published and appears nowhere in the fourteen PoSH
Rules; at least one District Officer elsewhere in India has notified 28 February. Where a row says
we have had no reply, that is the honest state of that district and we will not fill it with a
plausible date.</p>
<p class=note>Machine-readable: <a href="/api/register">/api/register</a>. Corrections welcome —
if you are a District Officer and a row here is wrong, tell us and we will publish your words
instead.</p>
"""
    return _page("Notified PoSH annual-return dates, by district", body)


@app.get("/api/districts")
def list_districts(state: str | None = None) -> dict:
    """
    The districts we can say anything about, and what we currently know for each.

    Served rather than hard-coded in the frontend. The frontend used to carry its own list of
    two — with a comment claiming they were "districts whose annual-return notification we
    actually hold", which was true when written and false the moment the register existed. One
    of the two was Gurugram, which the register has never held at all: picking it produced a
    lookup that raised, was caught, and silently degraded to no district note. A list that drifts
    from the register is how a user gets shown a district we cannot speak to.

    `note` is the same sentence ask_engine uses, from the same function. There is no second
    wording to keep in step.
    """
    out = []
    for r in sorted(register._rows().values(), key=lambda x: x.district):
        if state and not r.jurisdiction.startswith(f"IN-{state.upper()}-"):
            continue
        note, source = register.describe(r.jurisdiction)
        out.append({
            "code": r.jurisdiction, "district": r.district, "status": r.status,
            "note": note, "asked_on": r.asked_on,
            # Only ever present alongside a date, because describe() cannot produce one without it.
            "source": source,
        })
    return {"districts": out, "count": len(out)}


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
