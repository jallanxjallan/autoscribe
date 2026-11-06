import unittest
from live_acceptance_poll import wait_for_terminal_response


class Clock:
    def __init__(self): self.now = 0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class AcceptancePollingTests(unittest.TestCase):
    def test_failed_execution_then_published_failed_response_is_delivery_only(self):
        clock = Clock(); budgets = []; operations = []
        terminal = {'state':'completed','response_sha256':'a'*64,
                    'error':'smoke-test rejected malformed output'}
        receipts = iter([{'state':'running'}, {'state':'failed','response_sha256':None}, terminal])
        def status(budget):
            operations.append('status'); budgets.append(budget)
            return next(receipts)
        result = wait_for_terminal_response(status, timeout=1, interval=.1,
            monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(result, terminal)
        self.assertEqual(result['error'], 'smoke-test rejected malformed output')
        self.assertNotIn('processing_success', result)
        self.assertEqual(operations, ['status']*3)
        self.assertGreater(budgets[0], budgets[-1])

    def test_failed_execution_without_response_times_out_instead_of_passing(self):
        clock = Clock(); calls = []
        def failed(budget):
            calls.append(budget)
            return {'state':'failed','response_sha256':None}
        with self.assertRaisesRegex(TimeoutError, "last state='failed'"):
            wait_for_terminal_response(failed, timeout=1, interval=.25,
                monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(clock.now, 1)
        self.assertEqual(len(calls), 4)

    def test_invalid_delivery_receipts_and_exceeded_budget_fail_closed(self):
        for receipt in ({'state':'absent'}, {'state':'completed','response_sha256':None}):
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                wait_for_terminal_response(lambda budget: receipt)
        clock = Clock()
        def late(budget):
            clock.now += budget + .01
            return {'state':'completed','response_sha256':'a'*64}
        with self.assertRaises(TimeoutError):
            wait_for_terminal_response(late, timeout=1,
                monotonic=clock.monotonic, sleep=clock.sleep)
