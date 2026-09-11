"""Distinct A entry/exit/holding policies, no concentration optimization."""
import inspect,json
import validate_a_stage52 as constrained
import a_policy_engine_stage57 as policy_engine

def runner(threshold,policy):
    constrained.base.e.POLICY=policy
    return constrained.runner(0,'buffer140')

def main():
    base=constrained.base
    policies=('baseline','confirm_1h','confirm_6h','weak_move','weak_mean','hold_6','hold_12','hold_24','hold_48')
    src=inspect.getsource(base.main)
    src=src.replace("[('base',1,0),('candidate',3,1)]","[('base',1,0)]")
    src=src.replace("('entry_only','hourly_flatten')",repr(policies))
    env=dict(base.__dict__);env['runner']=runner;env['OUT']=base.a.RESULT_DIR/'a_stage57'
    original=base.e.a_replay;base.e.a_replay=policy_engine.a_replay
    try:exec(src,env);env['main']()
    finally:
        base.e.a_replay=original
        del base.e.POLICY
    path=env['OUT']/'results.json';r=json.loads(path.read_text())
    r['policies']={'baseline':'A unchanged signal weights with common research execution constraints',
      'confirm_1h':'Only new entries whose previous completed candle body agrees with A; rejected entries wait next daily signal',
      'confirm_6h':'Only new entries whose completed prior6h move agrees with A',
      'weak_move':'Exit on completed6h opposing move with efficiency>0.35',
      'weak_mean':'Exit when completed close is on wrong side of prior24h mean',
      'hold_N':'Exit at hourly open after N hours since entry; no same-boundary re-entry; otherwise original daily opportunities'}
    r['limitations']=['All policies tested individually, original A weights/directions/daily times, no concentration changes',
      'All use common1.4 new-entry gross cap and1.6 hourly partial risk reductions; not unchanged live A',
      'Spot OHLC, assumed funding,10x isolated proxy,current quantity rules historically applied',
      'No independent holdout; hourly sampling cannot certify continuous cap or exchange liquidation',
      'Exits use completed prior candles; no new entries on same boundary as policy exit',
      'Missing prior-hour indicators skip weakening check; 6h/24h indicators are six/24 observed bars around gaps']
    r['data_gaps']={}
    for symbol in base.a.CONFIG:
        rows=base.a.read_candles(base.a.DATA_DIR/f'{symbol}USDT_1h.csv')
        times=sorted(x['t'] for x in rows if r['range_ms'][0]<=x['t']<r['range_ms'][1])
        r['data_gaps'][symbol]=[{'after':x,'before':y,'missing_hours':(y-x)//base.H-1} for x,y in zip(times,times[1:]) if y-x>base.H]
    for item in r['results']:
        ledger=json.loads((env['OUT']/f"{item['name']}_{item['mode']}.json").read_text())['ledger']
        item['full']['partial_exit_fills']=sum(x['reason']=='partial_gross_reduction' for x in ledger)
        item['full']['position_exits']=sum(x['reason']!='partial_gross_reduction' for x in ledger)
    assert abs(r['results'][0]['full']['end_usd']-24001.26136824977)<1e-7
    path.write_text(json.dumps(r,indent=2),encoding='utf8')

if __name__=='__main__':main()
