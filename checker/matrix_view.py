"""The first Companies Act surface: a compliance matrix a person can open.

Everything in this repo until now has been reachable only from a Python prompt.
The only HTTP surface that exists belongs to the abandoned PoSH product. This is
the route that makes the corporate work usable, and it is deliberately the
smallest thing that is genuinely useful.

## No dependencies, and no model

`handle()` is a pure function: parameters in, (status, content type, body) out.
It imports nothing outside the standard library and this repo, so Stage 1 runs
with no API key, no framework and no network. That is not minimalism for its own
sake — Stage 1 is what every later stage degrades to when the budget is
exhausted, so it has to be a complete correct product on its own.

## Unknown must survive the form

A web form is where "unknown" usually dies: a select box defaults to something,
a number field defaults to zero, and by the time the value reaches the engine
nobody can tell what the user actually said. Every field here therefore has an
explicit "not known" option that maps to None, and a field left out entirely
stays None. For a threshold shaped "does not exceed X", zero is the strongest
possible pass, so a defaulted zero would silently convert ignorance into a
favourable answer.

## What it may not show

s.52(1)(q)(ii): Act text may only ever be served together with original matter.
This page renders our analysis, our citations and our refusals. It never renders
a provision's text as its own content, and there is a test asserting the card
carries no bare statutory extract.
"""
from __future__ import annotations

import html
from datetime import date
from urllib.parse import parse_qs

from checker.company_profile import CompanyProfile, Figure, Money
from checker.obligations import (CANNOT_DETERMINE, DOES_NOT_APPLY, build,
                                 REGISTER)

UNKNOWN = ""            # what the form submits for "not known"

_CLASSES = ("private", "public", "opc")

_TRISTATE = {"yes": True, "no": False, UNKNOWN: None}


class InputError(ValueError):
    """The submitted facts could not be read. Nothing is guessed."""


def _tri(params: dict, name: str) -> bool | None:
    raw = (params.get(name) or [UNKNOWN])[0].strip().lower()
    if raw not in _TRISTATE:
        raise InputError(f"{name}: expected yes, no, or blank for not known")
    return _TRISTATE[raw]


def _money(params: dict, name: str, fy: str | None) -> Figure | None:
    """A rupee figure in CRORE, bound to a financial year. Blank stays None."""
    raw = (params.get(name) or [UNKNOWN])[0].strip()
    if not raw:
        return None
    if fy is None:
        raise InputError(
            f"{name}: a figure needs the financial year it speaks to — "
            "s.2(85)(ii) asks for the immediately preceding year specifically")
    try:
        crore = float(raw)
    except ValueError:
        raise InputError(f"{name}: {raw!r} is not a number of crore") from None
    if crore < 0:
        raise InputError(f"{name}: a negative amount is not a figure")
    return Figure(Money.crore(crore), fy)


def parse_profile(params: dict) -> CompanyProfile:
    """Build a profile from form parameters. Unknown stays unknown."""
    cls = (params.get("company_class") or [UNKNOWN])[0].strip().lower()
    if cls not in _CLASSES:
        raise InputError(f"company_class: {cls!r} is not one of "
                         f"{', '.join(_CLASSES)}")

    inc_raw = (params.get("incorporation_date") or [UNKNOWN])[0].strip()
    if not inc_raw:
        raise InputError("incorporation_date is required — several deadlines "
                         "run from it")
    try:
        inc = date.fromisoformat(inc_raw)
    except ValueError:
        raise InputError(f"incorporation_date: {inc_raw!r} is not YYYY-MM-DD") from None

    as_of_raw = (params.get("as_of") or [UNKNOWN])[0].strip()
    try:
        as_of = date.fromisoformat(as_of_raw) if as_of_raw else date.today()
    except ValueError:
        raise InputError(f"as_of: {as_of_raw!r} is not YYYY-MM-DD") from None

    fy = (params.get("financial_year") or [UNKNOWN])[0].strip() or None

    dc_raw = (params.get("director_count") or [UNKNOWN])[0].strip()
    try:
        dc = int(dc_raw) if dc_raw else None
    except ValueError:
        raise InputError(f"director_count: {dc_raw!r} is not a whole number") from None

    return CompanyProfile(
        company_class=cls,                      # type: ignore[arg-type]
        incorporation_date=inc, as_of=as_of,
        latest_financial_year=fy,
        director_count=dc,
        is_listed=_tri(params, "is_listed"),
        is_section_8=_tri(params, "is_section_8"),
        is_holding_company=_tri(params, "is_holding_company"),
        is_subsidiary_company=_tri(params, "is_subsidiary_company"),
        governed_by_special_act=_tri(params, "governed_by_special_act"),
        paid_up_capital=_money(params, "paid_up_capital_crore", fy),
        turnover=_money(params, "turnover_crore", fy),
    )


