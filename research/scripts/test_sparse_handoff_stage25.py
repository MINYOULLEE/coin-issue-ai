"""Unit tests for the research-only chronological gate, not deployed DB concurrency."""
import unittest
from verify_sparse_handoff_stage25 import simulate,H,M

class HandoffTests(unittest.TestCase):
    def run_case(self,delay,confirm=0,adverse=False):
        times=[i*H for i in range(5)]
        series={sym:{t:dict(o=10,c=10,h=10,l=10) for t in times} for sym in ['ALGO','UNI']}
        entries={0:[dict(symbol='ALGO',group='supplement',entry_ts=0,exit_bar=0,side=1,lev=3)],H:[dict(symbol='UNI',group='B',entry_ts=H,exit_bar=2*H,side=1,lev=2)]}
        minutes={(sym,H+i*M):10.1 if adverse and sym=='UNI' else 10 for sym in series for i in range(16)}
        return simulate(series,entries,times,minutes,delay,confirm)
    def test_confirm_before_entry(self):
        r=self.run_case(1)
        self.assertEqual(r['trades'],2)
        self.assertEqual(r['ledger'][0]['exit_ts'],r['ledger'][1]['entry_ts'])
        self.assertEqual(r['waited'][0]['wait_minutes'],1)
    def test_deadline_is_strict(self):
        r=self.run_case(5)
        self.assertEqual(r['trades'],1)
        self.assertEqual(r['missed'][0]['reason'],'expired_waiting_confirmation')
    def test_confirmation_not_fill_releases_gate(self):
        r=self.run_case(1,4)
        self.assertEqual(r['trades'],1)
        self.assertEqual(len(r['missed']),1)
    def test_price_rechecked_after_wait(self):
        r=self.run_case(1,adverse=True)
        self.assertEqual(r['trades'],1)
        self.assertEqual(r['missed'][0]['reason'],'adverse_price_over_0.35_pct')

if __name__=='__main__':unittest.main()
