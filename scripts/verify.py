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
    src = _read("checker/app.py")
    if "expose_headers" not in src:
        return False, "no expose_headers on CORSMiddleware"
    missing = [h for h in ("X-Blocking-Issues", "Content-Disposition") if h not in src]
    return (not missing), f"not exposed: {missing}"


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
            and p.name != "verify.py" and p.suffix != ".md"]
    return (not hits), f"false verification claim in: {hits}"


@check("s.4 is never cited as the source of the ten-employee threshold",
       because="'Every employer employing 10 or more employees shall constitute an IC' is not "
               "in the PoSH Act. It appeared in the master spec, two scaffold files, and our own "
               "shipped rules.py comment. Only the verbatim corpus ever caught it.")
def _no_s4_threshold():
    src = _read("checker/rules.py")
    if "s.4 states no threshold" not in src:
        return False, "rules.py no longer records that s.4 contains no threshold"
    body = json.loads(POSH.read_text())["provisions"]
    s4 = next(p for p in body if p["section_number"] == 4)
    if re.search(r"\bten\b|\b10\b", s4["text_display"], re.I):
        return False, "s.4 text now contains a ten — re-read it, the corpus may have changed"
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


@check("no secrets committed",
       because="Standing rule, never yet violated. Cheap to keep.")
def _no_secrets():
    pat = re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}|ANTHROPIC_API_KEY\s*=\s*[\"'][^\"'{$]{8,}")
    hits = [str(p.relative_to(ROOT))
            for p in ROOT.rglob("*")
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".json", ".md", ".env"}
            and ".git" not in p.parts and "node_modules" not in p.parts
            and pat.search(p.read_text(encoding="utf-8", errors="replace"))
            and p.name != "verify.py"]
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
