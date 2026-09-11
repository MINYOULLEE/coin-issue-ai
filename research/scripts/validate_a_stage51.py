"""Offline proportional partial risk reduction, with allocated fee/funding basis."""
import inspect,json
import validate_a_stage50 as prior

def runner(threshold,mode):
    src=inspect.getsource(prior.runner)
    src=src.replace("if mode=='hourly_flatten':",'if True:')
    target=1.6 if mode=='trim160' else 1.5
    old="            for s in list(pos):close(s,t,series[s][t]['o'],'hourly_gross_risk_exit')"
    new=f"""            cost=sum(p['qty']*series[s][t]['o']*(slip+fee*(1-p['side']*slip)) for s,p in pos.items())
            fraction=min(1.,max(0.,(gross-{target}*equity)/(gross-{target}*cost)))
            for s in list(pos):
                original=pos[s].copy()
                part=original.copy()
                for key in ('qty','fee','fund'):part[key]*=fraction
                pos[s]=part
                close(s,t,series[s][t]['o'],'partial_gross_reduction')
                if fraction<1:
                    for key in ('qty','fee','fund'):original[key]*=(1-fraction)
                    pos[s]=original"""
    assert old in src;src=src.replace(old,new)
    src=src.replace("if mode_name=='hourly_flatten':assert",'if True:assert')
    if mode=='buffer140':
        src=src.replace('available=max(0,1.6*equity-gross)/(mark_per_notional+1.6*entry_equity_cost)',
                        'available=max(0,1.4*equity-gross)/(mark_per_notional+1.4*entry_equity_cost)')
    env=dict(prior.__dict__);exec(src,env)
    return env['runner'](threshold,mode)

def main():
    src=inspect.getsource(prior.main)
    src=src.replace("('entry_only','hourly_flatten')","('trim160','trim150','buffer140')")
    src=src.replace("'Hourly risk exits flatten ALL positions and await next scheduled signal; diagnostic alternative, not current live policy'",
        "'Hourly exposure>1.6 triggers proportional partial reductions to 1.6 or 1.5, preserving remaining entry basis; buffer140 admits new exposure only to 1.4'")
    src=src.replace("'Entry-only never adds notional beyond available gross budget, but cannot correct prior drift'",
        "'Trade count includes partial reductions; full position exits and partial fills must be distinguished'")
    env=dict(prior.__dict__);env['OUT']=prior.a.RESULT_DIR/'a_stage51';env['runner']=runner
    exec(src,env);env['main']()
    path=env['OUT']/'results.json';report=json.loads(path.read_text())
    for item in report['results']:
        ledger=json.loads((env['OUT']/f"{item['name']}_{item['mode']}.json").read_text())['ledger']
        item['full']['partial_exit_fills']=sum(x['reason']=='partial_gross_reduction' for x in ledger)
        item['full']['position_exits']=sum(x['reason']!='partial_gross_reduction' for x in ledger)
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
