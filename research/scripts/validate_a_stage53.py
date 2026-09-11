"""Replay identical Stage52 cases; change only proxy gap fill and assert cash ledger."""
import inspect,json
import validate_a_stage52 as prior
import a_gap_engine_stage53 as gap

def main():
    original=prior.base.e.a_replay
    prior.base.e.a_replay=gap.a_replay
    try:
        src=inspect.getsource(prior.main).replace("'a_stage52'","'a_stage53'")
        env=dict(prior.__dict__);exec(src,env);env['main']()
    finally:prior.base.e.a_replay=original
    path=prior.base.a.RESULT_DIR/'a_stage53/results.json'
    report=json.loads(path.read_text())
    report['limitations'] += ['Proxy gap fills use adverse bar open rather than unreachable threshold; still not actual exchange liquidation',
        'Final cash reconciled against every partial and full exit net PnL in each full/stress/third run']
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
