import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import {PLAN_B_STANDARD as STANDARD} from "../_shared/plan_b_sizing.mjs";
import {decidePlanB,signalRow} from "../_shared/plan_b_signals.mjs";
const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false } });

async function candles(symbol: string) {
  const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}USDT&interval=1h&limit=200`, { signal: AbortSignal.timeout(10000) });
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

    // Preview only: no signal table writes and no exchange order calls.
    if (body.action === "preview") {
      const outcomes = await Promise.all(Object.keys(STANDARD.symbols).map(async (symbol) => {
        try {
          const rows = await candles(symbol), now = Date.now(), d = decidePlanB(symbol, rows, now);
          return { symbol, ok: true, signal: d.side ? signalRow(symbol, d, now) : null, reason: d.reason || (d.side ? "signal" : "no signal") };
        } catch { return { symbol, ok: false, error: "market data validation failed" }; }
      }));
      return Response.json({ ok: outcomes.every((x) => x.ok), plan: "B", strategy_id: STANDARD.strategy_id, mode: "preview", orders_submitted: 0, outcomes });
    }

    // Live signal generation: stores eligible signals to plan_b_signals. Idempotent per
    // symbol+hour+side via the unique signal_key (a duplicate insert is treated as success).
    if (body.action === "run") {
      const now = Date.now();
      const results = await Promise.all(Object.keys(STANDARD.symbols).map(async (symbol) => {
        try {
          const rows = await candles(symbol);
          const d = decidePlanB(symbol, rows, now);
          if (!d.side) return { symbol, ok: true, stored: false, reason: d.reason || "no signal" };
          const row = signalRow(symbol, d, now);
          const { error: insertError } = await sb.from("plan_b_signals").insert(row);
          if (insertError) {
            if (String((insertError as any).code) === "23505") return { symbol, ok: true, stored: false, reason: "already stored this hour" };
            throw insertError;
          }
          return { symbol, ok: true, stored: true, signal_key: row.signal_key, side: row.side };
        } catch (e) { return { symbol, ok: false, error: e instanceof Error ? e.message : "signal generation failed" }; }
      }));
      return Response.json({ ok: results.every((x) => x.ok), plan: "B", strategy_id: STANDARD.strategy_id, mode: "run", results });
    }

    return Response.json({ ok: false, error: "unknown action" }, { status: 400 });
  } catch { return Response.json({ ok: false, error: "B strategy run failed" }, { status: 503 }); }
});
