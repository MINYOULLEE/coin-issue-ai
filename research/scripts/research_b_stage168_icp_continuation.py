"""Research-only ICP same-direction retention comparison against frozen Stage112.

No credentials, runtime writes, order requests or strategy standard changes.
Retain quantity, original entry and profit floor; only scheduled exits may extend.
"""
from __future__ import annotations
import builtins
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97
import validate_b_selective_gate_stage108 as s108

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/results/b_stage168_icp_continuation/RESULTS.json'
H=s97.HOUR

def compact(result):
    result={k:v for k,v in result.items() if k!='ledger'}
    return result

def extended_profit_exits(series, decisions, max_hours):
    """A fixed causal entry-time trigger, carried through later completed hours."""
    out={}
    hit=s101.ab.b91.s90.s86.s58.old.prev.hit
    bars=series['ICP']
    for d in decisions:
        if d['symbol']!='ICP' or not d.get('active') or not d.get('trigger_distance'):continue
        start=d['entry_ts'];raw=bars[start]['o']
        side=d['_side'];peak=0.;stop=None;armed=False
        for t in range(start,min(max(bars)+H,start+max_hours*H),H):
            if t not in bars:break
            bar=bars[t]
            if armed:
                price,_,_=hit(bar,stop,None,side)
                if price is not None:out[('ICP',start,t)]=float(price);break
            peak=max(peak,side*(bar['c']-raw))
            if peak>=d['trigger_distance']:
                armed=True;candidate=raw+side*peak*d['keep_fraction']
                stop=candidate if stop is None else max(stop,candidate) if side>0 else min(stop,candidate)
    return out

def runner(exits, max_hours, safe_extend=True):
    # Obtain the exact existing Stage112 replay, then add only retention/cost accounting.
    def compile_replay(src, env):
        src=src.replace('balance = start_cash','balance = start_cash\n    retained_boundaries = 0',1)
        old="if proxy or adaptive is not None or t >= p['exit_bar']:"
        new="""scheduled = t >= p['exit_bar']
            if max_hours > 2 and s == 'ICP' and scheduled and not proxy and adaptive is None:
                boundary=t+HOUR
                following=next((x for x in entries.get(boundary,[]) if x['symbol']=='ICP' and x['side']==p['side']),None)
                mark_now=balance+unrealized('c')
                risk_now=max(risk_peak,mark_now)
                total_gross=sum(q['qty']*series[k][t]['c'] for k,q in positions.items())
                reserve_now=sum(q['margin'] for q in positions.values())
                free_now=max(0.,min(balance-reserve_now,mark_now-reserve_now)-max(mark_now,0)*.05)
                extra_funding=p['qty']*bar['c']*FUNDING_PER_HOUR*cost_mult*2
                if (following is not None and following['exit_bar']<=last
                        and following['exit_bar']+HOUR-p['entry_ts']<=max_hours*HOUR
                        and boundary>=pause_until and mark_now/risk_now-1 > -trigger
                        and (not safe_extend or (total_gross<=gross_cap*max(mark_now,0) and free_now>=extra_funding))):
                    p['exit_bar']=following['exit_bar']
                    retained_boundaries+=1
                    scheduled=False
            if proxy or adaptive is not None or scheduled:"""
        assert src.count(old)==1
        src=src.replace(old,new)
        src=src.replace("net_pnl=net, proxy=bool(proxy)","net_pnl=net, proxy=bool(proxy), fees=p['entry_fee']+exit_fee, funding=p['funding']")
        src=src.replace('ledger=ledger)','retained_boundaries=retained_boundaries,ledger=ledger)')
        env['max_hours']=max_hours
        env['safe_extend']=safe_extend
        builtins.exec(src,env)
    env={**s97.__dict__,'exec':compile_replay}
    builtins.exec(inspect.getsource(s97.runner),env)
    return env['runner'](exits,3.75,.25,168)

def summarize(result):
    rows=result['ledger'];icp=[r for r in rows if r['symbol']=='ICP']
    out=compact(result)
    out.update(icp_trades=len(icp),icp_wins=sum(r['net_pnl']>0 for r in icp),
               fees_usd=sum(r['fees'] for r in rows),funding_usd=sum(r['funding'] for r in rows),
               icp_fees_usd=sum(r['fees'] for r in icp),icp_funding_usd=sum(r['funding'] for r in icp),
               max_icp_hold_hours=max(((r['exit_ts']-r['entry_ts'])/H for r in icp),default=0))
    return out

def self_checks():
    times=list(range(0,8*H,H))
    series={'ICP':{t:{'o':100.,'h':100.,'l':100.,'c':100.} for t in times}}
    entries={t:[dict(symbol='ICP',side=1,lev=5,entry_ts=t,exit_bar=t+H)] for t in times[:6:2]}
    baseline=runner({},2)(series,entries,times,.5)
    retained=runner({},4)(series,entries,times,.5)
    assert baseline['trades']==3 and retained['trades']==2 and retained['retained_boundaries']==1
    assert retained['end_usd']>baseline['end_usd'], 'constant market must benefit from skipped turnover'
    opposite={t:[dict(x,side=-1 if t==2*H else 1) for x in rows] for t,rows in entries.items()}
    assert runner({},4)(series,opposite,times,.5)['retained_boundaries']==0
    guarded=runner({('ICP',0,H):100.},4)(series,entries,times,.5)
    assert guarded['retained_boundaries']==1 and guarded['ledger'][0]['exit_ts']==2*H
    # The first trade's profit lock still closes it; only the later pair can merge.
    adverse={'ICP':{t:dict(row,**({'h':100.,'l':90.,'c':90.} if t==H else {})) for t,row in series['ICP'].items()}}
    assert runner({},4)(adverse,entries,times,.5)['ledger'][0]['exit_ts']==2*H

