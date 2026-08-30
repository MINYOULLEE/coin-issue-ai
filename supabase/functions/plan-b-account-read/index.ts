import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createHmac } from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";

const API_KEY = Deno.env.get("PLAN_B_BINGX_API_KEY") || "";
const SECRET_KEY = Deno.env.get("PLAN_B_BINGX_SECRET_KEY") || "";
const BASES = ["https://open-api.bingx.com", "https://open-api.bingx.pro"];
const parseBig = JSONBig({ storeAsString: true });
const CORS = {
  "Access-Control-Allow-Origin": "https://minyoullee.github.io",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-dashboard-session",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Cache-Control": "no-store",
};

function canonical(params: Record<string, unknown>): string {
  return Object.keys(params).sort().map((key) => `${key}=${params[key]}`).join("&");
}

async function signed(path: string, params: Record<string, unknown> = {}): Promise<any> {
  const all = { ...params, timestamp: Date.now() };
  const query = canonical(all);
  const signature = createHmac("sha256", SECRET_KEY).update(query).digest("hex");
  let last: unknown;
  for (const base of BASES) {
    try {
      const response = await fetch(`${base}${path}?${query}&signature=${signature}`, {
        headers: { "X-BX-APIKEY": API_KEY, "X-SOURCE-KEY": "COIN-ISSUE-PLAN-B" },
        signal: AbortSignal.timeout(10_000),
      });
      const json = parseBig.parse(await response.text());
      if (Number(json.code) !== 0) throw new Error(`BingX ${json.code}: ${json.msg}`);
      return json.data;
    } catch (error) {
      last = error;
    }
  }
  throw last instanceof Error ? last : new Error(String(last));
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (request.method !== "POST") return Response.json({ ok: false, error: "POST required" }, { status: 405, headers: CORS });
  const body = await request.json().catch(() => ({}));
  if (body.action !== "connection_check") {
    return Response.json({ ok: false, locked: true, error: "B플랜 계좌 조회는 비밀번호 연결 준비 중입니다." }, { status: 401, headers: CORS });
  }
  if (!API_KEY || !SECRET_KEY) {
    return Response.json({ ok: false, configured: false, error: "PLAN_B BingX secrets missing" }, { status: 503, headers: CORS });
  }
  try {
    const data = await signed("/openApi/swap/v3/user/balance", { recvWindow: 5000 });
    const balance = Array.isArray(data) ? data : (Array.isArray(data?.balance) ? data.balance : [data?.balance || data || {}]);
    const usdt = balance.find((row: any) => String(row?.asset || "").toUpperCase() === "USDT") || balance[0] || {};
    return Response.json({
      ok: true,
      configured: true,
      plan: "B",
      exchange: "BingX",
      futures_access: true,
      account_fingerprint: createHmac("sha256", SECRET_KEY).update(API_KEY).digest("hex").slice(0, 12),
      has_usdt_wallet: String(usdt?.asset || "USDT").toUpperCase() === "USDT",
      trading_enabled: false,
    }, { headers: CORS });
  } catch (error) {
    return Response.json({ ok: false, configured: true, futures_access: false, error: error instanceof Error ? error.message : String(error) }, { status: 502, headers: CORS });
  }
});
