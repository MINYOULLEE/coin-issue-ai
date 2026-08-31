import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import {PLAN_B_STANDARD as STANDARD} from "../_shared/plan_b_sizing.mjs";
import {runCombinationSignals} from "../_shared/plan_b_signal_cycle.mjs";
const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });

async function candles(symbol: string) {
  const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}USDT&interval=1h&limit=1000`, { signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw Error(`market data unavailable: ${symbol}`);
  const raw = await r.json();
  if (!Array.isArray(raw)) throw Error("invalid candles response");
  return raw.map((x: any) => ({ t: +x[0], o: +x[1], h: +x[2], l: +x[3], c: +x[4], v: +x[5] }));
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return Response.json({ ok: false }, { status: 405 });
  try {
    const key = req.headers.get("x-scheduler-key");
    if (!key) return Response.json({ ok: false }, { status: 403 });
    const { data: secret, error: authError } = await sb.from("private_runtime_secrets").select("secret_value").eq("id", "scheduler_auth").maybeSingle();
    if (authError || key !== secret?.secret_value?.key) return Response.json({ ok: false }, { status: 403 });
    const { data: state, error } = await sb.from("plan_b_trading_state").select("*").eq("id", "singleton").single();
    if (error) throw error;
    if (state.strategy_id !== STANDARD.strategy_id) return Response.json({ ok: false, error: "B strategy version mismatch" }, { status: 409 });
    const body = await req.json().catch(() => ({}));

    if (body.action === "preview" || body.action === "run") {
      const outcome=await runCombinationSignals({sb,fetchCandles:candles,preview:body.action==="preview"});
      if(body.action==="run"){
        const {error:healthError}=await sb.from("plan_b_runtime_health").upsert({id:"signals",payload:outcome,updated_at:new Date().toISOString()});
        if(healthError)throw healthError;
      }
      return Response.json(outcome);
    }

    return Response.json({ ok: false, error: "unknown action" }, { status: 400 });
  } catch(e) { console.error("B signals",String(e.message)); return Response.json({ ok: false, plan:"B", error: "B strategy run failed: "+String(e.message) }, { status: 503 }); }
});
