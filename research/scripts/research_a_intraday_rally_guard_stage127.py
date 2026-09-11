"""Research-only causal intraday rally guard for current A Stage126."""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import validate_a_scale_stop_stage70 as s70

H=s115.H; END=s115.END; SYMBOLS=s115.a68.SYMBOLS
OUT=s115.ab.OUT/'A_STAGE127_INTRADAY_RALLY_GUARD.json'
RULES={('SOL','long','decrease'),('BTC','short','decrease')}

def compact(x): return {k:v for k,v in x.items() if k!='stop_events'}

def replay(maps,bars,funding,cfg,start,end,fee=.0004,slip=.001,overlay_slip=0.,overlay_fill_prices=None):
    common=[t for t in sorted(set.intersection(*(set(bars[s]) for s in SYMBOLS))) if start<=t<end]
    equity=peak=100.; qty={s:0. for s in SYMBOLS}; entry={s:None for s in SYMBOLS}
    anchor={}; fired=False; phase=0; streak=0; close_mdd=adverse_mdd=0.; events=stops=overlay=0; turnover=0.
    guard=False; overlay_events=[]
    for i,t in enumerate(common):
        b={s:bars[s][t] for s in SYMBOLS}
        if i:
            pt=common[i-1]
            for s in SYMBOLS: equity+=qty[s]*(b[s]['o']-bars[s][pt]['c'])
        if equity<=0: break
        dd=equity/max(peak,1e-12)-1
        if not guard and dd<=-.35: guard=True
        elif guard and dd>=-.175: guard=False
        daily=any(t in maps[s] for s in SYMBOLS)
        if daily:
            anchor={s:b[s]['o'] for s in SYMBOLS}; fired=False; phase=0; streak=0
            scale=1.4*(.75 if guard else 1)
            for s in SYMBOLS:
                if t not in maps[s]: continue
                desired=s70.rounded_qty(s,maps[s][t]*scale*equity,b[s]['o'])
                dn=abs(desired-qty[s])*b[s]['o']; same=desired*qty[s]>0
                kind='increase' if abs(desired)>abs(qty[s]) else 'decrease'; side='long' if desired>0 else 'short'
                if same and (s,side,kind) in RULES and dn<.0125*equity: continue
                if abs(desired-qty[s])>1e-12: events+=1
                equity-=dn*fee; turnover+=dn; qty[s]=desired; entry[s]=b[s]['o'] if desired else None
        # At this hour open only prior completed closes are visible.
        second_enabled=cfg.get('second_mult') is not None
        if i and anchor and (not fired or second_enabled and phase==1) and cfg['scope']!='off':
            pt=common[i-1]; rets={s:bars[s][pt]['c']/anchor[s]-1 for s in SYMBOLS}
            btc_cut=cfg['btc'] if phase==0 else cfg.get('second_btc',cfg['btc'])
            asset_cut=cfg['asset'] if phase==0 else cfg.get('second_asset',cfg['asset'])
            breadth_cut=cfg['breadth'] if phase==0 else cfg.get('second_breadth',cfg['breadth'])
            confirm_cut=cfg.get('confirm',1) if phase==0 else cfg.get('second_confirm',1)
            target_mult=cfg['mult'] if phase==0 else cfg['second_mult']
            breadth=sum(x>=asset_cut for x in rets.values())
            raw_trigger=rets['BTC']>=btc_cut and breadth>=breadth_cut
            streak=streak+1 if raw_trigger else 0
            trigger=streak>=confirm_cut
            if trigger:
                for s in SYMBOLS:
                    if qty[s]>=0 or (cfg['scope']=='alts' and s not in ('ETH','XRP','SOL')): continue
                    desired=s70.rounded_qty(s,qty[s]*target_mult,b[s]['o'])
                    fill=(overlay_fill_prices or {}).get((s,t),b[s]['o'])
                    closed_qty=qty[s]-desired
                    dn=abs(closed_qty)*fill
                    equity+=closed_qty*(fill-b[s]['o'])-dn*(fee+overlay_slip); turnover+=dn
                    if abs(desired-qty[s])>1e-12: events+=1; overlay+=1
                    if abs(desired-qty[s])>1e-12: overlay_events.append({'time':t,'symbol':s,'phase':phase+1,'notional':dn})
                    qty[s]=desired
                    if not desired: entry[s]=None
                phase+=1; streak=0
                fired=not second_enabled or phase>=2
        adv=equity
        for s in SYMBOLS:
            if qty[s]: adv+=qty[s]*((b[s]['l']-b[s]['o']) if qty[s]>0 else (b[s]['h']-b[s]['o']))
        adverse_mdd=min(adverse_mdd,adv/max(peak,1e-12)-1)
        for s in SYMBOLS:
            q=qty[s]
            if not q: continue
            e=entry[s]; hit=(q>0 and b[s]['l']<=e*.85) or (q<0 and b[s]['h']>=e*1.15)
            if hit:
                fill=e*.85*(1-slip) if q>0 else e*1.15*(1+slip)
                equity+=q*(fill-b[s]['o'])-abs(q)*fill*fee; turnover+=abs(q)*fill
                qty[s]=0.; entry[s]=None; stops+=1; events+=1
            else:
                equity+=q*(b[s]['c']-b[s]['o'])-q*b[s]['c']*funding[s].get(t,0.)
        peak=max(peak,equity); close_mdd=min(close_mdd,equity/peak-1)
    return {'start_usd':100,'end_usd':equity,'return_pct':equity-100,'close_mark_mdd_pct':close_mdd*100,
            'hourly_adverse_bound_mdd_pct':adverse_mdd*100,'total_order_events':events,
            'overlay_actions':overlay,'overlay_events':overlay_events,'emergency_stop_exits':stops,'turnover_usd':turnover}

