from __future__ import annotations
import json, math
import numpy as np
import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal

def stream(symbol,threshold,hold,lev,min_move,vol_max,delay,slip,funding):
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv');t,c,r1,body,lower,upper,vr=indicators(rows);o=np.array([r['o'] for r in rows])
    sig=pattern_signal('volume_shock_revert',r1,body,lower,upper,vr,threshold);p={int(x):0. for x in t};a={int(x):0 for x in t};i=24
    while i+delay+hold<len(c):
        d=sig[i];vol=float(np.std(r1[i-24:i],ddof=1)*math.sqrt(365.25*24))
        if d==0 or abs(r1[i])<min_move or vol>vol_max:i+=1;continue
        entry=i+delay;exit_i=entry+hold;raw=d*(c[exit_i]/o[entry]-1)*lev;cost=2*(.0005+slip)*lev+(hold/8)*funding*lev
        p[int(t[exit_i])]=float(raw-cost);a[int(t[exit_i])]=1;i+=hold
    return p,a

def sim(times,e,l,ea,la,w,scale,s,n):
    eq=1.;peak=1.;mdd=0.;tr=0;wins=0
    for ts in times[s:n]:
        ret=scale*(w*e[ts]+(1-w)*l[ts]);k=ea[ts]+la[ts]
        if k:tr+=k;wins+=ret>0
        eq*=max(0.,1+ret);peak=max(peak,eq);mdd=min(mdd,eq/peak-1)
    return {'multiple':eq,'return_pct':(eq-1)*100,'mdd_pct':mdd*100,'trades':int(tr),'win_rate_pct':wins/tr*100 if tr else 0}

def main():
    rows=[]
    costs=[('base',.0005,.0001),('high',.00075,.00015)]
    for move in (.008,.009,.01,.011,.012):
      for vmax in (1.3,1.4,1.5,1.6,1.7):
       for delay in (1,2):
        for cname,slip,funding in costs:
         e,ea=stream('ETC',3.,6,3.,move,vmax,delay,slip,funding);l,la=stream('LINK',4.,12,3.,move,vmax,delay,slip,funding)
         times=sorted(set(e)&set(l));n=len(times);cuts=[0,n//3,2*n//3,n]
         for w in (.85,.9,.95):
          for scale in (1.25,1.5,1.75):
           seg=[sim(times,e,l,ea,la,w,scale,cuts[i],cuts[i+1]) for i in range(3)];full=sim(times,e,l,ea,la,w,scale,0,n)
           passed=bool(full['return_pct']>1_000_000 and full['mdd_pct']>=-50 and all(z['return_pct']>0 and z['mdd_pct']>=-50 and z['trades']>=20 for z in seg))
           rows.append({'move':move,'vol_max':vmax,'delay_hours':delay,'cost':cname,'etc_weight':w,'scale':scale,'segments':seg,'full':full,'passed':passed})
    passed=[x for x in rows if x['passed']];best=max(passed or rows,key=lambda x:x['full']['return_pct']);best['end_usd']=100*best['full']['multiple']
    print(json.dumps({'scenario_count':len(rows),'pass_count':len(passed),'base_pass_count':sum(x['passed'] and x['cost']=='base' for x in rows),'high_cost_pass_count':sum(x['passed'] and x['cost']=='high' for x in rows),'delay2_pass_count':sum(x['passed'] and x['delay_hours']==2 for x in rows),'best':best},ensure_ascii=False))
if __name__=='__main__':main()
