from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
import numpy as np
import replay_mdd30 as core


def indicators(rows):
    o=np.array([r['o'] for r in rows]); h=np.array([r['h'] for r in rows]); l=np.array([r['l'] for r in rows]); c=np.array([r['c'] for r in rows]); v=np.array([r['v'] for r in rows]); t=np.array([r['t'] for r in rows])
    r1=np.zeros(len(c)); r1[1:]=c[1:]/c[:-1]-1
    body=(c-o)/np.maximum(o,1e-12); span=np.maximum(h-l,1e-12)
    lower=(np.minimum(o,c)-l)/span; upper=(h-np.maximum(o,c))/span
    # 현재 봉보다 앞선 24개 완료봉만 사용한다. centered convolution의
    # 'same'은 미래 거래량을 포함해 백테스트 룩어헤드 편향을 만든다.
    vm=np.zeros(len(v))
    for i in range(24,len(v)): vm[i]=np.mean(v[i-24:i])
    vr=np.divide(v,vm,out=np.zeros_like(v,dtype=float),where=vm>0)
    return t,c,r1,body,lower,upper,vr


def pattern_signal(name,r1,body,lower,upper,vr,a):
    s=np.zeros(len(r1))
    if name=='shock_revert': s=np.where(r1<=-a,1,np.where(r1>=a,-1,0))
    elif name=='wick_revert': s=np.where((lower>=a)&(body<0),1,np.where((upper>=a)&(body>0),-1,0))
    elif name=='volume_shock_revert': s=np.where((vr>=a)&(r1<0),1,np.where((vr>=a)&(r1>0),-1,0))
    elif name=='three_candle_revert':
        down=(r1<0).astype(int); up=(r1>0).astype(int)
        for i in range(2,len(s)):
            if down[i-2:i+1].sum()==3: s[i]=1
            elif up[i-2:i+1].sum()==3: s[i]=-1
    return s


def simulate(t,c,sig,horizon,lev,start,end,fee=.0005):
    eq=1.; peak=1.; mdd=0.; wins=0; losses=0; trades=0; i=max(start,24)
    while i+horizon<end:
        d=sig[i]
        if d==0: i+=1; continue
        ret=d*(c[i+horizon]/c[i]-1)*lev-2*fee*lev
        eq*=max(0.,1+ret); peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
        trades+=1; wins+=ret>0; losses+=ret<=0; i+=horizon
    return {'multiple':eq,'return_pct':(eq-1)*100,'mdd_pct':mdd*100,'trades':trades,'win_rate_pct':wins/trades*100 if trades else 0}


def main():
    p=argparse.ArgumentParser(); p.add_argument('symbol'); args=p.parse_args(); symbol=args.symbol.upper()
    rows=core.read_candles(core.DATA_DIR/f'{symbol}USDT_1h.csv'); t,c,r1,body,lower,upper,vr=indicators(rows); split=int(len(c)*.70)
    defs=[]
    for a in (.005,.01,.015,.02,.03,.04): defs.append(('shock_revert',a))
    for a in (.45,.55,.65,.75): defs.append(('wick_revert',a))
    for a in (1.5,2.,3.,4.,5.): defs.append(('volume_shock_revert',a))
    defs.append(('three_candle_revert',0.))
    cand=[]
    for name,a in defs:
        sig=pattern_signal(name,r1,body,lower,upper,vr,a)
        for hold in (1,3,6,12,24):
            for lev in (.5,1.,2.,3.,5.,10.):
                tr=simulate(t,c,sig,hold,lev,0,split)
                if tr['trades']<50: continue
                score=np.log(max(tr['multiple'],1e-12))+tr['mdd_pct']/25
                if tr['mdd_pct'] < -50: score-=20
                cand.append({'score':float(score),'pattern':name,'threshold':a,'hold_hours':hold,'leverage':lev,'train':tr})
    cand.sort(key=lambda z:z['score'],reverse=True); best=cand[0]
    sig=pattern_signal(best['pattern'],r1,body,lower,upper,vr,best['threshold'])
    test=simulate(t,c,sig,best['hold_hours'],best['leverage'],split,len(c)); full=simulate(t,c,sig,best['hold_hours'],best['leverage'],0,len(c))
    gate=bool(full['return_pct']>1_000_000 and full['mdd_pct']>=-50 and test['return_pct']>0 and test['mdd_pct']>=-40)
    print(json.dumps({'symbol':symbol,'timeframe':'1h','selected_without_holdout':best,'full':full,'holdout':test,'start_usd':100,'end_usd':100*full['multiple'],'gate':gate},ensure_ascii=False))

if __name__=='__main__': main()
