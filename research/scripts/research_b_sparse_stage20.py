"""Rare non-overlapping B supplements. Offline research; no live writes."""
import json, inspect
from datetime import datetime, timezone
import numpy as np
import research_b_complement_stage17 as s

OUT=s.core.RESULT_DIR/'b_sparse_stage20'

def signals(rows):
    o,h,l,c,v=[np.array([r[k] for r in rows]) for k in ('o','h','l','c','v')]
    span=np.maximum(h-l,1e-12)
    lo=(np.minimum(o,c)-l)/span;hi=(h-np.maximum(o,c))/span
    avg=np.r_[np.full(48,np.nan),np.convolve(v,np.ones(48)/48,'valid')[:-1]]
    for n in (1,3,6,12,24):
        move=np.r_[np.zeros(n),c[n:]/c[:-n]-1]
        for shock in (.03,.05,.08):
            for vol in (1.5,3.):
                for wick in (.25,.5):
                    yield f'capitulation_n{n}_move{shock}_vol{vol}_wick{wick}',np.where((move < -shock)&(lo>wick)&(v>avg*vol),1,np.where((move>shock)&(hi>wick)&(v>avg*vol),-1,0))
    # Liquidity sweep and close back inside the PRIOR range; no future range.
    for n in (24,72,168):
        lows=np.r_[np.full(n,np.nan),np.min(np.lib.stride_tricks.sliding_window_view(l,n),axis=1)[:-1]]
        highs=np.r_[np.full(n,np.nan),np.max(np.lib.stride_tricks.sliding_window_view(h,n),axis=1)[:-1]]
        for excess in (.005,.015,.03):
            for vol in (1.5,3.):
                yield f'sweep_n{n}_excess{excess}_vol{vol}',np.where((l<lows*(1-excess))&(c>lows)&(lo>.4)&(v>avg*vol),1,np.where((h>highs*(1+excess))&(c<highs)&(hi>.4)&(v>avg*vol),-1,0))

def main():
    OUT.mkdir(exist_ok=True)
    series,entries,times=s.b.prepare();busy=set()
    for t,ps in entries.items():
        for p in ps:busy.update(range(t,p['exit_bar']+3600000,3600000))
    cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
    src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    env=dict(s.b.__dict__);exec(src,env);run=env['replay']
    base=run(series,entries,times,1.15)
    reference=json.loads((s.core.ROOT/'strategy/plan_b_standard.json').read_text())['reference']['return_pct']
    assert abs(base['return_pct']-reference)<1e-6
    baseline_stress=run(series,entries,times,1.15,cost_mult=2)
    all_candidates=[];rowsets={}
    for path in sorted(s.core.DATA_DIR.glob('*USDT_1h.csv')):
        symbol=path.name.replace('USDT_1h.csv','')
        if symbol in s.b.SYMBOLS:continue
        rows=s.core.read_candles(path)
        if rows[0]['t']>times[0] or rows[-1]['t']<times[-1]:continue
        for r in rows:r['symbol']=symbol
        rowsets[symbol]=rows
        # Prefix stability checks all new patterns, including prior rolling ranges.
        prefix=dict(signals(rows[:1000]))
        for name,sig in signals(rows):
            np.testing.assert_array_equal(sig[:1000],prefix[name])
            ops=s.opportunities(rows,sig,1,3,busy)
            seg=s.screen(rows,ops,cuts)
            all_candidates.append(dict(id=f'{symbol}:{name}',symbol=symbol,pattern=name,segments=seg,ops=ops,score=sum(x['sum_log'] for x in seg)))
        print('SCREEN',symbol,len(all_candidates),flush=True)
    # No trade-count growth objective. >=3 per third only avoids zero-evidence selections.
    eligible=[x for x in all_candidates if all(z['trades']>=3 for z in x['segments'])]
    nominees=[max(eligible,key=lambda x:x['segments'][k]['sum_log']) for k in range(3)]
    ranked=sorted(eligible,key=lambda x:x['score'],reverse=True)
    selected=[]
    for x in nominees+ranked:
        if x['id'] not in [z['id'] for z in selected]:selected.append(x)
        if len(selected)==16:break
    results=[]
    for x in selected:
        sym=x['symbol'];ss={**series,sym:{r['t']:r for r in rowsets[sym]}}
        for frac in (.25,.5,.9):
            e={t:[dict(p) for p in ps] for t,ps in entries.items()}
            for p in x['ops']:e.setdefault(p['entry_ts'],[]).append({**p,'weight_scale':frac/1.15})
            full=run(ss,e,times,1.15);stress=run(ss,e,times,1.15,cost_mult=2)
            seg=[s.compact(run(ss,e,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)]
            a=[p for p in full['ledger'] if p['symbol'] in s.b.SYMBOLS];extra=[p for p in full['ledger'] if p['symbol']==sym]
            overlap=sum(any(p['entry_ts']<z['exit_ts'] and p['exit_ts']>z['entry_ts'] for z in a) for p in extra)
            assert overlap==0
            result=dict(id=x['id'],supplement_target_fraction=frac,leverage=3,full=s.compact(full),double_cost=s.compact(stress),segments=seg,extra_trades=len(extra),holding_overlap_trades=overlap)
            result['research_filter_pass']=full['return_pct']>base['return_pct'] and stress['return_pct']>baseline_stress['return_pct'] and full['hourly_mark_mdd_pct']>=-70 and not full['liquidation_proxy_count'] and not stress['liquidation_proxy_count'] and all(z['return_pct']>0 for z in seg)
            results.append(result)
        print('REPLAY',x['id'],round(results[-1]['full']['return_pct']),results[-1]['research_filter_pass'],flush=True)
    results.sort(key=lambda x:x['full']['return_pct'],reverse=True)
    output=dict(id='B-SPARSE-STAGE20',generated_at=datetime.now(timezone.utc).isoformat(),cuts=list(map(s.stamp,cuts)),tested=len(all_candidates),portfolios=len(results),baseline=s.compact(base),baseline_stress=s.compact(baseline_stress),baseline_segments=[s.compact(run(series,entries,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)],third_nominees=[x['id'] for x in nominees],results=results,independent_validation=False)
    (OUT/'results.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    (OUT/'screening.json').write_text(json.dumps([{k:v for k,v in x.items() if k!='ops'} for x in all_candidates]),encoding='utf8')
    print('DONE',OUT,'PASS',sum(x['research_filter_pass'] for x in results),flush=True)

if __name__=='__main__':main()
