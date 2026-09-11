import unittest
import a_gap_engine_stage53 as gap

class GapTests(unittest.TestCase):
    def replay(self,side,opening):
        bars={'BTC':{0:{'o':100,'h':100,'l':100,'c':100},gap.H:{'o':opening,'h':opening,'l':opening,'c':opening}}}
        return gap.a_replay(bars,{'BTC':{0:side*.1}},{'BTC':{0:{'atr':1}}},[0,gap.H],'baseline')
    def test_long_adverse_open(self):
        r=self.replay(1,80)
        self.assertEqual(r['gap_adjustments'],1)
        self.assertLess(r['ledger'][0]['exit_price'],80)
    def test_short_adverse_open(self):
        r=self.replay(-1,120)
        self.assertEqual(r['gap_adjustments'],1)
        self.assertGreater(r['ledger'][0]['exit_price'],120)
    def test_no_gap(self):
        self.assertEqual(self.replay(1,100)['gap_adjustments'],0)

if __name__=='__main__':unittest.main()
