"""Research only. Causal B-idle additions; no network, no deployment or live state writes."""
import inspect,json,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import replay_reserved_margin_stage16 as b
import replay_mdd30 as core

ONE_HOUR='--one-hour' in sys.argv
RID='B-COMPLEMENT-STAGE18-1H' if ONE_HOUR else 'B-COMPLEMENT-STAGE17'
OUT=core.RESULT_DIR/('b_complement_stage18_1h' if ONE_HOUR else 'b_complement_stage17')
def compact(r): return {k:v for k,v in r.items() if k!='ledger'}
def stamp(t): return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()

def patterns(rows):
 o,h,l,c,v=[np.array([r[k] for r in rows]) for k in ('o','h','l','c','v')]
 span=np.maximum(h-l,1e-12); body=np.abs(c-o)/span
 lower=(np.minimum(o,c)-l)/span;upper=(h-np.maximum(o,c))/span
 ret=np.r_[0,c[1:]/c[:-1]-1]
 # All windows exclude the signal bar. Signal bar itself must close before entry.
 avg=np.r_[np.full(24,np.nan),np.convolve(v,np.ones(24)/24,'valid')[:-1]]
 for wick in (.55,.7,.8):
  for vr in (1.,1.5):
   yield f'wick_rejection_w{wick}_v{vr}',np.where((lower>wick)&(body<.3)&(v>avg*vr),1,np.where((upper>wick)&(body<.3)&(v>avg*vr),-1,0))
 for shock in (.01,.02,.03):
  # High-volume impulse which closes back in the opposite half of its range.
  yield f'failed_impulse_{shock}',np.where((ret<-shock)&((c-l)/span>.6)&(v>avg*1.5),1,np.where((ret>shock)&((c-l)/span<.4)&(v>avg*1.5),-1,0))
 for n in (3,5,7):
  positive=np.convolve((ret>0).astype(int),np.ones(n,dtype=int),'full')[:len(c)]
  negative=np.convolve((ret<0).astype(int),np.ones(n,dtype=int),'full')[:len(c)]
  for shock in (.015,.03):
   move=np.r_[np.zeros(n),c[n:]/c[:-n]-1]
   yield f'streak_exhaustion_n{n}_move{shock}',np.where((negative==n)&(move<-shock),1,np.where((positive==n)&(move>shock),-1,0))

def opportunities(rows,sig,hold,lev,busy):
 out=[];nxt=169
 for i in np.flatnonzero(sig[169:len(rows)-hold])+169:
  if i<nxt:continue
  t=rows[i+1]['t']
  if rows[i]['t']-rows[i-169]['t']!=169*3600000 or t-rows[i]['t']!=3600000:continue
  if t in busy:continue # Uses only B signals already confirmed at entry time.
  nxt=int(i)+hold+1
  out.append(dict(symbol=rows[0]['symbol'],side=int(sig[i]),lev=lev,entry_ts=t,exit_bar=rows[i+hold]['t']))
 return out

def screen(rows,ops,cuts):
 by={r['t']:r for r in rows};rs=[]
 for a,z in zip(cuts,cuts[1:]):
  vals=[]
  for p in ops:
   if not a<=p['entry_ts'] or p['exit_bar']+3600000>z:continue
   en=by[p['entry_ts']]['o']*(1+p['side']*b.SLIP);ex=by[p['exit_bar']]['c']*(1-p['side']*b.SLIP)
   hours=(p['exit_bar']-p['entry_ts'])/3600000+1
   vals.append(p['lev']*(p['side']*(ex/en-1)-b.FEE*(1+ex/en)-hours*b.FUNDING_PER_HOUR))
  # Screening metric only. Actual portfolio results always use reserved-margin replay.
  vals=np.array(vals);rs.append(dict(trades=len(vals),sum_log=float(np.log(np.maximum(.01,1+vals*.2)).sum()),mean_net=float(vals.mean()) if len(vals) else 0))
 return rs

