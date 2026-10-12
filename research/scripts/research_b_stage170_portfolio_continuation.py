"""Full isolated B portfolio: causal event-time ICP retention vs Stage112 exits.

Uses cached ICP perpetual minutes, cached ALGO/ADA execution minutes, and hourly
proxies for remaining markets. No live interfaces. No orders or runtime writes.
"""
from __future__ import annotations
import hashlib,json,math,pickle
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import research_b_stage168_icp_continuation as prior
import verify_b_stage169_icp_minutes as minute

ROOT=prior.ROOT;H=prior.H;M=60000
OUT=ROOT/'research/results/b_stage170_portfolio_continuation'
STANDARD=json.loads((ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf-8'))
START=prior.s101.START_5Y;END=prior.s101.END

def prepare():
    series,core_entries,times,_,_,raw,features,_=prior.s101.ab.build_b_inputs()
    entries,blocked=prior.s108.filter_entries(raw,-.06)
    learned={}
    for symbol,(q,keep,conditional) in prior.s101.ab.b91.s90.s86.CHOICES.items():
        _,ds=prior.s101.ab.b91.s90.s86.s61.learned_profit_locks(series,entries,features,symbol.lower(),q,keep,conditional)
        for d in ds:
            if d['symbol']!=symbol:continue
            assert d.get('latest_training_close') is None or d['latest_training_close']<=d['entry_ts']
            learned[(symbol,d['entry_ts'])]=d.get('trigger_distance',0)/series[symbol][d['entry_ts']]['o']
    signals={}
    for t,rows in entries.items():
        if t<START or t>=END:continue
        signals[t]=[]
        for old in rows:
            symbol=old['symbol'];rule=STANDARD['symbols'][symbol]
            previous=series[symbol].get(t-H)
            if not previous:raise RuntimeError('missing prior signal bar')
            old=dict(old,exit_bar=t+(rule['actual_hold_hours']-1)*H)
            atr=features[symbol][t]['atr'] if symbol in STANDARD['profit_lock']['symbols'] else 0
            signals[t].append({**old,'deadline':old['exit_bar']+H,'signal_price':previous['c'],'atr':atr,
                               'learned_ratio':learned.get((symbol,t),0),'group':rule['group']})
    core_busy=set()
    for t,rows in core_entries.items():
        for row in rows:core_busy.update(range(t,t+STANDARD['symbols'][row['symbol']]['actual_hold_hours']*H,H))
    minutes={s:{} for s in ('ICP','ALGO','ADA')};coverage=Counter()
    source=json.loads((minute.OUT/'RESULTS.json').read_text(encoding='utf-8'))
    for window in source['manifest']:
        path=minute.CACHE/f"ICP_{window['start']}.json"
        assert minute.digest(path)==window['sha256']
        for row in json.loads(path.read_text(encoding='utf-8')):
            minutes['ICP'][int(row[0])]=dict(zip(('o','h','l','c'),map(float,row[1:5])))
        coverage['ICP_windows']+=1
    for symbol in ('ALGO','ADA'):
        for path in prior.s101.s99.CACHE.glob(symbol+'_*.json'):
            for row in json.loads(path.read_text(encoding='utf-8')):
                t=int(row[0]);bar=dict(zip(('o','h','l','c'),map(float,row[1:5])))
                if t in minutes[symbol]:assert minutes[symbol][t]==bar
                minutes[symbol][t]=bar
            coverage[symbol+'_windows']+=1
    for symbol,rows in minutes.items():coverage[symbol+'_minutes']=len(rows)
    return series,signals,minutes,core_busy,dict(coverage),blocked

def run(series,signals,minutes,core_busy,retain,delay=1,cost=1,policy='frozen',haircut=0,start=START,end=END):
    balance=peak=risk_peak=100.;pause_until=-1
    positions={};pending_signals={};ledger=[];actions=[];quotes={};counts=Counter()
    mdd=adverse_mdd=closed_mdd=0.;closed_peak=100.;max_reserved=max_gross=0.
    fee=.0005*cost;slip=.0002*cost;fund=.0000125*cost
    hours=list(range(start,end+H,H))
    events=set(hours)
    for rows in minutes.values():events.update(t for t in rows if start<=t<=end+5*M)
    for t,rows in signals.items():
        if not start<=t<end:continue
        events.update(t+k*M for k in range(5))
        for row in rows:events.update(row['deadline']+k*M for k in range(5))
    # Hourly-only markets can have a protective close at any boundary plus delay.
    events.update(t+delay*M for t in hours)
    events=sorted(t for t in events if start<=t<=end+5*M)
    previous_clock=start
    def equity():return balance+sum(p['qty']*p['side']*(quotes[s]-p['entry']) for s,p in positions.items())
    def reserved():return sum(p['reservation'] for p in positions.values())
    def gross():return sum(p['qty']*quotes[s] for s,p in positions.items())
    def free():return max(0.,balance-sum(p['margin'] for p in positions.values()))
    def close(symbol,stamp,reason):
        nonlocal balance,closed_peak,closed_mdd
        p=positions[symbol];price=quotes[symbol]*(1-p['side']*(slip+haircut))
        exit_fee=p['qty']*price*fee;profit=p['qty']*p['side']*(price-p['entry'])
        balance+=profit-exit_fee
        net=profit-p['entry_fee']-exit_fee-p['funding']
        ledger.append({'symbol':symbol,'side':p['side'],'entry_ts':p['filled_at'],'exit_ts':stamp,'entry':p['entry'],'close':price,
                       'quantity':p['qty'],'margin':p['margin'],'net_pnl':net,'fees':p['entry_fee']+exit_fee,'funding':p['funding'],
                       'retained':p['retained'],'exit_reason':reason,'group':p['group']})
        actions.append({'t':stamp,'symbol':symbol,'event':'close','reason':reason})
        del positions[symbol];closed_peak=max(closed_peak,balance);closed_mdd=min(closed_mdd,balance/closed_peak-1)
    def request_close(symbol,stamp,reason):
        p=positions[symbol]
        if p.get('close_due') is not None:return
        p['close_due']=stamp+delay*M;p['close_reason']=reason
        counts['close_requests']+=1
        if delay==0:close(symbol,stamp,reason)
        else:
            # All minute-triggered ICP exits must have the delayed observation available.
            if symbol=='ICP' and p['close_due'] not in minutes['ICP']:raise RuntimeError('missing delayed ICP exit minute')
    for stamp in events:
        # Accrue only elapsed holding time at the last observed quote.
        for s,p in positions.items():
            funding=p['qty']*quotes[s]*fund*(stamp-previous_clock)/H
            p['funding']+=funding;balance-=funding
        previous_clock=stamp
        boundary=stamp//H*H;is_hour=stamp%H==0
        if is_hour:
            for s,rows in series.items():
                if stamp in rows:quotes[s]=rows[stamp]['o']
                elif stamp-H in rows:quotes[s]=rows[stamp-H]['c']
        for s,rows in minutes.items():
            if stamp in rows:quotes[s]=rows[stamp]['o']
        for s in list(positions):
            p=positions[s]
            if p.get('close_due') is not None and stamp>=p['close_due']:close(s,stamp,p['close_reason'])
        eq=equity()
        if pause_until>=0 and stamp>=pause_until:pause_until=-1;risk_peak=eq
        risk_peak=max(risk_peak,eq)
        if pause_until<0 and eq/risk_peak-1<=-.25:pause_until=stamp+168*H;counts['risk_pause']+=1
        # Check previous completed minute against its existing floor before updating the hour floor.
        for s in list(positions):
            p=positions[s]
            if p.get('close_due') is not None or p['floor'] is None:continue
            previous=minutes.get(s,{}).get(stamp-M)
            crossed=False
            if previous and stamp-M>=p['filled_at']:
                crossed=previous['l']<=p['floor'] if p['side']>0 else previous['h']>=p['floor']
            elif is_hour and s not in minutes:
                previous=series[s].get(stamp-H)
                if previous and stamp-H>=p['filled_at']:
                    crossed=previous['l']<=p['floor'] if p['side']>0 else previous['h']>=p['floor']
            if crossed:request_close(s,stamp,'profit_lock')
        if is_hour:
            for s in list(positions):
                p=positions[s]
                if p.get('close_due') is not None or stamp<=p['filled_at'] or p['trigger']<=0:continue
                previous=minutes.get(s,{}).get(stamp-M) or series[s].get(stamp-H)
                if not previous:
                    counts['missing_protection_hour']+=1
                    continue  # Keep the previous floor; never invent a completed candle.
                favorable=(previous['c']/p['entry']-1)*p['side'];p['peak']=max(p['peak'],favorable)
                if p['peak']>=p['trigger']:
                    floor=p['entry']*(1+p['side']*p['peak']*p['keep'])
                    p['floor']=floor if p['floor'] is None else max(p['floor'],floor) if p['side']>0 else min(p['floor'],floor)
            # Signals are published on their original selected boundaries independently of fills.
            for old in signals.get(stamp,[]):
                if old['deadline']<=end:pending_signals[(old['symbol'],stamp)]=dict(old)
        for s in list(positions):
            p=positions[s]
            if p.get('close_due') is not None:continue
            if p['floor'] is not None and (quotes[s]<=p['floor'] if p['side']>0 else quotes[s]>=p['floor']):
                request_close(s,stamp,'profit_lock');continue
            if stamp<p['deadline']:continue
            following=pending_signals.get((s,stamp))
            eq=equity();total_gross=gross();held=reserved()
            avail=max(0.,min(balance-held,eq-held)-max(eq,0)*.05)
            funding_extra=p['qty']*quotes[s]*fund*2
            safe=(eq>0 and stamp>=pause_until and total_gross<=3.75*eq and min(avail,free())>=funding_extra)
            if (retain and s=='ICP' and following and following['side']==p['side'] and safe
                    and following['deadline']-p['confirmed_at']<=8*H):
                p['deadline']=following['deadline'];p['retained']+=1;counts['retained_boundaries']+=1
                del pending_signals[(s,stamp)]
                actions.append({'t':stamp,'symbol':s,'event':'retain','quantity':p['qty']})
            else:request_close(s,stamp,'scheduled')
        # Expire before dispatch and never extend another group's TTL to wait for collateral.
        for key,x in list(pending_signals.items()):
            if stamp-x['entry_ts']>=5*M:counts['expired']+=1;del pending_signals[key]
        eligible=[(key,x) for key,x in pending_signals.items() if stamp-x['entry_ts']>=delay*M]
        if eligible:
            group='core' if any(x['group']=='core' for _,x in eligible) else 'supplement'
            if any(p.get('close_due') is not None for p in positions.values()):counts['waiting_close']+=1
            elif any(p['group']!=group for p in positions.values()):counts['group_conflict']+=1
            elif group=='supplement' and boundary in core_busy:counts['core_idle_gate']+=1
            elif stamp<pause_until:counts['risk_blocked']+=len(eligible)
            else:
                proposals=[]
                for key,x in eligible:
                    s=x['symbol']
                    if x['group']!=group or s in positions:continue
                    if s not in quotes:raise RuntimeError('missing entry quote')
                    if s=='ICP' and stamp not in minutes['ICP']:raise RuntimeError('ICP entry not minute-covered')
                    adverse=(quotes[s]/x['signal_price']-1)*x['side']
                    if not math.isfinite(adverse) or adverse>.0035:
                        counts['adverse_rejected']+=1;del pending_signals[key];continue
                    proposals.append((key,x))
                if proposals:
                    eq=equity();held=reserved()
                    available=max(0.,min(balance-held,eq-held)-max(eq,0)*.05)
                    available=min(available,max(0.,free()-max(eq,0)*.05))
                    targets=[max(eq,0)*STANDARD['symbols'][x['symbol']]['target_margin_fraction'] for _,x in proposals]
                    demands=[target*(1+x['lev']*(2*fee+fund*(x['deadline']-x['entry_ts'])/H)) for target,(_,x) in zip(targets,proposals)]
                    shrink=min(1.,available/sum(demands)) if sum(demands)>0 else 0.
                    proposed_gross=sum(target*x['lev']*shrink/(1+x['side']*slip) for target,(_,x) in zip(targets,proposals))
                    capacity=max(0.,3.75*eq-gross())
                    shrink*=min(1.,capacity/proposed_gross) if proposed_gross>0 else 0.
                    assert sum(demands)*shrink<=available+1e-8*max(eq,1)
                    if shrink<=0:counts['margin_rejected']+=len(proposals)
                    else:
                        counts['batches']+=1;counts['simultaneous_batches']+=len(proposals)>1
                        for target,demand,(key,x) in zip(targets,demands,proposals):
                            s=x['symbol'];margin=target*shrink;price=quotes[s]*(1+x['side']*slip)
                            quantity=margin*x['lev']/price;entry_fee=quantity*price*fee
                            lock=STANDARD['profit_lock']['symbols'].get(s)
                            if lock:
                                trigger=(x['atr']/price*lock['trigger_atr_ratio_long' if x['side']>0 else 'trigger_atr_ratio_short']) if policy=='frozen' else x['learned_ratio']
                            else:trigger=0.
                            balance-=entry_fee
                            positions[s]={'side':x['side'],'qty':quantity,'entry':price,'margin':margin,'reservation':demand*shrink,
                                          'entry_fee':entry_fee,'funding':0.,'filled_at':stamp,'confirmed_at':x['entry_ts'],'deadline':x['deadline'],
                                          'group':group,'trigger':trigger,'keep':lock['keep_fraction'] if lock else 0.,'peak':0.,'floor':None,'retained':0}
                            assert stamp-x['entry_ts']<5*M
                            counts['clipped']+=shrink<.999999
                            actions.append({'t':stamp,'symbol':s,'event':'entry','quantity':quantity,'group':group,'confirmed_at':x['entry_ts']})
                            del pending_signals[key]
                        assert gross()<=3.75*eq+1e-7*max(eq,1), 'new gross exceeds pre-entry equity cap'
        assert len({p['group'] for p in positions.values()})<=1,'cross-group overlap'
        eq=equity();peak=max(peak,eq);mdd=min(mdd,eq/peak-1)
        # Conservative sum of hourly adverse extremes for non-minute markets; statistics only.
        bound=balance
        for s,p in positions.items():
            bar=minutes.get(s,{}).get(stamp) or series[s].get(boundary)
            if bar:bound+=p['qty']*p['side']*(bar['l' if p['side']>0 else 'h']-p['entry'])
            else:bound+=p['qty']*p['side']*(quotes[s]-p['entry'])
        adverse_mdd=min(adverse_mdd,bound/peak-1)
        if eq<=0:raise RuntimeError('Portfolio insolvent')
        max_reserved=max(max_reserved,reserved()/eq);max_gross=max(max_gross,gross()/eq)
    assert not positions, 'unclosed portfolio positions'
    counts['cross_group_overlap']=0
    assert abs(balance-(100+sum(x['net_pnl'] for x in ledger)))<1e-7*max(balance,1)
    return {'start_usd':100,'end_usd':balance,'return_pct':(balance/100-1)*100,'trades':len(ledger),
            'win_rate_pct':sum(x['net_pnl']>0 for x in ledger)/max(len(ledger),1)*100,
            'hybrid_mark_mdd_pct':mdd*100,'hybrid_adverse_bound_pct':adverse_mdd*100,'closed_trade_mdd_pct':closed_mdd*100,
            'max_reserved_equity_ratio':max_reserved,'max_gross_equity_ratio':max_gross,'fees_usd':sum(x['fees'] for x in ledger),
            'funding_usd':sum(x['funding'] for x in ledger),'icp_trades':sum(x['symbol']=='ICP' for x in ledger),
            'counts':dict(counts),'ledger':ledger,'actions':actions}

def compact(r):return {k:v for k,v in r.items() if k not in ('ledger','actions')}

def checks():
    t=START;times=range(t-H,t+6*H,H)
    series={s:{h:{'o':100.,'h':100.,'l':100.,'c':100.} for h in times} for s in ('ICP','AVAX','ALGO')}
    minute_rows={s:{} for s in ('ICP','ALGO','ADA')}
    minute_rows['ICP']={m:{'o':100.,'h':100.,'l':100.,'c':100.} for m in range(t,t+6*H,M)}
    def signal(s,side=1):
        rule=STANDARD['symbols'][s];hold=2 if s=='ICP' else 2
        return {'symbol':s,'side':side,'lev':rule['leverage'],'entry_ts':t,'deadline':t+hold*H,'exit_bar':t+(hold-1)*H,
                'signal_price':100.,'atr':1.,'learned_ratio':.1,'group':rule['group']}
    signals={t:[signal('ICP'),signal('AVAX')]}
    r=run(series,signals,minute_rows,set(),False,1,start=t,end=t+5*H)
    assert r['trades']==2 and r['counts']['simultaneous_batches']==1
    assert r['counts']['cross_group_overlap']==0
    assert all(x['entry_ts']<x['exit_ts'] and x['fees']>0 and x['funding']>0 for x in r['ledger'])
    assert run(series,signals,minute_rows,set(),False,5,start=t,end=t+5*H)['trades']==0
    signal2=signal('ALGO');signal2.update(entry_ts=t+H,deadline=t+2*H)
    conflict=run(series,{t:[signal('ICP')],t+H:[signal2]},minute_rows,set(),False,1,start=t,end=t+5*H)
    assert conflict['counts']['cross_group_overlap']==0 and all(x['symbol']=='ICP' for x in conflict['ledger'])

def main():
    checks();print('CHECKS passed',flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    cache=OUT/'PREPARED_LOCAL.pkl'
    if cache.exists():
        with cache.open('rb') as f:series,signals,minutes,busy,coverage,blocked=pickle.load(f)
    else:
        prepared=prepare()
        with cache.open('wb') as f:pickle.dump(prepared,f)
        series,signals,minutes,busy,coverage,blocked=prepared
    print('INPUTS',coverage,'signal_boundaries',len(signals),flush=True)
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    scenarios=[('frozen',d,c,0.) for d in (0,1,3,4) for c in (1,2)]+[('frozen',4,2,.003)]+[('rolling',1,c,0.) for c in (1,2)]
    for policy,delay,cost,haircut in scenarios:
        baseline=run(series,signals,minutes,busy,False,delay,cost,policy,haircut)
        candidate=run(series,signals,minutes,busy,True,delay,cost,policy,haircut)
        row={'policy':policy,'delay_minutes':delay,'cost_multiplier':cost,'extra_exit_slippage_pct':haircut*100,
             'baseline':compact(baseline),'candidate':compact(candidate),
             'final_equity_improvement_pct':(candidate['end_usd']/baseline['end_usd']-1)*100,
             'return_better':candidate['end_usd']>baseline['end_usd'],
             'mdd_no_worse':candidate['hybrid_mark_mdd_pct']>=baseline['hybrid_mark_mdd_pct']-1e-9}
        rows.append(row)
        if policy=='frozen' and delay==1 and cost==1:
            (OUT/'PRIMARY_LEDGERS.json').write_text(json.dumps({'baseline':baseline,'candidate':candidate},ensure_ascii=False,indent=2),encoding='utf-8')
        print('SCENARIO',policy,delay,cost,haircut,json.dumps(row),flush=True)
        (OUT/'SCENARIOS.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    span=END-START;thirds=[]
    for i in range(3):
        a=START+(span*i//3)//H*H;b=START+(span*(i+1)//3)//H*H
        base=run(series,signals,minutes,busy,False,1,1,'frozen',start=a,end=b)
        cand=run(series,signals,minutes,busy,True,1,1,'frozen',start=a,end=b)
        thirds.append({'start':a,'end':b,'baseline':compact(base),'candidate':compact(cand),'return_better':cand['end_usd']>base['end_usd']})
    result={'id':'B-STAGE170-FULL-PORTFOLIO-ICP-CONTINUATION','research_only':True,'live_changes':False,
            'generated_at':datetime.now(timezone.utc).isoformat(),'period':['2021-08-28','2026-08-30'],'starting_capital_usd':100,
            'coverage':coverage,'synthetic_accounting_execution_tests':'passed','btc_blocked_all_opportunities':blocked,
            'scenarios':rows,'thirds':thirds,'legacy_hourly_reference_return_pct':STANDARD['reference']['return_pct'],
            'limits':['Hybrid quotes: ICP perpetual minutes throughout its opportunities; ALGO/ADA cached minutes; other markets retain hourly-price execution proxies.',
                      'Hybrid MDD is equity at observed event-time quotes; conservative hourly extremes reported separately. Not synchronized whole-market ticks or BingX mark-price MDD.',
                      'Funding is the adopted conservative cost proxy, not actual historical discrete funding settlements.',
                      'Missing hourly protection candles preserve the prior floor without inventing an update; gap counts are reported. Hourly proxy marks can remain stale through source gaps.',
                      'Frozen opportunities and historical research selected on previously seen data, not independent future evidence.',
                      'No exchange depth, tiered liquidation, contract rounding or uncertain order network simulation; this is a portfolio backtest, not live certification.',
                      'The old published hourly reference used different fill, gross valuation and profit-lock assumptions; compare baseline/candidate within this same event engine.']}
    (OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SAVED',OUT/'RESULTS.json',flush=True)

if __name__=='__main__':main()
