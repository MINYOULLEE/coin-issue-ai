"""Paired public futures diagnostics for Stage29's 55 selected windows.
Not a five-year futures portfolio replay; no credentials or orders.
"""
import json,urllib.parse,time,hashlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import numpy as np
import research_conditional_exits_stage28 as r
import verify_learned_targets_stage29 as v
from probe_futures_stage30 import get,OUT
H=r.H;M=60000;CACHE=OUT/'binance_windows'

def fetch(p):
    s=p['symbol'];t=p['entry_ts'];end=p['exit_bar']+H
    result={}
    for kind,endpoint,params in [('minutes','klines',dict(interval='1m',limit=1000)),('funding','fundingRate',dict(limit=100))]:
        path=CACHE/f'{s}_{t}_{kind}.json'
        if path.exists():data=json.loads(path.read_text(encoding='utf8'))
        else:
            query=urllib.parse.urlencode(dict(symbol=s+'USDT',startTime=t,endTime=end-1,**params))
            data=get('https://fapi.binance.com/fapi/v1/'+endpoint+'?'+query)
            path.write_text(json.dumps(data),encoding='utf8')
        if not isinstance(data,list):raise ValueError(str(data)[:200])
        result[kind]=data
    rows={int(x[0]):dict(o=float(x[1]),h=float(x[2]),l=float(x[3]),c=float(x[4])) for x in result['minutes']}
    assert sorted(rows)==list(range(t,end,M)),f'incomplete futures minutes: {s} {t}'
    return (s,t),rows,result['funding']

