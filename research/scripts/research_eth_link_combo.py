from __future__ import annotations

import json
import numpy as np
import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal


def pnl_stream(symbol, threshold, hold, leverage):
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv')
    t,c,r1,body,lower,upper,vr=indicators(rows)
    sig=pattern_signal('volume_shock_revert',r1,body,lower,upper,vr,threshold)
    pnl={int(stamp):0.0 for stamp in t}; trades={int(stamp):0 for stamp in t}
    i=24
    while i+hold<len(c):
        d=sig[i]
        if d==0: i+=1; continue
        exit_i=i+hold
        pnl[int(t[exit_i])]=float(d*(c[exit_i]/c[i]-1)*leverage-2*.0005*leverage)
        trades[int(t[exit_i])]=1
        i+=hold
    return pnl,trades


def simulate(times, eth, link, et, lt, weight_eth, scale, start, end):
    eq=1.; peak=1.; mdd=0.; trade_count=0; wins=0
    for stamp in times[start:end]:
        ret=scale*(weight_eth*eth[stamp]+(1-weight_eth)*link[stamp])
        active=et[stamp]+lt[stamp]
        if active:
            trade_count+=active; wins+=ret>0
        eq*=max(0.,1+ret); peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
    return {'multiple':eq,'return_pct':(eq-1)*100,'mdd_pct':mdd*100,
            'trades':int(trade_count),'win_rate_pct':wins/trade_count*100 if trade_count else 0}


def main():
    # Both rules independently survived the three-way transfer test.
    eth,et=pnl_stream('ETH',4.0,24,.5)
    link,lt=pnl_stream('LINK',4.0,12,3.0)
    times=sorted(set(eth)&set(link)); n=len(times); cuts=[0,n//3,2*n//3,n]
    rows=[]
    for w in (.25,.5,.75):
        for scale in (.5,1.,1.5,2.):
            seg=[simulate(times,eth,link,et,lt,w,scale,cuts[i],cuts[i+1]) for i in range(3)]
            full=simulate(times,eth,link,et,lt,w,scale,0,n)
            score=min(z['return_pct'] for z in seg)+full['return_pct']/100+full['mdd_pct']
            rows.append({'score':score,'eth_weight':w,'link_weight':1-w,'portfolio_scale':scale,'segments':seg,'full':full})
    rows.sort(key=lambda z:z['score'],reverse=True); best=rows[0]
    best['start_usd']=100; best['end_usd']=100*best['full']['multiple']
    best['gate']=bool(best['full']['return_pct']>1_000_000 and best['full']['mdd_pct']>=-50 and all(z['return_pct']>0 for z in best['segments']))
    print(json.dumps(best,ensure_ascii=False))

if __name__=='__main__': main()
