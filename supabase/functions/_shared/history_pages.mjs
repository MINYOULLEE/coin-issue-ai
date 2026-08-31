// Continue until an empty page: servers can cap pages below the requested size.
// Never return a silently truncated successful aggregate.
export async function allHistoryPages(fetchPage){
 const rows=[],seen=new Set();let offset=0;
 for(;;){const page=await fetchPage(offset,500);if(!Array.isArray(page))throw Error('invalid history page');if(!page.length)return rows;
  for(const row of page){if(typeof row.external_id!=='string'||seen.has(row.external_id))throw Error('history changed during pagination; retry');seen.add(row.external_id);rows.push(row);}
  offset+=page.length;
 }
}
