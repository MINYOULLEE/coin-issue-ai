"""Current public BingX contract-grid sensitivity; no authenticated/order calls."""
import inspect,json
import validate_a_stage50 as base
import validate_a_stage51 as partial
RULES={'BTC':(4,.0001,2),'ETH':(2,.01,2),'XRP':(0,2,2),'SOL':(2,.02,2),'TRX':(0,7,2)}

def runner(threshold,mode):
    src=inspect.getsource(partial.runner)
    # Modify generated partial close logic: unsendable reductions stay open.
    needle='                part=original.copy()'
    insert="""                precision,minimum,min_usd=CONTRACT_RULES[s]
                step=10**(-precision)
                amount=math.floor((original['qty']*fraction+1e-12)/step)*step
                if amount<minimum-1e-12 or amount*series[s][t]['o']<min_usd:continue
                local_fraction=min(1.,amount/original['qty'])
                part=original.copy()"""
    assert needle in src;src=src.replace(needle,insert)
    src=src.replace('part[key]*=fraction','part[key]*=local_fraction').replace('if fraction<1:','if local_fraction<1:').replace('original[key]*=(1-fraction)','original[key]*=(1-local_fraction)')
    # A rounded/skipped risk reduction may leave a breach; measure, do not assert compliance.
    src=src.replace("'if True:assert'", "'if False:assert'")
    anchor="    env=dict(prior.__dict__);exec(src,env)"
    additional="""    oldqty='qty=notional/entry;entryfee=qty*entry*fee;cash-=entryfee'
    newqty=\"precision,minimum,min_usd=CONTRACT_RULES[s]\\n                step=10**(-precision)\\n                qty=math.floor((notional/entry+1e-12)/step)*step\\n                if qty<minimum-1e-12 or qty*entry<min_usd:continue\\n                entryfee=qty*entry*fee;cash-=entryfee\"
    assert oldqty in src;src=src.replace(oldqty,newqty)
    src=src.replace(\"env=dict(e.__dict__);env['mode_name']=mode\",\"env=dict(e.__dict__);env['CONTRACT_RULES']=\"+repr(CONTRACT_RULES)+\";env['mode_name']=mode\")
"""
    assert anchor in src;src=src.replace(anchor,additional+anchor)
    env=dict(partial.__dict__);env['CONTRACT_RULES']=RULES;exec(src,env)
    return env['runner'](threshold,mode)

def main():
    src=inspect.getsource(base.main)
    src=src.replace("('entry_only','hourly_flatten')","('trim160','buffer140')")
    env=dict(base.__dict__);env['runner']=runner;env['OUT']=base.a.RESULT_DIR/'a_stage52'
    exec(src,env);env['main']()
    path=env['OUT']/'results.json';r=json.loads(path.read_text())
    r['contract_snapshot']={'source':'https://open-api.bingx.com/openApi/swap/v2/quote/contracts','retrieved_on':'2026-09-04','rules':RULES}
    r['limitations']=['Current contract precision/minimum quantity and $2 notional applied to historical spot prices; historical rules unverified',
      'Same minimum rule imposed on partial reductions conservatively; reduce-only exceptions unverified',
      'Unsendable partial reductions skipped and exposure breaches retained; not a certified cap-enforcement algorithm',
      'Hourly open sampling, not intrabar continuous risk control; assumed funding and 10x liquidation proxy',
      'No independent holdout, account margin audit or live changes; counters of trades include partial fills']
    for item in r['results']:
        ledger=json.loads((env['OUT']/f"{item['name']}_{item['mode']}.json").read_text())['ledger']
        item['full']['partial_exit_fills']=sum(x['reason']=='partial_gross_reduction' for x in ledger)
        item['full']['position_exits']=sum(x['reason']!='partial_gross_reduction' for x in ledger)
    path.write_text(json.dumps(r,indent=2),encoding='utf8')

if __name__=='__main__':main()
