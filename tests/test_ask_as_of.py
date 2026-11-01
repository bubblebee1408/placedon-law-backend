"""Ask "as of" a past date (PLACEDON_ASK_AS_OF). No provider keys, network, or paid calls.

s.173 gained its second proviso w.e.f. 7-5-2018 (Act 1 of 2018): it is the before/after case.
s.149 before 7-5-2018 is PARTIAL (two substitutions whose earlier wording is not quoted).
s.96 before 13-6-2018 has an amendment the source text does not let us locate: nothing shown.
"""
from dataclasses import replace
from datetime import date
import unittest
from unittest.mock import patch
import uuid

from agents import research_question as rq
from checker import quoted_span
from checker.as_of import UNRECOVERABLE
from gateway import envelope, verbs
from gateway.store import MemoryBackend

TODAY = "2026-10-10T00:00:00Z"
S173 = "How many meetings of the Board must a company hold under section 173?"
S149 = "What does section 149 require about the number of directors?"
S96 = "What is the time limit for holding an annual general meeting under section 96?"
PROVISO = ("Provided further that where there is quorum in a meeting through physical "
           "presence of directors")
ON = {verbs.ASK_AS_OF_ENV: "1"}


def _flat(text: str) -> str:
    return " ".join(text.split())


def model_for(question: str, as_of):
    """Quotes the 2018 proviso when its source holds it, else the opening of the section."""
    sources = tuple(s for s, _ in rq.evidence(question, as_of=as_of))

    def call(_prompt: str) -> str:
        flat = _flat(sources[0].text)
        quote = PROVISO if PROVISO in flat else flat[:180]
        return f"{quoted_span.SENTENCE_TAG} {quote}\n{quoted_span.QUOTE_TAG} {quote}\n"
    return lambda _origin: call


