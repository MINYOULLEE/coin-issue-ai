// Only idempotent project REST reads. Never retries writes, RPCs, orders or Telegram sends.
export function supabaseReadFetch(projectUrl, {fetchImpl=globalThis.fetch, sleep=ms=>new Promise(r=>setTimeout(r,ms)), onRetry=()=>{}, timeoutMs=3000}={}) {
 const project=new URL(projectUrl);
 return async (input,init={})=>{
  const url=new URL(typeof input==='string'||input instanceof URL?String(input):input.url);
  const method=String(init.method||(input instanceof Request?input.method:'GET')).toUpperCase();
  const safe=url.origin===project.origin&&url.pathname.startsWith('/rest/v1/')&&!url.pathname.startsWith('/rest/v1/rpc/')&&['GET','HEAD'].includes(method);
  if(!safe)return fetchImpl(input,init);
  const originalSignal=init.signal||(input instanceof Request?input.signal:undefined);
  for(let attempt=1;attempt<=3;attempt++){
   if(originalSignal?.aborted)throw originalSignal.reason||new Error('request aborted');
   const signal=originalSignal?AbortSignal.any([originalSignal,AbortSignal.timeout(timeoutMs)]):AbortSignal.timeout(timeoutMs);
   let response,error;
   try{response=await fetchImpl(input,{...init,signal});}catch(e){error=e;}
   if(originalSignal?.aborted)throw originalSignal.reason||error||new Error('request aborted');
   let retry=false;
   if(response){
    retry=[502,503,504].includes(response.status);
    if(response.status===400)retry=(await response.clone().text()).trim()==='Project not specified.';
   }else retry=error instanceof TypeError||error?.name==='TimeoutError';
   if(!retry||attempt===3){if(error)throw error;return response;}
   // Whitelisted metadata only: no headers/tokens, query strings or response bodies in logs.
   onRetry({attempt,status:response?.status??null,path:url.pathname,request_id:response?.headers.get('sb-request-id')||null,cf_ray:response?.headers.get('cf-ray')||null});
   if(response?.body)await response.body.cancel();
   await sleep(attempt===1?250:750);
  }
 };
}
