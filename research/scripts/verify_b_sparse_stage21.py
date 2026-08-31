"""Post-selection concentration stress, not independent validation."""
import json,inspect
import research_b_sparse_stage20 as p
s=p.s

def main():
    result=json.loads((p.OUT/'combinations.json').read_text());best=result['results'][0]
    series,entries,times=s.b.prepare();busy=set()
    for t,ps in entries.items():
        for x in ps:busy.update(range(t,x['exit_bar']+3600000,3600000))
    src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    env=dict(s.b.__dict__);exec(src,env);run=env['replay']
    for ident in best['patterns']:
        symbol,name=ident.split(':');rows=s.core.read_candles(s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
        for row in rows:row['symbol']=symbol
        series[symbol]={r['t']:r for r in rows}
        for x in s.opportunities(rows,dict(p.signals(rows))[name],1,3,busy):entries.setdefault(x['entry_ts'],[]).append({**x,'weight_scale':best['target_fraction_per_signal']/1.15})
    full=run(series,entries,times,1.15)
    assert abs(full['end_usd']-best['full']['end_usd'])<1e-6
    extra=[x for x in full['ledger'] if x['symbol'] not in s.b.SYMBOLS]
    wins=sorted([x for x in extra if x['net_pnl']>0],key=lambda x:x['net_pnl']/x['margin'],reverse=True)
    tests=[]
    for count in (1,3,5):
        omitted={(x['symbol'],x['entry_ts']) for x in wins[:count]}
        e={t:[x for x in ps if (x['symbol'],t) not in omitted] for t,ps in entries.items()}
        tests.append(dict(remove_best_supplemental_wins=count,full=s.compact(run(series,e,times,1.15)),double_cost=s.compact(run(series,e,times,1.15,cost_mult=2))))
    output=dict(best_patterns=best['patterns'],extra_trades=len(extra),supplement_win_rate=100*len(wins)/len(extra),per_symbol={sym:sum(x['symbol']==sym for x in extra) for sym in {x['symbol'] for x in extra}},concentration_tests=tests,notes='Winning supplemental trades ranked by net PnL/entry margin. Deliberate hindsight stress exclusion, not tradable filtering. B opportunities unchanged.')
    (p.OUT/'concentration.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    (p.OUT/'best_ledger.json').write_text(json.dumps(full['ledger'],indent=2),encoding='utf8')
    print(json.dumps(output),flush=True)

if __name__=='__main__':main()
