"""Offline A replay clone with adverse-open gap fills and cash reconciliation."""
from research_adaptive_exits_stage27 import a, math, levels, hit, H

def a_replay(series,maps,fs,times,rule,start=None,end=None,cost_mult=1):
    ts=[t for t in times if (start is None or t>=start) and (end is None or t<end)]
    cash=100.;pos={};ledger=[];peak=closed_peak=100.;mdd=closed_mdd=0.;both_count=0;proxies=0;gap_adjustments=0
    fee=.0005*cost_mult;slip=.0002*cost_mult;fund=.0000125*cost_mult
    def close(sym,t,price,why):
        nonlocal cash,closed_peak,closed_mdd
        p=pos.pop(sym);px=price*(1-p['side']*slip)
        gross=p['qty']*p['side']*(px-p['entry']);exitfee=p['qty']*px*fee
        cash+=gross-exitfee;net=gross-exitfee-p['fee']-p['fund']
        ledger.append({'symbol':sym,'entry_ts':p['t'],'exit_ts':t,'net_pnl':net,'reason':why,'quantity':p['qty'],'entry_price':p['entry'],'exit_price':px})
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
                gap_px=min(px,bar['o']) if p['side']>0 else max(px,bar['o'])
                if abs(gap_px-px)>1e-12:gap_adjustments+=1
                px=gap_px
            if px is not None:close(s,t+H,px,reason)
            elif t==ts[-1]:close(s,t+H,bar['c'],'end')
            elif p['trail']:
                width=1.5*math.sqrt(24) if rule in ('horizon_trail','judgement_wide') else 2
                candidate=bar['c']-p['side']*width*fs[s].get(t+H,fs[s][p['t']])['atr']
                p['stop']=max(p['stop'],candidate) if p['side']>0 else min(p['stop'],candidate)
        equity=cash+sum(p['qty']*p['side']*(series[s][t]['c']-p['entry']) for s,p in pos.items())
        peak=max(peak,equity);mdd=min(mdd,equity/peak-1)
        if equity<=0:raise RuntimeError('A insolvency')
    assert abs(cash-100-sum(x['net_pnl'] for x in ledger))<max(1e-7,abs(cash)*1e-9), 'ledger cash reconciliation'
    return {'gap_adjustments':gap_adjustments,'start_usd':100,'end_usd':cash,'return_pct':cash-100,'closed_trade_mdd_pct':closed_mdd*100,'hourly_mark_mdd_pct':mdd*100,'trades':len(ledger),'win_rate_pct':100*sum(x['net_pnl']>0 for x in ledger)/max(1,len(ledger)),'ambiguous_hours':both_count,'liquidation_proxy_count':proxies,'ledger':ledger}
