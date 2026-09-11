"""Portfolio replay using observed delayed minute opens for Stage132. Research only."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import research_a_intraday_rally_guard_stage127 as s127
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'research/results/ab_7y_extension/A_STAGE132_RALLY_GUARD_MDD_REFINEMENT.json'
MINUTES=ROOT/'research/results/a_rally_guard_minutes_stage133/binance_futures_minutes'
OUT=ROOT/'research/results/ab_7y_extension/A_STAGE134_RALLY_GUARD_MINUTE_PORTFOLIO.json'
M=60_000

def compact(x): return {k:v for k,v in x.items() if k!='overlay_events'}

def fills(delay):
    result={}
    for path in MINUTES.glob('*.json'):
        symbol,stamp_text=path.stem.split('_'); stamp=int(stamp_text)
        rows={int(row[0]):float(row[1]) for row in json.loads(path.read_text(encoding='utf-8'))}
        if stamp+delay*M in rows: result[(symbol,stamp)]=rows[stamp+delay*M]
    return result

def main():
    source=json.loads(SOURCE.read_text(encoding='utf-8')); cfg=source['ranked'][0]['config']
    maps,bars,funding=s113.a_inputs(); start=min(set.intersection(*(set(bars[s]) for s in s127.SYMBOLS)))
    maps=s115.filtered(maps,bars,.035,.12,3,0)
    rows=[]
    for delay in (0,1,3,5,10):
        prices=fills(delay)
        seven=compact(s127.replay(maps,bars,funding,cfg,start,s127.END,overlay_fill_prices=prices))
        five=compact(s127.replay(maps,bars,funding,cfg,s113.CUT,s127.END,overlay_fill_prices=prices))
        triple=compact(s127.replay(maps,bars,funding,cfg,start,s127.END,.0012,.005,0,prices))
        rows.append({'delay_min':delay,'fill_events':len(prices),'five':five,'seven':seven,'triple':triple})
    result={'id':'A-STAGE134-RALLY-GUARD-MINUTE-PORTFOLIO','generated_at':datetime.now(timezone.utc).isoformat(),
            'research_only':True,'live_changes':False,'candidate':cfg,'rows':rows,
            'limitations':['Binance USD-M minute opens, not BingX order-book fills.','Historical trigger windows are in-sample, not future/live validation.']}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
