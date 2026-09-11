"""Public historical market data availability probe. No credentials/orders."""
import json,time,urllib.request,urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'results/futures_targets_stage30'

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'coin-issue-research/1.0'}),timeout=20) as r:return json.load(r)

def main():
    OUT.mkdir(exist_ok=True)
    t=1670400000000;end=t+7*3600000
    jobs=[('bingx_klines','https://open-api.bingx.com/openApi/swap/v3/quote/klines',dict(symbol='UNI-USDT',interval='1m',startTime=t,endTime=end-1,limit=1000,timestamp=int(time.time()*1000))),
          ('bingx_funding','https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate',dict(symbol='UNI-USDT',startTime=t,endTime=end,limit=100,timestamp=int(time.time()*1000))),
          ('binance_klines','https://fapi.binance.com/fapi/v1/klines',dict(symbol='UNIUSDT',interval='1m',startTime=t,endTime=end-1,limit=1000)),
          ('binance_funding','https://fapi.binance.com/fapi/v1/fundingRate',dict(symbol='UNIUSDT',startTime=t,endTime=end,limit=100))]
    def run(job):
        name,base,params=job;url=base+'?'+urllib.parse.urlencode(params)
        try:
            data=get(url);(OUT/(name+'_probe.json')).write_text(json.dumps(data),encoding='utf8')
            return dict(name=name,url=url,rows=len(data) if isinstance(data,list) else None,preview=str(data)[:600])
        except Exception as e:return dict(name=name,url=url,error=str(e))
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,jobs))
    (OUT/'probe.json').write_text(json.dumps(results,indent=2),encoding='utf8');print(json.dumps(results),flush=True)

if __name__=='__main__':main()
