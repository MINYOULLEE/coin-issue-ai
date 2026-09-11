"""Offline A/B adaptive-exit screening. No network or production imports/writes.

All decisions use completed bars only. Hourly double touches are stop-first.
All thirds are discovery data: cross-application is NOT independent validation.
"""
import json, inspect, hashlib, math
from datetime import datetime, timezone
import numpy as np
import replay_mdd30 as a
import replay_reserved_margin_stage16 as b
import research_b_sparse_stage20 as sparse

H=3600000
OUT=a.RESULT_DIR/'adaptive_exits_stage27'
RULES=['baseline','atr_stop','structure_stop','atr_pair','structure_pair','mean_target','trail','judgement','horizon_stop','horizon_pair','horizon_trail','judgement_wide']

def features(rows):
    out={}
    for i in range(24,len(rows)):
        z=rows[i-23:i+1];last=rows[i]
        atr=sum(max(rows[j]['h']-rows[j]['l'],abs(rows[j]['h']-rows[j-1]['c']),abs(rows[j]['l']-rows[j-1]['c'])) for j in range(i-23,i+1))/24
        out[last['t']+H]={'atr':atr,'low':min(x['l'] for x in z[-6:]),'high':max(x['h'] for x in z[-6:]),
          'mean':sum(x['c'] for x in z)/24,'move':last['c']/rows[i-6]['c']-1,
          'eff':abs(last['c']-rows[i-6]['c'])/max(sum(abs(rows[j]['c']-rows[j-1]['c']) for j in range(i-5,i+1)),1e-12)}
    return out

def levels(rule,f,price,side,strength=.5,kind='reversion',hours=24):
    atr=max(f['atr'],price*1e-8)
    chosen=rule
    if rule=='judgement':
        # Causal choice, not a fitted future label: continuation gets room/trailing;
        # stretched reversion aims at the already observed mean.
        chosen='trail' if kind=='squeeze' or (strength>=.75 and side*f['move']>0 and f['eff']>.35) else 'mean_target'
    if chosen=='baseline':return None,None,False
    if rule=='judgement_wide':
        chosen='horizon_trail' if kind=='squeeze' or (strength>=.75 and side*f['move']>0 and f['eff']>.35) else 'horizon_stop'
    if chosen.startswith('horizon_'):
        distance=1.5*atr*math.sqrt(hours)
        return price-side*distance,price+side*2*distance if chosen=='horizon_pair' else None,chosen=='horizon_trail'
    distance=(2.5 if strength>=.75 else 1.5)*atr
    structure=min(price-.5*atr,f['low']-.25*atr) if side>0 else max(price+.5*atr,f['high']+.25*atr)
    stop=structure if chosen in ('structure_stop','structure_pair','mean_target') else price-side*distance
    target=None
    if chosen=='atr_pair':target=price+side*3*atr
    if chosen=='structure_pair':target=price+side*2*abs(price-stop)
    if chosen=='mean_target':target=f['mean'] if side*(f['mean']-price)>.5*atr else price+side*2*atr
    return stop,target,chosen=='trail'

def hit(bar,stop,target,side):
    # Gap stops fill at worse open; favorable target gaps capped at target.
    sl=stop is not None and (bar['l']<=stop if side>0 else bar['h']>=stop)
    tp=target is not None and (bar['h']>=target if side>0 else bar['l']<=target)
    if sl:return (min(stop,bar['o']) if side>0 else max(stop,bar['o'])),'stop',bool(tp)
    if tp:return target,'target',False
    return None,None,False