_E = html.escape

_STYLE = """
:root{--ink:#14171d;--soft:#4a515e;--faint:#767e8c;--rule:#dde1e7;
--bg:#f5f6f8;--card:#fff;--good:#1f6f4a;--warn:#8a6410;--bad:#a33232;
--accent:#24407a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:60rem;margin:0 auto;padding:2rem 1rem 5rem}
h1{font:600 1.9rem/1.15 "Iowan Old Style",Palatino,Georgia,serif;margin:0 0 .3rem}
.sub{color:var(--soft);margin:0 0 1.6rem}
form{background:var(--card);border:1px solid var(--rule);border-radius:6px;
padding:1.2rem;margin-bottom:1.6rem}
fieldset{border:0;padding:0;margin:0 0 1rem}
legend{font:500 .7rem/1 ui-monospace,monospace;letter-spacing:.1em;
text-transform:uppercase;color:var(--faint);padding:0 0 .5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.8rem}
label{display:block;font-size:.82rem;color:var(--soft);margin-bottom:.2rem}
input,select{width:100%;padding:.4rem .5rem;border:1px solid var(--rule);
border-radius:4px;font:inherit;font-size:.9rem;background:#fff;color:var(--ink)}
button{background:var(--accent);color:#fff;border:0;border-radius:4px;
padding:.55rem 1.1rem;font:inherit;font-weight:600;cursor:pointer}
.row{background:var(--card);border:1px solid var(--rule);border-left:4px solid var(--rule);
border-radius:6px;padding:1rem 1.2rem;margin-bottom:.9rem}
.row.attn{border-left-color:var(--warn)}
.row.no{border-left-color:var(--faint);opacity:.85}
.id{font:600 .8rem ui-monospace,monospace;color:var(--faint)}
.duty{font-weight:600;margin:.15rem 0 .4rem}
.state{display:inline-block;font:500 .68rem ui-monospace,monospace;
letter-spacing:.06em;padding:.15rem .45rem;border-radius:3px}
.s-APPLIES_UNDETERMINED{background:#f6eedc;color:var(--warn)}
.s-CANNOT_DETERMINE{background:#f7e7e7;color:var(--bad)}
.s-DOES_NOT_APPLY{background:#eff1f4;color:var(--faint)}
.s-APPLIES_NOT_SATISFIED{background:#f7e7e7;color:var(--bad)}
.s-APPLIES_SATISFIED{background:#e3f0e9;color:var(--good)}
dl{margin:.6rem 0 0;font-size:.88rem}
dt{font:500 .68rem ui-monospace,monospace;letter-spacing:.06em;
text-transform:uppercase;color:var(--faint);margin-top:.5rem}
dd{margin:.1rem 0 0;color:var(--soft)}
.blocked{color:var(--bad);font-weight:600}
.err{background:#f7e7e7;border-left:4px solid var(--bad);padding:.8rem 1rem;
border-radius:0 4px 4px 0;margin-bottom:1.2rem}
footer{margin-top:2rem;padding-top:1.2rem;border-top:1px solid var(--rule);
color:var(--faint);font-size:.85rem}
"""


def _field(label: str, name: str, value: str = "", kind: str = "text") -> str:
    return (f'<div><label for="{name}">{_E(label)}</label>'
            f'<input id="{name}" name="{name}" type="{kind}" value="{_E(value)}"></div>')


def _tri_field(label: str, name: str, value: str = "") -> str:
    opts = "".join(
        f'<option value="{v}"{" selected" if v == value else ""}>{_E(t)}</option>'
        for v, t in ((UNKNOWN, "not known"), ("yes", "yes"), ("no", "no")))
    return (f'<div><label for="{name}">{_E(label)}</label>'
            f'<select id="{name}" name="{name}">{opts}</select></div>')


