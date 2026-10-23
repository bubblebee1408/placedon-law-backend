"""Actor isolation for temporary uploads; no providers, network or paid calls."""
import unittest
from unittest.mock import patch
import uuid

from gateway.document_cache import DocumentCache


class ActorDocumentCache(unittest.TestCase):
    def test_actor_read_list_and_delete_are_private(self):
        cache = DocumentCache()
        alice = cache.for_actor('firm', 'alice')
        bob = cache.for_actor('firm', 'bob')
        alice['same-hash'] = {'text': 'private clause', 'name': 'alice.txt'}
        self.assertIsNone(bob.get('same-hash'))
        self.assertEqual(list(bob), [])
        with self.assertRaises(KeyError):
            del bob['same-hash']
        bob['same-hash'] = {'text': 'own copy', 'name': 'bob.txt'}
        self.assertEqual(alice['same-hash']['name'], 'alice.txt')
        self.assertEqual(bob['same-hash']['name'], 'bob.txt')
        self.assertIsNone(cache.for_actor('other-firm', 'alice').get('same-hash'))

    def test_missing_identity_is_rejected(self):
        cache = DocumentCache()
        for tenant, actor in [('', 'alice'), ('firm', ''), ('firm', None), ('firm', ' ')]:
            with self.subTest(tenant=tenant, actor=actor), self.assertRaises(ValueError):
                cache.for_actor(tenant, actor)

    def test_tenant_budget_cannot_be_bypassed_with_many_actors(self):
        cache = DocumentCache(total_bytes=1000, tenant_bytes=80)
        for i in range(20):
            cache.for_actor('firm', str(i))['doc'] = {'text': 'x' * 35}
        self.assertLessEqual(sum(size for _, size, _ in cache._rows.values()), 80)
        self.assertEqual(len(cache.for_actor('firm', '0')), 0)
        self.assertEqual(len(cache.for_actor('firm', '19')), 1)

    def test_expiry_applies_across_actor_views(self):
        now = [0]
        cache = DocumentCache(ttl_seconds=5, clock=lambda: now[0])
        cache.for_actor('firm', 'alice')['a'] = {'text': 'hello'}
        cache.for_actor('firm', 'bob')['b'] = {'text': 'world'}
        now[0] = 6
        self.assertEqual(len(cache.for_actor('firm', 'alice')), 0)
        self.assertEqual(len(cache.for_actor('firm', 'bob')), 0)


class UploadHttpIsolation(unittest.TestCase):
    def test_request_uses_authenticated_actor_not_payload_or_shared_memory(self):
        from fastapi.testclient import TestClient
        from gateway.app import create_app
        from gateway.auth import KeyStore
        from gateway import verbs
        tenant = str(uuid.uuid4())
        alice, bob = str(uuid.uuid4()), str(uuid.uuid4())
        keys = KeyStore()
        ka, _ = keys.mint(tenant_id=tenant, actor=alice, role='lawyer')
        kb, _ = keys.mint(tenant_id=tenant, actor=bob, role='lawyer')
        app = create_app(db_url='', keys=keys)
        # Stop before execution, after the real HTTP context reaches the resolver.
        # This observes the production lookup boundary without invoking a model.
        observed = []
        def probe(ids, ctx, matter, **kw):
            observed.append((ctx.actor, ctx.documents.get(ids[0])))
            return None, {'status': 'REFUSED', 'code': 'TEST_ONLY'}
        with TestClient(app) as client, patch.object(verbs, '_resolve_conversation_documents', probe):
            ra = client.post('/v2/documents/upload', headers={'Authorization': f'Bearer {ka}'},
                json={'name': 'private-alice.txt', 'text': 'Synthetic confidential clause.'})
            self.assertEqual(ra.status_code, 200)
            doc = ra.json()['document_id']
            for key in (kb, ka):
                response = client.post('/v2/conversation/send', headers={'Authorization': f'Bearer {key}'},
                    json={'text': 'Review this document', 'file_ids': [doc], 'actor': alice,
                          'task_override': 'REVIEW_DOCUMENT'})
                self.assertEqual(response.json()['code'], 'TEST_ONLY')
            self.assertEqual(observed[0], (bob, None))
            self.assertEqual(observed[1][0], alice)
            self.assertEqual(observed[1][1]['name'], 'private-alice.txt')


if __name__ == '__main__':
    unittest.main()
