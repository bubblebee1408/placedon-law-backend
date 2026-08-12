"""
The verification ratchet.

The idea comes from the agent-system document and it is the one genuinely new thing in it:

    "If the Verify Agent misses a bug, that check is added to the verification checklist
     permanently."

That is a ratchet — the suite only ever gets stricter, and a bug can be paid for once instead of
repeatedly. This session earned it three times over: the unit tests were green while a browser
found CORS hiding `X-Blocking-Issues`, "Change the details" wiping the committee, and the
"Before you sign this" panel printing below the signature line.

**The checklist is this file, not a document beside it.** A markdown checklist drifts from what
actually runs within about two weeks; nobody notices, and it becomes a record of intentions. So
every check below carries `because=` — the specific incident that bought it. When a new bug gets
through, add a check here with its story attached. Do not delete one because it has never fired;
a check that never fires is a bug that never came back.

The frontend half of this suite lives in the placedon-law-frontend repo, because a check
belongs in the repo that contains its subject. The button-rank check went there with the
button; the epistemic-ramp check stayed here, because that stylesheet is in checker/app.py.
A check that cannot see its subject either crashes or — far worse — skips quietly.

    python3 scripts/verify.py           # everything
    python3 scripts/verify.py --fast    # skip the suites (~2s)

Exit code is 0 for GO, 1 for NO-GO.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSH = ROOT / "corpus/provisions/posh_act_2013.json"

# Generated artefacts. Scanning them finds only what they copied out of real source — the badge
# check failed on .claude/index.json, which stores a summary of every file including the ones
# explaining why we refused the badge. Scanning derived files reports the same fact twice and
# blames the wrong one.
GENERATED = {".claude/index.json", "corpus/.budget.json"}

# A floor, not just a "> 0" guard. An empty run is the obvious failure; the subtle one is a
# check quietly deleted or commented out during a refactor, leaving 24 green checks where 25
# belong. Raise this whenever a check is added on purpose.
#
# It has to scale with the mode: --fast skips the per-module suites and tsc, so the expected
# total is the registry alone. Hard-coding one number broke --fast the moment it was added.
MIN_REGISTRY_CHECKS = 36

SUITES = [
    "applicability.py", "jurisdiction.py", "backend/budget.py",
    "checker/ic_order.py", "checker/verifier.py", "checker/test_unlock.py",
    "checker/board_report.py", "checker/documents.py",
    "checker/provision_graph.py", "checker/epistemic_status.py", "checker/ask_engine.py", "checker/register.py", "checker/path_validity.py", "checker/distress.py",
]

results: list[tuple[bool, str, str]] = []


def check(name: str, *, because: str):
    """Register a check. `because` is the incident that bought it — keep it specific."""
    def wrap(fn):
        try:
            ok, detail = fn()
        except Exception as e:                                    # noqa: BLE001
            ok, detail = False, f"raised {type(e).__name__}: {e}"
        results.append((ok, name, detail if not ok else because))
        return fn
    return wrap


def _read(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8", errors="replace")


def _index(force: bool = False) -> dict:
    """
    The built index, building it if needed.

    Never skip a check because its input is missing. `.claude/index.json` is gitignored, so
    "return True if absent" meant the two index checks asserted nothing on a fresh clone or in
    CI — and printed PASS while doing it.
    """
    sys.path.insert(0, str(ROOT))
    from scripts.index_codebase import build  # noqa: PLC0415
    idx_path = ROOT / ".claude/index.json"
    if force or not idx_path.exists():
        return build()
    return json.loads(idx_path.read_text())


def _uncommented(text: str) -> str:
    """
    Source with comment lines dropped.

    The false-badge check needs this. On its first run it flagged citation-badge.tsx and
    trust-footer.tsx — both of which mention the phrase only to explain why we REFUSED it. A
    check that cannot tell an assertion from an explanation of a refusal punishes the exact
    discipline it exists to protect, and would train us to delete the reasoning.
    """
    out = []
    for line in text.splitlines():
        t = line.lstrip()
        if t.startswith(("*", "//", "#", "/*", "<!--")):
            continue
        out.append(line)
    return "\n".join(out)


# ─────────────────── checks bought by real incidents ───────────────────

@check("budget: daily cap derived from monthly, never asserted",
       because="Two separate specs paired a Rs 150-250/day allowance with a Rs 3,500/month cap. "
               "150x30 and 250x30 both breach it, so every daily check would pass while the "
               "month blew out. The agent-system doc reintroduced it as 'Rs 155/day'.")
def _budget_derived():
    src = _read("backend/budget.py")
    if "MONTHLY_CAP_INR / 30" not in src:
        return False, "DAILY_CAP_INR is not derived from MONTHLY_CAP_INR"
    sys.path.insert(0, str(ROOT))
    from backend.budget import DAILY_CAP_INR, MONTHLY_CAP_INR  # noqa: PLC0415
    # Tolerance of one paisa: round(3500/30, 2) is 116.67, and 116.67 x 30 is 3500.1. The
    # rounding is harmless — what this check exists to catch is a daily figure ASSERTED far
    # above the derived one (the Rs 155 and Rs 250 cases), not a ten-paisa artefact.
    if DAILY_CAP_INR > MONTHLY_CAP_INR / 30 + 0.01:
        return False, f"daily {DAILY_CAP_INR} exceeds monthly/30 = {MONTHLY_CAP_INR / 30:.2f}"
    return True, ""


@check("CORS exposes the headers the browser actually reads",
       because="expose_headers was missing. The browser RECEIVED X-Blocking-Issues and refused "
               "to let JS read it, so cross-origin dev silently reported zero blocking issues "
               "and the unlawful-committee banner never fired. Unit tests could not see it.")
def _cors_expose():
    # Reads the ACTUAL middleware options, not the file text. The first version searched all of
    # app.py for "X-Blocking-Issues" — which also appears at the response-header site, so
    # deleting it from expose_headers left the string present and the check green. A reviewer
    # proved that bypass; string presence is not a proxy for configuration.
    sys.path.insert(0, str(ROOT))
    from starlette.middleware.cors import CORSMiddleware  # noqa: PLC0415

    from checker.app import app                            # noqa: PLC0415
    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            exposed = {h.lower() for h in (mw.kwargs.get("expose_headers") or [])}
            missing = [h for h in ("x-blocking-issues", "content-disposition")
                       if h not in exposed]
            if missing:
                return False, f"CORSMiddleware does not expose: {missing}"
            # The frontend is a separate project; an omitted origin silently kills every
            # document POST while the server-rendered grid keeps loading.
            origins = set(mw.kwargs.get("allow_origins") or [])
            for required in ("http://localhost:3000",
                             "https://placedon-hr-app.vercel.app"):
                if required not in origins:
                    return False, f"allow_origins is missing the frontend origin {required}"
            allowed = {m.upper() for m in (mw.kwargs.get("allow_methods") or [])}
            if not {"GET", "POST"} <= allowed and "*" not in allowed:
                return False, f"allow_methods missing GET/POST: {sorted(allowed)}"
            return True, ""
    return False, "no CORSMiddleware on the app"


@check("the IC-order warning sits above the signature and prints",
       because="A panel titled 'Before you sign this' sat AFTER the rule you sign on, and "
               "carried no-print — so the printed order came out clean while the screen showed "
               "two blocking failures. That is a tool that produces a tidy unlawful order.")
def _warning_placement():
    t = _read("checker/templates/ic_order.html")
    warn, sign = t.find("Before you sign this"), t.find("For and on behalf")
    if warn < 0 or sign < 0:
        return False, "could not locate the warning or the signature block"
    if warn > sign:
        return False, "the warning renders after the signature line"
    block = t[max(0, warn - 300):warn]
    if "no-print" in block:
        return False, "the issues section is still marked no-print"
    return True, ""


@check("Tier 1 is the retrieval closure, not a hand-written list",
       because="The lawyer pack asked for 6 sections and claimed they unlocked the product. "
               "They did not — should_abstain rejects a packet if ANY provision is unverified, "
               "and the flagship question also pulls s.7. Six bought one answer out of twelve.")
def _tier1_derived():
    src = _read("scripts/review_pack.py")
    if "def required_sections" not in src or "retrieve(q)" not in src:
        return False, "review_pack no longer derives Tier 1 from retrieval"
    sys.path.insert(0, str(ROOT))
    from scripts.review_pack import CORE_QUESTIONS, required_sections  # noqa: PLC0415
    from checker import retrieval, verifier                            # noqa: PLC0415
    need = required_sections()
    corpus = [{**p, "verified_by": "test"}
              for p in json.loads(POSH.read_text())["provisions"]
              if p["section_number"] in need]
    by = {p["section_number"]: p for p in corpus}
    for q in CORE_QUESTIONS:
        pkt = [by[n] for n in (retrieval.keyword_route(q) or ()) if n in by]
        if not pkt or verifier.should_abstain(q, pkt, None, state="IN-KA").abstained:
            return False, f"verifying Tier 1 still leaves this abstaining: {q!r}"
    return True, ""


@check("no false verification badge anywhere in the source",
       because="'Verified against India Code & Gazette' appeared in generated specs about seven "
               "times. It is false twice over — nothing is lawyer-verified, and the corpus came "
               "from India Code, not the Gazette. Refused every time; this makes it permanent. "
               "Comments and .md are exempt — the phrase belongs in the record of the refusal.")
def _no_false_badge():
    bad = re.compile(r"verified\s+against\s+india\s+code\s*(&|and)\s*gazette|"
                     r"lawyer[- ]reviewed\s+templates", re.I)
    hits = [str(p.relative_to(ROOT))
            for p in ROOT.rglob("*")
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".html", ".md", ".json"}
            and ".git" not in p.parts and "node_modules" not in p.parts
            and bad.search(_uncommented(p.read_text(encoding="utf-8", errors="replace")))
            and p.name != "verify.py" and p.suffix != ".md"
            and str(p.relative_to(ROOT)) not in GENERATED]
    return (not hits), f"false verification claim in: {hits}"


@check("s.4 is never cited as the source of the ten-employee threshold",
       because="'Every employer employing 10 or more employees shall constitute an IC' is not "
               "in the PoSH Act. It appeared in the master spec, two scaffold files, and our own "
               "shipped rules.py comment. Only the verbatim corpus ever caught it.")
def _no_s4_threshold():
    # Runs assess() and reads the citation it actually emits. The first version only grepped
    # rules.py and the corpus, and never touched checker/assess.py — the sole place the
    # threshold finding is cited. Flipping CITE_THRESHOLD to CITE_S4 there, which IS the
    # original incident, left this check green. A reviewer proved it.
    src = _read("checker/rules.py")
    if "s.4 states no threshold" not in src:
        return False, "rules.py no longer records that s.4 contains no threshold"

    body = json.loads(POSH.read_text())["provisions"]
    s4 = next(p for p in body if p["section_number"] == 4)
    if re.search(r"\bten\b|\b10\b", s4["text_display"], re.I):
        return False, "s.4 text now contains a ten — re-read it, the corpus may have changed"

    sys.path.insert(0, str(ROOT))
    from datetime import date                 # noqa: PLC0415

    from applicability import CompanyProfile   # noqa: PLC0415

    from checker.assess import assess          # noqa: PLC0415
    # 8 workers: below the inferred threshold, so the threshold finding fires.
    profile = CompanyProfile(state="IN-KA", employee_count=8, establishment_type="it_ites",
                             entity_type="pvt_ltd", as_of=date(2026, 8, 8),
                             contractor_count=0, districts=["IN-KA-BLR"])
    findings, _ = assess(profile, has_ic=False, ic_constituted_on=None,
                         has_policy=False, filed_return=False)
    # Match the CLAIM, not one phrasing of it. The first version required the word "threshold"
    # in the text, so the sentence a later spec proposed verbatim —
    #   "Section 4(1) of the PoSH Act, 2013 requires an Internal Committee at workplaces with
    #    10 or more employees"
    # — sailed straight through, cited to s.4, in user-facing prose. That IS the L-1 fabrication.
    # Any finding that pairs a headcount with an s.4 citation is the thing to catch.
    headcount = re.compile(r"\b(?:ten|10)\b[^.]{0,60}\b(?:employee|worker|person|people|staff)",
                           re.I)
    for f in findings:
        blob = f"{f.title} {f.detail}"
        cite = f.citation.lower().replace(" ", "")
        if not headcount.search(blob):
            continue
        if cite.startswith("s.4") and "inferred" not in cite:
            return False, (f"a headcount claim is cited to {f.citation!r}. Section 4 contains no "
                           f"number — this is the fabrication in LESSONS L-1, in prose a user "
                           f"reads. Cite s.6 and label it inferred.")

    # Also scan the source, because assess() only exercises the branches one profile reaches.
    # A fabricated sentence sitting in a branch this profile does not hit is still shipped.
    for f in ("checker/assess.py", "checker/rules.py"):
        for line in _uncommented(_read(f)).splitlines():
            if headcount.search(line) and re.search(r"section\s*4|s\.4", line, re.I):
                return False, (f"{f}: a headcount and an s.4 reference share a line — "
                               f"{line.strip()[:90]!r}. Section 4 states no number.")
    return True, ""


@check("documents never claim verification the corpus does not have",
       because="Every generated document states the real verification state. If someone hardcodes "
               "a reviewer name while the corpus is unverified, the document lies on paper that "
               "gets signed and filed.")
def _verification_honest():
    sys.path.insert(0, str(ROOT))
    from checker.documents import generate_document  # noqa: PLC0415
    from checker.ic_order import Member              # noqa: PLC0415
    provisions = json.loads(POSH.read_text())["provisions"]
    any_verified = any(p.get("verified_by") for p in provisions)
    html = generate_document(
        "ic_order", {"name": "Verify Check Pvt Ltd"},
        {"members": [{"name": "Ms A", "is_woman": True, "source": "employee",
                      "senior_level": True, "presiding": True},
                     {"name": "Ms B", "is_woman": True, "source": "employee"},
                     {"name": "Mr C", "is_woman": False, "source": "employee"},
                     {"name": "Ms D", "is_woman": True, "source": "external_ngo"}]}).html
    claims_review = "Sections reviewed by" in html
    if claims_review != any_verified:
        return False, ("document claims review but corpus is unverified" if claims_review
                       else "corpus is verified but the document still denies it")
    return True, ""


@check("the MCA corpus still admits it is a secondary source",
       because="The Companies Act text was read off a legal-news reproduction, not the Gazette. "
               "Every document built on it says so. If that warning is ever quietly dropped, the "
               "documents start overstating their own provenance.")
def _mca_provenance():
    mca = ROOT / "corpus/provisions/companies_accounts_rules_2014.json"
    if not mca.exists():
        return True, ""
    d = json.loads(mca.read_text())
    if "PROVENANCE_WARNING" not in d["instrument"]:
        return False, "PROVENANCE_WARNING removed while source_sha256 is still absent"
    if d["instrument"].get("source_sha256"):
        return True, ""            # gazette ingested; warning may go (M-4)
    if "quotation of a quotation" not in _read("checker/templates/board_report.html"):
        return False, "board_report.html no longer discloses the weaker MCA provenance"
    return True, ""


@check("agent search ranks the implementation above the documentation",
       because="'how did we implement rate limiting' returned scripts/search_memory.py, whose "
               "docstring quotes that phrase as an example, above checker/ratelimit.py which "
               "implements it. A document ABOUT a query beat the document ANSWERING it. Fixed "
               "by BM25F with identity (path + symbols) weighted 6x over prose.")
def _search_ranks_implementation():
    # BUILD it if absent rather than skipping. .claude/index.json is gitignored, so on any
    # fresh clone the old `return True` fired and this check asserted nothing at all — while
    # still printing PASS for the incident it is named after. Proven by a reviewer.
    from scripts.search_memory import search   # noqa: PLC0415
    idx = _index()
    for query, want in (("how did we implement rate limiting", "checker/ratelimit.py"),
                        ("board report three numbers", "checker/board_report.py"),
                        ("budget daily cap monthly", "backend/budget.py")):
        hits = search(query, idx, top_k=1)
        if not hits or hits[0][1]["path"] != want:
            got = hits[0][1]["path"] if hits else "(nothing)"
            return False, f"{query!r} ranked {got}, expected {want}"
    return True, ""


@check("the search index does not index itself",
       because="index.json contains every symbol in the repo, so it ranked first for 'who "
               "validates the internal committee'. A search tool returning its own index is "
               "noise that grows on every rebuild.")
def _index_excludes_itself():
    # Rebuilds from current source rather than inspecting a stale artifact, and asserts on the
    # result rather than on the presence of a substring. Deleting the `rel in SKIP_FILES` clause
    # while leaving the SKIP_FILES definition in place defeated the old string check.
    paths = {d["path"] for d in _index(force=True)["docs"]}
    if ".claude/index.json" in paths:
        return False, "the freshly built index contains itself"
    for leaked in ("node_modules", "corpus/provisions/"):
        if any(leaked in p for p in paths):
            return False, f"index includes {leaked!r}, which SKIP logic should exclude"
    return True, ""


@check("command files are real files, not self-referential symlinks",
       because="Creating uppercase aliases with `ln -sf start.md START.md` DESTROYED all four "
               "command files. macOS APFS is case-insensitive, so START.md and start.md are the "
               "same path and each link pointed at itself — 'too many levels of symbolic "
               "links'. Recovered from git. Aliases were never needed: a case-insensitive "
               "filesystem already resolves /START to start.md.")
def _commands_readable():
    d = ROOT / ".claude/commands"
    if not d.is_dir():
        return False, ".claude/commands is missing"
    broken = []
    for f in sorted(d.glob("*.md")):
        try:
            if not f.read_text(encoding="utf-8").strip():
                broken.append(f"{f.name} (empty)")
        except OSError as e:
            broken.append(f"{f.name} ({e.strerror})")
    required = {"start.md", "build.md", "fix.md", "research.md", "loop.md"}
    missing = sorted(required - {f.name for f in d.glob("*.md")})
    if missing:
        return False, f"missing commands: {missing}"
    return (not broken), f"unreadable: {broken}"


@check("the Vercel wrapper routes every API path in production",
       because="api/index.py restored the real path from __p and then the mount-prefix fallback "
               "stripped it AGAIN: /api/diagnose became /diagnose, which is not a route. Every "
               "JSON endpoint 404'd in production for a day while GET / and POST /check worked, "
               "because those have no /api prefix to lose. Local uvicorn never touches this "
               "wrapper, so no test could see it.")
def _vercel_wrapper_routes():
    import asyncio                                   # noqa: PLC0415
    sys.path.insert(0, str(ROOT))
    from api.index import app                        # noqa: PLC0415

    payload = json.dumps({"employees": 14, "contractors": 0, "state": "IN-KA",
                          "district": "IN-KA-BLR", "industry": "it_ites", "has_policy": "no",
                          "has_ic": "no", "filed_return": "no"}).encode()

    async def call(path, qs=b"", method="GET", body=b""):
        scope = {"type": "http", "method": method, "path": path, "query_string": qs,
                 "headers": [(b"content-type", b"application/json")], "root_path": "",
                 "scheme": "https", "server": ("x", 443), "client": ("1.2.3.4", 1),
                 "http_version": "1.1", "asgi": {"version": "3.0"}}
        sent = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(m):
            sent.append(m)

        await app(scope, receive, send)
        return next((m["status"] for m in sent if m["type"] == "http.response.start"), None)

    cases = [
        ("/api/index", b"__p=%2Fapi%2Fdiagnose", "POST", payload, "rewritten /api/diagnose"),
        ("/api/index", b"__p=%2Fapi%2Fgenerate%2Ftemplates", "GET", b"", "rewritten templates"),
        ("/api/index", b"__p=%2F", "GET", b"", "rewritten root"),
        ("/api/index", b"", "GET", b"", "bare mount point"),
        ("/api", b"", "GET", b"", "bare /api mount point"),
        ("/api/index", b"__p=%2Fapi%2Findex", "GET", b"", "chained rewrite: __p is the mount point"),
        ("/api/diagnose", b"", "POST", payload, "direct, no __p"),
        ("/", b"", "GET", b"", "bare root"),
    ]
    for path, qs, method, body, label in cases:
        got = asyncio.run(call(path, qs, method, body))
        if got != 200:
            return False, f"{label}: {method} {path} returned {got}, expected 200"
    return True, ""


@check("every third-party import in shipped code is pinned in requirements.txt",
       because="jinja2 was imported by checker/app.py and absent from requirements.txt. It was "
               "installed locally so every test passed, setup.sh reported 'deps present', and "
               "the FIRST production deploy returned 500 on every route: ModuleNotFoundError. "
               "A dependency that exists only on the author's laptop is an outage.")
def _imports_pinned():
    import ast                                       # noqa: PLC0415
    stdlib = set(sys.stdlib_module_names)
    local = {"checker", "backend", "applicability", "jurisdiction", "scripts", "api", "shared"}
    # Distribution name -> import name, where they differ.
    alias = {"python-multipart": "multipart", "jinja2": "jinja2"}

    pinned = set()
    for f in ("requirements.txt", "requirements-dev.txt"):
        p = ROOT / f
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                name = re.split(r"[=<>~!\[;]", line, maxsplit=1)[0].strip().lower()
                pinned.add(alias.get(name, name).lower())
    # starlette and pydantic arrive with fastapi; treat them as satisfied by it.
    if "fastapi" in pinned:
        pinned |= {"starlette", "pydantic"}

    missing: dict[str, str] = {}
    for py in ROOT.rglob("*.py"):
        if any(x in py.parts for x in (".git", "node_modules", "__pycache__", ".next", ".venv")):
            continue
        if py.parts[len(ROOT.parts)] == "scripts":      # tooling, not shipped
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m and m not in stdlib and m not in local and m.lower() not in pinned:
                    missing.setdefault(m, str(py.relative_to(ROOT)))
    if missing:
        return False, "; ".join(f"{m} (imported by {f})" for m, f in sorted(missing.items()))
    return True, ""


@check("edge-case questions abstain even on a verified corpus",
       because="Testing the POST-verification state found the product would confidently answer "
               "'do interns count toward the ten?' the moment a lawyer signed off — from s.2(f), "
               "a definition that never mentions interns. The gate opening is exactly when that "
               "fires: the day the product becomes useful is the day it starts answering the "
               "questions it must refuse. The first fix used substring matching and broke the "
               "flagship question, because 'Internal Committee' contains 'intern'.")
def _edge_cases_abstain():
    sys.path.insert(0, str(ROOT))
    from checker import retrieval, verifier            # noqa: PLC0415
    corpus = {p["section_number"]: {**p, "verified_by": "check"}
              for p in json.loads(POSH.read_text())["provisions"]}
    cases = [
        ("do interns count toward the ten?", True),
        ("do contractors count toward the threshold?", True),
        ("we operate in three states, which rules apply?", True),
        ("are remote employees covered?", True),
        ("do I need an Internal Committee?", False),      # must NOT trip on "intern"
        ("what is the penalty for not having an IC?", False),
    ]
    for q, want_abstain in cases:
        pkt = [corpus[n] for n in (retrieval.keyword_route(q) or ()) if n in corpus]
        got = verifier.should_abstain(q, pkt, None, state="IN-KA").abstained
        if got != want_abstain:
            return False, (f"{q!r} → {'abstain' if got else 'answer'}, expected "
                           f"{'abstain' if want_abstain else 'answer'}")
    return True, ""


@check("output guards hold against real model text, not hand-written examples",
       because="The LLM path had never executed. Running it against a local llama3 for the first "
               "time produced three passes that should have been blocks: 'Action: You should "
               "constitute an Internal Complaints Committee' (advice, forbidden by our own "
               "prompt), an answer citing nothing, and fabricated sub-clauses like s.26(9)(z) "
               "which resolved because only the base section was validated. Every prior test "
               "used strings I wrote to pass.")
def _output_guards():
    sys.path.insert(0, str(ROOT))
    from checker import verifier                          # noqa: PLC0415
    prov = {p["section_number"]: {**p, "verified_by": "check"}
            for p in json.loads(POSH.read_text())["provisions"]}
    packet = [prov[4], prov[26]]
    cases = [
        ("The fine may extend to fifty thousand rupees [s.26(1)(a)].", False, "real sub-clause"),
        ("The fine may extend to fifty thousand rupees [s.26(9)(z)].", True, "fake sub-clause"),
        ("Every employer shall constitute a Committee [s.4(99)].", True, "fake sub-clause"),
        ("Every employer shall constitute a Committee [s.4]. You should constitute one.",
         True, "advice language"),
        ("The Act applies regardless of the number of employees.", True, "no citation"),
        ("I don't have verified information on this.", False, "honest refusal"),
    ]
    for answer, want_abstain, label in cases:
        got = verifier.should_abstain("q", packet, answer).abstained
        if got != want_abstain:
            return False, (f"{label}: {'abstained' if got else 'passed'}, expected "
                           f"{'abstain' if want_abstain else 'pass'}")
    return True, ""


@check("no Rule is secretly an Act section",
       because="The reproduction carries the Act and the Rules, both numbered 'N. Heading.-'. "
               "The first ingest ran over the whole document and produced 'Rule 4' byte-identical "
               "to Act s.4 — the retriever would have cited 'Rule 4, PoSH Rules 2013' for text "
               "that is Section 4 of the Act. Nothing looked wrong; it was caught only by "
               "noticing two character counts exactly matched the Act's.")
def _rules_are_not_the_act():
    rules_path = ROOT / "corpus/provisions/posh_rules_2013.json"
    if not rules_path.exists():
        return True, ""
    act = json.loads(POSH.read_text())["provisions"]
    by_hash = {p["text_sha256"]: p["citation"] for p in act}
    by_norm = {" ".join(p["text_display"].split()): p["citation"] for p in act}
    rules = json.loads(rules_path.read_text())["provisions"]
    if not rules:
        return False, "the Rules corpus is empty"
    for r in rules:
        norm = " ".join(r["text_display"].split())
        clash = by_hash.get(r["text_sha256"]) or by_norm.get(norm)
        if clash:
            return False, f"{r['citation']} is the same text as {clash}"
    if len(rules) != 14:
        return False, f"{len(rules)} rules ingested; the PoSH Rules 2013 have exactly 14"
    return True, ""


@check("the lawyer pack is dependency-closed",
       because="Tier 1 was the retrieval closure only — 12 sections. Seven of them still rested "
               "on s.13, s.15 and s.16, which the pack never asked anyone to look at. A verified "
               "s.26 over an unverified s.4 leaves the penalty claim on unverified ground, and "
               "nothing tracked that until provision_graph extracted the statute's own "
               "cross-references.")
def _pack_dependency_closed():
    sys.path.insert(0, str(ROOT))
    from checker.provision_graph import ProvisionGraph      # noqa: PLC0415
    from scripts.review_pack import required_sections       # noqa: PLC0415

    need = required_sections()
    provisions = json.loads(POSH.read_text())["provisions"]
    simulated = [{**p, "verified_by": "pending" if p["section_number"] in need else None}
                 for p in provisions]
    graph = ProvisionGraph(simulated)
    leaks = sorted({b for n in need for b in graph.blocked_by(n)} - need)
    if leaks:
        return False, (f"sections {leaks} are depended upon but not in the pack — verifying "
                       f"Tier 1 would still leave claims resting on them")
    return True, ""


@check("epistemic status is ordinal — no probability anywhere in the engine",
       because="An adversarial audit of the nine papers behind the proposed design found the "
               "calibration citation unusable twice over: an LLM writing '0.94' has no logits to "
               "scale, and at n=20 the observable resolution IS 0.05, so an ECE<0.05 target sits "
               "below the instrument. The noise floor for a PERFECTLY calibrated model at p=0.9 "
               "is 0.0535 — it fails by construction. Distinguishing 0.94 from 0.93 needs ~2,256 "
               "labels per provision. We had built a correct Bayesian version anyway; correct "
               "maths on invented weights is still invented. Replaced by a weakest-link lattice.")
def _status_is_ordinal():
    sys.path.insert(0, str(ROOT))
    from checker.epistemic_status import Claim, Ground, Status   # noqa: PLC0415

    if not (Status.SILENT < Status.UNSUPPORTED < Status.UNCHECKED < Status.SECONDARY
            < Status.INFERRED < Status.VERIFIED < Status.QUOTED):
        return False, "the lattice is no longer totally ordered"
    if [s.name for s in Status if s.answerable] != ["VERIFIED", "QUOTED"]:
        return False, "the answerable threshold moved below VERIFIED"

    mixed = Claim("x", [Ground(Status.QUOTED, "strong", "t"),
                        Ground(Status.UNCHECKED, "weak", "t")])
    if mixed.status is not Status.UNCHECKED:
        return False, f"weakest link not enforced: got {mixed.status.name}"

    # No probability may creep back in. Floats in the engine mean invented weights returned.
    body = _uncommented((ROOT / "checker/epistemic_status.py").read_text())
    body = re.sub(r'""".*?"""', "", body, flags=re.S)
    floats = re.findall(r"\b\d+\.\d+\b", body)
    if floats:
        return False, f"numeric weights reappeared in the engine: {floats[:5]}"
    return True, ""


@check("no confidence number is ever shown to a user",
       because="Displaying '94% confident' needs a labelled validation set; we have zero "
               "scenarios, and the frontier on the nearest published task (Indian statute "
               "identification) is 64.58 macro-F1. Dahl et al., Journal of Legal Analysis 2024, "
               "measured 58-88% legal hallucination and found LLM confidence ANTI-correlated "
               "with reliability. A number here would be worse than no number.")
def _belief_not_displayed():
    import re                                               # noqa: PLC0415
    leaks: list[str] = []
    missing: list[str] = []
    scanned = 0
    for d in ("checker/templates",):
        p = ROOT / d
        if not p.is_dir():
            missing.append(d)
            continue
        scanned += 1
        for f in list(p.rglob("*.html")) + list(p.rglob("*.tsx")):
            body = _uncommented(f.read_text(encoding="utf-8", errors="replace"))
            if re.search(r"posterior|belief_state|confidence_tier|entropy", body):
                leaks.append(str(f.relative_to(ROOT)))
    if not scanned:
        # The original scanned three directories and skipped any that were absent. After
        # the repo split none of them existed here, and it reported PASS having read no
        # files at all — the exact vacuous green this suite exists to prevent.
        return False, f"scanned no backend directory at all; missing {missing}"
    return (not leaks), f"belief internals surfaced in: {leaks}"


@check("citations resolve by section NUMBER, never by string prefix",
       because="verify_citations matched with `base.startswith(b)`, so \"s.27\".startswith(\"s.2\") "
               "was True. With s.2 in the packet, EVERY fabricated citation resolved cleanly — "
               "s.21, s.22, s.26, s.27, even s.199. The citation enforcer, the component this "
               "product's trustworthiness rests on, failed open on every case it exists to catch.")
def _citations_by_number():
    sys.path.insert(0, str(ROOT))
    from checker import verifier                             # noqa: PLC0415
    prov = {p["section_number"]: p for p in json.loads(POSH.read_text())["provisions"]}
    packet = [prov[2], prov[19]]
    for cite, want_caught in (("[s.27]", True), ("[s.21]", True), ("[s.26]", True),
                              ("[s.199]", True), ("[s.2]", False), ("[s.19]", False),
                              ("[s.19(b)]", False)):
        caught = bool(verifier.verify_citations(f"text {cite}", packet))
        if caught != want_caught:
            return False, (f"{cite} {'was caught' if caught else 'passed'}, expected "
                           f"{'caught' if want_caught else 'passed'}")
    return True, ""


@check("off-topic questions retrieve nothing rather than weak matches",
       because="The term-overlap scan returned three sections for 'What is the GST rate on "
               "chocolate?'. Measured across the corpus, off-topic questions top out at score 1 "
               "— one common word — while on-topic score 2 to 8. Three weakly-matched sections "
               "are worse than none, because a model would then explain them. Also 'file' alone "
               "routed 'how do I file income tax?' to the PoSH annual return.")
def _offtopic_retrieves_nothing():
    sys.path.insert(0, str(ROOT))
    from checker import retrieval                            # noqa: PLC0415
    for q in ("What is the GST rate on chocolate?", "How do I renew my passport?",
              "What is the capital of France?", "How do I file income tax?"):
        hits, _ = retrieval.retrieve(q)
        if hits:
            return False, f"{q!r} retrieved {[h['citation'] for h in hits]}"
    for q in ("What must the employer display at the workplace?",
              "What is the penalty for non-compliance?", "Who can be on the Internal Committee?",
              "When is the annual return due?"):
        if not retrieval.retrieve(q)[0]:
            return False, f"on-topic question retrieved nothing: {q!r}"
    return True, ""


@check("a deduction never reaches the language model",
       because="'Do I need an Internal Committee?' is computed from the Act and the company's "
               "own headcount. Routing it to a model asks a probabilistic system to redo settled "
               "arithmetic, which is how a wrong answer gets a confident voice.")
def _deductions_routed_to_code():
    sys.path.insert(0, str(ROOT))
    from checker.ask_engine import AskEngine                 # noqa: PLC0415
    called = []

    class R:
        text, cost_inr, degraded = "should not run", 0.0, False

    prov = [{**p, "verified_by": "check"} for p in json.loads(POSH.read_text())["provisions"]]
    eng = AskEngine(provisions=prov,
                    generate=lambda q, p, c: (called.append(q), R())[1])
    for q in ("Do I need an Internal Committee?", "Does PoSH apply to us?",
              "Are we required to have a policy?", "Is it mandatory for a 12-person company?"):
        if eng.ask(q).route != "deterministic":
            return False, f"{q!r} was not routed to the rules engine"
    if called:
        return False, f"the model was called for a deduction: {called}"
    if eng.ask("What does section 19 require?").route != "corpus":
        return False, "an exposition question was wrongly routed away from the corpus"
    return True, ""


@check("corpus text is unaltered — raw hash recomputes and display text re-derives",
       because="text_sha256 hashes `text`, the raw pdfplumber extraction. But `text_display` is "
               "what we quote, cite, and print into documents a company signs, and NOTHING "
               "covered it. A corrupted display string — a dropped 'not', a changed figure — "
               "would have passed every check while the raw hash stayed valid. Found by "
               "verifying the PDF by hand and noticing the per-provision hash would not "
               "recompute over the field we actually show.")
def _corpus_text_unaltered():
    sys.path.insert(0, str(ROOT))
    import hashlib                                          # noqa: PLC0415

    from scripts.ingest_posh import join_wraps              # noqa: PLC0415
    bad: list[str] = []
    for p in json.loads(POSH.read_text())["provisions"]:
        cite = p.get("citation", "?")
        if hashlib.sha256(p["text"].encode()).hexdigest() != p["text_sha256"]:
            bad.append(f"{cite}: raw hash does not recompute")
        if join_wraps(p["text"]) != p["text_display"]:
            bad.append(f"{cite}: text_display is not derivable from text")
    return (not bad), "; ".join(bad[:4])


@check("footnote apparatus is never treated as statutory text",
       because="A section spanning a page break swallows the footnotes printed at the foot of "
               "that page. Three provisions carried them inside text_display — the field the "
               "number-checker compares model output against — so a model writing '6-5-2016' or "
               "'2016' against s.8 was ACCEPTED, leaning on 'Subs. by Act 23 of 2016 … (w.e.f. "
               "6-5-2016)'. That is a citation of an amendment, not a statement of law.")
def _no_apparatus_in_source():
    sys.path.insert(0, str(ROOT))
    from checker import verifier                              # noqa: PLC0415
    prov = {p["section_number"]: p for p in json.loads(POSH.read_text())["provisions"]}

    missing = [p["citation"] for p in prov.values() if not p.get("text_statutory")]
    if missing:
        return False, f"text_statutory absent on: {missing[:4]}"

    fn = re.compile(r"\d+\.\s*(?:Subs|Ins|Omitted|Cl)\.\s*by", re.I)
    dirty = [p["citation"] for p in prov.values() if fn.search(p["text_statutory"])]
    if dirty:
        return False, f"apparatus still present in text_statutory: {dirty}"

    # Footnote-only figures must not be citable.
    for probe in ("6-5-2016", "2016", "23"):
        if not verifier.check_hallucination(f"The figure is {probe}.", [prov[8]]):
            return False, f"a model could still cite {probe!r} from s.8's footnote"
    # Real statutory words must still pass.
    for n, probe in ((26, "fifty"), (11, "ninety"), (4, "three")):
        if verifier.check_hallucination(f"The text says {probe}.", [prov[n]]):
            return False, f"a genuine figure was rejected: {probe!r} in s.{n}"
    return True, ""


@check("every sub-section reproduces verbatim from its parent",
       because="Sub-sections are verbatim slices of already-verified text. If one drifts from "
               "its parent — a re-split against changed text, a hand edit — the pack would show "
               "a lawyer a clause that is not in the Act, and its hash would still look fine "
               "because it hashes itself.")
def _subsections_reproduce():
    doc = json.loads(POSH.read_text())
    subs = doc.get("subsections", [])
    if not subs:
        return True, ""                       # optional data; absent is not a failure
    import hashlib                            # noqa: PLC0415
    parents = {p["section_number"]: " ".join(p["text_statutory"].split())
               for p in doc["provisions"]}
    for s in subs:
        body = parents.get(s["section_number"])
        if body is None:
            return False, f"{s['citation']}: parent s.{s['section_number']} is not in the corpus"
        text = " ".join(s["text_statutory"].split())
        if text not in body:
            return False, f"{s['citation']}: does not reproduce from its parent"
        if hashlib.sha256(s["text_statutory"].encode()).hexdigest() != s["text_sha256"]:
            return False, f"{s['citation']}: hash does not recompute"
        if s.get("verified_by") is not None:
            return False, (f"{s['citation']}: verified_by is set. Splitting a transcription is "
                           f"not a legal opinion; only a lawyer moves this field.")
    return True, ""


@check("the pack shows clauses where we have them, not whole-section blobs",
       because="Sub-sections were added to the corpus and NOTHING read them — the pack still "
               "printed the full 5,570-character s.2. The reduction was real in the data and "
               "absent from the artifact a lawyer actually receives, which is the only place it "
               "counts. Dead data is the same mistake as an unwired lattice.")
def _pack_uses_subsections():
    pack = ROOT / "corpus/review_pack.html"
    if not pack.exists():
        return True, ""                       # generated on demand
    doc = json.loads(POSH.read_text())
    subs = doc.get("subsections", [])
    if not subs:
        return True, ""
    body = " ".join(pack.read_text().split())
    parents = {s["section_number"] for s in subs}
    for p in doc["provisions"]:
        if p["section_number"] not in parents:
            continue
        blob = " ".join(p["text_display"].split())[:80]
        if blob in body:
            return False, (f"{p['citation']}: the pack still prints the whole section although "
                           f"we hold its clauses")
    missing = [s["citation"] for s in subs if s["citation"] not in pack.read_text()]
    if missing:
        return False, f"clauses held but not shown in the pack: {missing}"
    return True, ""


@check("the epistemic ramp is legible without colour",
       because="The seven lattice states were first shipped hue-coded — green for VERIFIED, amber "
               "for INFERRED, red for UNSUPPORTED. That collapses a seven-state ORDER into three "
               "CATEGORIES: a reader can see 'bad' but not that SECONDARY outranks UNCHECKED, and "
               "the ordering is the entire point of the lattice. It also fails for the ~8% of "
               "men with red-green deficiency, and it competes with the severity hues, which are "
               "a different axis on the same page. The ramp now runs on border weight and fill. "
               "This check refuses a return to hue: at most one chromatic family may appear "
               "across all seven, and stripping colour entirely must still leave seven distinct "
               "states.")
def _ramp_not_hue_coded():
    import sys                                                 # noqa: PLC0415
    sys.path.insert(0, str(ROOT))
    from checker.app import CSS                                # noqa: PLC0415
    from checker.epistemic_status import Status                # noqa: PLC0415

    root = re.search(r":root\{(.*?)\}", CSS, re.S)
    if not root:
        return False, "no :root palette block in the stylesheet"
    palette = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", root.group(1)))

    # Chromatic by measurement, not by a hardcoded list, so a palette addition is classified
    # automatically. The tints (--crit-bg and friends) are pale enough to measure as neutral,
    # so a token inherits its base family's verdict: --good-bg is green even at 6% spread.
    def spread(hex_: str) -> int:
        r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
        return max(r, g, b) - min(r, g, b)

    # The warm paper neutrals top out at 25; the severity hues start at 41.
    families = {k[2:].removesuffix("-bg") for k, v in palette.items() if spread(v) > 35}

    rules = {}
    for state in Status:
        name = state.name.lower()
        found = re.findall(rf"\.status\.{name}(?:::[a-z]+)?\{{(.*?)\}}", CSS, re.S)
        if not found:
            return False, (f"Status.{state.name} has no .status.{name} rule. An unstyled state "
                           f"renders as unmarked prose and drops out of the order.")
        rules[state.name] = " ".join(found)

    used = {f for f in families
            for body in rules.values() if f"--{f}" in body}
    if len(used) > 1:
        return False, (f"the ramp draws on {len(used)} chromatic families ({sorted(used)}). More "
                       f"than one means hue is carrying the ordering again.")

    # Strip every colour channel and the seven must still be seven.
    stripped = {}
    for name, body in rules.items():
        decls = [d for d in body.split(";")
                 if d.strip() and d.split(":")[0].strip() not in
                 {"color", "background", "background-color", "border-color",
                  "text-decoration-color"}]
        flat = re.sub(r"var\(--[\w-]+\)|#[0-9a-fA-F]{3,6}", "", ";".join(decls))
        stripped[name] = " ".join(flat.split())

    seen = {}
    for name, sig in stripped.items():
        if sig in seen:
            return False, (f"{seen[sig]} and {name} are indistinguishable once colour is removed. "
                           f"Two rungs of an ordinal ladder that differ only in hue are one rung.")
        seen[sig] = name
    return True, ""


# Codes in use across applicability.py, jurisdiction.py, frontend checker-form and
# shared/types.ts. The first register build generated IN-KA-BENGA for Bengaluru Urban
# because Bengaluru Rural sorts first and took the letters.
_ESTABLISHED_CODES = {"Bengaluru Urban": "IN-KA-BLR"}


@check("the notified-date register never holds a date without the reply it came from",
       because="This register is the one asset no competitor has: what each District Officer "
               "ACTUALLY notified as the PoSH annual-return date. Its entire value is that every "
               "entry is backed by the officer's own words. The failure mode is obvious and fatal "
               "-- somebody reads '31 January' on a compliance blog, types it into a district row "
               "to fill a gap, and the register becomes the same folklore it exists to replace, "
               "except now with our name on it. It would also be undetectable: a plausible date in "
               "a plausible row. So the rule is the same one verified_by enforces on the corpus -- "
               "a claim is recordable only with its source attached -- and 'we asked and got no "
               "reply' is a first-class publishable value, not a gap to be filled.")
def _register_dates_have_sources():
    reg = ROOT / "corpus/reference/notified_dates.json"
    if not reg.exists():
        return False, ("corpus/reference/notified_dates.json is missing. This check does not skip "
                       "when its input is absent -- that is how two index checks silently asserted "
                       "nothing. Run scripts/build_register.py.")
    doc = json.loads(reg.read_text())
    rows = doc.get("districts", [])
    if not rows:
        return False, "register has no district rows"

    officers = {o["district"] for o in
                json.loads((ROOT / "corpus/reference/district_officers.json").read_text())["officers"]}
    VALID = {"UNASKED", "ASKED", "DATE_NOTIFIED", "NONE_NOTIFIED", "NO_REPLY"}

    for r in rows:
        d = r.get("district", "?")
        st = r.get("status")
        if st not in VALID:
            return False, f"{d}: status {st!r} is not one of {sorted(VALID)}"
        if d not in officers:
            return False, (f"{d}: not in the District Officer directory. Rows may only exist for "
                           f"districts we actually hold an officer for.")

        has_date  = bool(r.get("notified_date"))
        has_reply = bool((r.get("reply_verbatim") or "").strip())

        # The rule this check exists for.
        if has_date and not has_reply:
            return False, (f"{d}: notified_date={r['notified_date']!r} with no reply_verbatim. A "
                           f"date without the words it came from is folklore. Delete it or attach "
                           f"the reply.")
        if has_date and not r.get("replied_on"):
            return False, f"{d}: has a notified_date but no replied_on"
        if has_date and st != "DATE_NOTIFIED":
            return False, f"{d}: carries a date but status is {st!r}"
        # "No date is notified here" is itself a finding, and it needs a source too.
        if st == "NONE_NOTIFIED" and not has_reply:
            return False, (f"{d}: status NONE_NOTIFIED asserts a fact about the district. It needs "
                           f"the reply that says so.")
        if st in {"ASKED", "NO_REPLY", "DATE_NOTIFIED", "NONE_NOTIFIED"} and not r.get("asked_on"):
            return False, f"{d}: status {st} but no asked_on date"
        if st == "NO_REPLY" and has_date:
            return False, f"{d}: NO_REPLY cannot carry a date"

        # No national or state default may hide in here. There IS no national date; that is the
        # whole finding. A row at 'IN' or 'IN-KA' would reintroduce the 31 January fabrication
        # through the back door.
        # Codes must agree with the rest of the system, not merely be unique among themselves.
        if r["district"] in _ESTABLISHED_CODES and r["jurisdiction"] != _ESTABLISHED_CODES[r["district"]]:
            return False, (f"{d}: register uses {r['jurisdiction']!r} but applicability.py, "
                           f"jurisdiction.py and the frontend use "
                           f"{_ESTABLISHED_CODES[r['district']]!r}. A register nothing can query "
                           f"is worse than no register, because it looks like it works.")

        j = r.get("jurisdiction", "")
        if len(j.split("-")) != 3:
            return False, (f"{d}: jurisdiction {j!r} is not district-level. The register is "
                           f"district-scoped by construction -- a state or national row would be a "
                           f"default, and defaulting is the bug.")
    return True, ""


@check("no hand-maintained district list may disagree with the register",
       because="There were three lists: checker/rules.py, the frontend's checker-form.tsx, and "
               "the register itself. The first two each held the same hand-written pair and each "
               "carried a comment saying they were the districts we could speak to -- true when "
               "written, false the moment the register existed. One of the pair was Gurugram, "
               "which the register has never held, so selecting it produced a lookup that raised, "
               "was caught, and degraded silently to no district note at all. A picker that "
               "offers a district we cannot speak to is worse than a short picker, and this is "
               "invisible in review because each list looks reasonable on its own.")
def _district_lists_agree():
    sys.path.insert(0, str(ROOT))
    from checker import register                              # noqa: PLC0415
    from checker.rules import DISTRICTS                       # noqa: PLC0415

    known = set(register._rows())
    offered = {code for opts in DISTRICTS.values() for code, _ in opts if code}
    stray = sorted(offered - known)
    if stray:
        return False, (f"the form offers districts the register does not hold: {stray}. Either "
                       f"add them to the register or stop offering them.")
    if not known:
        return True, ""
    ka = {c for c, _ in DISTRICTS.get("IN-KA", []) if c}
    missing = sorted({c for c in known if c.startswith("IN-KA-")} - ka)
    if missing:
        return False, f"register holds Karnataka districts the form does not offer: {missing[:5]}"
    # The refusable fallback must survive. Removing it turns "a district we have not asked" into
    # a state-level answer, which jurisdiction.py exists to prevent.
    for state, opts in DISTRICTS.items():
        if not any(code == "" for code, _ in opts):
            return False, (f"{state} has no 'Elsewhere in the state' option. Without it a user "
                           f"from an unasked district must pick a district we did ask, and the "
                           f"answer becomes wrong rather than absent.")
    return True, ""


@check("the public register page shows every district and never a bare date",
       because="The register's whole commercial value is as a citable public artifact — the page "
               "a competitor has to link to. That only works if it is complete and if every date "
               "on it carries the officer's words. Two failure modes, both quiet: filtering to "
               "'interesting' rows would hide the non-answers, which ARE the evidence that we "
               "asked rather than guessed; and rendering a date without its quote turns the page "
               "into the same unsourced folklore every other site publishes, except with our "
               "name and an official's district attached to it.")
def _register_page_complete():
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient                 # noqa: PLC0415

    from checker.app import app                               # noqa: PLC0415
    from checker import register                              # noqa: PLC0415

    client = TestClient(app)
    r = client.get("/register")
    if r.status_code != 200:
        return False, f"GET /register returned {r.status_code}; the public page must exist"
    html = r.text

    rows = register._rows().values()
    if not rows:
        return False, "register is empty; the page cannot be verified against it"

    missing = [x.district for x in rows if x.district not in html]
    if missing:
        return False, (f"page omits {len(missing)} district(s), e.g. {missing[:3]}. Every row "
                       f"must appear — the ones with no reply are the evidence that we asked.")

    for x in rows:
        if x.notified_date and x.notified_date in html:
            quote = (x.reply_verbatim or "").strip()
            if not quote or quote[:40] not in html:
                return False, (f"{x.district}: the page shows {x.notified_date!r} without the "
                               f"officer's words. A date with no source is what everyone else "
                               f"publishes.")

    j = client.get("/api/register")
    if j.status_code != 200:
        return False, f"GET /api/register returned {j.status_code}; the data must be fetchable"
    if len(j.json().get("districts", [])) != len(rows):
        return False, "the JSON endpoint and the register disagree on how many districts exist"
    return True, ""


@check("retrieval recall@3 does not regress below its measured floor",
       because="Retrieval decides which section of the Act a user is shown, and it failed "
               "silently. 'Does the committee have to file an annual report?' returned s.4, 6 and "
               "7 — s.21 WAS in the route and fell off the end of top_k because the union was "
               "sorted by section number, so a generic key ('committee', which appears in 20 of "
               "30 sections) crowded out a specific one. Nothing looked wrong; only a benchmark "
               "with independent ground truth could see it. Weighting the keys at all took "
               "recall@3 from 0.80 to 1.00 — measured; IDF and a length heuristic are "
               "indistinguishable on this set, so this floor protects weighting in general and "
               "not one formula. A floor turns a lucky afternoon into a property.")
def _retrieval_recall():
    sys.path.insert(0, str(ROOT))
    from scripts.bench_retrieval import CASES, ground_truth, load, rank_current  # noqa: PLC0415

    FLOOR = 0.95                       # measured 1.00; raise this when it improves, never lower
    provisions = load()
    truth, problems = ground_truth(provisions)
    if problems:
        return False, (f"{len(problems)} benchmark case(s) no longer resolve to any section — "
                       f"the corpus or the case changed: {problems[:2]}")
    hits = miss = 0
    failed = []
    for c in CASES:
        want = truth[c.phrase]
        got = rank_current(c.question)[:3]
        if set(got) & set(want):
            hits += 1
        else:
            miss += 1
            failed.append(f"{c.question!r} wanted s.{want}, got s.{got}")
    n = hits + miss
    if not n:
        return False, "the benchmark ran zero cases; it is asserting nothing"
    rate = hits / n
    if rate < FLOOR:
        return False, (f"recall@3 is {rate:.2f}, below the {FLOOR} floor. {miss} of {n} failed: "
                       f"{failed[:3]}")
    return True, ""


@check("the paid explanation path refuses unverified provisions itself",
       because="The LLM path is 'dark until a lawyer verifies' — but that was held by a single "
               "`if not claim.status.answerable` in ask_engine, and nothing inside "
               "explain_provisions(). Any second caller bypasses it: the RAG pipeline every "
               "planning document proposes would call the client directly and explain unverified "
               "law to a user, fluently, with a real citation, while every planning document "
               "described the system as abstaining. A safety property that lives in one caller "
               "is a convention. Defence in depth means the module that spends money and "
               "produces prose refuses on its own account.")
def _llm_refuses_unverified():
    sys.path.insert(0, str(ROOT))
    from backend.services import llm                           # noqa: PLC0415

    unverified = [{"section_number": 4, "citation": "s.4", "heading": "IC",
                   "text_display": "Every employer shall constitute a Committee.",
                   "verified_by": None}]
    try:
        # tracker is keyword-only. Passing it positionally raised TypeError with AND without
        # the guard, so the check reported "caught" either way — asserting nothing.
        res = llm.explain_provisions("Do I need an IC?", unverified, {"name": "X"},
                                     tracker=None)
    except llm.UnverifiedProvisionError:
        return True, ""
    except Exception as exc:                                   # noqa: BLE001
        return False, (f"raised {type(exc).__name__} rather than refusing explicitly — an "
                       f"incidental failure is not a guarantee")
    if getattr(res, "degraded", False):
        return True, ""
    return False, ("explain_provisions() accepted a provision with verified_by=None. The dark "
                   "path is dark only by convention, and the next caller will not know.")


@check("the safety layer blocks every fabrication this project has actually produced",
       because="A guard is only worth having if it catches what already fooled us. Measured "
               "against twelve cases — eight fabrications really emitted in this project, four "
               "statements quoting the Act verbatim — the proposed embedding-similarity guard "
               "caught 6/8 but flagged 2 of the 4 CORRECT answers as fabrications, because "
               "quoting the statute exactly is not the same as resembling it. It also let "
               "'31 January' through, which is the fabrication this whole product exists to "
               "refuse. Exact checks caught the same 6 with zero false alarms. This pins the "
               "floor so a future 'improvement' to the safety layer cannot quietly lower it.")
def _safety_catches_known_fabrications():
    sys.path.insert(0, str(ROOT))
    from scripts.bench_safety import CASES, corpus, verifier_guard   # noqa: PLC0415

    text = corpus()
    fabs = [c for c in CASES if c.fabricated]
    trues = [c for c in CASES if not c.fabricated]
    if not fabs or not trues:
        return False, "the fabrication set is empty; this check would assert nothing"

    missed = [c.sentence[:60] for c in fabs if not verifier_guard(c.sentence, c.retrieved, text)]
    alarms = [c.sentence[:60] for c in trues if verifier_guard(c.sentence, c.retrieved, text)]

    # False alarms are the harder constraint. A guard that blocks correct answers gets switched
    # off by whoever is on call, and then nothing is guarding anything.
    if alarms:
        return False, f"blocks {len(alarms)}/{len(trues)} verbatim-correct statements: {alarms}"
    FLOOR = 6                          # measured; raise when it improves, never lower
    caught = len(fabs) - len(missed)
    if caught < FLOOR:
        return False, (f"catches {caught}/{len(fabs)} known fabrications, below the {FLOOR} "
                       f"floor. Missed: {missed}")
    return True, ""


@check("no module in checker/ is dead — every one has a caller",
       because="I built checker/path_validity.py with 15 passing tests and imported it from "
               "nothing. Green suite, real coverage, zero effect on any answer a user sees. This "
               "repository has caught the same shape before — sub-sections were added to the "
               "corpus and nothing read them, so the lawyer pack still printed the full 5,570 "
               "character s.2 while the commit message claimed a 28% reduction. Passing tests on "
               "unreachable code are worse than no tests, because the suite reports capability "
               "the product does not have.")
def _no_dead_modules():
    import ast                                                # noqa: PLC0415

    pkg = ROOT / "checker"
    # test_* modules are harnesses: verify.py runs them as subprocesses via SUITES, so being
    # imported by nothing is their correct state. Libraries are different — a library nothing
    # calls is a claim the product cannot cash.
    modules = {f.stem for f in pkg.glob("*.py")
               if f.stem not in {"__init__", "templates"} and not f.stem.startswith("test_")}
    # Where a caller could live: anywhere but the module itself and the verifier.
    sources = [f for f in [*ROOT.glob("*.py"), *pkg.glob("*.py"),
                           *(ROOT / "backend").rglob("*.py"), *(ROOT / "api").rglob("*.py")]
               if f.name != "verify.py"]

    imported: set[str] = set()
    for f in sources:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                # `from checker import x, y` and `from . import x, y`
                if (node.module or "").endswith("checker") or node.level:
                    for a in node.names:
                        if a.name in modules and f.stem != a.name:
                            imported.add(a.name)
                # `from checker.x import ...` / `from .x import ...`
                tail = (node.module or "").split(".")[-1]
                if tail in modules and f.stem != tail:
                    imported.add(tail)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    tail = a.name.split(".")[-1]
                    if tail in modules and f.stem != tail:
                        imported.add(tail)

    dead = sorted(modules - imported)
    if dead:
        return False, (f"no caller imports: {dead}. Tests on unreachable code report a "
                       f"capability the product does not have. Wire it in or delete it.")
    return True, ""


@check("a person describing harm is routed to a human, free, before anything else runs",
       because="This product is a compliance tool for employers, but the Act it implements is "
               "about harassment, and 'do I need an IC?' and 'what if they sack me for "
               "complaining?' are the same search box. When the person asking is the person it "
               "happened to, a better citation is the wrong output. The research on survivor-"
               "facing systems is consistent — every credible deployment escalates to a human "
               "early, because a chatbot is indifferent to its output and a person in crisis is "
               "not. Three invariants, and each would be easy to break by accident: the route "
               "must run BEFORE retrieval and the gate (so it works while verified_by is null), "
               "it must cost nothing (a paywall in front of someone asking whether she can be "
               "sacked for complaining is the worst thing this product could do), and it must "
               "not divert the employer questions that are the actual customers.")
def _distress_routes_free_and_first():
    sys.path.insert(0, str(ROOT))
    from checker import distress                              # noqa: PLC0415
    from checker.ask_engine import AskEngine                  # noqa: PLC0415

    engine = AskEngine()
    ctx = {"state": "IN-KA", "employees": 40, "districts": ["IN-KA-BLR"]}

    for q in distress.DISTRESS:
        a = engine.ask(q, ctx)
        if a.route != "referral":
            return False, f"not routed: {q!r} -> route={a.route!r}"
        if a.cost_inr != 0.0:
            return False, f"PRICED a distress query: {q!r} cost={a.cost_inr}"
        if not any(c.get("kind") == "portal" for c in a.sources):
            return False, f"referral without SHe-Box: {q!r}"
        if "not a person" not in a.reason:
            return False, f"referral does not say it is not a person: {q!r}"

        # Every contact must be dialable/reachable AND carry provenance we can re-check. A
        # helpline number is the one output in this product that gets ACTED ON immediately and
        # has no verifier downstream of it — if it is wrong it rings out at the worst moment.
        line = next((c for c in a.sources if c.get("kind") == "helpline"), None)
        if line is None:
            return False, f"referral offers no human voice, only forms: {q!r}"
        if not line.get("source", "").startswith("http"):
            return False, (f"helpline {line.get('detail')!r} has no source to re-check. An "
                           f"unsourced phone number is a fabricated citation someone dials.")
        if a.sources[0].get("kind") != "helpline":
            return False, (f"a portal or an email is listed before a person, for {q!r}. Ordering "
                           f"is the design here: forms are for after you have decided.")

    for q in distress.ROUTINE:
        a = engine.ask(q, ctx)
        if a.route == "referral":
            return False, (f"diverted an employer question: {q!r}. These are the customers; "
                           f"over-routing them breaks the product.")

    # It must not depend on verification — it has to work today.
    if any(p.get("verified_by") for p in json.loads(POSH.read_text())["provisions"]):
        return True, ""                      # corpus verified; the ordering claim is moot
    a = engine.ask(distress.DISTRESS[0], ctx)
    if a.route != "referral":
        return False, "the route does not fire while the corpus is unverified"
    return True, ""


@check("no secrets committed",
       because="Standing rule, never yet violated. Cheap to keep.")
def _no_secrets():
    pat = re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}|ANTHROPIC_API_KEY\s*=\s*[\"'][^\"'{$]{8,}")
    hits = [str(p.relative_to(ROOT))
            for p in ROOT.rglob("*")
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".json", ".md", ".env"}
            and ".git" not in p.parts and "node_modules" not in p.parts
            and pat.search(p.read_text(encoding="utf-8", errors="replace"))
            and p.name != "verify.py" and str(p.relative_to(ROOT)) not in GENERATED]
    return (not hits), f"possible secret in: {hits}"


def run_suites() -> None:
    for s in SUITES:
        r = subprocess.run([sys.executable, s], cwd=ROOT, capture_output=True, text=True)
        results.append((r.returncode == 0, f"suite: {s}",
                        "" if r.returncode == 0 else (r.stdout or r.stderr)[-300:]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="skip the suites and tsc")
    args = ap.parse_args()

    if not args.fast:
        run_suites()

    # Vacuous-pass guard. Idea taken from a proposed rewrite of this file — which, ironically,
    # could never have run a test at all: its @test decorator returned the wrapper without ever
    # calling it, so a live `assert 1 + 1 == 3` still reported "0 passed, 0 failed".
    #
    # A suite that reports success while testing nothing is worse than no suite, because it is
    # trusted. This is the last thing checked and the first thing that should fail.
    if not results:
        print("\nNO-GO — no checks ran at all. Something removed or broke the check registry; "
              "this is a vacuous pass and it is a bug in the verifier itself.")
        return 1
    expected = MIN_REGISTRY_CHECKS + (0 if args.fast else len(SUITES))
    if len(results) < expected:
        print(f"\nNO-GO — only {len(results)} checks ran, expected at least {expected}. "
              f"A check was deleted or silently skipped. Verify the registry before trusting "
              f"a green run, then raise MIN_CHECKS if the removal was deliberate.")
        return 1

    width = max(len(n) for _, n, _ in results)
    failed = 0
    print()
    for ok, name, note in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}")
        if not ok:
            failed += 1
            for line in note.strip().splitlines():
                print(f"        {line}")
    print()
    if failed:
        print(f"NO-GO — {failed} of {len(results)} checks failed.")
        return 1
    print(f"GO — {len(results)} checks passed.")
    print("\nEvery check above exists because something got through once. Adding one costs a "
          "few lines;\nremoving one costs the bug coming back. When a new bug escapes, add it "
          "here with its story.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
