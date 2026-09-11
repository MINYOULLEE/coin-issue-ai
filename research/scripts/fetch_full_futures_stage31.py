"""Download public Binance perpetual 1h/funding for the frozen research range."""
import json,time,urllib.parse,hashlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from probe_futures_stage30 import get

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/results/full_futures_stage31'
CACHE=OUT/'data'
H=3600000

def fetch_symbol(s,start,end):
    cache=CACHE/s;cache.mkdir(parents=True,exist_ok=True)
    summary={'symbol':s}
    for kind,endpoint,limit in [('hours','klines',1500),('funding','fundingRate',1000)]:
        stamp=start;all_rows=[];page=0
        while stamp<end:
            path=cache/f'{kind}_{stamp}.json'
            if path.exists():rows=json.loads(path.read_text(encoding='utf8'))
            else:
                params=dict(symbol=s+'USDT',startTime=stamp,endTime=end-1,limit=limit)
                if kind=='hours':params['interval']='1h'
                rows=get('https://fapi.binance.com/fapi/v1/'+endpoint+'?'+urllib.parse.urlencode(params))
                if not isinstance(rows,list):raise ValueError(str(rows)[:200])
                path.write_text(json.dumps(rows),encoding='utf8');time.sleep(.2)
            if not rows:break
            stamps=[int(x[0] if kind=='hours' else x['fundingTime']) for x in rows]
            assert stamps==sorted(set(stamps)) and stamps[0]>=stamp
            all_rows.extend(rows);stamp=stamps[-1]+(H if kind=='hours' else 1);page+=1
            if page>100:raise RuntimeError('unexpected pagination length')
        (cache/(kind+'.json')).write_text(json.dumps(all_rows),encoding='utf8')
        summary[kind+'_rows']=len(all_rows)
        if kind=='hours':
            got={int(x[0]) for x in all_rows};missing=sorted(set(range(start,end,H))-got)
            summary['missing_hours']=missing
        else:
            ts=[int(x['fundingTime']) for x in all_rows]
            summary['funding_first']=ts[0] if ts else None;summary['funding_last']=ts[-1] if ts else None
            summary['funding_gaps_over_16h']=[(a,b) for a,b in zip(ts,ts[1:]) if b-a>16*H+60000]
    print(json.dumps(summary),flush=True);return summary

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    std=json.loads((ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf8'))
    prev=json.loads((ROOT/'research/results/conditional_exits_stage28/RESULTS.json').read_text(encoding='utf8'))
    start,end=prev['cuts'][0],prev['cuts'][-1];results=[];errors=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(fetch_symbol,s,start,end):s for s in std['symbols']}
        for job in as_completed(jobs):
            try:results.append(job.result())
            except Exception as e:errors.append({'symbol':jobs[job],'error':str(e)});print(errors[-1],flush=True)
    result=dict(start=start,end=end,source='Binance USD-M public API',results=results,errors=errors,
                hashes={str(p.relative_to(CACHE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob('*/*.json') if p.name in ('hours.json','funding.json')})
    (OUT/'COVERAGE.json').write_text(json.dumps(result,indent=2),encoding='utf8')

if __name__=='__main__':main()
