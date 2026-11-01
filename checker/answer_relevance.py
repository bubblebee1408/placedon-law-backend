"""Does the answer cite the provision the question is about?

The verifier proves every quote byte-matches the section it names. It does not prove that
section is the one the question asked about: a board-quorum question once came back
"Answered" from s.96 (AGM timing), every quote genuine. Board quorum is s.174.

This is a small, deterministic topic -> sections map for core Companies Act 2013 topics.
No model. When a question clearly matches a topic and NONE of the cited sections is in
that topic's set, the topic is "unaddressed" and the caller must not serve ANSWERED.
A question that matches no topic is untouched -- an unmatched question is not evidence of
anything, and refusing it would be a false refusal.

Every section number below was checked against `corpus/companies_act/_index.json` (title
quoted beside it) on 2026-11-01. A section the user names explicitly in the question
(`legal_retrieval.resolve`) always counts as on point: they asked about it.

ponytail: keyword patterns, not semantics. A topic phrased in words no pattern knows
falls through to today's behaviour (no gate). Widen a pattern when a real miss is seen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    label: str                          # plain English, used in the reason
    sections: frozenset[str]
    all_of: tuple[str, ...]             # every regex must match
    none_of: tuple[str, ...] = ()       # any match disqualifies


_BOARD = r"\bboard\b|\bdirectors?\b"
_GM = r"general meeting|\bagm\b|\begm\b|\bmembers?\b|\bshareholders?\b"

TOPICS: tuple[Topic, ...] = (
    # 174 "Quorum for meetings of Board"; 378V "Meetings of Board and quorum" (Producer Co.)
    Topic("board_quorum", "board meeting quorum", frozenset({"174", "378V"}),
          (r"\bquorum\b", _BOARD), (_GM,)),
    # 103 "Quorum for meetings"
    Topic("gm_quorum", "general meeting quorum", frozenset({"103"}),
          (r"\bquorum\b", _GM), (_BOARD,)),
    # 96 "Annual general meeting"
    Topic("agm_timing", "when an annual general meeting must be held", frozenset({"96"}),
          (r"annual general meeting|\bagm\b",
           r"\bwhen\b|\bwithin\b|time limit|deadline|\bmonths?\b|\bgap\b|\binterval\b|"
           r"\bextend|\bextension\b|\bdue\b|\bfirst\b"),
          (r"\bquorum\b|\bnotice\b|\bprox(y|ies)\b|\bminutes\b|\bvot(e|es|ing)\b",)),
    # 101 "Notice of meeting"
    Topic("gm_notice", "notice of a general meeting", frozenset({"101"}),
          (r"\bnotice\b", r"general meeting|\bagm\b|\begm\b|shareholders'? meeting|"
           r"members'? meeting"),
          (r"\bquorum\b", r"special notice")),
    # 173 "Meetings of Board"
    Topic("board_frequency", "how often the Board must meet", frozenset({"173", "378V"}),
          (r"board meetings?|meetings? of (the )?board|board of directors (must |shall )?meet",
           r"how many|how often|frequen|\bgap\b|\binterval\b|minimum number|first (board )?"
           r"meeting|in a (calendar |financial )?year|each year|every year|days between"),
          (r"\bquorum\b",)),
    # 114 "Ordinary and special resolutions"
    Topic("resolution_types", "ordinary and special resolutions", frozenset({"114"}),
          (r"(ordinary|special) resolutions?",
           r"what is|defin|differ|meaning|majority|three times|three-fourths|votes? cast"),),
    # 117 "Resolutions and agreements to be filed"
    Topic("resolution_filing", "filing resolutions with the Registrar", frozenset({"117"}),
          (r"\bresolutions?\b", r"\bfil(e|ed|ing)\b|registrar|mgt[- ]?14"),),
    # 152 "Appointment of directors"; 160 "Right of persons other than retiring directors
    # to stand for directorship"; 161 "Appointment of additional director, alternate
    # director and nominee director"
    Topic("director_appointment", "appointment of directors",
          frozenset({"152", "160", "161"}),
          (r"\bappoint", r"\bdirectors?\b"),
          (r"managing|whole[- ]time|independent|disqualif|eligib|key managerial|\bkmp\b|"
           r"\bdin\b|auditor|\bremov",)),
    # 135 "Corporate Social Responsibility"
    Topic("csr", "corporate social responsibility", frozenset({"135"}),
          (r"\bcsr\b|corporate social responsibility",)),
    # 188 "Related party transactions"; 177 "Audit committee" (approves RPTs);
    # 2 definitions (s.2(76) "related party")
    Topic("rpt", "related party transactions", frozenset({"188", "177", "2"}),
          (r"related[- ]part(y|ies)|\brpts?\b",)),
    # 139 "Appointment of auditors"
    Topic("auditor_appointment", "appointment of auditors", frozenset({"139"}),
          (r"\bauditors?\b", r"\bappoint|\breappoint|\brotation\b|\bterm\b"),
          (r"cost auditor|secretarial|internal audit",)),
    # 92 "Annual return"
    Topic("annual_return", "the annual return", frozenset({"92"}),
          (r"annual return",)),
    # 137 "Copy of financial statement to be filed with Registrar"
    Topic("fs_filing", "filing financial statements with the Registrar",
          frozenset({"137"}),
          (r"financial statements?|\baccounts\b|balance sheet",
           r"\bfil(e|ed|ing)\b|registrar|aoc[- ]?4")),
    # 185 "Loan to directors, etc"
    Topic("director_loans", "loans to directors", frozenset({"185"}),
          (r"\bloans?\b", r"\bto (a |its |the )?directors?\b"),),
    # 164 "Disqualifications for appointment of director"
    Topic("director_disqualification", "disqualification of directors",
          frozenset({"164"}),
          (r"disqualif", r"\bdirectors?\b"),),
    # 118 "Minutes of proceedings of general meeting, meeting of Board ..."; 119
    # "Inspection of minute-books of general meeting"
    Topic("minutes", "minutes of meetings", frozenset({"118", "119"}),
          (r"\bminutes\b|minute[- ]books?",),),
    # 100 "Calling of extraordinary general meeting"
    Topic("egm_calling", "calling an extraordinary general meeting", frozenset({"100"}),
          (r"extraordinary general meeting|\begm\b",
           r"\bcall|\brequisition|\bconven"),),
)


def matched(question: str) -> tuple[Topic, ...]:
    """The topics this question clearly asks about. Empty is the common, safe case."""
    q = (question or "").lower()
    return tuple(t for t in TOPICS
                 if all(re.search(p, q) for p in t.all_of)
                 and not any(re.search(p, q) for p in t.none_of))


def section_number(source_id: str) -> str:
    """"Companies Act 2013, s.174" -> "174"; anything else -> ""."""
    m = re.search(r",\s*s\.(\w+)$", source_id or "")
    return m.group(1) if m else ""


def unaddressed(question: str, cited: set[str] | frozenset[str]) -> tuple[Topic, ...]:
    """Matched topics the answer's ACTUAL citations (bare section numbers) do not address.

    Only cited sections are evidence; a section the question names but the answer does not
    cite counts for nothing. A named section changes which citations count:
      * the question names a section IN the topic's set ("board quorum? compare s.174 and
        s.96") -- the user anchored the topic there, so that set must be cited; citing only
        the other named section (s.96) does not address it;
      * the question names sections outside the set ("the CSR disclosure in s.134") -- a
        citation of one of those named sections counts as on topic, even though the map
        files CSR under s.135.
    """
    from checker.legal_retrieval import resolve
    named = {h.ref.number for h in resolve(question or "")}
    cited = set(cited)
    out = []
    for t in matched(question):
        on_point = t.sections if (named & t.sections) else (t.sections | named)
        if not (cited & on_point):
            out.append(t)
    return tuple(out)


def reason(topics: tuple[Topic, ...]) -> str:
    labels = " or ".join(t.label for t in topics)
    return (f"The sources found don't address {labels}, so this is not marked answered. "
            f"The quotes below are exact, but they are about something else.")


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

    print("answer_relevance")
    Q = "What is the quorum for a board meeting?"
    check([t.key for t in unaddressed(Q, {"96"})] == ["board_quorum"],
          "board-quorum question answered from s.96 -> board quorum unaddressed")
    check(unaddressed(Q, {"174"}) == () and unaddressed(Q, {"174", "103"}) == (),
          "...answered from s.174 -> nothing unaddressed")
    check("board meeting quorum" in reason(unaddressed(Q, {"96"})),
          "...and the reason names the topic in plain English")
    check(unaddressed("Who signs the share certificate?", {"96"}) == (),
          "a question matching no topic is never gated")
    check(unaddressed("What is the quorum under section 96?", {"96"}) == (),
          "a section the user names explicitly, AND the answer cites, counts as on point")
    QC = "What is the quorum for a board meeting? Compare section 174 and section 96."
    check([t.key for t in unaddressed(QC, {"96"})] == ["board_quorum"],
          "board quorum naming s.174 and s.96, answered only from s.96 -> unaddressed: a "
          "named-but-uncited s.174 is not evidence")
    check(unaddressed(QC, {"174"}) == () and unaddressed(QC, {"174", "96"}) == (),
          "...and answered from s.174 it is addressed")
    QS = "Give me the exact CSR disclosure quote from section 134."
    check(unaddressed(QS, {"134"}) == (),
          "CSR question that explicitly asks for s.134, answered from s.134 -> on point")
    check([t.key for t in unaddressed(QS, {"96"})] == ["csr"],
          "...but answered from s.96 it is not")
    check([t.key for t in unaddressed("What is the quorum for a board meeting under "
                                      "section 96?", set())] == ["board_quorum"],
          "a named section the answer does not cite counts for nothing")
    check([t.key for t in matched("What is the quorum for an AGM?")] == ["gm_quorum"],
          "AGM quorum -> s.103 topic, not board quorum")
    check(matched("Quorum for board meetings and for the AGM?") == (),
          "a quorum question naming both board and general meeting is ambiguous: no gate")
    check([t.key for t in matched("Within how many months must the AGM be held?")]
          == ["agm_timing"], "AGM timing matches")
    check([t.key for t in matched("How much notice is needed for an AGM?")] == ["gm_notice"],
          "AGM notice is the notice topic, not AGM timing")
    check([t.key for t in matched("How many board meetings must a company hold in a year?")]
          == ["board_frequency"], "board meeting frequency matches")
    check(matched("Who is disqualified from appointment as a director?")[0].key
          == "director_disqualification" and len(matched(
              "Who is disqualified from appointment as a director?")) == 1,
          "disqualification is not misread as director appointment")
    check(section_number("Companies Act 2013, s.378V") == "378V"
          and section_number("garbage") == "", "section_number parses source ids")

    # Every mapped section must exist in the held corpus index, with a title.
    import json
    from checker import public_only
    idx = json.loads((public_only.ROOT / "corpus" / "companies_act" / "_index.json")
                     .read_text())["entries"]
    missing = sorted(s for t in TOPICS for s in t.sections
                     if not (idx.get(s) or {}).get("section_id"))
    check(missing == [], f"every mapped section is a live, indexed corpus section {missing}")
    check(idx["174"]["title"] == "Quorum for meetings of Board"
          and idx["96"]["title"] == "Annual general meeting"
          and idx["103"]["title"] == "Quorum for meetings",
          "the headline mappings match the corpus titles")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
