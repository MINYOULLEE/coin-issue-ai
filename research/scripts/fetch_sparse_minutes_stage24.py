"""Public Binance spot minute windows for 80 frozen supplemental trades; no credentials."""
import json,urllib.request,urllib.parse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import research_b_sparse_stage20 as p

def main():
    out=p.OUT/'minute_windows';out.mkdir(exist_ok=True)
    ledger=json.loads((p.OUT/'best_ledger.json').read_text())
    trades=[x for x in ledger if x['symbol'] in ('ALGO','ETH','VET')]
    def fetch(x):
        path=out/f"{x['symbol']}_{x['entry_ts']}.json"
        if path.exists():return dict(symbol=x['symbol'],entry_ts=x['entry_ts'],cached=True)
        q=urllib.parse.urlencode(dict(symbol=x['symbol']+'USDT',interval='1m',startTime=x['entry_ts'],endTime=x['exit_ts']+15*60000,limit=100))
        req=urllib.request.Request('https://api.binance.com/api/v3/klines?'+q,headers={'User-Agent':'coin-issue-research/1.0'})
        with urllib.request.urlopen(req,timeout=15) as r:rows=json.load(r)
        assert isinstance(rows,list) and len(rows)>=76,'incomplete minute window'
        assert all(int(row[0])==x['entry_ts']+i*60000 for i,row in enumerate(rows[:76])),'minute gap'
        path.write_text(json.dumps(rows),encoding='utf8')
        return dict(symbol=x['symbol'],entry_ts=x['entry_ts'],rows=len(rows))
    result=[]
    # Probe before parallel retrieval so connectivity failures do not cause 80 blind retries.
    try:result.append(fetch(trades[0]))
    except Exception as e:
        print('PROBE_FAILED',type(e).__name__,str(e),flush=True);raise
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch,x):x for x in trades[1:]}
        for f in as_completed(futures):
            x=futures[f]
            try:result.append(f.result())
            except Exception as e:result.append(dict(symbol=x['symbol'],entry_ts=x['entry_ts'],error=str(e)))
            if len(result)%10==0:print('FETCHED',len(result),flush=True)
    (p.OUT/'minute_fetch_stage24.json').write_text(json.dumps(dict(generated_at=datetime.now(timezone.utc).isoformat(),source='Binance spot 1m, not BingX futures',windows=result),indent=2),encoding='utf8')
    print('DONE',len(result),'errors',sum('error'in x for x in result),flush=True)

if __name__=='__main__':main()
