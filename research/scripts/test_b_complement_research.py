"""Research signal causality and data freshness regression checks."""
import unittest
import numpy as np
from research_b_complement_stage17 import patterns, opportunities

class ComplementTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(t=i*3600000, o=100+i*.01, h=102+i*.01,
                          l=98+i*.01, c=100+np.sin(i)*.5+i*.01,
                          v=100+i%11, symbol='TEST') for i in range(400)]

    def test_future_removal_does_not_change_signals(self):
        full = dict(patterns(self.rows))
        for name, sig in patterns(self.rows[:300]):
            np.testing.assert_array_equal(sig, full[name][:300])

    def test_busy_gate_and_one_hour_exit(self):
        sig = np.zeros(400, dtype=int)
        sig[200] = 1
        ops = opportunities(self.rows, sig, 1, 3, set())
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]['entry_ts'], ops[0]['exit_bar'])
        self.assertEqual(opportunities(self.rows, sig, 1, 3, {201*3600000}), [])

    def test_gap_rejects_stale_signal(self):
        sig = np.zeros(400, dtype=int)
        sig[200] = 1
        for row in self.rows[190:]:
            row['t'] += 3600000
        self.assertEqual(opportunities(self.rows, sig, 1, 3, set()), [])

if __name__ == '__main__':
    unittest.main()
