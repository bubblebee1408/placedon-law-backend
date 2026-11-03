"""032: the firm's company profile -- saved once, read back with provenance, used by
`events.assess` and `ask` when a request carries no company facts of its own."""
import unittest
import uuid

from gateway import verbs
from gateway.roles import LAWYER, REQUIRED, VIEWER
from gateway.store import MemoryBackend

V = verbs.by_name()
MCA = "MCA master data, as uploaded by the user on 2026-10-01"
LISTED = {"field": "listed", "value": "yes", "confirmed": True}
STATE = {"field": "state", "value": "Maharashtra", "basis": "COMPANY_FACT",
         "quoted_span": "Registered Address: 5 Fort, Mumbai, Maharashtra",
         "source_label": MCA, "confirmed": True}
REASON = "Confirmed on the Company page"


class CompanyProfile(unittest.TestCase):
    def setUp(self):
        self.store = MemoryBackend(tenant_id=str(uuid.uuid4()))
        self.actor = str(uuid.uuid4())
        self.ctx = verbs.Context(store=self.store, actor=self.actor, role="lawyer")

    def save(self, facts, ctx=None):
        return V["company_profile.set"].run({"facts": facts, "reason": REASON}, ctx or self.ctx)

    def test_roles(self):
        self.assertEqual(REQUIRED["company_profile.get"], VIEWER)
        self.assertEqual(REQUIRED["company_profile.set"], LAWYER)

    def test_set_then_get_carries_provenance(self):
        self.assertEqual(self.save([LISTED, STATE])["status"], "SAVED")
        got = {f["field"]: f for f in V["company_profile.get"].run({}, self.ctx)["facts"]}
        self.assertEqual(set(got), {"listed", "state"})
        self.assertEqual(got["listed"]["label"], "you told us")
        self.assertIsNone(got["listed"]["uploaded_on"])
        self.assertEqual(got["state"]["uploaded_on"], "2026-10-01")
        self.assertEqual(got["state"]["quoted_span"], STATE["quoted_span"])
        for f in got.values():
            self.assertEqual(f["confirmed_by"], self.actor)
            self.assertTrue(f["confirmed_at"])
            self.assertFalse(f["can_verify"])

    def test_refusals(self):
        for args, code in (({"facts": [dict(LISTED, confirmed=False)], "reason": REASON}, "BAD_REQUEST"),
                           ({"facts": [LISTED]}, "BAD_REQUEST"),
                           ({"facts": [LISTED], "reason": "short"}, "REASON_REQUIRED"),
                           ({"facts": [{"field": "din", "value": "1", "confirmed": True}],
                             "reason": REASON}, "BAD_REQUEST")):
            with self.subTest(args=args):
                self.assertEqual(V["company_profile.set"].run(args, self.ctx)["code"], code)
        self.assertEqual(V["company_profile.get"].run({}, self.ctx)["facts"], [])
        self.assertEqual(V["company_profile.get"].run({}, verbs.Context())["code"], "NO_STORE")

    def test_changes_supersede_and_nothing_is_deleted(self):
        self.save([LISTED, STATE])
        first = {r["field"]: r["fact_id"] for r in self.store.read_company_profile()}
        self.save([dict(LISTED, value="no")])         # state removed, listed changed
        now = self.store.read_company_profile()
        self.assertEqual([(r["field"], r["value"]) for r in now], [("listed", "no")])
        self.assertEqual(len(self.store.company_profile), 3)
        gone = [r for r in self.store.company_profile if r["superseded_at"]]
        self.assertEqual({r["fact_id"] for r in gone}, set(first.values()))
        self.assertTrue(all(r["superseded_by"] == self.actor for r in gone))
        # Unchanged facts keep their row (and so who confirmed them, and when).
        self.save([dict(LISTED, value="no")])
        self.assertEqual(len(self.store.company_profile), 3)

    def test_events_assess_falls_back_to_the_profile(self):
        bare = V["events.assess"].run({"event": "share_allotment"}, self.ctx)
        self.assertNotIn("SEBI_LODR", bare["body_ids"])
        self.save([LISTED])
        used = V["events.assess"].run({"event": "share_allotment"}, self.ctx)
        self.assertIn("SEBI_LODR", used["body_ids"])
        self.assertEqual(used["company_facts"]["from"], "company_profile")
        # Explicit request facts win, both ways they can be sent.
        explicit = V["events.assess"].run({"event": "share_allotment", "company_facts": []}, self.ctx)
        self.assertNotIn("SEBI_LODR", explicit["body_ids"])
        override = V["events.assess"].run(
            {"event": "share_allotment", "facts": {"listed": False}}, self.ctx)
        self.assertNotIn("SEBI_LODR", override["body_ids"])
        self.assertEqual(override["company_facts"]["overridden_by_request"], ["listed"])
        self.assertEqual(override["company_facts"]["used"], [])

    def test_events_assess_refuses_when_the_profile_cannot_be_read(self):
        # Codex on #149 (P1): a failed read is not "no profile". Assessing without the
        # stored facts would silently drop bodies (SEBI_LODR for a listed firm).
        self.save([LISTED])

        def broken():
            raise ConnectionError("db down")
        self.store.read_company_profile = broken
        out = V["events.assess"].run({"event": "share_allotment"}, self.ctx)
        self.assertEqual(out["status"], "REFUSED")
        self.assertEqual(out["code"], "STORAGE_UNAVAILABLE")
        # Facts sent with the request do not need the profile, so they still assess.
        sent = V["events.assess"].run(
            {"event": "share_allotment", "company_facts": [LISTED]}, self.ctx)
        self.assertIn("SEBI_LODR", sent["body_ids"])
        # `ask` only SHOWS the profile (it never steers the answer), so it still answers.
        q = {"question": "What is the quorum for a board meeting?", "sources": ["vault"]}
        self.assertNotIn("user_facts", V["ask"].run(q, self.ctx))

    def test_conversation_event_turn_keeps_the_profile_attribution(self):
        # Codex on #149 (P2): the stored fact that added SEBI bodies must ride the turn.
        self.save([LISTED])
        out = V["conversation.send"].run(
            {"text": "We are allotting shares next week.", "event": "share_allotment"},
            self.ctx)
        self.assertIn("SEBI_LODR", [b["body_id"] for b in out["envelope"]["bodies"]])
        for where in (out["company_facts"], out["metadata"]["company_facts"]):
            self.assertEqual(where["from"], "company_profile")
            self.assertEqual([f["field"] for f in where["used"]], ["listed"])
            self.assertEqual(where["overridden_by_request"], [])
        saved = V["conversation.get"].run({"conversation_id": out["conversation_id"]}, self.ctx)
        reply = [m for m in saved["messages"] if m["message_id"] == out["message_id"]][0]
        self.assertEqual(reply["metadata"]["company_facts"]["from"], "company_profile")

    def test_ask_shows_the_profile_without_caching_it(self):
        q = {"question": "What is the quorum for a board meeting?", "sources": ["vault"]}
        self.assertNotIn("user_facts", V["ask"].run(q, self.ctx))
        self.save([LISTED, {"field": "company_class", "value": "private", "confirmed": True}])
        out = V["ask"].run(q, self.ctx)
        self.assertEqual(out["user_facts_from"], "company_profile")
        self.assertEqual([f["field"] for f in out["user_facts"]], ["listed"])
        self.assertNotIn("user_facts", V["ask"].run(dict(q, company_facts=[]), self.ctx))

    def test_another_firm_never_sees_this_profile(self):
        self.save([LISTED])
        other = verbs.Context(store=MemoryBackend(tenant_id=str(uuid.uuid4())),
                              actor=str(uuid.uuid4()), role="lawyer")
        self.assertEqual(V["company_profile.get"].run({}, other)["facts"], [])
        self.assertNotIn("SEBI_LODR",
                         V["events.assess"].run({"event": "share_allotment"}, other)["body_ids"])


if __name__ == "__main__":
    unittest.main()
