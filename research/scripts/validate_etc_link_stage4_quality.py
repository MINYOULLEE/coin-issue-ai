from __future__ import annotations
import json, math
import numpy as np
import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal

def stream(symbol,threshold,hold,lev,min_move,direction,wick_min,vol_max):
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv'); t,c,r1,body,lower,upper,vr=indicators(rows); o=np.array([r['o'] for r in rows])
    sig=pattern_signal('volume_shock_revert',r1,body,lower,upper,vr,threshold)
    pnl={int(x):0. for x in t}; active={int(x):0 for x in t}; i=24
    while i+1+hold<len(c):
        d=sig[i]
        vol=float(np.std(r1[i-24:i],ddof=1)*math.sqrt(365.25*24))
        wick_ok=(d>0 and lower[i]>=wick_min) or (d<0 and upper[i]>=wick_min)
        direction_ok=direction=='both' or (direction=='long' and d>0) or (direction=='short' and d<0)
        if d==0 or abs(r1[i])<min_move or not wick_ok or not direction_ok or vol>vol_max: i+=1; continue
        entry=i+1; exit_i=entry+hold; raw=d*(c[exit_i]/o[entry]-1)*lev
        cost=2*(.0005+.0005)*lev+(hold/8)*.0001*lev
        pnl[int(t[exit_i])]=float(raw-cost); active[int(t[exit_i])]=1; i+=hold
    return pnl,active

def sim(times,a,b,at,bt,w,scale,start,end):
    eq=1.;peak=1.;mdd=0.;trades=0;wins=0
    for ts in times[start:end]:
        ret=scale*(w*a[ts]+(1-w)*b[ts]); n=at[ts]+bt[ts]
        if n: trades+=n;wins+=ret>0
        eq*=max(0.,1+ret);peak=max(peak,eq);mdd=min(mdd,eq/peak-1)
    return {'multiple':eq,'return_pct':(eq-1)*100,'mdd_pct':mdd*100,'trades':int(trades),'win_rate_pct':wins/trades*100 if trades else 0}

def main():
    rows=[]
    for move in (0.,.01,.02):
      for direction in ('both','long','short'):
       for wick in (0.,.2):
        for vmax in (1.5,3.,99.):
         e,et=stream('ETC',3.,6,3.,move,direction,wick,vmax);l,lt=stream('LINK',4.,12,3.,move,direction,wick,vmax)
         times=sorted(set(e)&set(l));n=len(times);cuts=[0,n//3,2*n//3,n]
         for w in (.6,.7,.8,.9):
          for scale in (.75,1.,1.25,1.5):
           seg=[sim(times,e,l,et,lt,w,scale,cuts[i],cuts[i+1]) for i in range(3)];full=sim(times,e,l,et,lt,w,scale,0,n)
           passed=bool(full['return_pct']>1_000_000 and full['mdd_pct']>=-50 and all(z['return_pct']>0 and z['mdd_pct']>=-50 and z['trades']>=20 for z in seg))
           rows.append({'min_move':move,'direction':direction,'wick_min':wick,'vol_max':vmax,'etc_weight':w,'scale':scale,'segments':seg,'full':full,'passed':passed})
    passed=[z for z in rows if z['passed']]; risk=[z for z in rows if z['full']['mdd_pct']>=-50 and all(s['return_pct']>0 and s['mdd_pct']>=-50 and s['trades']>=20 for s in z['segments'])]
    pool=passed or risk or rows;best=max(pool,key=lambda z:z['full']['return_pct']);best['start_usd']=100;best['end_usd']=100*best['full']['multiple']
    print(json.dumps({'scenario_count':len(rows),'pass_count':len(passed),'risk_ok_count':len(risk),'best':best},ensure_ascii=False))
if __name__=='__main__':main()
