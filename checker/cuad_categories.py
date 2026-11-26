"""CUAD question-template registry — the 41 CUAD categories plus India-specific extensions.

Data only. Each category has a question template, answer type, and description.
The extractor sends the question; deterministic code verifies the answer.

Based on: Hendrycks et al. (2021), "CUAD: An Expert-Annotated NLP Dataset for
Legal Contract Review", NeurIPS 2021, arXiv 2103.06268.

Run: PYTHONPATH=. python3 checker/cuad_categories.py --test
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Category", "CATEGORIES", "INDIA_CATEGORIES", "ALL_CATEGORIES",
           "select_categories"]

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Category:
    name: str
    question: str
    answer_type: str  # "entity", "date", "boolean", "span", "currency"
    description: str
    cuad_index: int | None = None  # 1-41 for CUAD, None for extensions


# The 41 CUAD categories, questions from the official dataset appendix.
CATEGORIES: dict[str, Category] = {
    "Document Name": Category(
        "Document Name", "What is the name of the contract?",
        "entity", "The title or name of the agreement.", 1),
    "Parties": Category(
        "Parties", "Who are the parties to the agreement?",
        "entity", "Names of the contracting parties.", 2),
    "Agreement Date": Category(
        "Agreement Date", "What is the date of the agreement?",
        "date", "The date the agreement was executed.", 3),
    "Effective Date": Category(
        "Effective Date", "What is the effective date of the agreement?",
        "date", "The date from which the agreement takes effect.", 4),
    "Expiration Date": Category(
        "Expiration Date", "On what date does the agreement expire?",
        "date", "The date on which the agreement terminates.", 5),
    "Renewal Term": Category(
        "Renewal Term", "What is the renewal term after the initial term expires?",
        "span", "Provisions for renewal or extension.", 6),
    "Notice Period To Terminate Renewal": Category(
        "Notice Period To Terminate Renewal",
        "What is the notice period required to terminate renewal?",
        "span", "Notice required to prevent automatic renewal.", 7),
    "Governing Law": Category(
        "Governing Law", "Which state/country's law governs the agreement?",
        "entity", "The jurisdiction whose laws govern the contract.", 8),
    "Most Favored Nation": Category(
        "Most Favored Nation",
        "Is there a most favored nation clause?",
        "boolean", "Whether one party gets terms at least as favorable as others.", 9),
    "Non-Compete": Category(
        "Non-Compete",
        "Is there a restriction on a party competing with the counterparty?",
        "span", "Restrictions on competition.", 10),
    "Exclusivity": Category(
        "Exclusivity", "Is there an exclusivity obligation?",
        "span", "Whether a party has exclusive rights or obligations.", 11),
    "No-Solicitation Of Customers": Category(
        "No-Solicitation Of Customers",
        "Is there a restriction on soliciting customers?",
        "span", "Restrictions on soliciting the other party's customers.", 12),
    "No-Solicitation Of Employees": Category(
        "No-Solicitation Of Employees",
        "Is there a restriction on soliciting employees?",
        "span", "Restrictions on soliciting the other party's employees.", 13),
    "Competitive Restriction Exception": Category(
        "Competitive Restriction Exception",
        "What exceptions exist to the non-compete or exclusivity restrictions?",
        "span", "Exceptions to competitive restrictions.", 14),
    "Non-Disparagement": Category(
        "Non-Disparagement",
        "Is there a non-disparagement clause?",
        "boolean", "Restrictions on making negative statements.", 15),
    "Termination For Convenience": Category(
        "Termination For Convenience",
        "Can a party terminate the agreement without cause?",
        "span", "Rights to terminate without breach.", 16),
    "Rofr/Rofo/Rofn": Category(
        "Rofr/Rofo/Rofn",
        "Is there a right of first refusal, first offer, or first negotiation?",
        "span", "Pre-emptive rights on sale or transfer.", 17),
    "Change Of Control": Category(
        "Change Of Control",
        "Does a change of control trigger any rights or obligations?",
        "span", "Provisions triggered by ownership changes.", 18),
    "Anti-Assignment": Category(
        "Anti-Assignment",
        "Is consent required for assignment of the agreement?",
        "span", "Restrictions on assigning rights or obligations.", 19),
    "Revenue/Profit Sharing": Category(
        "Revenue/Profit Sharing",
        "Is there a revenue or profit sharing arrangement?",
        "span", "Terms for sharing revenue or profits.", 20),
    "Price Restrictions": Category(
        "Price Restrictions",
        "Are there restrictions on pricing?",
        "span", "Limitations on price changes or pricing terms.", 21),
    "Minimum Commitment": Category(
        "Minimum Commitment",
        "Is there a minimum order or commitment requirement?",
        "span", "Minimum purchase or performance obligations.", 22),
    "Volume Restriction": Category(
        "Volume Restriction",
        "Are there restrictions on volume?",
        "span", "Limitations on quantities.", 23),
    "IP Ownership Assignment": Category(
        "IP Ownership Assignment",
        "Does the agreement assign intellectual property rights?",
        "span", "Transfer of IP ownership.", 24),
    "Joint IP Ownership": Category(
        "Joint IP Ownership",
        "Is there joint ownership of intellectual property?",
        "boolean", "Shared ownership of developed IP.", 25),
    "License Grant": Category(
        "License Grant",
        "Does the agreement grant a license to intellectual property?",
        "span", "IP license terms.", 26),
    "Non-Transferable License": Category(
        "Non-Transferable License",
        "Is the license non-transferable?",
        "boolean", "Whether the license cannot be transferred.", 27),
    "Affiliate License-Licensee": Category(
        "Affiliate License-Licensee",
        "Can affiliates of the licensee use the license?",
        "boolean", "Whether licensee affiliates can use the licensed IP.", 28),
    "Affiliate License-Licensor": Category(
        "Affiliate License-Licensor",
        "Do licensor affiliates grant licenses under the agreement?",
        "boolean", "Whether licensor affiliates are covered.", 29),
    "Unlimited/All-You-Can-Eat-License": Category(
        "Unlimited/All-You-Can-Eat-License",
        "Is the license unlimited or all-you-can-eat?",
        "boolean", "Whether the license has no usage limits.", 30),
    "Irrevocable Or Perpetual License": Category(
        "Irrevocable Or Perpetual License",
        "Is the license irrevocable or perpetual?",
        "boolean", "Whether the license survives termination.", 31),
    "Source Code Escrow": Category(
        "Source Code Escrow",
        "Is there a source code escrow arrangement?",
        "boolean", "Whether source code is held in escrow.", 32),
    "Post-Termination Services": Category(
        "Post-Termination Services",
        "Are there post-termination service obligations?",
        "span", "Services required after termination.", 33),
    "Audit Rights": Category(
        "Audit Rights",
        "Does a party have the right to audit the other?",
        "span", "Rights to inspect books, records, or compliance.", 34),
    "Uncapped Liability": Category(
        "Uncapped Liability",
        "Is liability uncapped under the agreement?",
        "boolean", "Whether there is no cap on liability.", 35),
    "Cap On Liability": Category(
        "Cap On Liability",
        "What is the cap on liability?",
        "currency", "The maximum amount of liability.", 36),
    "Liquidated Damages": Category(
        "Liquidated Damages",
        "Are there liquidated damages provisions?",
        "span", "Pre-determined damages for breach.", 37),
    "Warranty Duration": Category(
        "Warranty Duration",
        "What is the duration of any warranty?",
        "span", "How long warranties last.", 38),
    "Insurance": Category(
        "Insurance",
        "Is there an insurance obligation?",
        "span", "Requirements to maintain insurance.", 39),
    "Covenant Not To Sue": Category(
        "Covenant Not To Sue",
        "Is there a covenant not to sue?",
        "boolean", "Agreement not to bring legal action.", 40),
    "Third Party Beneficiary": Category(
        "Third Party Beneficiary",
        "Are there third party beneficiaries?",
        "span", "Rights of parties not to the agreement.", 41),
}

# India-specific extensions — clearly marked as non-CUAD.
INDIA_CATEGORIES: dict[str, Category] = {
    "Stamp Duty": Category(
        "Stamp Duty",
        "What stamp duty provisions apply to this agreement?",
        "span", "Indian stamp duty requirements and payment obligations.", None),
    "Arbitration Seat": Category(
        "Arbitration Seat",
        "What is the seat of arbitration?",
        "entity", "The city/jurisdiction designated as the seat of arbitration.", None),
    "Companies Act Reference": Category(
        "Companies Act Reference",
        "Which sections of the Companies Act 2013 are referenced?",
        "span", "References to specific Companies Act provisions.", None),
    "SEBI Compliance": Category(
        "SEBI Compliance",
        "What SEBI reporting or compliance requirements are mentioned?",
        "span", "Securities and Exchange Board of India obligations.", None),
    "Indemnification": Category(
        "Indemnification",
        "What are the indemnification obligations?",
        "span", "Obligation to compensate for losses or damages.", None),
    "Confidentiality": Category(
        "Confidentiality",
        "What are the confidentiality obligations?",
        "span", "Obligations to protect confidential information.", None),
    "Representations And Warranties": Category(
        "Representations And Warranties",
        "What representations and warranties are made?",
        "span", "Statements of fact and promises about conditions.", None),
    "Conditions Precedent": Category(
        "Conditions Precedent",
        "What conditions must be satisfied before the agreement takes effect?",
        "span", "Pre-conditions to effectiveness or closing.", None),
    "Payment Terms": Category(
        "Payment Terms",
        "What are the payment obligations and terms?",
        "currency", "Payment amounts, schedules, and methods.", None),
    "Dispute Resolution": Category(
        "Dispute Resolution",
        "What is the dispute resolution mechanism?",
        "span", "How disputes are resolved (arbitration, mediation, litigation).", None),
}

ALL_CATEGORIES: dict[str, Category] = {**CATEGORIES, **INDIA_CATEGORIES}

# Map from regex tagger tag names (clause_tags.TAGS) to CUAD/India category names.
_TAG_TO_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Governing Law": ("Governing Law",),
    "Term": ("Effective Date", "Expiration Date", "Renewal Term"),
    "Termination for Convenience": ("Termination For Convenience",),
    "Confidentiality": ("Confidentiality",),
    "Indemnity": ("Indemnification",),
    "Limitation of Liability": ("Cap On Liability", "Uncapped Liability", "Liquidated Damages"),
    "Non-Compete": ("Non-Compete", "Exclusivity", "Competitive Restriction Exception"),
    "Assignment": ("Anti-Assignment",),
    "Notice Period": ("Notice Period To Terminate Renewal",),
    "Renewal": ("Renewal Term",),
    "Audit Rights": ("Audit Rights",),
    "Insurance": ("Insurance",),
    "Dispute Resolution": ("Dispute Resolution", "Arbitration Seat"),
}

# Categories always asked regardless of regex tag detection.
_ALWAYS_ASK = frozenset({
    "Document Name", "Parties", "Agreement Date", "Effective Date",
    "Governing Law", "Representations And Warranties",
    "Conditions Precedent", "Payment Terms",
})


def select_categories(tag_names: frozenset[str], doc_class: str) -> list[str]:
    """Pick which categories to extract, given detected tags and doc class."""
    selected: set[str] = set(_ALWAYS_ASK)

    # Add categories triggered by detected regex tags.
    for tag_name in tag_names:
        for cat in _TAG_TO_CATEGORIES.get(tag_name, ()):
            selected.add(cat)

    # For NDAs, always check confidentiality-related categories.
    if doc_class == "nda":
        selected.update({"Confidentiality", "Non-Compete",
                         "No-Solicitation Of Employees", "No-Solicitation Of Customers"})

    # For service agreements, check service-specific categories.
    if doc_class in ("service_agreement", "msa"):
        selected.update({"Cap On Liability", "Indemnification", "Insurance",
                         "Post-Termination Services", "Warranty Duration"})

    return sorted(selected)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("cuad_categories")

    check(len(CATEGORIES) == 41, f"41 CUAD categories ({len(CATEGORIES)})")
    check(len(INDIA_CATEGORIES) == 10, f"10 India-specific ({len(INDIA_CATEGORIES)})")
    check(len(ALL_CATEGORIES) == 51, f"51 total ({len(ALL_CATEGORIES)})")

    # No duplicate names across both dicts.
    overlap = set(CATEGORIES) & set(INDIA_CATEGORIES)
    check(len(overlap) == 0, f"no duplicates between CUAD and India ({overlap})")

    # Every category has required fields.
    for name, cat in ALL_CATEGORIES.items():
        check(cat.name == name, f"{name}: name matches key")
    check(all(c.question for c in ALL_CATEGORIES.values()), "all have questions")
    check(all(c.description for c in ALL_CATEGORIES.values()), "all have descriptions")

    valid_types = {"entity", "date", "boolean", "span", "currency"}
    types = {c.answer_type for c in ALL_CATEGORIES.values()}
    check(types <= valid_types, f"all answer_types valid ({types - valid_types})")

    # CUAD indices 1-41, contiguous.
    cuad_indices = sorted(c.cuad_index for c in CATEGORIES.values() if c.cuad_index)
    check(cuad_indices == list(range(1, 42)), f"CUAD indices 1-41 ({len(cuad_indices)})")

    # India categories have no CUAD index.
    check(all(c.cuad_index is None for c in INDIA_CATEGORIES.values()),
          "India categories have no CUAD index")

    # All 13 regex tagger tags map to at least one category.
    from checker.clause_tags import TAGS
    for tag_name in TAGS:
        mapped = _TAG_TO_CATEGORIES.get(tag_name, ())
        check(len(mapped) >= 1, f"regex tag '{tag_name}' maps to {len(mapped)} categories")

    # select_categories returns subset of ALL_CATEGORIES.
    selected = select_categories(frozenset({"Governing Law", "Indemnity"}), "nda")
    check(all(s in ALL_CATEGORIES for s in selected),
          f"selected categories all valid ({len(selected)})")
    check("Governing Law" in selected, "Governing Law in selection")
    check("Indemnification" in selected, "Indemnification from Indemnity tag")
    check("Confidentiality" in selected, "NDA gets Confidentiality")
    check("Document Name" in selected, "always-ask Document Name present")

    # Empty tags still get _ALWAYS_ASK.
    minimal = select_categories(frozenset(), "unknown")
    check(len(minimal) >= len(_ALWAYS_ASK), f"empty tags → {len(minimal)} categories")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