def _form(params: dict) -> str:
    g = lambda k: (params.get(k) or [""])[0]  # noqa: E731
    cls = g("company_class")
    cls_opts = "".join(
        f'<option value="{c}"{" selected" if c == cls else ""}>{c}</option>'
        for c in _CLASSES)
    return f"""<form method="get" action="/matrix">
<fieldset><legend>the company</legend><div class="grid">
<div><label for="company_class">company class</label>
<select id="company_class" name="company_class">{cls_opts}</select></div>
{_field("incorporation date", "incorporation_date", g("incorporation_date"), "date")}
{_field("as of", "as_of", g("as_of"), "date")}
{_field("financial year (e.g. 2024-25)", "financial_year", g("financial_year"))}
{_field("number of directors", "director_count", g("director_count"))}
</div></fieldset>
<fieldset><legend>status — leave as “not known” if you are not sure</legend><div class="grid">
{_tri_field("listed", "is_listed", g("is_listed"))}
{_tri_field("registered under s.8", "is_section_8", g("is_section_8"))}
{_tri_field("holding company", "is_holding_company", g("is_holding_company"))}
{_tri_field("subsidiary company", "is_subsidiary_company", g("is_subsidiary_company"))}
{_tri_field("governed by a special Act", "governed_by_special_act",
            g("governed_by_special_act"))}
</div></fieldset>
<fieldset><legend>figures, in crore — blank means not known</legend><div class="grid">
{_field("paid-up share capital (crore)", "paid_up_capital_crore",
        g("paid_up_capital_crore"))}
{_field("turnover, preceding FY (crore)", "turnover_crore", g("turnover_crore"))}
</div></fieldset>
<button type="submit">Build the matrix</button></form>"""


def _rows_html(profile: CompanyProfile) -> str:
    out = []
    for r in build(profile):
        cls = "no" if r.state == DOES_NOT_APPLY else ("attn" if r.needs_attention else "")
        parts = [f'<div class="row {cls}"><div class="id">{_E(r.obligation_id)}</div>',
                 f'<div class="duty">{_E(r.duty)}</div>',
                 f'<span class="state s-{_E(r.state)}">{_E(r.state)}</span>',
                 "<dl>",
                 f"<dt>provision</dt><dd>{_E(r.provision)}</dd>",
                 f"<dt>basis</dt><dd>{_E(r.basis)}</dd>"]
        if r.missing_facts:
            parts.append("<dt>what would settle it</dt><dd>"
                         + _E("; ".join(r.missing_facts)) + "</dd>")
        if r.blocked_by:
            parts.append('<dt>blocked</dt><dd class="blocked">'
                         + _E(r.blocked_by)
                         + " — a source this system has not properly acquired</dd>")
        parts.append("</dl></div>")
        out.append("".join(parts))
    return "".join(out)


def _page(body: str) -> str:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f'<meta name=viewport content="width=device-width,initial-scale=1">'
            f"<title>Compliance matrix — Companies Act 2013</title>"
            f"<style>{_STYLE}</style></head><body><div class=wrap>{body}"
            f"<footer>No language model was consulted. Every line above is a "
            f"provision, a fact you supplied, or arithmetic on the two. "
            f"Nothing here states that an obligation was complied with — "
            f"establishing that needs the documents.</footer>"
            f"</div></body></html>")


