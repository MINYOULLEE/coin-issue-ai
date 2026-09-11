"""Combination search over Stage122 selective resize groups. Research only."""
from __future__ import annotations
import inspect,itertools,json
from datetime import datetime,timezone
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_selective_resize_stage122 as s122
import validate_a_scale_stop_stage70 as s70
OUT=s115.ab.OUT/'A_STAGE123_SELECTIVE_RESIZE_COMBINATIONS.json';END=s115.END;T=.015

def build():
 src=inspect.getsource(s70.replay)
 src=src.replace('dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None):','dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None, resize_filters=None, min_delta_equity_fraction=0.0):')
 src=src.replace('stops = wins = allocation_actions = executed_rebalances = skipped = 0','stops = wins = allocation_actions = executed_rebalances = skipped = selective_skips = 0')
 needle='''            delta_notional = abs(desired - qty[s]) * bar[s]["o"]
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1'''
 repl='''            delta_notional = abs(desired - qty[s]) * bar[s]["o"]
            same_direction = qty[s] * desired > 0
            resize_kind = "increase" if abs(desired) > abs(qty[s]) else "decrease"
            side_name = "long" if desired > 0 else "short"
            selected = resize_filters is not None and (s, side_name, resize_kind) in resize_filters
            if same_direction and selected and delta_notional < min_delta_equity_fraction * equity:
                selective_skips += 1
                continue
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1'''
 if needle not in src:raise RuntimeError('anchor')
 src=src.replace(needle,repl).replace('"minimum_order_skips": skipped,','"minimum_order_skips": skipped, "selective_resize_skips": selective_skips,')
 ns=dict(s70.__dict__);exec(src,ns);return ns['replay']
R=build()
def run(m,b,f,start,end,rules,fee=.0004,slip=.001):return R(m,b,f,1.4,.15,start=start,end=end,fee=fee,stop_slippage=slip,dd_trigger=.35,dd_reduced_scale=.75,dd_recovery=.175,resize_filters=set(rules),min_delta_equity_fraction=T)
def c(x):return{k:v for k,v in x.items()if k not in('stop_events','ledger')}
def main():
 maps,bars,funding=s113.a_inputs();start=min(set.intersection(*(set(bars[s])for s in s115.a68.SYMBOLS)));g=s115.filtered(maps,bars,.035,.12,3,0)
 groups=[('SOL','long','decrease'),('SOL','short','decrease'),('ETH','long','increase'),('BTC','short','decrease'),('XRP','short','decrease')]
 rows=[]
 for n in range(1,len(groups)+1):
  for rules in itertools.combinations(groups,n):
   full=run(g,bars,funding,start,END,rules);triple=run(g,bars,funding,start,END,rules,.0012,.005)
   rows.append({'rules':[list(x)for x in rules],'full':c(full),'triple':c(triple)})
   print(len(rows),round(full['return_pct'],1),round(triple['return_pct'],1),flush=True)
 for x in rows:
  x['screen_pass']=x['full']['return_pct']>=4_937_714 and x['triple']['return_pct']>=1_000_000 and x['full']['hourly_adverse_bound_mdd_pct']>=-55
 ranked=sorted(rows,key=lambda x:(x['screen_pass'],x['triple']['return_pct'],x['full']['return_pct']),reverse=True)
 for x in ranked[:8]:
  rules=[tuple(z)for z in x['rules']];x['five']=c(run(g,bars,funding,s113.CUT,END,rules));x['double']=c(run(g,bars,funding,start,END,rules,.0008,.003))
  x['pass']=x['screen_pass'] and x['five']['return_pct']>=4_000_000 and x['double']['return_pct']>=2_000_000
 result={'id':'A-STAGE123-SELECTIVE-RESIZE-COMBINATIONS','generated_at':datetime.now(timezone.utc).isoformat(),'research_only':True,'live_changes':False,'screens':len(rows),'screen_passing':sum(x['screen_pass']for x in rows),'ranked':ranked,'limitations':['Combinations derive from the same historical diagnosis and require delay/synthetic validation.']}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'passing':sum(bool(x.get('pass'))for x in ranked),'top':ranked[:5]},ensure_ascii=False))
if __name__=='__main__':main()
