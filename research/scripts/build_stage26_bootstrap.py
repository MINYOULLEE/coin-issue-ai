"""Seed causal selection state from archived research, not from fills. No live writes."""
import json,hashlib
from pathlib import Path
import research_b_sparse_stage20 as p
ROOT=Path(__file__).resolve().parents[2]
H=3600000
def main():
    standard=json.loads((ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf-8'))
    series,entries,times=p.s.b.prepare()
    cutoff=times[-1]-24*H # well before truncated research tail opportunities
    state=dict(version=standard['standard_version'],lastConfirmedAt=cutoff,coreBusyUntil=0,nextEligibleAt={s:0 for s in standard['symbols']})
    busy=set()
    for t,items in entries.items():
        for x in items:
            busy.update(range(t,x['exit_bar']+H,H))
            if t<=cutoff:
                rule=standard['symbols'][x['symbol']]
                state['nextEligibleAt'][x['symbol']]=max(state['nextEligibleAt'][x['symbol']],t+rule['opportunity_cooldown_hours']*H)
                state['coreBusyUntil']=max(state['coreBusyUntil'],x['exit_bar']+H)
    for ident in standard['reference']['selector']['patterns']:
        symbol,name=ident.split(':')
        rows=p.s.core.read_candles(p.s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
        for row in rows:row['symbol']=symbol
        for x in p.s.opportunities(rows,dict(p.signals(rows))[name],1,3,busy):
            if x['entry_ts']<=cutoff:state['nextEligibleAt'][symbol]=max(state['nextEligibleAt'][symbol],x['entry_ts']+2*H)
    result=dict(state=state,source='archived Stage16 opportunities + Stage20 selected rules; cutoff before truncated tail',
        source_hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'strategy/archive/plan_b_stage16_v1.json',ROOT/'research/results/b_sparse_stage20/combinations.json']})
    (ROOT/'strategy/plan_b_stage26_bootstrap.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