def net_return(rows,p,stamp,raw,cost,funding):
    side=p['side'];entry=rows[p['entry_ts']]['o']*(1+side*.0002*cost)
    close=raw*(1-side*.0002*cost)
    # Funding at entry boundary excluded; trade assumed opened immediately after
    # that boundary settlement. Empty historical markPrice uses minute-open proxy.
    charges=0.;fallback=0;events=0
    for x in funding:
        ft=int(x['fundingTime'])
        if p['entry_ts']<ft<=stamp:
            mark=float(x.get('markPrice') or 0)
            if not mark:
                mark=rows.get(ft//M*M,rows[max(rows)])['o'];fallback+=1
            charges+=side*float(x['fundingRate'])*mark*cost;events+=1
    net=side*(close-entry)-.0005*cost*(entry+close)-charges
    return dict(net_price_return_pct=net/entry*100,margin_return_pct=net/entry*p['lev']*100,
                funding_price_return_pct=charges/entry*100,funding_events=events,mark_fallback= fallback)

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    series,entries,times,std=r.prev.b_setup();ps={(p['symbol'],t):p for t,xs in entries.items() for p in xs}
    decisions=json.loads((r.OUT/'target_only_q80.json').read_text(encoding='utf8'))['decisions']
    selected=[d for d in decisions if 'exit_bar' in d];minutes={};fundings={};errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(fetch,ps[(d['symbol'],d['entry_ts'])]):d for d in selected}
        for f in as_completed(jobs):
            d=jobs[f]
            try:key,rows,funds=f.result();minutes[key]=rows;fundings[key]=funds
            except Exception as e:errors.append(dict(symbol=d['symbol'],t=d['entry_ts'],error=str(e)))
    availability=[]
    for d in [selected[0],selected[len(selected)//2],selected[-1]]:
        p=ps[(d['symbol'],d['entry_ts'])];end=p['exit_bar']+H
        for kind,endpoint in [('minutes','/openApi/swap/v3/quote/klines'),('funding','/openApi/swap/v2/quote/fundingRate')]:
            query=dict(symbol=p['symbol']+'-USDT',startTime=p['entry_ts'],endTime=end-1,limit=1000,timestamp=int(time.time()*1000))
            if kind=='minutes':query['interval']='1m'
            try:
                data=get('https://open-api.bingx.com'+endpoint+'?'+urllib.parse.urlencode(query))
                path=OUT/f"bingx_{p['symbol']}_{p['entry_ts']}_{kind}.json";path.write_text(json.dumps(data),encoding='utf8')
                payload=data.get('data');availability.append(dict(symbol=p['symbol'],entry_ts=p['entry_ts'],kind=kind,code=data.get('code'),rows=len(payload) if isinstance(payload,list) else 0))
            except Exception as e:availability.append(dict(symbol=p['symbol'],entry_ts=p['entry_ts'],kind=kind,error=str(e)))
            time.sleep(1.05)
    rows_out=[];basis=[]
    for d in selected:
        key=(d['symbol'],d['entry_ts'])
        if key not in minutes:continue
        p=ps[key];rows=minutes[key];fund=fundings[key];end=p['exit_bar']+H
        spot=series[key[0]][key[1]]['o'];fut=rows[key[1]]['o']
        basis.append(100*(fut/spot-1))
        # Two explicitly different mappings; no retrospective choice per trade.
        for mapping,target in [('absolute_spot_target',d['target']),('entry_relative_target',d['target']/spot*fut)]:
            for mode in ('delay_1m','delay_5m'):
                fill=v.execution(rows,p,target,mode)
                stamp,price=fill if fill else (end,rows[end-M]['c'])
                for cost in (1,2):
                    baseline=net_return(rows,p,end,rows[end-M]['c'],cost,fund)
                    candidate=net_return(rows,p,stamp,price,cost,fund)
                    rows_out.append(dict(symbol=key[0],entry_ts=key[1],mapping=mapping,mode=mode,cost=cost,
                                         target=target,target_market_exit=fill is not None,exit_ts=stamp,
                                         baseline=baseline,candidate=candidate,
                                         improvement_margin_pp=candidate['margin_return_pct']-baseline['margin_return_pct']))
    summaries=[]
    for mapping in ('absolute_spot_target','entry_relative_target'):
        for mode in ('delay_1m','delay_5m'):
            for cost in (1,2):
                xs=[x for x in rows_out if x['mapping']==mapping and x['mode']==mode and x['cost']==cost]
                if not xs:continue
                summaries.append(dict(mapping=mapping,mode=mode,cost=cost,windows=len(xs),
                    target_market_exits=sum(x['target_market_exit'] for x in xs),
                    mean_baseline_margin_return_pct=float(np.mean([x['baseline']['margin_return_pct'] for x in xs])),
                    mean_candidate_margin_return_pct=float(np.mean([x['candidate']['margin_return_pct'] for x in xs])),
                    mean_improvement_pp=float(np.mean([x['improvement_margin_pp'] for x in xs])),
                    improved=sum(x['improvement_margin_pp']>1e-9 for x in xs),worsened=sum(x['improvement_margin_pp']<-1e-9 for x in xs),
                    mark_fallback_events=sum(x['baseline']['mark_fallback'] for x in xs)))
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),requested=55,complete=len(minutes),errors=errors,
                bingx_sample_availability=availability,summaries=summaries,diagnostics=rows_out,
                entry_basis_pct=dict(min=min(basis),max=max(basis),median=float(np.median(basis))) if basis else None,
                five_year_futures_return_pct=None,live_changes=False,independent_validation=False,
                notes=['Selected 55 spot-target-touch opportunities only: selection-biased, not all 756 opportunities',
                       'BingX samples checked only; not asserting all historical data unavailable',
                       'Binance perpetuals are not BingX perpetuals','No compounding or portfolio MDD calculated from partial futures windows',
                       'Funding historical rates, empty markPrice fallback to minute-open; boundary convention explicit',
                       'Fees/slippage remain assumptions, not account-specific observed fills',
                       'Delay counted from opening timestamp of target-touch minute, not exact tick time'],
                hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob('*.json')})
    (OUT/'RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('diagnostics','hashes')}),flush=True)

if __name__=='__main__':main()
