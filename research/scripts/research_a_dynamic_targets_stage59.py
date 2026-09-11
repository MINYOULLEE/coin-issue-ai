"""Research-only causal profit targets for A's fixed-quantity daily-position comparator."""
import json, math
from datetime import datetime, timezone
import numpy as np
import research_adaptive_exits_stage27 as base

H=3_600_000
OUT=base.a.RESULT_DIR/'a_dynamic_targets_stage59'
QUANTILES=(None,.30,.50,.65,.80,.95)

def episodes(series,maps,features):
    out=[]
    for symbol,mp in maps.items():
        decisions=sorted(mp)
        for j,t in enumerate(decisions[:-1]):
            weight=mp[t]
            prev=mp[decisions[j-1]] if j else 0
            if not weight or weight==prev or t not in series[symbol] or t not in features[symbol]:continue
            end=next((x for x in decisions[j+1:] if mp[x]!=weight),decisions[-1])
            bars=[series[symbol].get(x) for x in range(t,end,H)]
            if not bars or any(x is None for x in bars):continue
            side=1 if weight>0 else -1; raw=bars[0]['o']; atr=features[symbol][t]['atr']
            final=bars[-1]['c']; net=side*(final/raw-1)-.001-.0000125*len(bars)
            mfe=max(0,max(side*(x['h' if side>0 else 'l']-raw) for x in bars))/atr
            strength=round(abs(weight)/base.a.CONFIG[symbol][0],2)
            out.append(dict(symbol=symbol,side=side,entry=t,end=end,known=end,mfe=mfe,win=net>0,strength=strength))
    return out

def target_map(rows,series,features,q,picture=False):
    targets={};armed=0
    for cur in sorted(rows,key=lambda x:x['entry']):
        hist=[x for x in rows if x['symbol']==cur['symbol'] and x['side']==cur['side'] and x['known']<=cur['entry'] and x['win']][-120:]
        if picture:
            matched=[x for x in hist if x['strength']==cur['strength']]
            if len(matched)>=12:hist=matched
        if len(hist)<20:continue
        raw=series[cur['symbol']][cur['entry']]['o'];atr=features[cur['symbol']][cur['entry']]['atr']
        targets[(cur['symbol'],cur['entry'])]=raw+cur['side']*max(.5,float(np.quantile([x['mfe'] for x in hist],q)))*atr
        armed+=1
    return targets,armed

def replay(series,maps,targets,times,start=None,end=None,cost_mult=1):
    ts=[t for t in times if(start is None or t>=start)and(end is None or t<end)]
    cash=100.;pos={};blocked={};ledger=[];peak=closed_peak=100.;mdd=closed_mdd=0.;hits=0
    fee=.0005*cost_mult;slip=.0002*cost_mult;fund=.0000125*cost_mult
    def close(sym,t,price,why):
        nonlocal cash,closed_peak,closed_mdd,hits
        p=pos.pop(sym);px=price*(1-p['side']*slip);gross=p['qty']*p['side']*(px-p['entry']);exitfee=p['qty']*px*fee
        cash+=gross-exitfee;net=gross-exitfee-p['fee']-p['fund'];ledger.append({'symbol':sym,'entry_ts':p['t'],'exit_ts':t,'net_pnl':net,'reason':why})
        if why=='target':blocked[sym]=p['weight'];hits+=1
        closed_peak=max(closed_peak,cash);closed_mdd=min(closed_mdd,cash/closed_peak-1)
    for t in ts:
        equity=cash+sum(p['qty']*p['side']*(series[s][t]['o']-p['entry']) for s,p in pos.items())
        wants={s:mp[t] for s,mp in maps.items() if t in mp}
        for s,w in wants.items():
            if s in blocked and blocked[s]!=w:blocked.pop(s)
            if s in pos and abs(pos[s]['weight']-w)>1e-9:close(s,t,series[s][t]['o'],'rebalance')
        for s,w in wants.items():
            if w and s not in pos and s not in blocked:
                side=1 if w>0 else -1;entry=series[s][t]['o']*(1+side*slip);qty=max(0,equity)*abs(w)/entry;entryfee=qty*entry*fee;cash-=entryfee
                pos[s]={'qty':qty,'side':side,'entry':entry,'fee':entryfee,'fund':0.,'t':t,'weight':w,'target':targets.get((s,t))}
        for s,p in list(pos.items()):
            bar=series[s][t];charge=p['qty']*bar['o']*fund;p['fund']+=charge;cash-=charge
            target=p['target'];hit=target is not None and (bar['h']>=target if p['side']>0 else bar['l']<=target)
            if hit:close(s,t+H,target,'target')
            elif t==ts[-1]:close(s,t+H,bar['c'],'end')
        equity=cash+sum(p['qty']*p['side']*(series[s][t]['c']-p['entry']) for s,p in pos.items());peak=max(peak,equity);mdd=min(mdd,equity/peak-1)
        if equity<=0:raise RuntimeError('A insolvency')
    return {'start_usd':100,'end_usd':cash,'return_pct':cash-100,'closed_trade_mdd_pct':closed_mdd*100,'hourly_mark_mdd_pct':mdd*100,'trades':len(ledger),'win_rate_pct':100*sum(x['net_pnl']>0 for x in ledger)/max(1,len(ledger)),'targets_hit':hits,'ledger':ledger}

