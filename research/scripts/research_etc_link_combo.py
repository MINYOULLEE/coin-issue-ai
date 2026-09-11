from __future__ import annotations

import json
from research_eth_link_combo import pnl_stream, simulate


def main():
    etc,et=pnl_stream('ETC',3.0,6,3.0)
    link,lt=pnl_stream('LINK',4.0,12,3.0)
    times=sorted(set(etc)&set(link)); n=len(times); cuts=[0,n//3,2*n//3,n]
    rows=[]
    for w in (.20,.35,.50,.65,.80):
        for scale in (.5,.75,1.,1.25,1.5,2.):
            seg=[simulate(times,etc,link,et,lt,w,scale,cuts[i],cuts[i+1]) for i in range(3)]
            full=simulate(times,etc,link,et,lt,w,scale,0,n)
            robust=all(z['return_pct']>0 and z['mdd_pct']>=-50 and z['trades']>=20 for z in seg)
            score=(min(z['return_pct'] for z in seg)+full['return_pct']/100+full['mdd_pct']) if robust else -1e9
            rows.append({'score':score,'etc_weight':w,'link_weight':1-w,'portfolio_scale':scale,'segments':seg,'full':full,'robust':robust})
    rows.sort(key=lambda z:z['score'],reverse=True); best=rows[0]
    best['start_usd']=100; best['end_usd']=100*best['full']['multiple']
    best['gate']=bool(best['robust'] and best['full']['return_pct']>1_000_000 and best['full']['mdd_pct']>=-50)
    print(json.dumps(best,ensure_ascii=False))

if __name__=='__main__': main()
