"""Final research gate for adopted Stage34 candidate. Research only; no live writes."""
import inspect,json,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone

import research_b_idle_stage32 as p

s=p.s; H=3600000;M=60000
OUT=s.core.RESULT_DIR/'b_idle_stage35'; CACHE=OUT/'minute_windows'

def setup():
    chosen=json.loads((s.core.RESULT_DIR/'b_idle_stage34/results.json').read_text())['results'][0]
    series,entries,times,standard=p.current_stage26();busy=set()
    for t,ps in entries.items():
        for x in ps:busy.update(range(t,x['exit_bar']+H,H))
    rules={'LINK':('exhaust_n3_move0.05',3),'DOT':('capitulation_n12_move0.05_vol3.0_wick0.5',3),'LTC':('exhaust_n5_move0.05',3)}
    ops=[]
    for symbol,(name,lev) in rules.items():
        rows=s.core.read_candles(s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
        for r in rows:r['symbol']=symbol
        series[symbol]={r['t']:r for r in rows}
        sig=dict(p.candidate_patterns(rows))[name]
        frac=chosen['allocation'][symbol]
        for x in s.opportunities(rows,sig,1,lev,busy):
            x={**x,'weight_scale':frac/1.15};entries.setdefault(x['entry_ts'],[]).append(x);ops.append(x)
    return chosen,series,entries,times,ops,standard

def fetch_minutes(x):
    path=CACHE/f"{x['symbol']}_{x['entry_ts']}.json"
    if path.exists():return {'cached':True,'path':str(path)}
    q=urllib.parse.urlencode({'symbol':x['symbol']+'USDT','interval':'1m','startTime':x['entry_ts'],'endTime':x['entry_ts']+70*M,'limit':100})
    req=urllib.request.Request('https://api.binance.com/api/v3/klines?'+q,headers={'User-Agent':'coin-issue-research/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:rows=json.load(r)
    if len(rows)<70 or any(int(row[0])!=x['entry_ts']+i*M for i,row in enumerate(rows[:70])):raise RuntimeError('incomplete/gapped minute data')
    path.write_text(json.dumps(rows),encoding='utf8');return {'cached':False,'path':str(path)}

def main():
    OUT.mkdir(exist_ok=True);CACHE.mkdir(exist_ok=True)
    chosen,series,entries,times,ops,standard=setup();unique={(x['symbol'],x['entry_ts']):x for x in ops if times[0]<=x['entry_ts']<=times[-1]}
    fetched=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fs={pool.submit(fetch_minutes,x):key for key,x in unique.items()}
        for f in as_completed(fs):
            try:fetched.append({**dict(zip(('symbol','entry_ts'),fs[f])),**f.result()})
            except Exception as e:fetched.append({**dict(zip(('symbol','entry_ts'),fs[f])),'error':str(e)})
    errors=[x for x in fetched if 'error'in x]
    if errors:raise RuntimeError(f'minute fetch errors {len(errors)}: {errors[:3]}')
    minutes={}
    for key in unique:
        rows=json.loads((CACHE/f'{key[0]}_{key[1]}.json').read_text())
        minutes[key]={int(r[0]):{'o':float(r[1]),'h':float(r[2]),'l':float(r[3]),'c':float(r[4])} for r in rows}
    mismatches=[]
    for key,x in unique.items():
        v=minutes[key];t=x['entry_ts'];bar=series[x['symbol']][t]
        checks={'o':v[t]['o'],'c':v[t+59*M]['c'],'h':max(v[t+i*M]['h'] for i in range(60)),'l':min(v[t+i*M]['l'] for i in range(60))}
        for f,val in checks.items():
            if abs(val-bar[f])>max(1e-8,abs(bar[f])*1e-8):mismatches.append({'symbol':x['symbol'],'t':t,'field':f,'hour':bar[f],'minute':val})
    if mismatches:raise RuntimeError(f'OHLC mismatch {len(mismatches)}')
    src=inspect.getsource(s.b.replay).replace('target*(1+x',"target*x.get('weight_scale',1.)*(1+x").replace('margin = target*shrink',"margin = target*shrink*x.get('weight_scale',1.)")
    src=src.replace("raw_open = series[x['symbol']][t]['o']","raw_open = entry_override.get((x['symbol'],t),series[x['symbol']][t]['o'])")
    src=src.replace("bar = series[s][t]","bar = bar_override.get((s,t),series[s][t])")
    scenarios=[]
    for delay in (0,1,5,10):
        prices={};bars={}
        for key,x in unique.items():
            v=minutes[key];t=x['entry_ts'];prices[key]=v[t+delay*M]['o'];bars[key]={'o':series[x['symbol']][t]['o'],'c':v[t+59*M]['c'],'h':max(v[t+i*M]['h'] for i in range(delay,60)),'l':min(v[t+i*M]['l'] for i in range(delay,60))}
        env={**s.b.__dict__,'entry_override':prices,'bar_override':bars};exec(src,env)
        result=env['replay'](series,entries,times,1.15)
        if delay==0 and abs(result['return_pct']-chosen['full']['return_pct'])>1e-6:raise RuntimeError('zero-delay replay mismatch')
        scenarios.append({'delay_minutes':delay,**p.compact(result)})
    output={'id':'B-IDLE-STAGE35','generated_at':datetime.now(timezone.utc).isoformat(),'research_only':True,'candidate':chosen['allocation'],'minute_windows':len(unique),'ohlc_mismatches':mismatches,'entry_delay_scenarios':scenarios,'passes':all(x['return_pct']>standard['acceptance']['base_cost_return_floor_pct'] and x['hourly_mark_mdd_pct']>=-70 and not x['liquidation_proxy_count'] for x in scenarios),'limitations':['Binance spot minute data, not BingX futures fills','Exit remains at original hourly boundary','No independent untouched holdout']}
    (OUT/'results.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(output),flush=True)

if __name__=='__main__':main()
