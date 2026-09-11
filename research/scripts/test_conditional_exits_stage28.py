import unittest
import research_conditional_exits_stage28 as r

class ConditionalExitTests(unittest.TestCase):
    def history(self):
        return [dict(symbol='ETH',side=1,t=i,known_at=i+1,win=True,mae=i/10,mfe=2,regime=(1,0)) for i in range(30)]
    def current(self):
        return dict(symbol='ETH',side=1,t=50,regime=(1,0))
    def test_future_and_wrong_symbol_direction_excluded(self):
        hist=self.history();cur=self.current()
        extra=[{**hist[0],'known_at':51},{**hist[0],'symbol':'AVAX'},{**hist[0],'side':-1}]
        self.assertEqual(r.select_history(hist,cur,False),r.select_history(hist+extra,cur,False))
    def test_minimum_winners_and_original_close(self):
        self.assertEqual(r.select_history(self.history()[:19],self.current(),False),[])
        hist=self.history()[:20]
        self.assertEqual(len(r.select_history(hist,self.current(),False)),20)
        hist[-1]['known_at']=51
        self.assertEqual(r.select_history(hist,self.current(),False),[])
    def test_regime_fallback_and_matching(self):
        hist=self.history();cur=self.current()
        for x in hist[:19]:x['regime']=(0,1)
        self.assertEqual(len(r.select_history(hist,cur,True)),30)
        hist[18]['regime']=(1,0)
        self.assertEqual(len(r.select_history(hist,cur,True)),12)
    def test_losing_examples_do_not_set_winner_quantile(self):
        hist=self.history()
        for x in hist[:11]:x['win']=False
        self.assertEqual(r.select_history(hist,self.current(),False),[])
    def test_generated_runner_without_adaptive_exit_matches_baseline(self):
        H=r.H
        series={'ETH':{i*H:dict(o=100.,h=101.,l=99.,c=100.5) for i in range(3)}}
        entries={0:[dict(symbol='ETH',side=1,lev=3,entry_ts=0,exit_bar=H)]}
        times=[0,H,2*H]
        direct=r.prev.b.replay(series,entries,times,1.15)
        self.assertEqual(r.runner({})(series,entries,times,1.15),direct)
    def test_adaptive_close_releases_at_earlier_boundary(self):
        H=r.H
        series={'ETH':{i*H:dict(o=100.,h=101.,l=99.,c=100.5) for i in range(3)}}
        entries={0:[dict(symbol='ETH',side=1,lev=3,entry_ts=0,exit_bar=H)]}
        result=r.runner({('ETH',0,0):99.5})(series,entries,[0,H,2*H],1.15)
        self.assertEqual(result['ledger'][0]['exit_ts'],H)
        self.assertLess(result['ledger'][0]['net_pnl'],0)

    def test_missing_candle_not_used_as_a_training_label(self):
        H=r.H
        series={'ETH':{0:dict(o=100.,h=101.,l=99.,c=100.)}}
        entries={0:[dict(symbol='ETH',side=1,lev=3,entry_ts=0,exit_bar=H)]}
        self.assertEqual(r.samples(series,entries,{'ETH':{}}),[])

    def test_full_future_dataset_cannot_change_earlier_decisions(self):
        H=r.H
        series={'ETH':{i*H:dict(o=100.,h=101.,l=99.5,c=100.5) for i in range(160)}}
        entries={i*H:[dict(symbol='ETH',side=1,lev=3,entry_ts=i*H,exit_bar=i*H)] for i in range(0,160,2)}
        fs={'ETH':{i*H:dict(atr=1.,move=.01,eff=.5) for i in range(160)}}
        rule=('target_only_q80',None,.8,False,False)
        full=r.learned_exits(series,entries,fs,rule)
        prefix_series={'ETH':{t:x for t,x in series['ETH'].items() if t<80*H}}
        prefix_entries={t:x for t,x in entries.items() if t<80*H}
        prefix=r.learned_exits(prefix_series,prefix_entries,fs,rule)
        self.assertEqual(prefix[1],[d for d in full[1] if d['entry_ts']<80*H])
        self.assertEqual(prefix[0],{k:v for k,v in full[0].items() if k[1]<80*H})

if __name__=='__main__':unittest.main()
