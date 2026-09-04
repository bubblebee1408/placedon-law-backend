"""Cross-section retrieval eval: does a plain question reach the right section?

The sub-agent route to expand this hit an account session limit, so the cases are
authored here directly — which is fine, because the label is STRUCTURAL, not a
legal judgement: "a question about loans to directors is governed by s.185" is
read straight off the section's own subject (its title, dumped from the corpus),
not interpreted. Each case is a plain-English question a CS/lawyer would ask,
mapped to the section that governs it.

Measures precision@1 (top hit correct) and recall@5 (correct section in the top
five) for `corpus_retrieval`. As with retrieval_eval, the self-test verifies the
MEASUREMENT and records the numbers; it asserts an honest floor and prints the
failures so the retriever can be improved against them, not tuned to them.
"""
from __future__ import annotations

from dataclasses import dataclass

from checker.corpus_retrieval import best_section, search


@dataclass(frozen=True)
class Case:
    question: str
    section: str


# Authored from section titles (structural). Two-ish per section, spread across
# the Act's commercial core.
CASES: tuple[Case, ...] = (
    Case("how do we issue shares through private placement", "42"),
    Case("rules for a private placement offer and allotment", "42"),
    Case("how does a company issue further shares to existing shareholders", "62"),
    Case("rights issue procedure and pricing", "62"),
    Case("can a company accept deposits from the public", "73"),
    Case("duty to register a charge on the company's assets", "77"),
    Case("how to register a charge with the registrar", "77"),
    Case("declaration of beneficial interest in shares", "89"),
    Case("register of significant beneficial owners", "90"),
    Case("what must be filed in the annual return", "92"),
    Case("when must a company hold its annual general meeting", "96"),
    Case("how to call an extraordinary general meeting", "100"),
    Case("how many days notice is required for a general meeting", "101"),
    Case("explanatory statement to be annexed to the meeting notice", "102"),
    Case("how should minutes of board and general meetings be kept", "118"),
    Case("declaration and payment of dividend", "123"),
    Case("can a company pay dividend out of past reserves", "123"),
    Case("what must the board's report to shareholders contain", "134"),
    Case("corporate social responsibility spending obligation", "135"),
    Case("which companies must constitute a CSR committee", "135"),
    Case("a member's right to copies of the audited financial statements", "136"),
    Case("filing the financial statement with the registrar", "137"),
    Case("appointment and rotation of auditors", "139"),
    Case("minimum and maximum number of directors on the board", "149"),
    Case("how are directors appointed at a general meeting", "152"),
    Case("when is a person disqualified from being appointed a director", "164"),
    Case("how many board meetings must a company hold in a year", "173"),
    Case("which companies must have an audit committee", "177"),
    Case("nomination and remuneration committee requirements", "178"),
    Case("what are the general powers of the board", "179"),
    Case("borrowing beyond paid-up capital needs shareholder approval", "180"),
    Case("a director's duty to disclose interest in a contract", "184"),
    Case("can a company give a loan to its director", "185"),
    Case("loan or guarantee to a person connected with a director", "185"),
    Case("inter-corporate loan and investment limits", "186"),
    Case("ceiling on loans and investments to other bodies corporate", "186"),
    Case("board approval for a contract with a related party", "188"),
    Case("related party transaction thresholds and approvals", "188"),
    Case("restriction on non-cash transactions involving directors", "192"),
    Case("appointment of a managing director or whole-time director", "196"),
    Case("maximum managerial remuneration a company may pay", "197"),
    Case("which companies must appoint key managerial personnel", "203"),
    Case("scheme of compromise or arrangement with creditors", "230"),
    Case("registrar striking a company's name off the register", "248"),
    Case("punishment for fraud under the companies act", "447"),
)


@dataclass
class Result:
    n: int
    p_at_1: int
    recall_5: int
    misses: list[tuple[str, str, str]]         # (question, expected, got)
    near: list[tuple[str, str, list]]           # in top-5 but not top-1

    @property
    def precision(self) -> float:
        return self.p_at_1 / self.n if self.n else 0.0

    @property
    def recall(self) -> float:
        return self.recall_5 / self.n if self.n else 0.0


def run(cases: tuple[Case, ...] = CASES) -> Result:
    res = Result(len(cases), 0, 0, [], [])
    for c in cases:
        top5 = [n for n, _, _ in search(c.question, 5)]
        got = top5[0] if top5 else None
        if got == c.section:
            res.p_at_1 += 1
        if c.section in top5:
            res.recall_5 += 1
            if got != c.section:
                res.near.append((c.question, c.section, top5))
        else:
            res.misses.append((c.question, c.section, got or "None"))
    return res


def render(res: Result) -> str:
    L = [f"cross-section precision@1: {res.p_at_1}/{res.n} = {res.precision:.2f}",
         f"cross-section recall@5:    {res.recall_5}/{res.n} = {res.recall:.2f}"]
    for q, exp, got in res.misses:
        L.append(f"  MISS   exp=s.{exp:5} got=s.{got:6} q={q[:52]}")
    for q, exp, top5 in res.near:
        L.append(f"  NEAR   exp=s.{exp:5} top5={top5}  q={q[:44]}")
    return "\n".join(L)


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

    print("cross_section_eval")
    res = run()
    check(res.n >= 40, f"the eval has a real number of cases ({res.n})")
    check(0.0 <= res.precision <= 1.0 and 0.0 <= res.recall <= 1.0,
          "precision and recall are well-formed ratios")
    # Honest floors, not a pinned target. recall@5 is the operational metric (a
    # retriever that surfaces the right section in the top five is useful with a
    # human in the loop); precision@1 is the stretch.
    check(res.recall >= 0.75,
          f"recall@5 clears an honest floor ({res.recall:.2f})")
    check(res.precision >= 0.55,
          f"precision@1 clears an honest floor ({res.precision:.2f})")
    print(render(res))
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
