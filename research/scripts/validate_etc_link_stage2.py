from __future__ import annotations

import json
import numpy as np
import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal


def pnl_stream(symbol, threshold, hold, leverage, slip_side, funding_8h):
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv')
    t,c,r1,body,lower,upper,vr=indicators(rows)
    o=np.array([r['o'] for r in rows])
    sig=pattern_signal('volume_shock_revert',r1,body,lower,upper,vr,threshold)
    pnl={int(stamp):0.0 for stamp in t}; trades={int(stamp):0 for stamp in t}
    i=24
    while i+1+hold<len(c):
        d=sig[i]
        if d==0: i+=1; continue
        entry_i=i+1; exit_i=entry_i+hold
        raw=d*(c[exit_i]/o[entry_i]-1)*leverage
        costs=2*(.0005+slip_side)*leverage+(hold/8)*funding_8h*leverage
        pnl[int(t[exit_i])]=float(raw-costs); trades[int(t[exit_i])]=1
        i+=hold
    return pnl,trades


def simulate(times,a,b,at,bt,w,scale,start,end):
    eq=1.; peak=1.; mdd=0.; count=0; wins=0
    for stamp in times[start:end]:
        ret=scale*(w*a[stamp]+(1-w)*b[stamp]); active=at[stamp]+bt[stamp]
        if active: count+=active; wins+=ret>0
        eq*=max(0.,1+ret); peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
    return {'multiple':eq,'return_pct':(eq-1)*100,'mdd_pct':mdd*100,'trades':int(count),'win_rate_pct':wins/count*100 if count else 0}


def evaluate(etc_thr,link_thr,w,scale,slip,funding):
    etc,et=pnl_stream('ETC',etc_thr,6,3.,slip,funding)
    link,lt=pnl_stream('LINK',link_thr,12,3.,slip,funding)
    times=sorted(set(etc)&set(link)); n=len(times); cuts=[0,n//3,2*n//3,n]
    seg=[simulate(times,etc,link,et,lt,w,scale,cuts[i],cuts[i+1]) for i in range(3)]
    full=simulate(times,etc,link,et,lt,w,scale,0,n)
    passed=bool(full['return_pct']>1_000_000 and full['mdd_pct']>=-50 and all(z['return_pct']>0 and z['mdd_pct']>=-50 for z in seg))
    return {'etc_threshold':etc_thr,'link_threshold':link_thr,'etc_weight':w,'scale':scale,'slippage_each_side':slip,'funding_each_8h':funding,'segments':seg,'full':full,'end_usd':100*full['multiple'],'passed':passed}


def main():
    scenarios=[]
    # Base realistic execution and progressively harsher trading costs.
    for slip,funding in ((0.,0.),(.00025,.00005),(.0005,.0001),(.001,.0002)):
        scenarios.append(evaluate(3.,4.,.8,1.25,slip,funding))
    # Neighbour stability under the middle cost assumption.
    for et in (2.5,3.,3.5):
        for lt in (3.5,4.,4.5):
            for w in (.7,.8,.9):
                scenarios.append(evaluate(et,lt,w,1.25,.0005,.0001))
    print(json.dumps({'method':'ETC_LINK_stage2','scenario_count':len(scenarios),'pass_count':sum(z['passed'] for z in scenarios),'base_next_open':scenarios[0],'realistic_cost':scenarios[2],'worst_cost':scenarios[3],'neighbour_pass_count':sum(z['passed'] for z in scenarios[4:]),'best':max(scenarios,key=lambda z:z['full']['return_pct'])},ensure_ascii=False))

if __name__=='__main__': main()