def compact(x):return{k:v for k,v in x.items()if k!='ledger'}
def main():
    OUT.mkdir(exist_ok=True)
    candles={s:base.a.read_candles(base.a.DATA_DIR/f'{s}USDT_1h.csv') for s in base.a.CONFIG};trees=base.a.load_trees()
    maps={s:base.a.targets(s,rs,trees[s],0) for s,rs in candles.items()};series={s:{r['t']:r for r in rs}for s,rs in candles.items()}
    features={s:base.features(rs)for s,rs in candles.items()};times=sorted(set.intersection(*(set(v)for v in series.values())))
    eps=episodes(series,maps,features);cuts=[times[0]+int((times[-1]+H-times[0])*k/3)for k in range(4)];results=[]
    for picture in (False,True):
      for q in QUANTILES:
        if q is None and picture:continue
        name='baseline' if q is None else ('picture_' if picture else 'target_')+f'q{int(q*100)}';targets,armed=({},0)if q is None else target_map(eps,series,features,q,picture)
        run=lambda **kw:replay(series,maps,targets,times,**kw);full=run();stress=run(cost_mult=2);thirds=[compact(run(start=cuts[k],end=cuts[k+1]))for k in range(3)]
        results.append({'rule':name,'full':compact(full),'double_cost':compact(stress),'thirds':thirds,'targets_armed':armed})
        (OUT/f'{name}.json').write_text(json.dumps({'summary':results[-1],'ledger':full['ledger']},indent=2),encoding='utf8');print(name,compact(full),flush=True)
    baseline=results[0]
    for x in results:x['pass']=x['rule']!='baseline'and x['full']['return_pct']>baseline['full']['return_pct']and x['double_cost']['return_pct']>baseline['double_cost']['return_pct']and all(t['return_pct']>0 for t in x['thirds'])
    out={'id':'A-DYNAMIC-TARGETS-STAGE59','generated_at':datetime.now(timezone.utc).isoformat(),'research_only':True,'start_usd':100,'results':results,
      'target_definition':'Prior completed profitable episodes, same symbol+direction; optional picture match by A exposure-strength tier; MFE/ATR quantile times current pre-entry ATR.',
      'execution_rule':'Target closes early; unchanged daily signal is locked out until A weight/direction changes, preventing repeated entry on the same prediction.',
      'limitations':['Fixed-quantity A research comparator, not historical constant-weight +257,597.52% replay','Binance spot hourly proxy and assumed costs','All thirds previously used; no independent holdout','No live changes']}
    (OUT/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'baseline':baseline,'best':max(results,key=lambda x:x['full']['return_pct'])},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
