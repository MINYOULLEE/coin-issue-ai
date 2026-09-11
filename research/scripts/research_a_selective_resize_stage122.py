"""Diagnose selective A resize suppression by symbol/side/increase-decrease. Research only."""
from __future__ import annotations
import inspect, json
from datetime import datetime, timezone
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_cost_resilience_stage117 as s117
import validate_a_scale_stop_stage70 as s70

OUT=s115.ab.OUT/'A_STAGE122_SELECTIVE_RESIZE_DIAGNOSIS.json'; END=s115.END; T=.015

def build():
 src=inspect.getsource(s70.replay)
 src=src.replace('dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None):',
  'dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None, resize_filter=None, min_delta_equity_fraction=0.0):')
 src=src.replace('stops = wins = allocation_actions = executed_rebalances = skipped = 0',
  'stops = wins = allocation_actions = executed_rebalances = skipped = selective_skips = 0')
 needle='''            delta_notional = abs(desired - qty[s]) * bar[s]["o"]
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1'''
 repl='''            delta_notional = abs(desired - qty[s]) * bar[s]["o"]
            same_direction = qty[s] * desired > 0
            resize_kind = "increase" if abs(desired) > abs(qty[s]) else "decrease"
            side_name = "long" if desired > 0 else "short"
            selected = (resize_filter is not None and s == resize_filter[0]
                        and side_name == resize_filter[1] and resize_kind == resize_filter[2])
            if same_direction and selected and delta_notional < min_delta_equity_fraction * equity:
                selective_skips += 1
                continue
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1'''
 if needle not in src: raise RuntimeError('anchor changed')
 src=src.replace(needle,repl).replace('"minimum_order_skips": skipped,','"minimum_order_skips": skipped, "selective_resize_skips": selective_skips,')
 ns=dict(s70.__dict__);exec(src,ns);return ns['replay']
REPLAY=build()
def run(m,b,f,start,end,rule=None,fee=.0004,slip=.001):
 return REPLAY(m,b,f,1.4,.15,start=start,end=end,fee=fee,stop_slippage=slip,dd_trigger=.35,
  dd_reduced_scale=.75,dd_recovery=.175,resize_filter=rule,min_delta_equity_fraction=T)
def c(x):return {k:v for k,v in x.items() if k not in ('stop_events','ledger')}

def main():
 maps,bars,funding=s113.a_inputs();start=min(set.intersection(*(set(bars[s]) for s in s115.a68.SYMBOLS)))
 guarded=s115.filtered(maps,bars,.035,.12,3,0)
 base=run(guarded,bars,funding,start,END);base3=run(guarded,bars,funding,start,END,None,.0012,.005)
 rows=[]
 for sym in s115.a68.SYMBOLS:
  for side in ('long','short'):
   for kind in ('increase','decrease'):
    rule=(sym,side,kind);full=run(guarded,bars,funding,start,END,rule);triple=run(guarded,bars,funding,start,END,rule,.0012,.005)
    rows.append({'symbol':sym,'side':side,'resize':kind,'full':c(full),'triple':c(triple),
     'full_delta_pct':full['return_pct']-base['return_pct'],'triple_delta_pct':triple['return_pct']-base3['return_pct'],
     'both_improve':full['return_pct']>base['return_pct'] and triple['return_pct']>base3['return_pct']})
    print(rule,round(rows[-1]['full_delta_pct'],1),round(rows[-1]['triple_delta_pct'],1),flush=True)
 ranked=sorted(rows,key=lambda x:(x['both_improve'],x['triple_delta_pct'],x['full_delta_pct']),reverse=True)
 # Complete expensive metrics only for groups that improve both normal and triple-cost history.
 for x in ranked:
  if not x['both_improve']:continue
  rule=(x['symbol'],x['side'],x['resize'])
  x['five']=c(run(guarded,bars,funding,s113.CUT,END,rule));x['double']=c(run(guarded,bars,funding,start,END,rule,.0008,.003))
 result={'id':'A-STAGE122-SELECTIVE-RESIZE-DIAGNOSIS','generated_at':datetime.now(timezone.utc).isoformat(),
  'research_only':True,'live_changes':False,'threshold_pct_of_equity':1.5,'baseline':c(base),'baseline_triple':c(base3),
  'groups':len(rows),'both_improve':sum(x['both_improve'] for x in rows),'ranked':ranked,
  'limitations':['Each group is tested alone; interactions among groups require a separate combination test.',
   'Historical diagnosis is not independent future validation.']}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'both_improve':result['both_improve'],'top':ranked[:8]},ensure_ascii=False))
if __name__=='__main__':main()