class AskAsOf(unittest.TestCase):
    def setUp(self):
        self.store = MemoryBackend()

    def ctx(self, question, as_of=None, **kw):
        return verbs.Context(store=self.store, clock=lambda: TODAY, actor="lawyer-1",
                             model_for=model_for(question, as_of), **kw)

    def send(self, question, as_of=None, law_date=None):
        args = {"text": question, "request_id": str(uuid.uuid4())}
        if as_of:
            args["as_of"] = as_of
        return verbs._conversation_send(args, self.ctx(question, law_date))

    # ── flag off: exactly today's refusal ───────────────────────────────────
    def test_flag_off_refuses_exactly_as_before(self):
        with patch.dict("os.environ", {verbs.ASK_AS_OF_ENV: ""}):
            got = self.send(S173, "2017-01-01")
            ask = verbs._ask({"question": S173, "as_of": "2017-01-01"}, self.ctx(S173))
        expected = {"status": "REFUSED", "code": "AS_OF_UNSUPPORTED",
                    "detail": "This conversation reads current law only. Ask without as_of."}
        self.assertEqual(got, expected)
        self.assertEqual(ask, expected)

    def test_flag_off_today_still_answers_current_law(self):
        with patch.dict("os.environ", {verbs.ASK_AS_OF_ENV: ""}):
            got = self.send(S173, "2026-10-10")
        env = got["envelope"]
        self.assertEqual(env["as_of"], "2026-10-10")
        self.assertNotIn("law_as_of", got["metadata"])
        self.assertTrue(any(PROVISO in _flat(c["quote"]) for c in env["citations"]))

    # ── before and after the amendment: different wording ───────────────────
    def test_section_answered_before_and_after_its_2018_amendment(self):
        with patch.dict("os.environ", ON):
            before = self.send(S173, "2017-01-01", date(2017, 1, 1))
            after = self.send(S173, "2019-01-01", date(2019, 1, 1))
        b, a = before["envelope"], after["envelope"]
        self.assertEqual(envelope.errors(b), [])
        self.assertEqual((b["status"], b["as_of"]), ("ANSWERED", "2017-01-01"))
        self.assertEqual((a["status"], a["as_of"]), ("ANSWERED", "2019-01-01"))
        self.assertFalse(any(PROVISO in _flat(c["quote"]) for c in b["citations"]))
        self.assertTrue(any(PROVISO in _flat(c["quote"]) for c in a["citations"]))
        self.assertTrue(b["text_blocks"][1]["text"].startswith("Law as it stood on 1 January 2017."))
        self.assertIn("rebuilt from India Code's amendment notes", b["text_blocks"][1]["text"])
        self.assertEqual(b["text_blocks"][0]["citation_ids"], [c["id"] for c in b["citations"]])
        # 2019: nothing after it was rolled back, so nothing is called rebuilt.
        self.assertEqual(a["text_blocks"][1]["text"], "Law as it stood on 1 January 2019.")
        self.assertEqual(before["metadata"]["law_as_of"]["date"], "2017-01-01")
        self.assertTrue(before["metadata"]["law_as_of"]["rebuilt"])

    def test_verifier_checks_quotes_against_the_past_text_not_todays(self):
        # A model that quotes the 2018 proviso for a 2017 question is quoting law that did
        # not yet exist. The verifier reads the 2017 text, so nothing traces.
        sources = tuple(s for s, _ in rq.evidence(S173, as_of=date(2017, 1, 1)))
        liar = (f"{quoted_span.SENTENCE_TAG} {PROVISO}\n{quoted_span.QUOTE_TAG} {PROVISO}\n")
        out = rq.answer(S173, model=lambda _p: liar, available=("gemini",),
                        as_of=date(2017, 1, 1))
        self.assertEqual((out.status, out.code), ("REFUSED", "NOTHING_TRACED"))
        self.assertNotIn(PROVISO, _flat(sources[0].text))

    def test_source_panel_reverifies_against_that_dates_wording(self):
        with patch.dict("os.environ", ON):
            before = self.send(S173, "2017-01-01", date(2017, 1, 1))
            after = self.send(S173, "2019-01-01", date(2019, 1, 1))
            cid = before["conversation_id"]
            c1 = before["envelope"]["citations"][0]
            got = verbs._citation_get({"citation_id": c1["id"], "conversation_id": cid},
                                      self.ctx(S173))
            # The 2019 proviso quote does not exist in the 2017 text; asked against 2017
            # through the caller's as_of it fails, against its own stored date it passes.
            c19 = next(c for c in after["envelope"]["citations"] if PROVISO in _flat(c["quote"]))
            own = verbs._citation_get({"citation_id": c19["id"],
                                       "conversation_id": after["conversation_id"]},
                                      self.ctx(S173))
        self.assertTrue(got["reverified"], got["reverified_note"])
        self.assertIn("rebuilt to 2017-01-01", got["reverified_note"])
        self.assertEqual(got["law_as_of"]["date"], "2017-01-01")
        self.assertNotIn(PROVISO, _flat(got["section"]["text"]))
        self.assertTrue(own["reverified"])
        self.assertFalse(verbs.verify_citation(c19, "2017-01-01")[0])

    # ── partly known ────────────────────────────────────────────────────────
    def test_partial_names_the_unknown_parts(self):
        with patch.dict("os.environ", ON):
            got = self.send(S149, "2017-01-01", date(2017, 1, 1))
        env = got["envelope"]
        self.assertEqual(env["status"], "PARTIAL")
        lead = env["text_blocks"][1]["text"]
        self.assertIn("Part of s.149 on that date is not known", lead)
        self.assertIn("for sub-section (3)", lead)
        self.assertIn("for Clause (d)", lead)
        self.assertTrue(any(UNRECOVERABLE in _flat(s.text)
                            for s, _ in rq.evidence(S149, as_of=date(2017, 1, 1))))
        section = got["metadata"]["law_as_of"]["sections"][0]
        self.assertEqual((section["provision"], section["fidelity"]), ("s.149", "PARTIAL"))

    # ── nothing recoverable ─────────────────────────────────────────────────
    def test_nothing_recoverable_refuses_with_a_reason(self):
        with patch.dict("os.environ", ON):
            got = verbs._ask({"question": S96, "as_of": "2017-01-01"}, self.ctx(S96))
        self.assertEqual((got["status"], got["code"]), ("REFUSED", "AS_OF_NOT_RECOVERABLE"))
        self.assertIn("s.96 as it stood on 1 January 2017 cannot be recovered", got["detail"])
        env = verbs._envelope_for("RESEARCH_QUESTION", got, as_of="2017-01-01", ctx=self.ctx(S96))
        self.assertEqual((env["status"], env["citations"]), ("ABSTAINED", []))

    # ── out of range ────────────────────────────────────────────────────────
    def test_dates_outside_2014_to_today_are_refused_plainly(self):
        with patch.dict("os.environ", ON):
            early = self.send(S173, "2014-03-31")
            future = self.send(S173, "2026-10-11")
            first = self.send(S173, "2014-04-01", date(2014, 4, 1))
            bad = self.send(S173, "2017-02-30")
        self.assertEqual(early["code"], "AS_OF_OUT_OF_RANGE")
        self.assertIn("1 April 2014", early["detail"])
        self.assertIn("1956", early["detail"])
        self.assertEqual(future["code"], "AS_OF_OUT_OF_RANGE")
        self.assertIn("future", future["detail"])
        self.assertEqual(first["envelope"]["as_of"], "2014-04-01")
        self.assertEqual(bad["code"], "BAD_REQUEST")

    # ── only research questions take a past date ───────────────────────────
    def test_other_tasks_refuse_a_past_date(self):
        with patch.dict("os.environ", ON):
            review = verbs._conversation_send(
                {"text": "Check these minutes.", "request_id": str(uuid.uuid4()),
                 "task_override": "REVIEW_DOCUMENT", "as_of": "2014-04-01"}, self.ctx(S173))
            draft = verbs._conversation_send(
                {"text": "Draft a memo.", "request_id": str(uuid.uuid4()),
                 "task_override": "DRAFT", "as_of": "2017-01-01"}, self.ctx(S173))
        for got in (review, draft):
            self.assertEqual((got["status"], got["code"]), ("REFUSED", "AS_OF_UNSUPPORTED"))
            self.assertIn("only to research questions", got["detail"])

    # ── wholesale replacement: nothing but placeholders is nothing ─────────
    def test_section_replaced_wholesale_is_not_recoverable(self):
        q = "What does section 185 say about loans to directors?"
        self.assertTrue(any(s.source_id.endswith("s.185") for s, _ in rq.evidence(q)))
        self.assertFalse(any(s.source_id.endswith("s.185")
                             for s, _ in rq.evidence(q, as_of=date(2017, 1, 1))))
        with patch.dict("os.environ", ON):
            got = verbs._ask({"question": q, "as_of": "2017-01-01"}, self.ctx(q, date(2017, 1, 1)))
        self.assertEqual(got.get("code"), "AS_OF_NOT_RECOVERABLE", got)
        self.assertIn("s.185", got["detail"])

    def test_a_placeholder_is_never_a_quotation(self):
        sources = tuple(s for s, _ in rq.evidence(S149, as_of=date(2017, 1, 1)))
        self.assertTrue(sources[0].undetermined, "masked spans are marked for the verifier")
        # A model that quotes our placeholder: whatever the verifier makes of the sentence,
        # no citation may carry the placeholder as if it were statute.
        liar = f"{quoted_span.SENTENCE_TAG} {UNRECOVERABLE}\n{quoted_span.QUOTE_TAG} {UNRECOVERABLE}\n"
        ctx = verbs.Context(store=self.store, clock=lambda: TODAY, actor="lawyer-1",
                            model_for=lambda _o: (lambda _p: liar))
        with patch.dict("os.environ", ON):
            got = verbs._conversation_send({"text": S149, "request_id": str(uuid.uuid4()),
                                            "as_of": "2017-01-01"}, ctx)
        self.assertFalse(any(UNRECOVERABLE[:20] in c["quote"] for c in got["envelope"]["citations"]))
        provision = verbs._provision_citations(["Companies Act 2013, s.149"], "2017-01-01")
        self.assertFalse(any(UNRECOVERABLE[:20] in c["quote"] for c in provision))

    # ── firm isolation ──────────────────────────────────────────────────────
    def test_past_date_does_not_open_another_persons_or_firms_citation(self):
        with patch.dict("os.environ", ON):
            mine = self.send(S173, "2017-01-01", date(2017, 1, 1))
            args = {"citation_id": mine["envelope"]["citations"][0]["id"],
                    "conversation_id": mine["conversation_id"], "as_of": "2017-01-01"}
            colleague = verbs._citation_get(args, replace(self.ctx(S173), actor="lawyer-2"))
            other_firm = verbs._citation_get(
                args, replace(self.ctx(S173), store=MemoryBackend(tenant_id=str(uuid.uuid4()))))
        self.assertEqual(colleague["code"], "NOT_FOUND")
        self.assertEqual(other_firm["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
