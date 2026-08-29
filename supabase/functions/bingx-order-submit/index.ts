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
async function release(signalId: number) {
  await db(`trade_execution_reservations?signal_id=eq.${signalId}`, { method: "DELETE" });
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("POST required", { status: 405 });
  if (!INTERNAL_KEY || !same(req.headers.get("x-internal-key") || "", INTERNAL_KEY)) return new Response("forbidden", { status: 403 });
  const p = await req.json();
  const signal = p.signal || {}; const signalId = Number(signal.id);
  let orderAccepted = false;
  let tradeRecorded = false;
  try {
    const reservation = await db("rpc/reserve_real_trade_slot", { method: "POST", body: JSON.stringify({
      p_signal_id: signalId,
      p_symbol: signal.symbol,
      p_side: signal.side,
      p_max_concurrent: Number(p.max_concurrent_positions),
      p_max_same_direction: Number(p.max_same_direction),
    }) });
    if (!reservation?.reserved) throw new Error(`reservation rejected: ${reservation?.reason || "unavailable"}`);
    // The research standard requires 10x on every MDD30 asset. Never rely on
    // whatever leverage happened to be left on the BingX symbol previously.
    await signed("POST", "/openApi/swap/v2/trade/leverage", {
      symbol: p.symbol, side: p.positionSide, leverage: Number(p.leverage), recvWindow: 5000,
    });
    const clientOrderId = `ciai${signalId}`;
    const submittedAt = new Date();
    const raw = await signed("POST", "/openApi/swap/v2/trade/order", {
      symbol: p.symbol, side: p.side, positionSide: p.positionSide, type: "MARKET",
      quantity: p.quantity, clientOrderId, recvWindow: 5000,
    });
    orderAccepted = true;
    let order = raw?.order ?? raw;
    let orderId = String(order?.orderID ?? order?.orderId ?? "");
    if (!orderId) {
      await new Promise(r => setTimeout(r, 200));
      const found = await signed("GET", "/openApi/swap/v2/trade/order", { symbol: p.symbol, clientOrderId, recvWindow: 5000 });
      order = found?.order ?? found; orderId = String(order?.orderID ?? order?.orderId ?? "");
    }
    if (!orderId) throw new Error("BingX order id missing");
    let fillPrice = Number(order?.avgPrice || 0), executedQty = Number(order?.executedQty || 0);
    if (!(fillPrice > 0) || !(executedQty > 0)) {
      await new Promise(r => setTimeout(r, 250));
      const found = await signed("GET", "/openApi/swap/v2/trade/order", { symbol: p.symbol, clientOrderId, recvWindow: 5000 });
      const f = found?.order ?? found; fillPrice = Number(f?.avgPrice || fillPrice); executedQty = Number(f?.executedQty || executedQty);
    }
    if (!(fillPrice > 0)) fillPrice = Number(p.signal_price);
    if (!(executedQty > 0)) executedQty = Number(p.quantity);
    const notional = executedQty * fillPrice, actualMargin = notional / Number(p.leverage), fee = notional * Number(p.fee_rate || 0.001);
    const filledAt = new Date();
    await db("real_trades", { method: "POST", headers: { Prefer: "return=minimal" }, body: JSON.stringify({
      signal_id: signalId, symbol: signal.symbol, bingx_symbol: p.symbol, side: signal.side,
      signal_type: signal.signal_type, status: "open", test_mode: false, margin_usd: actualMargin,
      leverage: Number(p.leverage), notional_usd: notional, quantity: executedQty, entry_price: fillPrice,
      stop_price: null, target_price: null, bingx_order_id: orderId,
      strategy_epoch: signal.strategy_epoch, collector_version: Number(signal.collector_version || 0),
      executor_version: Number(p.executor_version), signal_model_version: signal.signal_model_version,
      signal_price: Number(p.signal_price), submitted_price: Number(p.signal_price),
      slippage_pct: (fillPrice / Number(p.signal_price) - 1) * 100 * (signal.side === "long" ? 1 : -1),
      entry_submitted_at: submittedAt.toISOString(), entry_filled_at: filledAt.toISOString(),
      expected_fee_usd: fee, strategy_config: { daily_rebalance: true, exposure_multiplier: p.exposure_multiplier, max_gross_exposure: p.max_gross_exposure },
    }) });
    tradeRecorded = true;
    await db(`trade_signals?id=eq.${signalId}`, { method: "PATCH", headers: { Prefer: "return=minimal" }, body: JSON.stringify({
      account_equity_usd: Number(p.equity), margin_usd: actualMargin, leverage: Number(p.leverage),
      notional_usd: notional, fee_usd: fee, updated_at: filledAt.toISOString(),
    }) });
    await release(signalId);
    return Response.json({ ok: true, signal_id: signalId, order_id: orderId, fill_price: fillPrice, quantity: executedQty });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    // If BingX accepted the entry but its durable DB record failed, close the
    // exact newly-created hedge-side quantity immediately. The admission
    // function guarantees there was no pre-existing same-symbol/same-side
    // position, so this cannot close an unrelated position.
    if (orderAccepted && !tradeRecorded) {
      try {
        await signed("POST", "/openApi/swap/v2/trade/order", {
          symbol: p.symbol,
          side: p.side === "BUY" ? "SELL" : "BUY",
          positionSide: p.positionSide,
          type: "MARKET",
          quantity: p.quantity,
          recvWindow: 5000,
        });
      } catch (closeError) {
        const closeMessage = closeError instanceof Error ? closeError.message : String(closeError);
        try { await db("system_errors", { method: "POST", headers: { Prefer: "return=minimal" }, body: JSON.stringify({ source: "bingx-order-submit", status_code: 500, message: `EMERGENCY CLOSE FAILED signal ${signalId}: ${closeMessage}`, fingerprint: `orphan-${signalId}` }) }); } catch { /* ignore */ }
      }
    }
    try { await db(`trade_signals?id=eq.${signalId}`, { method: "PATCH", headers: { Prefer: "return=minimal" }, body: JSON.stringify({ status: "invalidated", close_reason: `전용 주문 실행 실패: ${message}`.slice(0,500), closed_at: new Date().toISOString(), updated_at: new Date().toISOString() }) }); } catch { /* ignore */ }
    try { await release(signalId); } catch { /* ignore */ }
    return Response.json({ ok: false, error: message }, { status: 502 });
  }
});
