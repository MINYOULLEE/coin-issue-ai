import unittest
import a_policy_engine_stage57 as engine

class PolicyTests(unittest.TestCase):
    def run_case(self,policy,maps,move=0):
        engine.POLICY=policy
        times=[i*engine.H for i in range(8)]
        bars={'BTC':{t:{'o':100,'h':100,'l':100,'c':100} for t in [-engine.H]+times}}
        fs={'BTC':{t:{'atr':1,'mean':100,'move':move,'eff':.5} for t in times}}
        return engine.a_replay(bars,{'BTC':maps},fs,times,'baseline')
    def test_time_exit_does_not_reenter_same_boundary(self):
        r=self.run_case('hold_6',{0:.1,6*engine.H:.1})
        self.assertEqual(r['trades'],1)
        self.assertEqual(r['ledger'][0]['exit_ts'],6*engine.H)
        self.assertEqual(r['ledger'][0]['reason'],'time_limit')
    def test_confirmation_rejects_opposing_move(self):
        self.assertEqual(self.run_case('confirm_6h',{0:.1},-.01)['trades'],0)
    def test_weakening_closes_next_boundary(self):
        r=self.run_case('weak_move',{0:.1},-.01)
        self.assertEqual(r['ledger'][0]['exit_ts'],engine.H)
        self.assertEqual(r['ledger'][0]['reason'],'opposing_completed_6h_move')

if __name__=='__main__':unittest.main()