def handle(path: str, query: str = "") -> tuple[int, str, str]:
    """Route. Pure: no I/O, no globals, no model. (status, content-type, body)."""
    params = parse_qs(query, keep_blank_values=True)

    if path not in ("/", "/matrix"):
        return 404, "text/html; charset=utf-8", _page(
            "<h1>Not found</h1><p class=sub>There is no page at that address.</p>")

    head = ("<h1>Compliance matrix</h1><p class=sub>Companies Act 2013. "
            "Obligations are generated from what the company <em>is</em>, "
            "not from documents you upload — so a company that has filed "
            "nothing still gets a full matrix.</p>")

    if path == "/" or not params.get("company_class"):
        return 200, "text/html; charset=utf-8", _page(head + _form(params))

    try:
        profile = parse_profile(params)
    except InputError as e:
        return 400, "text/html; charset=utf-8", _page(
            head + f'<div class="err">{_E(str(e))}</div>' + _form(params))

    return 200, "text/html; charset=utf-8", _page(
        head + _form(params) + _rows_html(profile))


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

    print("matrix_view")

    st, ct, body = handle("/")
    check(st == 200 and "text/html" in ct, f"the root serves a page ({st})")
    check("<form" in body, "...with the form")
    check(body.count("not known") >= 5,
          "every status field offers 'not known' as its default")

    st4, _, _ = handle("/nope")
    check(st4 == 404, f"an unknown path 404s ({st4})")

    q = ("company_class=private&incorporation_date=2019-06-01&as_of=2026-08-31"
         "&financial_year=2024-25&paid_up_capital_crore=2&turnover_crore=30"
         "&is_holding_company=no&is_subsidiary_company=no&is_section_8=no"
         "&governed_by_special_act=no")
    st2, _, page = handle("/matrix", q)
    check(st2 == 200, f"a filled form builds the matrix ({st2})")
    check("CA13-S96-AGM" in page and "CA13-S173-BOARD" in page,
          "...and renders the obligation rows")
    check("S-002" in page and "not properly acquired" in page,
          "a row blocked on an unacquired source says so on the page")
    check("No language model was consulted" in page,
          "the page states no model was consulted")
    check("compl" in page.lower() and "needs the documents" in page,
          "...and that it does not claim compliance")

    # Unknown must survive the round trip.
    q_unknown = ("company_class=private&incorporation_date=2019-06-01"
                 "&financial_year=2024-25")
    p = parse_profile(parse_qs(q_unknown, keep_blank_values=True))
    check(p.turnover is None, "a blank figure stays None, never 0")
    check(p.is_section_8 is None, "an unanswered status stays None, never False")
    check(p.director_count is None, "a blank count stays None")

    # And a zeroed figure is a real answer, distinct from blank.
    p0 = parse_profile(parse_qs(q_unknown + "&turnover_crore=0",
                                keep_blank_values=True))
    check(p0.turnover is not None and p0.turnover.amount.rupees == 0,
          "an explicit zero is recorded as zero, not as unknown")

    # Crore scaling must survive the form.
    p2 = parse_profile(parse_qs(q_unknown + "&paid_up_capital_crore=4",
                                keep_blank_values=True))
    check(p2.paid_up_capital.amount.rupees == 40_000_000,
          f"4 in the crore field is 40,000,000 rupees "
          f"({p2.paid_up_capital.amount.rupees})")

    # Bad input refuses and says why, without losing what was typed.
    st3, _, err = handle("/matrix", "company_class=private&incorporation_date=oops")
    check(st3 == 400, f"an unreadable date is a 400 ({st3})")
    check("YYYY-MM-DD" in err, "...and the message says the expected form")
    check("<form" in err, "...and the form comes back so nothing is retyped")

    st5, _, err2 = handle("/matrix", "company_class=llp&incorporation_date=2019-06-01")
    check(st5 == 400 and "company_class" in err2,
          "an unsupported company class refuses rather than guessing")

    # A figure with no financial year cannot be accepted: s.2(85)(ii) is
    # specific about which year it means.
    st6, _, err3 = handle("/matrix", "company_class=private&"
                                     "incorporation_date=2019-06-01&turnover_crore=30")
    check(st6 == 400 and "financial year" in err3,
          "a figure without its financial year is refused")

    # Injection: user input must never reach the page unescaped.
    st7, _, evil = handle("/matrix", "company_class=%3Cscript%3E&"
                                     "incorporation_date=2019-06-01")
    check("<script>" not in evil, "user input is escaped, not injected")
    check("&lt;script&gt;" in evil, "...and appears escaped in the message")

    # s.52(1)(q)(ii): the page must not serve statutory text as its content.
    _, _, full = handle("/matrix", q)
    for phrase in ("Every company shall hold", "paid-up share capital of which",
                   "shall be the quorum"):
        if phrase in full:
            check(False, f"the page served bare statutory text: {phrase!r}")
            break
    else:
        check(True, "the card cites provisions but serves no bare statutory text")

    # No dependency outside the standard library and this repo. Parsed from the
    # module's own import statements rather than searched for as text, because a
    # string search finds the search string itself.
    import ast
    import checker.matrix_view as mod
    tree = ast.parse(open(mod.__file__).read())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    import sys
    third_party = {r for r in roots
                   if r not in sys.stdlib_module_names and r != "checker"}
    check(not third_party,
          f"no third-party import — Stage 1 runs with nothing installed "
          f"({third_party or 'clean'})")
    check("checker" in roots, "...and it does use this repo's own engine")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
