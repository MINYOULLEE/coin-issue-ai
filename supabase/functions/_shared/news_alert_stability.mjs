// Only non-trading news alerts are debounced. Trading health remains immediate.
export function stableHealthAlerts(previous={},current={},now=Date.now()){
 const prior=Object.fromEntries(Object.entries(previous).filter(([k])=>k!=='__news_state'));
 const active={...current},state={},old=previous.__news_state||{};
 const keys=new Set([...Object.keys(prior),...Object.keys(current),...Object.keys(old)].filter(k=>k.startsWith('news:')));
 for(const key of keys){
  const failed=Object.hasOwn(current,key),before=old[key];
  const same=before&&before.failed===failed;
  const s={failed,since:same?before.since:now,last:now,count:same?before.count+(Math.floor(now/60000)>Math.floor(before.last/60000)?1:0):1};
  if(failed){
   if(prior[key])active[key]=prior[key]; // Error wording changes are not a new incident.
   else if(s.count<3||now-s.since<120000)delete active[key];
  }else if(prior[key]&&(s.count<2||now-s.since<60000))active[key]=prior[key];
  if(failed||active[key])state[key]=s;
 }
 return {previous:prior,active,stored:{...active,__news_state:state}};
}
