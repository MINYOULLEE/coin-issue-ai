from __future__ import annotations

import json, math
import numpy as np
import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal


def stream(symbol, threshold, hold, base_leverage, vol_target):
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv')
    t,c,r1,body,lower,upper,vr=indicators(rows); o=np.array([r['o'] for r in rows])
    sig=pattern_signal('volume_shock_revert',r1,body,lower,upper,vr,threshold)
    pnl={int(x):0. for x in t}; active={int(x):0 for x in t}; i=24
    while i+1+hold<len(c):
        d=sig[i]
        if d==0: i+=1; continue
        realized_vol=float(np.std(r1[max(1,i-24):i],ddof=1)*math.sqrt(365.25*24))
        vol_factor=float(np.clip(vol_target/max(realized_vol,.05),.25,1.25))
        lev=base_leverage*vol_factor; entry=i+1; exit_i=entry+hold
        raw=d*(c[exit_i]/o[entry]-1)*lev
        # Realistic cost case from stage 2.
        cost=2*(.0005+.0005)*lev+(hold/8)*.0001*lev
        pnl[int(t[exit_i])]=float(raw-cost); active[int(t[exit_i])]=1; i+=hold
    return pnl,active


def simulate(times,a,b,at,bt,w,scale,guard,start,end):
    eq=1.; peak=1.; mdd=0.; trades=0; wins=0
    for stamp in times[start:end]:
        dd=eq/peak-1
        risk=1.
        if guard:
            if dd<=-.35: risk=.25
            elif dd<=-.20: risk=.5
        ret=scale*risk*(w*a[stamp]+(1-w)*b[stamp]); n=at[stamp]+bt[stamp]
        if n: trades+=n; wins+=ret>0
        eq*=max(0.,1+ret); peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
    return {'multiple':eq,'return_pct':(eq-1)*100,'mdd_pct':mdd*100,'trades':int(trades),'win_rate_pct':wins/trades*100 if trades else 0}


def main():
    rows=[]
    for vt in (.5,.75,1.,1.25,1.5):
        etc,et=stream('ETC',3.,6,3.,vt); link,lt=stream('LINK',4.,12,3.,vt)
        times=sorted(set(etc)&set(link)); n=len(times); cuts=[0,n//3,2*n//3,n]
        for w in (.6,.7,.8,.9):
            for scale in (.75,1.,1.25,1.5,2.):
                for guard in (False,True):
                    seg=[simulate(times,etc,link,et,lt,w,scale,guard,cuts[i],cuts[i+1]) for i in range(3)]
                    full=simulate(times,etc,link,et,lt,w,scale,guard,0,n)
                    passed=bool(full['return_pct']>1_000_000 and full['mdd_pct']>=-50 and all(z['return_pct']>0 and z['mdd_pct']>=-50 for z in seg))
                    score=min(z['return_pct'] for z in seg)+full['return_pct']/100+full['mdd_pct'] if passed else -1e9+full['return_pct']/1e6
                    rows.append({'score':score,'vol_target':vt,'etc_weight':w,'scale':scale,'drawdown_guard':guard,'segments':seg,'full':full,'passed':passed})
    passed=[z for z in rows if z['passed']]; best=max(rows,key=lambda z:z['score'])
    risk_ok=[z for z in rows if z['full']['mdd_pct']>=-50 and all(s['return_pct']>0 and s['mdd_pct']>=-50 for s in z['segments'])]
    best_risk_ok=max(risk_ok,key=lambda z:z['full']['return_pct']) if risk_ok else None
    best['start_usd']=100; best['end_usd']=100*best['full']['multiple']
    if best_risk_ok:
        best_risk_ok['start_usd']=100; best_risk_ok['end_usd']=100*best_risk_ok['full']['multiple']
    print(json.dumps({'scenario_count':len(rows),'pass_count':len(passed),'risk_ok_count':len(risk_ok),'best':best,'best_risk_ok':best_risk_ok},ensure_ascii=False))

if __name__=='__main__': main()
