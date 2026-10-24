"""Azure admission/settlement simulations; no provider network calls."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import tempfile
import unittest
from pathlib import Path

from backend.budget import BudgetTracker, FileStore
from checker import azure_model as azure, public_only
from checker.prompt_safety import wrap_untrusted


def reply(**usage):
    return {'choices': [{'message': {'content': 'Payment is due in thirty days.'},
                         'finish_reason': 'stop'}], 'usage': usage}


class AzureBudgetReservationTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'AZURE_AI_DEPLOYMENT': azure.DEFAULT_DEPLOYMENT})
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tracker = BudgetTracker(store=FileStore(Path(directory.name) / 'ledger.json'))
        text = 'Synthetic payment clause: payment is due in thirty days.'
        origin = public_only.clear_matter(text, name='budget-fixture', provider='azure', test_data=True)
        self.cleared = wrap_untrusted(text, 's1'), origin

    def test_concurrent_last_request_admits_only_one(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        entered, release = Event(), Event()
        def transport(_deployment, _body):
            entered.set()
            assert release.wait(5)
            return reply(prompt_tokens=20, completion_tokens=10)
        with patch('backend.budget.DAILY_REQUEST_CAP', 1), ThreadPoolExecutor(2) as pool:
            first = pool.submit(azure.narrate, prompt, origin=origin, budget=tracker, _transport=transport)
            assert entered.wait(5)
            try:
                with self.assertRaisesRegex(azure.ModelUnavailable, 'budget'):
                    azure.narrate(prompt, origin=origin, budget=tracker, _transport=lambda *_: reply())
            finally:
                release.set()
            assert first.result()
        assert tracker._state()['calls_today'] == 1
        assert not tracker._state()['reservations']


    def test_unknown_usage_is_conservatively_charged(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        azure.narrate(prompt, origin=origin, budget=tracker, _transport=lambda *_: reply())
        state = tracker._state()
        assert state['calls_today'] == 1
        assert state['day_inr'] > 0
        assert not state['reservations']


    def test_each_retry_is_counted_and_bounded(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        def fail(*_):
            raise azure.RateLimited('quota')
        wrapped = azure.with_backoff(azure.as_text_model(origin=origin, budget=tracker, _transport=fail),
                                    sleep=lambda _: None, tries=3)
        with self.assertRaises(azure.RateLimited):
            wrapped(prompt)
        assert tracker._state()['calls_today'] == 3
        assert tracker._state()['day_inr'] > 0
        assert not tracker._state()['reservations']


    def test_invalid_usage_does_not_credit_ledger(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        azure.narrate(prompt, origin=origin, budget=tracker,
                      _transport=lambda *_: reply(prompt_tokens=-1000, completion_tokens=float('nan')))
        assert tracker._state()['day_inr'] > 0
        assert tracker._state()['calls_today'] == 1


    def test_preflight_refusal_leaves_no_hold(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        with patch.dict('os.environ', {'AZURE_AI_API_KEY': '', 'AZURE_AI_DEPLOYMENT': ''}):
            with self.assertRaises(azure.ModelUnavailable):
                azure.narrate(prompt, origin=origin, budget=tracker)
        assert not tracker._state()['reservations']
        assert tracker._state()['calls_today'] == 0


    def test_truncated_response_still_counts(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        data = reply(prompt_tokens=20, completion_tokens=10)
        data['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(azure.ModelUnavailable):
            azure.narrate(prompt, origin=origin, budget=tracker, _transport=lambda *_: data)
        assert tracker._state()['calls_today'] == 1
        assert not tracker._state()['reservations']


    def test_invalid_explicit_price_is_rejected(self):
        tracker = self.tracker
        for amount in (-1, float('nan'), float('inf'), True, '1'):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    tracker.reserve(model='azure:test', input_tokens=1, max_tokens=1, amount_inr=amount)
                self.assertFalse(tracker._state()['reservations'])


    def test_unknown_deployment_is_refused_before_transport(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        with patch.dict('os.environ', {'AZURE_AI_DEPLOYMENT': 'unpriced-test'}):
            with self.assertRaisesRegex(azure.ModelUnavailable, 'cannot price'):
                azure.narrate(prompt, origin=origin, budget=tracker,
                              _transport=lambda *_: self.fail('transport reached'))
        assert not tracker._state()['reservations']
        assert tracker._state()['calls_today'] == 0


    def test_settlement_failure_withholds_answer(self):
        cleared, tracker = self.cleared, self.tracker
        prompt, origin = cleared
        with patch.object(tracker, 'settle', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(azure.ModelUnavailable, 'answer withheld'):
                azure.narrate(prompt, origin=origin, budget=tracker, _transport=lambda *_: reply())
        assert tracker._state()['reservations']


    def test_known_usage_settles_actual_price(self):
        cleared, tracker = self.cleared, self.tracker
        from backend.azure_pricing import price_inr
        prompt, origin = cleared
        with patch.dict('os.environ', {'AZURE_AI_DEPLOYMENT': azure.DEFAULT_DEPLOYMENT}):
            azure.narrate(prompt, origin=origin, budget=tracker,
                          _transport=lambda *_: reply(prompt_tokens=20, completion_tokens=10))
        actual, _ = price_inr(azure.DEFAULT_DEPLOYMENT, tokens_in=20, tokens_out=10)
        assert tracker._state()['day_inr'] == actual


    def test_privacy_refusal_does_not_reserve(self):
        cleared, tracker = self.cleared, self.tracker
        _, origin = cleared
        with self.assertRaises(public_only.NotPublic):
            azure.narrate('unwrapped secret', origin=origin, budget=tracker,
                          _transport=lambda *_: self.fail('transport reached'))
        assert not tracker._state()['reservations']
        assert tracker._state()['calls_today'] == 0


if __name__ == "__main__":
    unittest.main()