def main():
    self_checks()
    # Refuse implicit downloads; reuse existing research inputs only.
    original_fetch=s101.s99.fetch
    def cached_fetch(op):
        path=s101.s99.CACHE/f"{op['symbol']}_{op['entry_ts']}.json"
        if not path.exists():raise RuntimeError(f'Required existing minute cache missing: {path}')
        return original_fetch(op)
    s101.s99.fetch=cached_fetch
    series,raw_entries,times,_=s101.delayed_inputs(1)
    entries,blocked=s108.filter_entries(raw_entries,-.06)
    features={s:s101.ab.b91.s90.s86.s58.old.prev.features(list(v.values())) for s,v in series.items()}
    exits={};decisions=[]
    for symbol,(q,keep,conditional) in s101.ab.b91.s90.s86.CHOICES.items():
        learned,ds=s101.ab.b91.s90.s86.s61.learned_profit_locks(series,entries,features,symbol.lower(),q,keep,conditional)
        exits.update(learned)
        if symbol=='ICP':decisions=ds
    side_map={(x['symbol'],t):x['side'] for t,rows in entries.items() for x in rows}
    for d in decisions:
        if d['symbol']=='ICP':d['_side']=side_map[('ICP',d['entry_ts'])]
        assert d.get('latest_training_close') is None or d['latest_training_close']<=d['entry_ts']
    start,end=min(times),max(times)+H
    bounds=[start+(end-start)*k//3 for k in range(4)]
    rows=[]; baseline=None
    for limit,safe_extend in [(2,True)]+[(h,g) for h in (4,8,24,168) for g in (True,False)]:
        candidate_exits=dict(exits)
        if limit>2:
            extra=extended_profit_exits(series,decisions,limit)
            # The carried floor must reproduce the original ICP exit inside its original window.
            for key,value in exits.items():
                if key[0]=='ICP':assert abs(extra[key]-value)<1e-10
            candidate_exits.update(extra)
        fn=runner(candidate_exits,limit,safe_extend)
        five=fn(series,entries,times,1.15,start=s101.START_5Y,end=s101.END)
        full=fn(series,entries,times,1.15)
        row={'max_hold_hours':limit,'additional_continuation_margin_gross_guard':safe_extend,
             'method':'2h close/reenter' if limit==2 else 'retain fixed ICP quantity at consecutive same-side selected 2h boundaries; carry original profit floor',
             'five':summarize(five),'extended':summarize(full),
             'five_double_cost':summarize(fn(series,entries,times,1.15,cost_mult=2,start=s101.START_5Y,end=s101.END)),
             'extended_double_cost':summarize(fn(series,entries,times,1.15,cost_mult=2)),
             'thirds':[summarize(fn(series,entries,times,1.15,start=bounds[i],end=bounds[i+1])) for i in range(3)]}
        if limit==2:
            baseline=row
            standard=json.loads((ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf-8'))
            assert abs(row['five']['return_pct']-standard['reference']['return_pct'])<1e-7
            assert abs(row['extended']['return_pct']-standard['reference']['extended_7y']['return_pct'])<1e-7
        row['beat_baseline_both']=limit>2 and row['five']['return_pct']>baseline['five']['return_pct'] and row['extended']['return_pct']>baseline['extended']['return_pct']
        row['mdd_no_worse_both']=limit>2 and all(row[k]['hourly_mark_mdd_pct']>=baseline[k]['hourly_mark_mdd_pct']-1e-9 for k in ('five','extended'))
        row['thirds_no_worse']=limit>2 and all(x['return_pct']>=b['return_pct'] for x,b in zip(row['thirds'],baseline['thirds']))
        rows.append(row)
        print('RESULT',limit,safe_extend,json.dumps({k:row[k] for k in ('five','extended','beat_baseline_both','mdd_no_worse_both','thirds_no_worse')},ensure_ascii=False),flush=True)
    out={'id':'B-STAGE168-ICP-CONTINUATION','generated_at':datetime.now(timezone.utc).isoformat(),
         'research_only':True,'live_changes':False,'baseline_reproduced_exactly':True,'start_usd':100,
         'requested_comparison':'ICP same-side close/reentry versus fixed-quantity continuation including costs',
         'range_utc':[datetime.fromtimestamp(start/1000,timezone.utc).isoformat(),datetime.fromtimestamp(end/1000,timezone.utc).isoformat()],
         'calendar_note':'Extended calendar request is seven years; ICP and required shared inputs determine the shorter effective replay range.',
         'third_bounds':bounds,'btc_blocked':blocked,'rows':rows,
         'limitations':['Historical Binance spot-hourly proxy with existing ALGO/ADA minute substitution; no new BingX or ICP tick verification.',
                        'Candidate carries fixed entry-time causal learned profit thresholds from baseline research; extension behavior is new and not live-approved.',
                        'A 168h cap approximates holding until same-direction signal ends; it is not unbounded holding.',
                        'Fees in dollars cannot be compared as savings when account sizes differ; trade count and retained boundaries are also reported.',
                        'Three sections reuse historically researched data, not an untouched future holdout.']}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SAVED',OUT,flush=True)

if __name__=='__main__':main()