def b_setup():
    series,entries,times=b.prepare();busy=set()
    for t,ps in entries.items():
        for p in ps:busy.update(range(t,p['exit_bar']+H,H))
    standard=json.loads((a.ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf8'))
    for ident in standard['reference']['selector']['patterns']:
        sym,name=ident.split(':');rows=a.read_candles(a.DATA_DIR/f'{sym}USDT_1h.csv')
        for r in rows:r['symbol']=sym
        series[sym]={r['t']:r for r in rows}
        for p in sparse.s.opportunities(rows,dict(sparse.signals(rows))[name],1,3,busy):
            entries.setdefault(p['entry_ts'],[]).append({**p,'weight_scale':.9/1.15})
    return series,entries,times,standard

def b_runner(series,entries,fs,rule,standard):
    exits={};ambiguous=0
    for t,ps in entries.items():
        for p in ps:
            sym=p['symbol'];side=p['side'];f=fs[sym][t];price=series[sym][t]['o']
            hours=standard['symbols'][sym]['actual_hold_hours']
            stop,target,trail=levels(rule,f,price,side,kind=standard['symbols'][sym]['kind'],hours=hours)
            for now in range(t,p['exit_bar']+H,H):
                bar=series[sym].get(now)
                if bar is None:break
                px,reason,both=hit(bar,stop,target,side)
                if px is not None:
                    exits[(sym,t,now)]=px;ambiguous+=both;break
                if trail:
                    width=1.5*math.sqrt(hours) if rule in ('horizon_trail','judgement_wide') else 2
                    candidate=bar['c']-side*width*fs[sym].get(now+H,f)['atr']
                    stop=max(stop,candidate) if side>0 else min(stop,candidate)
    src=inspect.getsource(b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    src=src.replace("if proxy or t >= p['exit_bar']:","adaptive = exits.get((s,p['entry_ts'],t))\n            if adaptive is not None and p['qty']*p['side']*(adaptive-p['entry'])-p['entry_fee']-p['funding'] > -.9*p['margin']: proxy=False\n            if proxy or adaptive is not None or t >= p['exit_bar']:")
    src=src.replace("close = bar['c']*(1-p['side']*slip)","close = (adaptive if adaptive is not None else bar['c'])*(1-p['side']*slip)")
    env={**b.__dict__,'exits':exits};exec(src,env)
    return env['replay'],ambiguous

def a_replay(series,maps,fs,times,rule,start=None,end=None,cost_mult=1):
    ts=[t for t in times if (start is None or t>=start) and (end is None or t<end)]
    cash=100.;pos={};ledger=[];peak=closed_peak=100.;mdd=closed_mdd=0.;both_count=0;proxies=0
    fee=.0005*cost_mult;slip=.0002*cost_mult;fund=.0000125*cost_mult
    def close(sym,t,price,why):
        nonlocal cash,closed_peak,closed_mdd
        p=pos.pop(sym);px=price*(1-p['side']*slip)
        gross=p['qty']*p['side']*(px-p['entry']);exitfee=p['qty']*px*fee
        cash+=gross-exitfee;net=gross-exitfee-p['fee']-p['fund']
        ledger.append({'symbol':sym,'entry_ts':p['t'],'exit_ts':t,'net_pnl':net,'reason':why})
        closed_peak=max(closed_peak,cash);closed_mdd=min(closed_mdd,cash/closed_peak-1)
    for t in ts:
        equity=cash+sum(p['qty']*p['side']*(series[s][t]['o']-p['entry']) for s,p in pos.items())
        wants={s:mp[t] for s,mp in maps.items() if t in mp}
        for s,w in wants.items():
            if s in pos and abs(pos[s]['weight']-w)>1e-9:close(s,t,series[s][t]['o'],'rebalance')
        for s,w in wants.items():
            if w and s not in pos:
                side=1 if w>0 else -1;entry=series[s][t]['o']*(1+side*slip)
                qty=max(0,equity)*abs(w)/entry;entryfee=qty*entry*fee;cash-=entryfee
                pos[s]={'qty':qty,'side':side,'entry':entry,'fee':entryfee,'fund':0.,'t':t,'weight':w}
            if s in pos:
                p=pos[s];strength=abs(w)/max(a.CONFIG[s][0],1e-9)/2
                stop,target,trail=levels(rule,fs[s][t],series[s][t]['o'],p['side'],strength)
                # Stops may tighten on a new judgement, never widen existing risk.
                old=p.get('stop');p['stop']=stop if old is None or stop is None else max(old,stop) if p['side']>0 else min(old,stop)
                p['target']=target;p['trail']=trail
        for s,p in list(pos.items()):
            bar=series[s][t];charge=p['qty']*bar['o']*fund;p['fund']+=charge;cash-=charge
            px,reason,both=hit(bar,p['stop'],p['target'],p['side']);both_count+=both
            # Same conservative 90%-of-isolated-margin proxy as B, at A's 10x.
            limit=-.9*p['qty']*p['entry']/10
            worst=p['qty']*p['side']*(bar['l' if p['side']>0 else 'h']-p['entry'])-p['fee']-p['fund']
            exit_net=p['qty']*p['side']*(px-p['entry'])-p['fee']-p['fund'] if px is not None else None
            if worst<=limit and (exit_net is None or exit_net<=limit):
                px=p['entry']+p['side']*(limit+p['fee']+p['fund'])/p['qty'];reason='liquidation_proxy';proxies+=1
            if px is not None:close(s,t+H,px,reason)
            elif t==ts[-1]:close(s,t+H,bar['c'],'end')
            elif p['trail']:
                width=1.5*math.sqrt(24) if rule in ('horizon_trail','judgement_wide') else 2
                candidate=bar['c']-p['side']*width*fs[s].get(t+H,fs[s][p['t']])['atr']
                p['stop']=max(p['stop'],candidate) if p['side']>0 else min(p['stop'],candidate)
        equity=cash+sum(p['qty']*p['side']*(series[s][t]['c']-p['entry']) for s,p in pos.items())
        peak=max(peak,equity);mdd=min(mdd,equity/peak-1)
        if equity<=0:raise RuntimeError('A insolvency')
    return {'start_usd':100,'end_usd':cash,'return_pct':cash-100,'closed_trade_mdd_pct':closed_mdd*100,'hourly_mark_mdd_pct':mdd*100,'trades':len(ledger),'win_rate_pct':100*sum(x['net_pnl']>0 for x in ledger)/max(1,len(ledger)),'ambiguous_hours':both_count,'liquidation_proxy_count':proxies,'ledger':ledger}

def compact(x):return {k:v for k,v in x.items() if k!='ledger'}
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def main():
    OUT.mkdir(exist_ok=True)
    bs,entries,bt,std=b_setup();afs={};rows={s:a.read_candles(a.DATA_DIR/f'{s}USDT_1h.csv') for s in a.CONFIG}
    trees=a.load_trees();maps={}
    for s,rs in rows.items():
        maps[s]=a.targets(s,rs,trees[s],0);afs[s]=features(rs);print('A TARGETS',s,flush=True)
    aseries={s:{r['t']:r for r in rs} for s,rs in rows.items()};at=sorted(set.intersection(*(set(v) for v in aseries.values())))
    reference=a.replay(rows,maps,.0004);print('A LEGACY',reference,flush=True)
    bfs={s:features(list(v.values())) for s,v in bs.items()};results={}
    for plan,series,times in [('A',aseries,at),('B',bs,bt)]:
        cuts=[times[0]+int((times[-1]+H-times[0])*k/3) for k in range(4)];items=[]
        for rule in RULES:
            if plan=='B':
                fn,amb=b_runner(bs,entries,bfs,rule,std)
                run=lambda **kw:fn(bs,entries,bt,1.15,**kw)
            else:run=lambda **kw:a_replay(aseries,maps,afs,at,rule,**kw)
            full=run();stress=run(cost_mult=2);segments=[compact(run(start=cuts[k],end=cuts[k+1])) for k in range(3)]
            if plan=='B' and rule=='baseline':assert abs(full['end_usd']-std['reference']['end_usd'])<1e-6
            item={'rule':rule,'full':compact(full),'double_cost':compact(stress),'segments':segments}
            if plan=='B':item['candidate_ambiguous_hours']=amb
            items.append(item);save(f'{plan}_{rule}.json',{'summary':item,'ledger':full['ledger']})
            print(plan,rule,json.dumps(compact(full)),flush=True)
        baseline=items[0];nominations=[]
        for k in range(3):
            winner=max(items,key=lambda x:x['segments'][k]['return_pct']);nominations.append({'discovery_third':k+1,'rule':winner['rule'],'cross_applied_returns':[x['return_pct'] for x in winner['segments']]})
        for item in items:
            item['research_pass']=item['rule']!='baseline' and item['full']['return_pct']>baseline['full']['return_pct'] and item['double_cost']['return_pct']>baseline['double_cost']['return_pct'] and item['full']['hourly_mark_mdd_pct']>=-70 and not item['full']['liquidation_proxy_count'] and not item['double_cost']['liquidation_proxy_count'] and all(x['return_pct']>0 for x in item['segments'])
        results[plan]={'cuts':cuts,'nominations':nominations,'results':items}
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'plans':results,'A_legacy_reproduction':reference,'rules':RULES,'independent_validation':False,'live_changes':False,
      'limitations':['All thirds used for discovery; no untouched holdout','Hourly stop-first and gap handling; no intrahour certified execution','Binance spot, not actual BingX futures mark/funding/liquidation data','A fixed-entry quantity research comparator is not the historical hourly constant-weight headline','A fees 0.05%/side, slippage 0.02%/side, funding 0.00125%/hour; B same costs','B cooldowns and core/supplement idle gate preserve original selected opportunities even after early exit','B fee/funding reservations use original holding horizon','A fixed-quantity baseline is a research model, not an audited complete live executor clone'],
      'data_sha256':{s:hashlib.sha256((a.DATA_DIR/f'{s}USDT_1h.csv').read_bytes()).hexdigest() for s in sorted(set(aseries)|set(bs))}}
    save('RESULTS.json',output)

if __name__=='__main__':main()
