from __future__ import annotations

import argparse, json
import numpy as np
import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal, simulate


def definitions():
    out=[]
    for a in (.005,.01,.015,.02,.03,.04): out.append(('shock_revert',a))
    for a in (.45,.55,.65,.75): out.append(('wick_revert',a))
    for a in (1.5,2.,3.,4.,5.): out.append(('volume_shock_revert',a))
    out.append(('three_candle_revert',0.))
    return out


def choose(t,c,r1,body,lower,upper,vr,start,end):
    rows=[]
    for name,a in definitions():
        sig=pattern_signal(name,r1,body,lower,upper,vr,a)
        for hold in (1,3,6,12,24):
            for lev in (.5,1.,2.,3.,5.,10.):
                z=simulate(t,c,sig,hold,lev,start,end)
                if z['trades']<30: continue
                score=np.log(max(z['multiple'],1e-12))+z['mdd_pct']/25
                if z['mdd_pct'] < -50: score-=20
                rows.append({'score':float(score),'pattern':name,'threshold':a,'hold_hours':hold,'leverage':lev,'origin':z})
    rows.sort(key=lambda z:z['score'],reverse=True)
    return rows[0]


def main():
    p=argparse.ArgumentParser(); p.add_argument('symbol'); args=p.parse_args(); symbol=args.symbol.upper()
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv')
    t,c,r1,body,lower,upper,vr=indicators(rows); n=len(c)
    cuts=[0,n//3,2*n//3,n]
    selected=[]; matrix=[]
    for origin in range(3):
        best=choose(t,c,r1,body,lower,upper,vr,cuts[origin],cuts[origin+1])
        sig=pattern_signal(best['pattern'],r1,body,lower,upper,vr,best['threshold'])
        tests=[simulate(t,c,sig,best['hold_hours'],best['leverage'],cuts[j],cuts[j+1]) for j in range(3)]
        selected.append({k:v for k,v in best.items() if k not in ('score','origin')})
        matrix.append(tests)
    transferable=[]
    for i,(rule,tests) in enumerate(zip(selected,matrix)):
        if all(z['return_pct']>0 and z['mdd_pct']>=-50 and z['trades']>=20 for z in tests):
            full_sig=pattern_signal(rule['pattern'],r1,body,lower,upper,vr,rule['threshold'])
            full=simulate(t,c,full_sig,rule['hold_hours'],rule['leverage'],0,n)
            transferable.append({'origin_segment':i+1,'rule':rule,'segments':tests,'full':full,'end_usd':100*full['multiple']})
    print(json.dumps({'symbol':symbol,'timeframe':'1h','segment_ranges':[cuts[:2],cuts[1:3],cuts[2:]],'selected_rules':selected,'cross_matrix':matrix,'transferable':transferable},ensure_ascii=False))

if __name__=='__main__': main()
