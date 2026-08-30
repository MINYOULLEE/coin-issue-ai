import { createAEntryCycle } from "../_shared/a_entry_cycle.mjs";
import { createHmac } from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";

const parseBig = JSONBig({ storeAsString: true });
const PROJECT_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const API_KEY = Deno.env.get("BINGX_API_KEY") || "";
const SECRET_KEY = Deno.env.get("BINGX_SECRET_KEY") || "";
const INTERNAL_KEY = Deno.env.get("INTERNAL_TRADE_SECRET") || "";
const BASE = "https://open-api.bingx.com";

function same(a: string, b: string) {
  if (a.length !== b.length) return false;
  let x = 0; for (let i = 0; i < a.length; i++) x |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return x === 0;
}
function headers(extra: Record<string,string> = {}) {
  return { apikey: SERVICE_KEY, Authorization: "Bearer " + SERVICE_KEY, "Content-Type": "application/json", ...extra };
}
async function db(path: string, init: RequestInit = {}) {
  const r = await fetch(PROJECT_URL + "/rest/v1/" + path, { ...init, headers: { ...headers(), ...(init.headers || {}) } });
  const t = await r.text(); if (!r.ok) throw new Error(`db ${path} ${r.status} ${t}`);
  return t ? JSON.parse(t) : null;
}
function canonical(p: Record<string,unknown>) {
  return Object.keys(p).sort().map(k => `${k}=${p[k]}`).join("&");
}
async function signed(method: "GET"|"POST", path: string, params: Record<string,unknown>) {
  const all = { ...params, timestamp: Date.now() };
  const query = canonical(all);
  const signature = createHmac("sha256", SECRET_KEY).update(query).digest("hex");
  const r = await fetch(method === "GET" ? `${BASE}${path}?${query}&signature=${signature}` : `${BASE}${path}`, {
    method,
    headers: { "X-BX-APIKEY": API_KEY, "X-SOURCE-KEY": "BX-AI-SKILL", ...(method === "POST" ? { "Content-Type": "application/x-www-form-urlencoded" } : {}) },
    body: method === "POST" ? `${query}&signature=${signature}` : undefined,
    signal: AbortSignal.timeout(10000),
  });
  const j = parseBig.parse(await r.text());
  if (j.code !== 0) throw new Error(`BingX ${j.code}: ${j.msg}`);
  return j.data;
}
const cycle=createAEntryCycle({db,signed});
Deno.serve(async req=>{
 if(req.method!=="POST")return new Response("POST required",{status:405});
 if(!INTERNAL_KEY||!same(req.headers.get("x-internal-key")||"",INTERNAL_KEY))return new Response("forbidden",{status:403});
 try{const p=await req.json();const result=p.action==="recover"?await cycle.recover():await cycle.submit(p);return Response.json(result,{status:result.ok?200:result.pending?202:409});}
 catch(e){return Response.json({ok:false,error:String(e.message)},{status:502});}
});
