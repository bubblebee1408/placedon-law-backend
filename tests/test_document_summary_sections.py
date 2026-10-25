"""A readable document summary: type, parties, key terms, dates, obligations, risks and
the questions the document leaves open -- each point tied to an exact quote, except the
open questions, which by their nature quote nothing and are labelled as such."""
import json
import unittest

from gateway import document_summary as ds

TEXT = ("This Services Agreement is made on 1 April 2026 between Kestrel Analytics Private "
        "Limited (Provider) and Marlowe Textiles LLP (Client).\n\n"
        "The Client shall pay a monthly fee of INR 3,50,000 within thirty days of each invoice.\n\n"
        "The Provider's aggregate liability shall not exceed the fees paid in the twelve months "
        "preceding the claim.")


def evidence():
    return ds.prepare({"d1": {"name": "sa.pdf", "text": TEXT, "doc_class": "services_agreement",
                              "class_reason": "matched ['services agreement']"}})


def pid(ev, needle):
    return next(p["id"] for p in ev["passages"] if needle in p["text"])


class Sections(unittest.TestCase):
    def test_every_requested_section_kind_is_accepted_with_an_exact_quote(self):
        ev = evidence()
        def item(text, needle, quote):
            return {"text": text, "citations": [{"passage_id": pid(ev, needle), "quote": quote}]}
        raw = json.dumps({"sections": [
            {"kind": "parties", "items": [item("Kestrel Analytics is the provider.", "Kestrel",
                                               "Kestrel Analytics Private Limited (Provider)")]},
            {"kind": "terms", "items": [item("A monthly fee is payable.", "monthly fee",
                                             "monthly fee of INR 3,50,000")]},
            {"kind": "dates", "items": [item("Made on 1 April 2026.", "Kestrel", "1 April 2026")]},
            {"kind": "obligations", "items": [item("The client pays within thirty days.", "monthly fee",
                                                   "within thirty days of each invoice")]},
            {"kind": "risks", "items": [item("Liability is capped.", "liability",
                                             "aggregate liability shall not exceed")]},
            {"kind": "questions", "items": [{"text": "Which law governs this agreement?", "citations": []}]},
        ]})
        out = ds.parse(raw, ev)
        self.assertEqual([s["heading"] for s in out["sections"]],
                         ["Parties", "Key terms", "Dates", "Obligations", "Risks to review",
                          "Questions the document leaves open"])
        question = out["sections"][-1]["items"][0]
        self.assertEqual((question["quotes"], question["basis"]), ([], "NOT_STATED_IN_DOCUMENT"))
        self.assertEqual(out["sections"][0]["items"][0]["basis"], "QUOTED")

    def test_document_type_comes_from_the_rules_classifier_never_the_model(self):
        ev = evidence()
        raw = json.dumps({"sections": [{"kind": "questions", "items": [
            {"text": "Is there a termination clause?", "citations": []}]}]})
        out = ds.parse(raw, ev)
        self.assertEqual(out["coverage"][0]["doc_class"], "services_agreement")
        self.assertIn("services agreement", out["coverage"][0]["class_reason"])

    def test_an_open_question_must_be_a_question_and_assert_no_figure(self):
        ev = evidence()
        for bad in ("The agreement has no governing law clause.",       # a claim, not a question
                    "Is the fee INR 4,00,000 per month?"):              # a figure from nowhere
            with self.subTest(bad=bad):
                raw = json.dumps({"sections": [{"kind": "questions", "items": [
                    {"text": bad, "citations": []}]}]})
                out = ds.parse(raw, ev)
                self.assertEqual((out["status"], out["withheld_items"]), ("NO_VALID_ITEMS", 1))

    def test_every_other_kind_still_needs_a_quote(self):
        ev = evidence()
        raw = json.dumps({"sections": [{"kind": "risks", "items": [
            {"text": "There is no indemnity.", "citations": []}]}]})
        self.assertEqual(ds.parse(raw, ev)["withheld_items"], 1)

    def test_the_prompt_asks_for_each_section_and_says_questions_quote_nothing(self):
        p = ds.prompt(evidence())
        for kind in ("parties", "terms", "dates", "obligations", "risks", "questions"):
            self.assertIn(kind, p)
        self.assertIn("questions", p.split("Every item")[1] if "Every item" in p else p)


if __name__ == "__main__":
    unittest.main()
