#!/usr/bin/env python3
"""What we hold, instrument by instrument, read from the engine at run time.

objection_sim O-01. The senior-advocate persona caught a contradiction in our own
materials, and it is a real one:

    "Your flagship example is the Rs 4 crore small-company threshold. That figure
    is not in the Act -- s.2(85) says 'as may be prescribed' and the number lives
    in a delegated Rule, which you have just told me you mostly do not hold. So
    either your disclosure is false or your example is. Which?"

Checked, and his PREMISE is false: `staleness.DEPENDENCIES` shows S-002 and S-003
-- G.S.R. 700(E) and G.S.R. 880(E), which ARE the Specification of Definition
Details Rules -- both HELD_ATTESTED. We hold the very instrument the demo turns on.

But he is right about the thing that matters. Our coverage STATEMENT is loose.
"We do not hold most delegated Rules" is true in aggregate and misleading about
the one Rule the whole demonstration depends on, and a practitioner who catches
that in minute one has stopped listening by minute two.

An adjective cannot be checked. A table can. So this prints one, and it prints it
from `staleness.DEPENDENCIES` and `scope.BODIES` at run time rather than from a
maintained list -- because a maintained list is a second place for the truth to
live, and it will drift from the first one exactly when it matters.

**Never quote a coverage figure that did not come out of this script.**

    python3 scripts/holdings.py
    python3 scripts/holdings.py --markdown     # paste into a doc
    python3 scripts/holdings.py --json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import scope, staleness  # noqa: E402

# What each acquisition state means to a reader who is not us. The distinction
# that matters to a practitioner is not our enum -- it is "can this answer a
# question today, and if not, what is missing".
MEANING = {
    staleness.HELD_ATTESTED: ("USABLE", "held, and a person has verified its "
                              "identity and its verbatim clause"),
    staleness.HELD_UNREVIEWED: ("NOT USABLE", "the file is on disk but nobody has "
                                "read it; storage is not review"),
    staleness.STAGED: ("NOT USABLE", "registered and hashed, awaiting the human "
                       "attestation that makes it servable"),
    staleness.CHAIN_TRACED: ("NOT USABLE", "the principal Rules and every "
                             "amendment are held and the chain is traced, but a "
                             "reader must still confirm the resulting text"),
    staleness.CHAIN_UNRESOLVED: ("NOT USABLE", "later amendments are unacquired, "
                                 "so any figure served could already have moved"),
    staleness.NOT_HELD: ("NOT USABLE", "not acquired"),
}


def rows() -> list[dict]:
    out = []
    for dep in staleness.DEPENDENCIES:
        state = dep.state()
        usable, why = MEANING.get(state, ("NOT USABLE", state))
        out.append({
            "rule_id": dep.rule_id,
            "instrument": dep.instrument,
            "state": state,
            "usable": usable == "USABLE",
            "meaning": why,
            "governs": list(dep.governs),
            "artifact": dep.artifact,
            "supersession_watched": dep.supersession_watched,
        })
    return out


def bodies() -> list[dict]:
    return [{"key": b.key, "name": b.name, "state": b.status,
             "point_in_time": b.point_in_time, "answerable": b.answerable}
            for b in scope.BODIES]


def payload() -> dict:
    r, b = rows(), bodies()
    held = [x for x in r if x["usable"]]
    return {
        "delegated_instruments": r,
        "bodies_of_law": b,
        "summary": {
            "instruments_inventoried": len(r),
            "instruments_usable": len(held),
            "bodies_in_scope": len(b),
            "bodies_held": sum(1 for x in b if x["state"] == scope.IN_CORPUS),
        },
        "rule": ("Quote no coverage figure that did not come from this script. An "
                 "aggregate adjective -- 'most', 'some', 'largely' -- is not "
                 "checkable and will be checked."),
    }


def text(markdown: bool = False) -> str:
    p = payload()
    L = []
    if markdown:
        L += ["## Instruments held", "",
              "| Instrument | State | Usable today | Governs |",
              "|---|---|---|---|"]
        for x in p["delegated_instruments"]:
            L.append(f"| {x['instrument']} | `{x['state']}` | "
                     f"{'**yes**' if x['usable'] else 'no'} | "
                     f"{', '.join(x['governs'])} |")
        L += ["", "## Bodies of law", "",
              "| Body | State | Point-in-time | Answerable |", "|---|---|---|---|"]
        for x in p["bodies_of_law"]:
            L.append(f"| {x['name']} | `{x['state']}` | "
                     f"{'yes' if x['point_in_time'] else 'no'} | "
                     f"{'yes' if x['answerable'] else 'no'} |")
    else:
        L.append("\nDELEGATED INSTRUMENTS — what we hold, and whether it is usable")
        L.append("=" * 78)
        for x in p["delegated_instruments"]:
            mark = "USABLE    " if x["usable"] else "NOT USABLE"
            L.append(f"\n  {mark}  {x['instrument']}")
            L.append(f"              state: {x['state']} — {x['meaning']}")
            L.append(f"              governs: {', '.join(x['governs'])}")
        L.append("\n\nBODIES OF LAW IN SCOPE")
        L.append("=" * 78)
        for x in p["bodies_of_law"]:
            L.append(f"  {x['state']:<14} {x['name']}"
                     + ("  [point-in-time]" if x["point_in_time"] else ""))

    s = p["summary"]
    L += ["", "-" * 78,
          f"  {s['instruments_usable']} of {s['instruments_inventoried']} "
          f"inventoried instruments are usable today.",
          f"  {s['bodies_held']} of {s['bodies_in_scope']} bodies of law are held; "
          f"the rest are declared and actively refused.",
          "",
          "  The small-company thresholds — the figures the demonstration turns on —",
          "  rest on G.S.R. 700(E) and G.S.R. 880(E). Both are above, both attested.",
          "  Saying we 'do not hold most delegated Rules' is true in aggregate and",
          "  misleading about those two. Quote this table, never that adjective.", ""]
    return "\n".join(L)


def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [PASS] {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("holdings")
    p = payload()

    check(len(p["delegated_instruments"]) == len(staleness.DEPENDENCIES),
          "every inventoried instrument appears -- the table is the engine's own "
          "inventory, not a maintained copy that could drift from it")

    # The advocate's premise, settled against the engine.
    defs = [x for x in p["delegated_instruments"]
            if "Specification of Definition" in x["instrument"]]
    check(len(defs) == 2,
          "both Specification of Definition Details instruments are inventoried")
    check(all(x["usable"] for x in defs),
          "...and BOTH are usable, which is why 'we do not hold most delegated "
          "Rules' was a false thing to say about the demo's own example")
    check(all("CA13-S2-85-SMALL" in x["governs"] for x in defs),
          "...and they govern the small-company obligation the demo turns on")

    # It must be capable of saying no, or it is a brochure.
    check(any(not x["usable"] for x in p["delegated_instruments"]),
          "the table reports unusable instruments too -- a holdings list that only "
          "lists holdings is marketing")
    for x in p["delegated_instruments"]:
        check(bool(x["meaning"]),
              f"{x['rule_id']}: the state is explained in a reader's words, not "
              f"left as an enum")

    t = text()
    check("Quote this table, never that adjective" in t,
          "the output states the rule it exists to enforce")
    check(all(x["instrument"][:28] in t for x in p["delegated_instruments"]),
          "every instrument is named in the rendered text, none summarised away")
    check("| Instrument |" in text(markdown=True),
          "a markdown form exists, so the doc and the engine cannot disagree")
    check(json.loads(json.dumps(p))["summary"]["instruments_usable"]
          == p["summary"]["instruments_usable"],
          "the payload is JSON-serialisable for the docs pipeline")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main(argv: list[str]) -> int:
    if "--test" in argv:
        return _test()
    if "--json" in argv:
        print(json.dumps(payload(), indent=1))
        return 0
    print(text(markdown="--markdown" in argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
