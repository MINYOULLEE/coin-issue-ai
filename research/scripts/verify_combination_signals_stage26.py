"""Compare adopted JS supplemental signals against the independent Stage22 scalar audit.
Historical gaps are explicitly counted, not silently converted into no-signal samples.
"""
import json,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
import audit_b_sparse_stage22 as audit
ROOT=Path(__file__).resolve().parents[2]

def main():
    payload=[]
    for symbol in ('ALGO','ETH','VET'):
        rows=audit.s.core.read_candles(audit.s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
        expected=[audit.direct_signal(symbol,rows,i) if i>=169 else 0 for i in range(len(rows))]
        payload.append(dict(symbol=symbol,rows=rows,expected=expected))
    node=os.environ.get('CODEX_RESEARCH_NODE') or str(Path('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'))
    result=subprocess.run([node,str(ROOT/'research/scripts/verify_combination_signals_stage26.mjs')],input=json.dumps(payload),text=True,capture_output=True,check=True)
    report=json.loads(result.stdout)
    report.update(generated_at=datetime.now(timezone.utc).isoformat(),independent_market_validation=False,live_deployed=False,
        note='JS preparation module vs independent scalar signal rules; excludes noncontiguous windows as required by production validation, not full execution replay')
    (ROOT/'research/results/b_sparse_stage20/SIGNAL_PORT_STAGE26.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