def main():
 OUT.mkdir(exist_ok=True)
 print('Loading and reproducing frozen B baseline...',flush=True)
 series,entries,times=b.prepare();cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
 baseline=b.replay(series,entries,times,1.15)
 expected=json.loads((core.ROOT/'strategy/plan_b_standard.json').read_text())['reference']
 assert abs(baseline['return_pct']-expected['return_pct'])<1e-6
 # Reuse exact frozen simulator with a per-proposal demand scale. Default 1 preserves B.
 source=inspect.getsource(b.replay)
 assert 'target*(1+x' in source and 'margin = target*shrink' in source
 source=source.replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
 env=dict(b.__dict__);exec(source,env);replay=env['replay']
 assert abs(replay(series,entries,times,1.15)['end_usd']-baseline['end_usd'])<1e-8
 busy=set()
 for t,ps in entries.items():
  for p in ps:busy.update(range(t,p['exit_bar']+3600000,3600000))
 clustering=dict(opportunities=sum(map(len,entries.values())),entry_hours=len(entries),multi_signal_hours=sum(len(x)>1 for x in entries.values()),busy_hours=len(busy&set(times)),total_hours=len(times))
 print('BASELINE',json.dumps(compact(baseline)), 'CLUSTERING',clustering,flush=True)
 rows_by={};candidates=[]
 for path in sorted(core.DATA_DIR.glob('*USDT_1h.csv')):
  symbol=path.name.replace('USDT_1h.csv','')
  if symbol in b.SYMBOLS:continue
  rows=core.read_candles(path)
  if rows[0]['t']>times[0] or rows[-1]['t']<times[-1]:continue
  for r in rows:r['symbol']=symbol
  rows_by[symbol]=rows
  for name,sig in patterns(rows):
   raw=[rows[i+1]['t'] for i in np.flatnonzero(sig[:-1])]
   overlap=sum(t in busy for t in raw)/max(1,len(raw))
   for hold in ((1,) if ONE_HOUR else (2,4,8)):
    for lev in (2,3):
     ops=opportunities(rows,sig,hold,lev,busy);segments=screen(rows,ops,cuts)
     candidate=dict(id=f'{symbol}:{name}:h{hold}:l{lev}',symbol=symbol,pattern=name,hold_hours=hold,leverage=lev,raw_overlap_pct=overlap*100,segments=segments,ops=ops)
     candidate['score']=min(x['sum_log'] for x in segments)
     candidates.append(candidate)
  print('SCREENED',symbol,len(candidates),flush=True)
 eligible=[x for x in candidates if all(s['trades']>=15 for s in x['segments'])]
 # Each third independently nominates a rule; all nominees are compared on every third.
 winners=[max(eligible,key=lambda x:x['segments'][k]['sum_log']) for k in range(3)]
 ranked=sorted(eligible,key=lambda x:x['score'],reverse=True)
 selected=[]
 for x in winners+ranked:
  if x['id'] not in [q['id'] for q in selected]:selected.append(x)
  if len(selected)>=12:break
 results=[]
 for rank,x in enumerate(selected):
  symbol=x['symbol'];s={**series,symbol:{r['t']:r for r in rows_by[symbol]}}
  for fraction in (.1,.25):
   e={t:[dict(p) for p in ps] for t,ps in entries.items()}
   for p in x['ops']:e.setdefault(p['entry_ts'],[]).append({**p,'weight_scale':fraction/1.15})
   full=replay(s,e,times,1.15);segs=[compact(replay(s,e,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)]
   stress=replay(s,e,times,1.15,cost_mult=2)
   base_actual={p['entry_ts'] for p in full['ledger'] if p['symbol'] in b.SYMBOLS}
   extra=[p for p in full['ledger'] if p['symbol']==symbol]
   base_intervals=[(p['entry_ts'],p['exit_ts']) for p in full['ledger'] if p['symbol'] in b.SYMBOLS]
   overlap_trades=sum(any(p['entry_ts']<end and p['exit_ts']>start for start,end in base_intervals) for p in extra)
   item=dict(candidate={k:v for k,v in x.items() if k!='ops'},extra_target_fraction=fraction,full=compact(full),segments=segs,double_cost=compact(stress),extra_trades=len(extra),same_hour_entries=sum(p['entry_ts'] in base_actual for p in extra),holding_overlap_trades=overlap_trades)
   if ONE_HOUR:assert overlap_trades==0,'One-hour supplement must finish before next B entry boundary'
   item['preliminary_pass']=full['return_pct']>baseline['return_pct'] and full['trades']>baseline['trades'] and full['hourly_mark_mdd_pct']>=-70 and full['liquidation_proxy_count']==0 and all(z['return_pct']>0 for z in segs)
   results.append(item)
   print('COMBO',x['id'],fraction,round(full['return_pct'],2),full['trades'],round(full['hourly_mark_mdd_pct'],2),item['preliminary_pass'],flush=True)
 results.sort(key=lambda x:(x['preliminary_pass'],x['full']['return_pct']),reverse=True)
 best=results[0]
 output=dict(id=RID,generated_at=datetime.now(timezone.utc).isoformat(),range=[stamp(cuts[0]),stamp(cuts[-1])],cuts=list(map(stamp,cuts)),baseline=compact(baseline),baseline_stress=compact(b.replay(series,entries,times,1.15,cost_mult=2)),baseline_segments=[compact(b.replay(series,entries,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)],clustering=clustering,tested=len(candidates),portfolio_tests=len(results),third_winners=[x['id'] for x in winners],results=results,limitations=['All three thirds used for discovery; cross-period comparison is NOT independent holdout','B-idle gate uses already-confirmed B opportunities only; multi-hour supplements can overlap future B signals','Hourly close MDD and adverse OHLC bound are not exchange mark-price liquidation guarantees','No contract quantity floors, minimum notional, historical listing/funding/maintenance tiers; research only'])
 (OUT/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
 (OUT/'screening.json').write_text(json.dumps([{k:v for k,v in x.items() if k!='ops'} for x in candidates],ensure_ascii=False),encoding='utf8')
 folder='success' if best['preliminary_pass'] else 'failure'
 (core.RESULT_DIR/folder/(RID+'.md')).write_text('# '+RID+'\n\nPreliminary research candidate only; not adopted or independently validated.\n\n'+json.dumps(best,ensure_ascii=False,indent=2)+'\n\nDetails: ../'+OUT.name+'/results.json\n',encoding='utf8')
 print('SAVED',OUT,'BEST',json.dumps(best),flush=True)
if __name__=='__main__':main()
