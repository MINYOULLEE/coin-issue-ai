import unittest
from research_adaptive_exits_stage27 import features,levels,hit,H

class AdaptiveExitTests(unittest.TestCase):
    def test_features_prefix_causal(self):
        rows=[dict(t=i*H,o=100+i,h=102+i,l=99+i,c=101+i,v=1) for i in range(80)]
        short=features(rows[:40]);full=features(rows)
        self.assertEqual(short[40*H],full[40*H])
        self.assertNotIn(41*H,short)
    def test_long_short_gap_and_ambiguous(self):
        self.assertEqual(hit(dict(o=100,h=110,l=90),95,105,1),(95,'stop',True))
        self.assertEqual(hit(dict(o=92,h=100,l=90),95,105,1),(92,'stop',False))
        self.assertEqual(hit(dict(o=108,h=110,l=100),105,95,-1),(108,'stop',False))
    def test_volatility_and_structure_change_levels(self):
        f=dict(atr=2,low=94,high=106,mean=103,move=-.03,eff=.5)
        self.assertNotEqual(levels('atr_stop',f,100,1),levels('atr_stop',{**f,'atr':4},100,1))
        self.assertNotEqual(levels('structure_stop',f,100,1),levels('structure_stop',{**f,'low':90},100,1))
        self.assertEqual(levels('judgement',f,100,1,kind='rsi'),levels('mean_target',f,100,1))
        self.assertTrue(levels('judgement',f,100,1,kind='squeeze')[2])

    def test_horizon_changes_distance_not_price_percentage(self):
        f=dict(atr=2,low=94,high=106,mean=103,move=-.03,eff=.5)
        short=levels('horizon_stop',f,100,1,hours=1)
        longer=levels('horizon_stop',f,100,1,hours=4)
        self.assertAlmostEqual(100-longer[0],2*(100-short[0]))
        self.assertTrue(levels('judgement_wide',f,100,1,kind='squeeze')[2])

if __name__=='__main__':unittest.main()
