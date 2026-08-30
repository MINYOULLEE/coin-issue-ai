import unittest
import replay_reserved_margin_stage16 as m

class ReservedMarginTests(unittest.TestCase):
    def test_fixed_quantity_and_simultaneous_allocation(self):
        times=[0,3600000]
        bars={0:dict(o=100.,h=100.,l=100.,c=100.),3600000:dict(o=100.,h=110.,l=100.,c=110.)}
        series={'AVAX':bars,'ICP':bars}
        entries={0:[dict(symbol=s,side=1,lev=2,entry_ts=0,exit_bar=3600000) for s in series]}
        result=m.replay(series,entries,times,1.15)
        self.assertEqual(result['trades'],2)
        self.assertEqual(result['margin_clipped'],2)
        self.assertLessEqual(sum(x['margin'] for x in result['ledger']),95.)
        for trade in result['ledger']:
            qty=trade['margin']*2/(100*(1+m.SLIP))
            self.assertAlmostEqual(qty,trade['quantity'])
            expected=qty*(110*(1-m.SLIP)-100*(1+m.SLIP))-qty*(100*(1+m.SLIP)+110*(1-m.SLIP))*m.FEE-qty*200*m.FUNDING_PER_HOUR
            self.assertAlmostEqual(expected,trade['net_pnl'])
        self.assertAlmostEqual(100+sum(x['net_pnl'] for x in result['ledger']),result['end_usd'])

    def test_short_uses_linear_adverse_price(self):
        times=[0]
        series={'ICP':{0:dict(o=100.,h=150.,l=99.,c=100.)}}
        entries={0:[dict(symbol='ICP',side=-1,lev=5,entry_ts=0,exit_bar=0)]}
        result=m.replay(series,entries,times,.2)
        self.assertEqual(result['liquidation_proxy_count'],1)
        self.assertLess(result['end_usd'],100.)

if __name__=='__main__':unittest.main()
