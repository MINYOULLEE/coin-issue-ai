"""Minute entry sensitivity, exit-price diagnostics and temporal collision audit."""
import json,inspect
from datetime import datetime,timezone
import research_b_sparse_stage20 as p
s=p.s
H=3600000;M=60000

def main():
    best=json.loads((p.OUT/'combinations.json').read_text())['results'][0]
    series,base,times=s.b.prepare();entries={t:[dict(x) for x in ps] for t,ps in base.items()};busy=set();supp=[];minutes={}
    for t,ps in base.items():
        for x in ps:busy.update(range(t,x['exit_bar']+H,H))
    for ident in best['patterns']:
        sym,name=ident.split(':');rows=s.core.read_candles(s.core.DATA_DIR/f'{sym}USDT_1h.csv')
        for row in rows:row['symbol']=sym
        series[sym]={r['t']:r for r in rows}
        for x in s.opportunities(rows,dict(p.signals(rows))[name],1,3,busy):
            x={**x,'weight_scale':.9/1.15};entries.setdefault(x['entry_ts'],[]).append(x)
            if times[0]<=x['entry_ts']<=times[-1]:
                supp.append(x);data=json.loads((p.OUT/'minute_windows'/f"{sym}_{x['entry_ts']}.json").read_text())
                minutes[(sym,x['entry_ts'])]={int(r[0]):dict(o=float(r[1]),h=float(r[2]),l=float(r[3]),c=float(r[4])) for r in data}
    assert len(supp)==80
    mismatches=[]
    for x in supp:
        t=x['entry_ts'];v=minutes[(x['symbol'],t)];hour=series[x['symbol']][t]
        for field,value in [('o',v[t]['o']),('c',v[t+59*M]['c']),('h',max(v[t+i*M]['h'] for i in range(60))),('l',min(v[t+i*M]['l'] for i in range(60)))]:
            if abs(value-hour[field])>max(1e-8,abs(hour[field])*1e-8):mismatches.append(dict(symbol=x['symbol'],t=t,field=field,hour=hour[field],minute=value))
    assert not mismatches, 'Minute data does not reproduce original hourly OHLC'
    src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    src=src.replace("raw_open = series[x['symbol']][t]['o']", "raw_open = entry_override.get((x['symbol'],t),series[x['symbol']][t]['o'])")
    src=src.replace("bar = series[s][t]", "bar = bar_override.get((s,t),series[s][t])")
    scenarios=[]
    for delay in (0,1,5,10):
        prices={};bars={}
        for x in supp:
            key=(x['symbol'],x['entry_ts']);v=minutes[key];t=x['entry_ts']
            prices[key]=v[t+delay*M]['o']
            bars[key]=dict(o=series[x['symbol']][t]['o'],c=v[t+59*M]['c'],h=max(v[t+i*M]['h'] for i in range(delay,60)),l=min(v[t+i*M]['l'] for i in range(delay,60)))
        env={**s.b.__dict__,'entry_override':prices,'bar_override':bars};exec(src,env)
        full=env['replay'](series,entries,times,1.15)
        if delay==0:assert abs(full['end_usd']-best['full']['end_usd'])<1e-6
        # Only supplemental entry is delayed; B remains hourly baseline.
        scenarios.append(dict(delay_minutes=delay,full=s.compact(full)))
    exits=[]
    for delay in (0,1,5,10):
        changes=[];collisions=[]
        for x in supp:
            sym=x['symbol'];t=x['entry_ts'];exit_t=t+H;v=minutes[(sym,t)]
            changes.append(100*x['side']*(v[exit_t+delay*M]['o']/v[t+59*M]['c']-1))
            # Baseline B opportunities arriving before delayed closure has completed.
            for bt,ps in base.items():
                if exit_t<=bt<exit_t+delay*M:
                    collisions.extend(dict(supplement=sym,supplement_entry=t,b_symbol=z['symbol'],b_entry=bt) for z in ps)
        exits.append(dict(exit_delay_minutes=delay,mean_directional_exit_price_change_pct=sum(changes)/len(changes),worst_directional_exit_price_change_pct=min(changes),b_signal_collisions=len(collisions),collisions=collisions))
    output=dict(generated_at=datetime.now(timezone.utc).isoformat(),source='Binance spot 1m matching original spot hourly research; NOT BingX executions',minute_windows=len(supp),ohlc_mismatches=mismatches,baseline=s.compact(s.b.replay(series,base,times,1.15)),entry_scenarios=scenarios,exit_diagnostics=exits,notes=['Entry scenarios retain fixed scheduled exit; no time extension','Same full-hour funding charge and reservation retained conservatively despite delayed entry','MDD remains hybrid hourly evaluation; not full minute-by-minute account MDD','Hourly adverse-bound metric includes pre-entry bar extremes; do not interpret as measured minute MDD','Exit diagnostics are price/collision checks, NOT compounded exit-delay portfolio returns','5/10-minute entries are fault stress tests; not authorization to relax current entry TTL','Independent historical holdout and live execution validation not performed'])
    (p.OUT/'delay_stage24.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(output),flush=True)

if __name__=='__main__':main()
