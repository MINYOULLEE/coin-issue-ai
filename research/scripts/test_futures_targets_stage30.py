import unittest
from verify_futures_targets_stage30 import net_return,M

class FuturesFundingTests(unittest.TestCase):
    def setUp(self):
        self.rows={i*M:dict(o=100.,h=101.,l=99.,c=100.) for i in range(5)}
        self.p=dict(entry_ts=0,side=1,lev=3)
    def test_positive_funding_long_pays_short_receives(self):
        f=[dict(fundingTime=M,fundingRate='.001',markPrice='100')]
        long=net_return(self.rows,self.p,2*M,100.,1,f)
        short=net_return(self.rows,{**self.p,'side':-1},2*M,100.,1,f)
        self.assertGreater(long['funding_price_return_pct'],0)
        self.assertLess(short['funding_price_return_pct'],0)
    def test_entry_boundary_and_future_funding_excluded(self):
        f=[dict(fundingTime=0,fundingRate='.001'),dict(fundingTime=4*M,fundingRate='.001')]
        self.assertEqual(net_return(self.rows,self.p,2*M,100.,1,f)['funding_events'],0)
    def test_missing_mark_is_explicit(self):
        f=[dict(fundingTime=M,fundingRate='.001',markPrice='')]
        result=net_return(self.rows,self.p,2*M,100.,1,f)
        self.assertEqual(result['mark_fallback'],1)
    def test_cost_stress_reduces_flat_price_net(self):
        a=net_return(self.rows,self.p,2*M,100.,1,[])
        b=net_return(self.rows,self.p,2*M,100.,2,[])
        self.assertLess(b['margin_return_pct'],a['margin_return_pct'])

if __name__=='__main__':unittest.main()