def main():
    maps,bars,funding=s113.a_inputs(); start=min(set.intersection(*(set(bars[s]) for s in SYMBOLS)))
    maps=s115.filtered(maps,bars,.035,.12,3,0)
    base={'scope':'off','btc':9,'asset':9,'breadth':9,'mult':1}
    configs=[]
    for scope in ('alts','all'):
      for btc in (.01,.02,.03):
       for asset in (.01,.02,.03):
        for breadth in (3,4,5):
         for mult in (0,.5): configs.append({'scope':scope,'btc':btc,'asset':asset,'breadth':breadth,'mult':mult})
    baseline={'five':replay(maps,bars,funding,base,s113.CUT,END),'seven':replay(maps,bars,funding,base,start,END)}
    rows=[]
    for n,cfg in enumerate(configs,1):
        five=replay(maps,bars,funding,cfg,s113.CUT,END); seven=replay(maps,bars,funding,cfg,start,END)
        cost=replay(maps,bars,funding,cfg,start,END,.0012,.005)
        row={'config':cfg,'five':five,'seven':seven,'triple_cost':cost}
        row['pass']=five['return_pct']>=baseline['five']['return_pct'] and seven['return_pct']>=baseline['seven']['return_pct'] and cost['return_pct']>=1_000_000 and seven['hourly_adverse_bound_mdd_pct']>=baseline['seven']['hourly_adverse_bound_mdd_pct']
        rows.append(row)
        if n%18==0: print('screen',n,flush=True)
    ranked=sorted(rows,key=lambda x:(x['pass'],x['seven']['return_pct'],x['triple_cost']['return_pct']),reverse=True)
    result={'id':'A-STAGE127-INTRADAY-RALLY-GUARD','generated_at':datetime.now(timezone.utc).isoformat(),'research_only':True,'live_changes':False,
            'causality':'At each hourly open, use only closes completed since the latest daily A execution anchor.',
            'baseline':baseline,'screens':len(rows),'passing':sum(x['pass'] for x in rows),'ranked':ranked,
            'limitations':['Hourly OHLC cannot resolve intrahour trigger/fill order.','Same historical data; finalists require thirds, delay and ordered synthetic validation.']}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'baseline':baseline,'screens':len(rows),'passing':result['passing'],'top':ranked[:5]},ensure_ascii=False))
if __name__=='__main__': main()
