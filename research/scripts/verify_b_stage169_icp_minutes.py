"""ICP USD-M minute execution comparison; research windows, not full B CAGR.

Frozen causal Stage168 signals/thresholds, identical $100 ICP-only sleeves per
continuous signal chain. Full B portfolio remains the Stage168 hourly study.
Public quotes only. No credentials, orders, deployment or runtime state.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,threading,time,urllib.parse,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import research_b_stage168_icp_continuation as s

H=s.H;M=60000
OUT=s.ROOT/'research/results/b_stage169_icp_minutes'
CACHE=OUT/'binance_futures_minutes'
INPUT=OUT/'INPUTS.json'
ONBOARD=1627628400000 # Public exchangeInfo verified 2026-10-12: 2021-07-30T07:00Z.
ARCHIVE_LOCK=threading.Lock()

def archive_rows(start,end):
    rows=[];sources=[];folder=OUT/'official_daily_archives';folder.mkdir(parents=True,exist_ok=True)
    for day in range(start//(24*H)*24*H,(end-1)//(24*H)*24*H+1,24*H):
        date=datetime.fromtimestamp(day/1000,timezone.utc).strftime('%Y-%m-%d')
        name=f'ICPUSDT-1m-{date}.zip';path=folder/name
        url=f'https://data.binance.vision/data/futures/um/daily/klines/ICPUSDT/1m/{name}'
        with ARCHIVE_LOCK:
            if path.exists():payload=path.read_bytes();expected=path.with_suffix('.sha256').read_text().strip()
            else:
                with urllib.request.urlopen(url,timeout=20) as response:payload=response.read()
                with urllib.request.urlopen(url+'.CHECKSUM',timeout=20) as response:expected=response.read().decode().split()[0]
                assert hashlib.sha256(payload).hexdigest()==expected,'Official archive checksum mismatch'
                path.write_bytes(payload);path.with_suffix('.sha256').write_text(expected,encoding='utf-8')
        assert hashlib.sha256(payload).hexdigest()==expected
        z=zipfile.ZipFile(io.BytesIO(payload))
        for row in csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())):
            if not row or not row[0].isdigit():continue
            if start<=int(row[0])<end:rows.append(row)
        sources.append({'url':url,'sha256':expected})
    rows.sort(key=lambda x:int(x[0]));return rows,sources

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inputs():
    fingerprints={str(p.relative_to(s.ROOT)):digest(p) for p in (s.ROOT/'research/data_7y/ICPUSDT_1h.csv',s.ROOT/'strategy/plan_b_standard.json')}
    if INPUT.exists():
        saved=json.loads(INPUT.read_text(encoding='utf-8'))
        assert saved['fingerprints']==fingerprints
        return saved
    original_fetch=s.s101.s99.fetch
    def cached(op):
        path=s.s101.s99.CACHE/f"{op['symbol']}_{op['entry_ts']}.json"
        if not path.exists():raise RuntimeError(f'Prior study minute cache missing: {path}')
        return original_fetch(op)
    s.s101.s99.fetch=cached
    series,raw,times,_=s.s101.delayed_inputs(1)
    entries,blocked=s.s108.filter_entries(raw,-.06)
    features={k:s.s101.ab.b91.s90.s86.s58.old.prev.features(list(v.values())) for k,v in series.items()}
    _,decisions=s.s101.ab.b91.s90.s86.s61.learned_profit_locks(series,entries,features,'icp',.30,.70,False)
    ds={d['entry_ts']:d for d in decisions if d['symbol']=='ICP'}
    ops=[]
    for t,rows in sorted(entries.items()):
        for x in rows:
            if x['symbol']!='ICP' or t<min(times) or x['exit_bar']>max(times):continue
            d=ds[t]
            assert d.get('latest_training_close') is None or d['latest_training_close']<=t
            ops.append({'t':t,'side':x['side'],'signal_price':series['ICP'][t-H]['c'],
                        'trigger_ratio':d.get('trigger_distance',0)/series['ICP'][t]['o'],
                        'latest_training_close':d.get('latest_training_close')})
    chains=[];group=[]
    for op in ops:
        if group and (op['t']!=group[-1]['t']+2*H or op['side']!=group[-1]['side']):
            if len(group)>1:chains.append(group)
            group=[]
        group.append(op)
    if len(group)>1:chains.append(group)
    result={'fingerprints':fingerprints,'ops':ops,'chains':chains,'btc_blocked_all_symbols':blocked,
            'effective_range':[min(times),max(times)+H],
            'decision_rule':'Frozen hourly selected opportunities and past-only learned entry profit trigger from Stage168.'}
    OUT.mkdir(parents=True,exist_ok=True)
    INPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('INPUTS',len(ops),'ICP opportunities;',len(chains),'continuous same-side chains',flush=True)
    return result

def fetch(op):
    start=op['t'];end=start+8*H+10*M;path=CACHE/f'ICP_{start}.json'
    provenance_path=path.with_suffix('.source.json')
    provenance={'source':'Binance USD-M REST klines'}
    if path.exists():raw=json.loads(path.read_text(encoding='utf-8'));cached=True
    else:
        query=urllib.parse.urlencode(dict(symbol='ICPUSDT',interval='1m',startTime=start,endTime=end-1,limit=1000))
        req=urllib.request.Request('https://fapi.binance.com/fapi/v1/klines?'+query,headers={'User-Agent':'coin-issue-research/1.0'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req,timeout=20) as response:raw=json.load(response)
                break
            except Exception:
                if attempt==2:raise
                time.sleep(1+attempt)
        if not isinstance(raw,list):raise ValueError('Invalid public quote response')
        if [int(row[0]) for row in raw]!=list(range(start,end,M)):
            raw,sources=archive_rows(start,end)
            provenance={'source':'Binance official USD-M daily archive','archives':sources}
        # Only complete quote coverage may enter the evidence cache.
        validate(raw,start,end)
        path.write_text(json.dumps(raw),encoding='utf-8');provenance_path.write_text(json.dumps(provenance),encoding='utf-8');cached=False
    validate(raw,start,end)
    if provenance_path.exists():provenance=json.loads(provenance_path.read_text(encoding='utf-8'))
    return start,raw,cached,provenance

def validate(raw,start,end):
    expected=list(range(start,end,M))
    stamps=[int(row[0]) for row in raw]
    if stamps!=expected:raise ValueError(f'ICP minute coverage mismatch {start}: {len(stamps)}/{len(expected)}')
    for row in raw:
        o,h,l,c=map(float,row[1:5])
        if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)) or l>min(o,c) or h<max(o,c):raise ValueError('Invalid OHLC')

def sleeve(chain,minutes,retain,delay,cost_mult=1,extra_exit_slip=0):
    """Every decision uses only the current open or an already completed candle.

    Protected exits react after a completed minute, never assume a stop fills
    exactly at the floor. Exit confirmation precedes the next eligible entry.
    Funding is the existing conservative hourly proxy accrued by minute.
    """
    signals={x['t']:x for x in chain};start=chain[0]['t'];end=chain[-1]['t']+2*H
    balance=peak=100.;position=None;pending=None;trades=[];retained=missed=0;pause_until=-1
    mdd=bound_mdd=0.;exposure_margin_ratio=0.;actions=[]
    fee=.0005*cost_mult;slip=.0002*cost_mult;fund=.0000125*cost_mult/60
    def equity(mark):return balance+(position['qty']*position['side']*(mark-position['entry']) if position else 0)
    def close(stamp,raw,reason):
        nonlocal balance,position
        price=raw*(1-position['side']*(slip+extra_exit_slip))
        exit_fee=position['qty']*price*fee
        gross=position['qty']*position['side']*(price-position['entry'])
        balance+=gross-exit_fee
        trades.append({'entry_t':position['filled_at'],'exit_t':stamp,'side':position['side'],'entry':position['entry'],'exit':price,
                       'quantity':position['qty'],'margin':position['margin'],'net':gross-position['fee']-exit_fee-position['funding'],
                       'fees':position['fee']+exit_fee,'funding':position['funding'],'reason':reason,'retained':position['retained']})
        actions.append({'t':stamp,'event':'close','reason':reason});position=None
    for stamp in range(start,end+(delay+3)*M,M):
        bar=minutes[stamp];mark=bar['o']
        if pending and stamp>=pending['fill_at']:
            close(stamp,mark,pending['reason']);pending=None
        # Reproduce hour-close-only profit floor updates using known completed closes.
        if position and stamp%H==0 and stamp>position['filled_at']:
            previous=minutes[stamp-M]['c']
            favorable=(previous/position['entry']-1)*position['side']
            position['peak']=max(position['peak'],favorable)
            if position['trigger']>0 and position['peak']>=position['trigger']:
                floor=position['entry']*(1+position['side']*position['peak']*.70)
                position['floor']=floor if position['floor'] is None else max(position['floor'],floor) if position['side']>0 else min(position['floor'],floor)
        if position and not pending and stamp>=position['deadline']:
            upcoming=signals.get(stamp)
            eq=equity(mark);reserved=position['margin'];risk_peak=max(peak,eq)
            free=max(0.,min(balance-reserved,eq-reserved)-max(eq,0)*.05)
            safe=(eq>0 and eq/risk_peak-1>-.25 and stamp>=pause_until and position['qty']*mark<=3.75*eq
                  and free>=position['qty']*mark*.0000125*cost_mult*2)
            if retain and upcoming and upcoming['side']==position['side'] and safe and stamp+2*H-position['confirmed_at']<=8*H:
                position['deadline']=stamp+2*H;position['retained']+=1;retained+=1
                actions.append({'t':stamp,'event':'retain','quantity':position['qty']})
            elif delay==0:close(stamp,mark,'scheduled')
            else:pending={'fill_at':stamp+delay*M,'reason':'scheduled'}
        # Strictly <5m TTL. A delayed close must settle before the same signal enters.
        boundary=stamp//H*H;signal=signals.get(boundary)
        if signal and not position and not pending and delay*M<=stamp-boundary<5*M and stamp<end and not signal.get('used'):
            signal['used']=True
            adverse=(mark/signal['signal_price']-1)*signal['side']
            if stamp<pause_until or adverse>.0035:
                missed+=1;actions.append({'t':stamp,'event':'entry_rejected','adverse':adverse});continue
            eq=balance;target=max(eq,0)*1.15
            demand=target*(1+5*(2*fee+.0000125*cost_mult*2))
            free=max(0.,eq*.95)
            shrink=min(1,free/demand,3.75*eq/(target*5)) if target>0 else 0
            margin=target*shrink
            if margin<=0:missed+=1;continue
            price=mark*(1+signal['side']*slip);qty=margin*5/price;entry_fee=qty*price*fee
            balance-=entry_fee
            position={'side':signal['side'],'entry':price,'qty':qty,'margin':margin,'fee':entry_fee,'funding':0.,
                      'trigger':signal['trigger_ratio'],'peak':0.,'floor':None,'filled_at':stamp,'confirmed_at':boundary,
                      'deadline':boundary+2*H,'retained':0}
            assert signal['latest_training_close'] is None or signal['latest_training_close']<=boundary
            actions.append({'t':stamp,'event':'entry','confirmed_at':boundary,'quantity':qty})
        if position:
            funding=position['qty']*mark*fund;position['funding']+=funding;balance-=funding
            eq=equity(bar['c']);worst=equity(bar['l'] if position['side']>0 else bar['h'])
            exposure_margin_ratio=max(exposure_margin_ratio,position['margin']/max(eq,1e-12))
            bound_mdd=min(bound_mdd,worst/peak-1)
            if not pending and position['floor'] is not None:
                touched=bar['l']<=position['floor'] if position['side']>0 else bar['h']>=position['floor']
                if touched:pending={'fill_at':stamp+M+delay*M,'reason':'profit_lock'}
        eq=equity(bar['c']);peak=max(peak,eq);mdd=min(mdd,eq/peak-1)
        if pause_until<0 and eq/peak-1<=-.25:pause_until=stamp+168*H
        if eq<=0:raise RuntimeError('Minute sleeve insolvent')
    if position:close(end+(delay+3)*M,minutes[end+(delay+3)*M]['c'],'window_end_pending')
    return {'end_usd':balance,'return_pct':balance-100,'trades':len(trades),'wins':sum(x['net']>0 for x in trades),
            'retained_boundaries':retained,'missed_entries':missed,'minute_mark_mdd_pct':mdd*100,
            'minute_adverse_mdd_pct':bound_mdd*100,'fees':sum(x['fees'] for x in trades),'funding':sum(x['funding'] for x in trades),
            'max_reserved_equity_ratio':exposure_margin_ratio,'ledger':trades,'actions':actions}

def checks():
    ts=1700002800000//H*H
    minutes={t:{'o':100.,'h':100.,'l':100.,'c':100.} for t in range(ts,ts+5*H,M)}
    chain=[{'t':ts+k*H,'side':1,'signal_price':100.,'trigger_ratio':.02,'latest_training_close':None} for k in (0,2)]
    # A constant cap-sized position can lose its eligibility through costs. Never force retention.
    for retain in (False,True):
        result=sleeve([dict(x) for x in chain],minutes,retain,3)
        actions=result['actions']
        assert all(a['t']-a['confirmed_at']<5*M for a in actions if a['event']=='entry')
        for i,a in enumerate(actions):
            if a['event']=='entry' and i:assert actions[i-1]['event'] in ('close','retain','entry_rejected')
        assert all(x['exit_t']>x['entry_t'] and x['fees']>0 and x['funding']>0 for x in result['ledger'])
    assert sleeve([dict(x) for x in chain],minutes,False,5)['trades']==0
    rising={t:{'o':102. if t>=ts+H else 100.,'h':102. if t>=ts+H else 100.,
               'l':102. if t>=ts+H else 100.,'c':102. if t>=ts+H else 100.} for t in minutes}
    touch=ts+2*H+30*M
    for t in rising:
        if t>=touch:rising[t]={'o':100.,'h':100.,'l':100.,'c':100.}
    protected=[dict(x,signal_price=102. if x['t']>ts else 100.,trigger_ratio=.01) for x in chain]
    result=sleeve(protected,rising,True,0)
    assert result['retained_boundaries']==1
    trade=result['ledger'][0]
    assert trade['reason']=='profit_lock' and trade['exit_t']==touch+M
    assert trade['exit']<100., 'Gap exit cannot fabricate a fill at the higher protection floor'
    assert all(a['quantity']==trade['quantity'] for a in result['actions'] if a['event']=='retain')
    try:validate([[ts,100,100,100,100]],ts,ts+2*M)
    except ValueError:pass
    else:raise AssertionError('Missing minutes must not pass coverage validation')

def main():
    checks();data=inputs();CACHE.mkdir(parents=True,exist_ok=True)
    raw_by_ts={};manifest=[];errors=[]
    available_ops=[op for op in data['ops'] if op['t']>=ONBOARD]
    prelisting=[op for op in data['ops'] if op['t']<ONBOARD]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(fetch,op):op for op in available_ops}
        for future in as_completed(jobs):
            op=jobs[future]
            try:
                start,raw,cached,provenance=future.result()
                for row in raw:
                    t=int(row[0]);bar=dict(zip(('o','h','l','c'),map(float,row[1:5])))
                    if t in raw_by_ts:assert raw_by_ts[t]==bar,'overlapping historical quotes disagree'
                    raw_by_ts[t]=bar
                manifest.append({'start':start,'minutes':len(raw),'cached':cached,'sha256':digest(CACHE/f'ICP_{start}.json'),'provenance':provenance})
                if len(manifest)%10==0:print('FETCHED',len(manifest),'/',len(available_ops),flush=True)
            except Exception as exc:errors.append({'entry_ts':op['t'],'error':str(exc)[:250]})
    if errors:
        (OUT/'FETCH_FAILURE.json').write_text(json.dumps({'research_only':True,'errors':errors,'complete':len(manifest),'requested':len(data['ops'])},indent=2),encoding='utf-8')
        raise RuntimeError(f'Missing required ICP minute windows: {errors[:3]}')
    results=[]
    for delay in (0,1,3,4):
        for cost in (1,2):
            for haircut in (0,.001,.003):
                cases=[]
                for group in data['chains']:
                    if any(op['t']<ONBOARD for op in group):continue
                    base=sleeve([dict(x) for x in group],raw_by_ts,False,delay,cost,haircut)
                    candidate=sleeve([dict(x) for x in group],raw_by_ts,True,delay,cost,haircut)
                    cases.append({'start':group[0]['t'],'signals':len(group),'baseline':base,'candidate':candidate,
                                  'end_difference_usd':candidate['end_usd']-base['end_usd']})
                # Each window starts at $100 independently; no invented portfolio CAGR.
                summary={'delay_minutes':delay,'cost_multiplier':cost,'extra_exit_slippage_pct':haircut*100,
                         'windows':len(cases),'candidate_better':sum(x['end_difference_usd']>1e-8 for x in cases),
                         'candidate_worse':sum(x['end_difference_usd']<-1e-8 for x in cases),
                         'equal':sum(abs(x['end_difference_usd'])<=1e-8 for x in cases),
                         'mean_end_difference_usd':sum(x['end_difference_usd'] for x in cases)/len(cases),
                         'baseline_trades':sum(x['baseline']['trades'] for x in cases),
                         'candidate_trades':sum(x['candidate']['trades'] for x in cases),
                         'retained_boundaries':sum(x['candidate']['retained_boundaries'] for x in cases),
                         'worst_candidate_minute_adverse_mdd_pct':min(x['candidate']['minute_adverse_mdd_pct'] for x in cases)}
                results.append({'summary':summary,'cases':cases})
                print('SCENARIO',json.dumps(summary),flush=True)
    result={'id':'B-STAGE169-ICP-PERPETUAL-MINUTE-WINDOWS','research_only':True,'live_changes':False,
            'generated_at':datetime.now(timezone.utc).isoformat(),'source':'Binance USD-M ICPUSDT public 1m klines',
            'coverage':{'all_requested_windows':len(data['ops']),'tradable_required_windows':len(available_ops),'complete_windows':len(manifest),'unique_minutes':len(raw_by_ts),'fetch_errors':[],
                        'contract_onboard_at':'2021-07-30T07:00:00Z','prelisting_unavailable_opportunities':prelisting},
            'manifest':manifest,'scenarios':results,'synthetic_checks':'passed',
            'method':'Independent $100 ICP-only sleeve per frozen same-direction signal chain; 2h exit/reentry vs guarded fixed-quantity retention up to 8h. Hour-close profit-floor update, completed-minute crossing, delayed market fill, strictly <5m entry TTL and 0.35% adverse-move filter.',
            'limits':['This is local execution-window validation, not recomputed whole-B five-year/seven-year compounded performance.',
                      'Other B positions, mutual exclusion and concurrent portfolio margin allocation are not reproduced in the independent sleeves.',
                      'Funding is the adopted conservative cost proxy accrued each minute, not historical discrete funding settlement.',
                      'Binance trade candles are not BingX mark price, order-book liquidity or actual orders.',
                      'Hourly-selected chains are historical and previously researched; this is not an untouched holdout.',
                      'No certified exchange liquidation formula or contract-minimum rounding; minute drawdowns are sleeve indicators only.']}
    (OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SAVED',OUT/'RESULTS.json',flush=True)

if __name__=='__main__':main()
