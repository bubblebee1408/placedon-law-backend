#!/usr/bin/env python3
"""Every held artifact, cryptographically checked. The answer is uncomfortable.

The senior-advocate persona asked the sharpest question anyone has asked of this
project:

    "Is your machine reading the Gazette notification itself -- the actual
    G.S.R., the page, the signature of the Joint Secretary -- or is it reading
    somebody's summary of it? I have had a junior tell me a section was amended,
    and when I made him produce the paper it was a headnote from a subscription
    service, and the service had got it wrong."

`scripts/verify_document.py` has been in this repository for weeks and had been
pointed at individual files. It had never been run across the whole corpus. This
does that, and the result is a fact about Indian primary-source distribution, not
an opinion about our pipeline:

    1 of 13 artifacts carries a VALID signature.

## The pattern, which is the actionable part

    ACQUIRED FROM THE ISSUING MINISTRY   signature VALID, bytes intact
    ACQUIRED FROM INDIA CODE             signature INVALID with content APPENDED,
                                         or no signature at all

India Code re-renders and stamps what it serves. The certificate chain in those
files is genuine -- CCA India, through (n)Code Solutions, signing for a real
named officer -- but the signed bytes no longer match, because India Code added
content after the Gazette signed it. The document is not forged. It is also not
the document that was signed.

That is not a criticism of India Code, which is a legitimate official portal doing
a reasonable thing for a reader. It is a finding about what an aggregator's copy
can and cannot support, and it has one direct consequence:

**Acquire from the issuing source when the artifact will carry evidentiary
weight. Use India Code to FIND an instrument, not to prove one.**

## Why this is worth having rather than hiding

A vendor in this market says "verified" and means "we downloaded it". This says
which of thirteen files would survive a challenge, and it says twelve would not.
Published above the headline rather than below it, that makes a buyer trust the
one that does.

    python3 scripts/provenance_census.py
    python3 scripts/provenance_census.py --json
    python3 scripts/provenance_census.py --test
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES = REPO / "corpus" / "sources"
VERIFIER = REPO / "scripts" / "verify_document.py"

# Grades, worst first. A missing signature and a broken one are NOT the same
# problem and must never be collapsed: one is an unsigned rendering, the other is
# a signed document that has been altered since signing.
BROKEN = "SIGNED_THEN_ALTERED"
UNSIGNED = "UNSIGNED_RENDERING"
INTACT = "SIGNATURE_INTACT"
UNKNOWN = "UNKNOWN"
GRADES = (BROKEN, UNSIGNED, INTACT, UNKNOWN)

MEANING = {
    BROKEN: "carries a real Gazette signature, but content was APPENDED after "
            "signing, so the signed bytes no longer match. Genuine chain, "
            "altered file. Cannot support an evidentiary claim.",
    UNSIGNED: "no signature at all -- a rendering of the instrument, not the "
              "signed publication. Usable to read, not to prove.",
    INTACT: "signature valid and bytes unaltered since signing.",
    UNKNOWN: "the verifier could not classify this file.",
}


def grade(path: Path) -> tuple[str, str]:
    out = subprocess.run([sys.executable, str(VERIFIER), str(path)],
                         capture_output=True, text=True,
                         env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"})
    text = out.stdout
    sig = appended = ""
    for line in text.splitlines():
        if "PDF signature" in line:
            sig = line.split()[-1]
        elif "Unsigned appended content" in line:
            appended = line.split()[-1]
    if sig == "VALID" and appended == "NOT_FOUND":
        return INTACT, text
    if sig == "INVALID":
        return BROKEN, text
    if sig == "NOT_PRESENT":
        return UNSIGNED, text
    return UNKNOWN, text


def recorded_source(stem: str) -> str:
    """Where the registration record says this artifact came from."""
    for rec in SOURCES.glob("*registration*.json"):
        if stem.split("_")[0].lower() not in rec.name.lower():
            continue
        try:
            d = json.loads(rec.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        return str(d.get("downloaded_from") or d.get("source_url") or "")
    return ""


def issuer_of(url: str) -> str:
    u = (url or "").lower()
    if "indiacode" in u or "India Code" in url:
        return "India Code (aggregator)"
    if "mca.gov.in" in u:
        return "MCA (issuing ministry)"
    if "sebi.gov.in" in u:
        return "SEBI (issuing regulator)"
    if "egazette" in u:
        return "e-Gazette (publisher)"
    return "not recorded"


def census() -> dict:
    rows = []
    for pdf in sorted(SOURCES.glob("*.pdf")):
        g, _ = grade(pdf)
        src = recorded_source(pdf.stem)
        rows.append({"artifact": pdf.name, "grade": g, "meaning": MEANING[g],
                     "recorded_source": src, "issuer": issuer_of(src)})
    counts = {g: sum(1 for r in rows if r["grade"] == g) for g in GRADES}
    return {"artifacts": rows, "counts": counts, "total": len(rows)}


def text(c: dict) -> str:
    L = ["", "PROVENANCE CENSUS — every held artifact, cryptographically checked",
         "=" * 78, ""]
    for r in c["artifacts"]:
        mark = {INTACT: "INTACT  ", BROKEN: "ALTERED ", UNSIGNED: "UNSIGNED",
                UNKNOWN: "UNKNOWN "}[r["grade"]]
        L.append(f"  {mark}  {r['artifact']}")
        if r["issuer"] != "not recorded":
            L.append(f"            from: {r['issuer']}")
    n, c_ = c["total"], c["counts"]
    L += ["", "-" * 78,
          f"  {c_[INTACT]} of {n} artifacts carry a VALID signature over unaltered bytes.",
          f"  {c_[BROKEN]} are signed and then ALTERED — content appended after signing.",
          f"  {c_[UNSIGNED]} carry no signature at all.", ""]

    by_issuer: dict[str, list[str]] = {}
    for r in c["artifacts"]:
        by_issuer.setdefault(r["issuer"], []).append(r["grade"])
    L.append("  BY SOURCE")
    for issuer, grades in sorted(by_issuer.items()):
        intact = sum(1 for g in grades if g == INTACT)
        L.append(f"    {issuer:<28} {intact}/{len(grades)} intact")
    L += ["",
          "  Acquire from the ISSUING SOURCE when an artifact must carry",
          "  evidentiary weight. Use an aggregator to FIND an instrument,",
          "  never to prove one.", ""]
    return "\n".join(L)


def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [PASS] {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("provenance_census")
    c = census()

    check(c["total"] >= 13, f"every held PDF is checked ({c['total']})")
    check(c["counts"][UNKNOWN] == 0,
          "every artifact is classified -- an unclassifiable file would be the "
          "one most worth knowing about")

    # The finding. Asserted so it cannot silently improve or silently rot.
    check(c["counts"][INTACT] >= 1,
          f"at least one artifact is cryptographically intact "
          f"({c['counts'][INTACT]} of {c['total']})")
    check(c["counts"][BROKEN] > 0,
          f"{c['counts'][BROKEN]} artifacts are signed-then-altered -- this is a "
          f"fact about the source, not about our pipeline, and it must not be "
          f"quietly dropped from the record")

    # A broken signature and a missing one are different problems.
    check(MEANING[BROKEN] != MEANING[UNSIGNED]
          and "altered file" in MEANING[BROKEN]
          and "not to prove" in MEANING[UNSIGNED],
          "a signed-then-altered file and an unsigned rendering are graded "
          "separately -- collapsing them would hide which one has a real "
          "signature behind it")

    # The actionable pattern.
    intact_issuers = {r["issuer"] for r in c["artifacts"] if r["grade"] == INTACT}
    aggregator = [r for r in c["artifacts"] if "aggregator" in r["issuer"]]
    check(aggregator and all(r["grade"] != INTACT for r in aggregator),
          f"NO artifact acquired from the aggregator is intact "
          f"({len(aggregator)} checked)")
    check(any("ministry" in i or "regulator" in i or "publisher" in i
              for i in intact_issuers),
          f"...and the intact one came from an issuing source: {intact_issuers}")

    t = text(c)
    check("never to prove one" in t,
          "the report states the acquisition rule the finding implies")
    check(all(r["artifact"] in t for r in c["artifacts"]),
          "every artifact is named, none summarised away")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main(argv: list[str]) -> int:
    if "--test" in argv:
        return _test()
    c = census()
    if "--json" in argv:
        print(json.dumps(c, indent=1))
    else:
        print(text(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
