"""Fixed fee, separately varied slippage/funding; offline research only."""
import json,inspect
from datetime import datetime,timezone
import research_b_sparse_stage20 as p
s=p.s

def main():
    prior=json.loads((p.OUT/'combinations.json').read_text());best=prior['results'][0]
    series,base,times=s.b.prepare();entries={t:[dict(x) for x in ps] for t,ps in base.items()};busy=set()
    for t,ps in base.items():
        for x in ps:busy.update(range(t,x['exit_bar']+3600000,3600000))
    for ident in best['patterns']:
        sym,name=ident.split(':');rows=s.core.read_candles(s.core.DATA_DIR/f'{sym}USDT_1h.csv')
        for row in rows:row['symbol']=sym
        series[sym]={r['t']:r for r in rows}
        for x in s.opportunities(rows,dict(p.signals(rows))[name],1,3,busy):entries.setdefault(x['entry_ts'],[]).append({**x,'weight_scale':best['target_fraction_per_signal']/1.15})
    src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    def runner(slip,funding):
        env={**s.b.__dict__,'FEE':.0005,'SLIP':slip,'FUNDING_PER_HOUR':funding/8}
        exec(src,env);return env['replay']
    results=[]
    for slip in (.0002,.0003,.0004,.0005):
        for funding in (0,.0001,.0002,.0004):
            run=runner(slip,funding)
            full=run(series,entries,times,1.15);baseline=run(series,base,times,1.15)
            a=[x for x in full['ledger'] if x['symbol'] in s.b.SYMBOLS];extra=[x for x in full['ledger'] if x['symbol'] not in s.b.SYMBOLS]
            overlap=sum(any(x['entry_ts']<y['exit_ts'] and x['exit_ts']>y['entry_ts'] for y in a) for x in extra)
            assert overlap==0
            if slip==.0002 and funding==.0001:assert abs(full['end_usd']-best['full']['end_usd'])<1e-6
            r=dict(fee_each_side_pct=.05,slippage_each_side_pct=slip*100,funding_8h_pct=funding*100,baseline=s.compact(baseline),combination=s.compact(full),holding_overlap_trades=overlap)
            results.append(r);print('COST',slip,funding,round(full['return_pct'],2),flush=True)
    lo,hi=.0002,.0005
    for _ in range(12):
        mid=(lo+hi)/2
        value=runner(mid,.0001)(series,entries,times,1.15)['return_pct']
        if value>=1000000:lo=mid
        else:hi=mid
    cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
    segments=[]
    for slip in (.0002,.0003,.0004):
        run=runner(slip,.0001)
        segments.append(dict(slippage_pct=slip*100,results=[dict(baseline=s.compact(run(series,base,times,1.15,start=cuts[k],end=cuts[k+1])),combination=s.compact(run(series,entries,times,1.15,start=cuts[k],end=cuts[k+1]))) for k in range(3)]))
    output=dict(generated_at=datetime.now(timezone.utc).isoformat(),fee_reference='Prior read-only A history: 43/45 closed records approximately 0.05% per turnover. Reference for research, not B account fee verification.',a_entry_reference=dict(n=10,favorable=7,adverse=3,mean_signed_pct=-.018763014208518225,mean_abs_pct=.05381024815289015),notes=['Do not treat absolute price difference as a realized cost','Fixed adverse slippage on entry AND exit; A samples only entry and signal-reference differences','Funding always paid and accrued hourly: sensitivity assumption, not actual settlement history','No new signal selection, live changes or deployment'],patterns=best['patterns'],target_fraction_per_signal=best['target_fraction_per_signal'],results=results,slippage_threshold_for_million_pct=[lo*100,hi*100],threshold_assumes_fee_pct=.05,threshold_assumes_funding_8h_pct=.01,segments=segments,independent_validation=False)
    (p.OUT/'cost_components_stage23.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print('DONE threshold',output['slippage_threshold_for_million_pct'],flush=True)

if __name__=='__main__':main()
