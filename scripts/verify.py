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

    python3 scripts/verify.py           # everything
    python3 scripts/verify.py --fast    # skip tsc and the suites (~2s)

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

SUITES = [
    "applicability.py", "jurisdiction.py", "backend/budget.py",
    "checker/ic_order.py", "checker/verifier.py", "checker/test_unlock.py",
    "checker/board_report.py", "checker/documents.py",
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


@check("the form is hidden, not unmounted, when the preview opens",
       because="Unmounting DocumentForm discarded every committee member typed. The one moment "
               "you most need to go back — the document came out defective — was the moment "
               "that cost you the whole committee.")
def _form_state():
    for page in ("ic_order", "posh_policy", "board_report"):
        src = _read(f"frontend/app/generate/{page}/page.tsx")
        if "hidden={!!doc}" not in src:
            return False, f"{page}/page.tsx unmounts the form instead of hiding it"
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


def run_tsc() -> None:
    fe = ROOT / "frontend"
    r = subprocess.run(["npx", "tsc", "--noEmit"], cwd=fe, capture_output=True, text=True)
    results.append((r.returncode == 0, "frontend: tsc --noEmit",
                    "" if r.returncode == 0 else (r.stdout or r.stderr)[-300:]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="skip the suites and tsc")
    args = ap.parse_args()

    if not args.fast:
        run_suites()
        run_tsc()

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
