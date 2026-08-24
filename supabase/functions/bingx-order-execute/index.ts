// bingx-order-execute
// 종합추천 신호 엔진(coin-collector)이 새 신호를 확정하면 내부 호출로만 실행되는
// 실거래 주문 함수. 브라우저에서는 절대 직접 호출하지 않는다 (CORS 미허용).
//
// 안전장치 요약 (모두 이 파일 안에서 강제됨):
//  - 내부 비밀 헤더(x-internal-key) 불일치 시 즉시 거부
//  - real_trading_state.enabled = false 면 어떤 주문도 나가지 않음 (긴급 정지 스위치)
//  - 신호당 주문 1건 제한 (signal_id unique index + 사전 조회)
//  - 오래된 신호 차단 (signal_type별 신선도 기준)
//  - 수집기 정지 상태면 신규 진입 차단 (coin_snapshots heartbeat 확인)
//  - 손절가 없는 주문 차단
//  - 총 담보 상한 / 동시 포지션 수 / 동일방향 포지션 수 / 종목당 담보 상한 / 레버리지 상한
//  - 포지션 모드가 Hedge(양방향)가 아니면 차단 (스윙·전술 신호가 같은 심볼에서
//    반대 방향으로 동시에 열릴 수 있으므로 One-way 모드는 안전하지 않음)

import { createHmac } from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";

const JSONBigParse = JSONBig({ storeAsString: true });

const PROJECT_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const API_KEY = Deno.env.get("BINGX_API_KEY") || "";
const SECRET_KEY = Deno.env.get("BINGX_SECRET_KEY") || "";
const INTERNAL_KEY = Deno.env.get("INTERNAL_TRADE_SECRET") || "";

const ENV_URLS: Record<string, string[]> = {
  "prod-live": ["https://open-api.bingx.com", "https://open-api.bingx.pro"],
};
const COINS = ["BTC", "ETH", "XRP", "SOL", "BNB"];
const STALE_MS: Record<string, number> = { tactical: 120000, swing: 900000 };
const COLLECTOR_STALE_MS = 5 * 60 * 1000;
const EXECUTOR_VERSION = 16;
const DEFAULT_STRATEGY_EPOCH = "v27_profit_measurement_1";

function isNetworkOrTimeout(e: unknown): boolean {
  if (e instanceof TypeError) return true;
  if (e instanceof DOMException && e.name === "AbortError") return true;
  if (e instanceof Error && e.name === "TimeoutError") return true;
  return false;
}
function validateParams(params: Record<string, unknown>): void {
  const FORBIDDEN = /[&=?#\r\n]/;
  for (const [k, v] of Object.entries(params)) {
    const s = String(v);
    if (FORBIDDEN.test(s)) throw new Error(`Param "${k}" has forbidden char in: "${s}"`);
  }
}
function buildCanonical(params: Record<string, unknown>): string {
  return Object.keys(params).sort().map((k) => `${k}=${params[k]}`).join("&");
}

// BingX 서명 요청 헬퍼. bingx-account-read와 동일한 방식이며 임의로 바꾸지 않는다.
async function fetchSigned(
  apiKey: string,
  secretKey: string,
  method: "GET" | "POST" | "DELETE",
  path: string,
  params: Record<string, unknown> = {},
): Promise<any> {
  const urls = ENV_URLS["prod-live"];
  const all = { ...params, timestamp: Date.now() };
  validateParams(all);
  const canonical = buildCanonical(all);
  const signature = createHmac("sha256", secretKey).update(canonical).digest("hex");
  for (const base of urls) {
    try {
      const url = method === "GET" || method === "DELETE"
        ? `${base}${path}?${canonical}&signature=${signature}`
        : `${base}${path}`;
      const body = (method === "GET" || method === "DELETE") ? undefined : `${canonical}&signature=${signature}`;
      const res = await fetch(url, {
        method,
        headers: {
          "X-BX-APIKEY": apiKey,
          "X-SOURCE-KEY": "BX-AI-SKILL",
          ...(method === "POST" ? { "Content-Type": "application/x-www-form-urlencoded" } : {}),
        },
        body,
        signal: AbortSignal.timeout(10000),
      });
      const json = JSONBigParse.parse(await res.text());
      if (json.code !== 0) throw new Error(`BingX ${json.code}: ${json.msg}`);
      return json.data;
    } catch (e) {
      if (!isNetworkOrTimeout(e) || base === urls[urls.length - 1]) throw e;
    }
  }
}

function adminHeaders(extra: Record<string, string> = {}) {
  return { apikey: SERVICE_KEY, Authorization: "Bearer " + SERVICE_KEY, "Content-Type": "application/json", ...extra };
}
async function db(path: string, init: RequestInit = {}) {
  const r = await fetch(PROJECT_URL + "/rest/v1/" + path, { ...init, headers: { ...adminHeaders(), ...(init.headers || {}) } });
  const text = await r.text();
  if (!r.ok) throw new Error("db " + path + " " + r.status + " " + text);
  // Prefer: return=minimal 인 POST/PATCH는 201/200이어도 본문이 비어있다. 상태코드만으로 판단하지 않는다.
  if (!text) return null;
  try { return JSON.parse(text); } catch { throw new Error("db json parse failed on " + path + " (len=" + text.length + ")"); }
}

async function insertRejected(signal: any, reason: string, metrics: Record<string, any> = {}) {
  try {
    await db("real_trades", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        signal_id: signal.id, symbol: signal.symbol, bingx_symbol: signal.symbol + "-USDT",
        side: signal.side, signal_type: signal.signal_type, status: "rejected",
        test_mode: true, margin_usd: 0, leverage: 0, notional_usd: 0, quantity: 0,
        entry_price: signal.entry_price, stop_price: signal.invalidation_price, target_price: signal.target_price,
        strategy_epoch: signal.strategy_epoch || DEFAULT_STRATEGY_EPOCH,
        collector_version: Number(signal.collector_version || 27), executor_version: EXECUTOR_VERSION,
        signal_model_version: signal.signal_model_version || "signal_v27",
        reject_reason: reason.slice(0, 500),
        ...metrics,
      }),
    });
  } catch (e) { console.error("insertRejected failed:", e); }
}

let contractCache: Record<string, { data: any; ts: number }> = {};
async function getContract(bxSymbol: string) {
  const c = contractCache[bxSymbol];
  if (c && Date.now() - c.ts < 6 * 3600000) return c.data;
  const rows = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/quote/contracts", { symbol: bxSymbol });
  const info = Array.isArray(rows) ? rows[0] : rows;
  if (!info) throw new Error("contract info not found for " + bxSymbol);
  contractCache[bxSymbol] = { data: info, ts: Date.now() };
  return info;
}
function roundDown(v: number, precision: number) {
  const f = Math.pow(10, precision);
  return Math.floor(v * f) / f;
}
function roundTo(v: number, precision: number) {
  const f = Math.pow(10, precision);
  return Math.round(v * f) / f;
}
function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}
function percentile(values: number[], q: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * clamp(q, 0, 1);
  const low = Math.floor(index), high = Math.ceil(index);
  if (low === high) return sorted[low];
  return sorted[low] + (sorted[high] - sorted[low]) * (index - low);
}

// real_trades.status='open'인데 실제 BingX 포지션은 이미 손절/익절로 종료된 경우를
// 찾아 'closed'로 정리한다. 이게 없으면 종료된 포지션이 동시 포지션 한도를 영원히
// 차지해서, 초기 몇 건 이후로 신규 진입이 전부 거부되는 문제가 생긴다.
async function reconcileOpenTrades(): Promise<void> {
  const live = new Map<string, any>();
  try {
    const positions = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/positions", { recvWindow: 5000 });
    const rows = Array.isArray(positions) ? positions : (positions?.positions || []);
    for (const p of rows) {
      const amt = Number(p.positionAmt ?? p.positionAmount ?? 0);
      if (Math.abs(amt) <= 0) continue;
      const symbol = String(p.symbol || ""), side = String(p.positionSide || (amt >= 0 ? "LONG" : "SHORT"));
      live.set(symbol + "|" + side, p);
    }
  } catch (e) {
    console.error("reconcile: position fetch failed, skipping:", e instanceof Error ? e.message : String(e));
    return;
  }
  let openRows: any[] = [];
  try {
    openRows = await db("real_trades?status=eq.open&select=*");
  } catch (e) {
    console.error("reconcile: failed to load open trades:", e instanceof Error ? e.message : String(e));
    return;
  }
  for (const row of openRows) {
    const posSide = row.side === "long" ? "LONG" : "SHORT";
    const position = live.get(row.bingx_symbol + "|" + posSide);
    if (position) {
      const mark = Number(position.markPrice ?? position.price ?? 0);
      const entry = Number(row.entry_price || 0);
      if (mark > 0 && entry > 0) {
        const movePct = (mark / entry - 1) * 100 * (row.side === "long" ? 1 : -1);
        const roePct = movePct * Number(row.leverage || 1);
        try {
          await db("real_trades?id=eq." + row.id, {
            method: "PATCH",
            body: JSON.stringify({
              mfe_pct: Math.max(Number(row.mfe_pct || 0), movePct),
              mae_pct: Math.min(Number(row.mae_pct || 0), movePct),
              peak_roe_pct: Math.max(Number(row.peak_roe_pct || 0), roePct),
              lowest_roe_pct: Math.min(Number(row.lowest_roe_pct || 0), roePct),
              last_mark_price: mark,
              measurement_updated_at: new Date().toISOString(),
            }),
          });
        } catch (e) {
          console.error("reconcile: excursion update failed", row.id, e instanceof Error ? e.message : String(e));
        }
      }
      continue;
    }
    let netPnl: number | null = null, feeUsd: number | null = null;
    try {
      const startMs = Date.parse(row.created_at) - 60000;
      const income = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/income", { symbol: row.bingx_symbol, startTime: startMs, limit: 200 });
      const list = Array.isArray(income) ? income : [];
      const relevant = list.filter((x: any) => ["REALIZED_PNL", "TRADING_FEE", "FUNDING_FEE"].includes(x.incomeType));
      if (relevant.length) {
        const realizedPnl = relevant.filter((x: any) => x.incomeType === "REALIZED_PNL").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const tradingFee = relevant.filter((x: any) => x.incomeType === "TRADING_FEE").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const fundingFee = relevant.filter((x: any) => x.incomeType === "FUNDING_FEE").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        netPnl = realizedPnl + tradingFee + fundingFee;
        feeUsd = -(tradingFee + fundingFee);
      }
    } catch (e) {
      console.error("reconcile: income fetch failed for", row.bingx_symbol, e instanceof Error ? e.message : String(e));
    }
    try {
      await db("real_trades?id=eq." + row.id, {
        method: "PATCH",
        body: JSON.stringify({ status: "closed", closed_at: new Date().toISOString(), net_pnl_usd: netPnl, fee_usd: feeUsd, close_reason: "거래소 포지션 종료 확인(자동 정산)", measurement_updated_at: new Date().toISOString() }),
      });
    } catch (e) {
      console.error("reconcile: failed to close real_trades row", row.id, e instanceof Error ? e.message : String(e));
    }
  }
}

// coin-collector의 20분 재점검에서 손절/익절이 바뀌었을 때 호출된다. 기존 SL/TP 조건부 주문을
// 취소하고 새 가격으로 다시 등록한다. closePosition을 쓰설여 수량 오차와 무관하게 포지션 전체를 정리한다.
async function handleReprice(payload: any): Promise<Response> {
  try {
    if (!API_KEY || !SECRET_KEY) return Response.json({ ok: false, error: "BingX secrets not configured" });
    const rows = await db(`real_trades?signal_id=eq.${payload.id}&status=eq.open&select=*&limit=1`);
    const row = rows?.[0];
    if (!row) return Response.json({ ok: true, skipped: "no matching open real trade" });
    const newStop = Number(payload.invalidation_price), newTarget = Number(payload.target_price);
    if (!(newStop > 0) || !(newTarget > 0)) return Response.json({ ok: false, error: "invalid reprice values" });

    const bxSymbol = String(row.bingx_symbol);
    const positionSide = row.side === "long" ? "LONG" : "SHORT";
    const closeSide = row.side === "long" ? "SELL" : "BUY";
    const contract = await getContract(bxSymbol);
    const pricePrecision = Number(contract.pricePrecision ?? 2);
    const qtyPrecision = Number(contract.quantityPrecision ?? 3);
    const qty = roundDown(Number(row.quantity), qtyPrecision);
    const stopPrice = roundTo(newStop, pricePrecision);
    const targetPrice = roundTo(newTarget, pricePrecision);
    if (stopPrice === Number(row.stop_price) && targetPrice === Number(row.target_price)) {
      return Response.json({ ok: true, skipped: "no change" });
    }

    const openOrders = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/trade/openOrders", { symbol: bxSymbol, recvWindow: 5000 });
    const list = Array.isArray(openOrders) ? openOrders : (openOrders?.orders || []);
    const mine = list.filter((o: any) => String(o.positionSide) === positionSide && ["STOP_MARKET", "TAKE_PROFIT_MARKET"].includes(String(o.type)));
    for (const o of mine) {
      try {
        await fetchSigned(API_KEY, SECRET_KEY, "DELETE", "/openApi/swap/v2/trade/order", { symbol: bxSymbol, orderId: o.orderId ?? o.orderID, recvWindow: 5000 });
      } catch (e) {
        console.error("reprice: cancel failed", o.orderId ?? o.orderID, e instanceof Error ? e.message : String(e));
      }
    }

    await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
      symbol: bxSymbol, side: closeSide, positionSide, type: "STOP_MARKET",
      stopPrice, quantity: qty, workingType: "MARK_PRICE", recvWindow: 5000,
    });
    await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
      symbol: bxSymbol, side: closeSide, positionSide, type: "TAKE_PROFIT_MARKET",
      stopPrice: targetPrice, quantity: qty, workingType: "MARK_PRICE", recvWindow: 5000,
    });

    await db(`real_trades?id=eq.${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ stop_price: stopPrice, target_price: targetPrice, updated_at: new Date().toISOString() }),
    });

    return Response.json({ ok: true, repriced: true, stop_price: stopPrice, target_price: targetPrice });
  } catch (e) {
    console.error("reprice failed:", e instanceof Error ? e.message : String(e));
    return Response.json({ ok: false, error: "reprice failed" }, { status: 502 });
  }
}

// 손절/익절이 안 걸려있는 것으로 확인된 기존 열린 실거래에 즉시 조건부 주문을 걸어준다.
// id를 주면 그 1건만, 안 주면 열려있는 전체를 대상으로 한다. 이미 걸려있는 건 건드리지 않고
// 빠진 것만 채우기 때문에 매 주기 반복 호출해도 안전하다(불필요한 취소·재등록 없음).
async function handleProtect(payload: any): Promise<Response> {
  try {
    if (!API_KEY || !SECRET_KEY) return Response.json({ ok: false, error: "BingX secrets not configured" });
    const path = payload.id ? `real_trades?id=eq.${payload.id}&status=eq.open&select=*` : "real_trades?status=eq.open&select=*";
    const rows = (await db(path)) || [];
    const results: any[] = [];
    const livePositions = new Map<string, any>();
    try {
      const rawPositions = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/positions", { recvWindow: 5000 });
      const positionRows = Array.isArray(rawPositions) ? rawPositions : (rawPositions?.positions || []);
      for (const p of positionRows) {
        const amt = Number(p.positionAmt ?? p.positionAmount ?? 0);
        if (Math.abs(amt) <= 0) continue;
        livePositions.set(String(p.symbol || "") + "|" + String(p.positionSide || (amt >= 0 ? "LONG" : "SHORT")), p);
      }
    } catch (positionError) {
      console.error("protect: MFE/MAE position fetch failed:", positionError instanceof Error ? positionError.message : String(positionError));
    }
    for (const row of rows) {
      const bxSymbol = String(row.bingx_symbol), positionSide = row.side === "long" ? "LONG" : "SHORT", closeSide = row.side === "long" ? "SELL" : "BUY";
      try {
        const livePosition = livePositions.get(bxSymbol + "|" + positionSide);
        const markPrice = Number(livePosition?.markPrice ?? livePosition?.price ?? 0);
        const measuredEntry = Number(row.entry_price || 0);
        if (markPrice > 0 && measuredEntry > 0) {
          const movePct = (markPrice / measuredEntry - 1) * 100 * (row.side === "long" ? 1 : -1);
          const roePct = movePct * Number(row.leverage || 1);
          await db("real_trades?id=eq." + row.id, {
            method: "PATCH",
            body: JSON.stringify({
              mfe_pct: Math.max(Number(row.mfe_pct || 0), movePct),
              mae_pct: Math.min(Number(row.mae_pct || 0), movePct),
              peak_roe_pct: Math.max(Number(row.peak_roe_pct || 0), roePct),
              lowest_roe_pct: Math.min(Number(row.lowest_roe_pct || 0), roePct),
              last_mark_price: markPrice,
              measurement_updated_at: new Date().toISOString(),
            }),
          });
        }
        const openOrders = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/trade/openOrders", { symbol: bxSymbol, recvWindow: 5000 });
        const list = Array.isArray(openOrders) ? openOrders : (openOrders?.orders || []);
        const mine = list.filter((o: any) => String(o.positionSide) === positionSide);
        const hasSl = mine.some((o: any) => String(o.type) === "STOP_MARKET");
        const hasTp = mine.some((o: any) => String(o.type) === "TAKE_PROFIT_MARKET");
        if (hasSl && hasTp) {
          if (!row.protective_verified) {
            await db("real_trades?id=eq." + row.id, { method: "PATCH", body: JSON.stringify({ protective_verified: true, measurement_updated_at: new Date().toISOString() }) });
          }
          results.push({ id: row.id, symbol: row.symbol, skipped: "already protected" }); continue;
        }

        const contract = await getContract(bxSymbol);
        const pricePrecision = Number(contract.pricePrecision ?? 2);
        const qtyPrecision = Number(contract.quantityPrecision ?? 3);
        const stopPrice = roundTo(Number(row.stop_price), pricePrecision);
        const targetPrice = roundTo(Number(row.target_price), pricePrecision);
        const qty = roundDown(Number(row.quantity), qtyPrecision);

        let slOk = hasSl, tpOk = hasTp, slErr = "", tpErr = "";
        if (!hasSl) {
          try {
            await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", { symbol: bxSymbol, side: closeSide, positionSide, type: "STOP_MARKET", stopPrice, quantity: qty, workingType: "MARK_PRICE", recvWindow: 5000 });
            slOk = true;
          } catch (e) { slErr = e instanceof Error ? e.message : String(e); }
        }
        if (!hasTp) {
          try {
            await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", { symbol: bxSymbol, side: closeSide, positionSide, type: "TAKE_PROFIT_MARKET", stopPrice: targetPrice, quantity: qty, workingType: "MARK_PRICE", recvWindow: 5000 });
            tpOk = true;
          } catch (e) { tpErr = e instanceof Error ? e.message : String(e); }
        }

        const nowIso = new Date().toISOString();
        const patch: any = {
          protective_verified: slOk && tpOk,
          protect_retry_count: Number(row.protect_retry_count || 0) + 1,
          measurement_updated_at: nowIso,
        };
        if (!row.stop_order_created_at && slOk) patch.stop_order_created_at = nowIso;
        if (!row.target_order_created_at && tpOk) patch.target_order_created_at = nowIso;
        if (slOk && tpOk && row.entry_filled_at) {
          patch.protective_latency_ms = Math.max(0, Date.parse(nowIso) - Date.parse(row.entry_filled_at));
        }
        await db("real_trades?id=eq." + row.id, { method: "PATCH", body: JSON.stringify(patch) });
        results.push({ id: row.id, symbol: row.symbol, side: row.side, stopPrice, targetPrice, slOk, tpOk, slErr, tpErr });
      } catch (e) {
        results.push({ id: row.id, symbol: row.symbol, error: e instanceof Error ? e.message : String(e) });
      }
    }
    return Response.json({ ok: true, protected: results });
  } catch (e) {
    console.error("protect failed:", e instanceof Error ? e.message : String(e));
    return Response.json({ ok: false, error: "protect failed" }, { status: 502 });
  }
}

// real_trades의 모든 행을 BingX 실제 주문 체결 내역(주문ID 기준 조회) 및 실시간 포지션과
// 하나하나 대조한다. 진입가/수량이 실제 체결값과 다르거나, open인데 실제 포지션이 없거나
// 수량이 다르면 전부 잡아낸다. 결과는 로그로 남겨서 바로 확인할 수 있게 한다.
async function handleAudit(): Promise<Response> {
  try {
    if (!API_KEY || !SECRET_KEY) return Response.json({ ok: false, error: "BingX secrets not configured" });

    // 1. 주문ID가 있는 모든 행(진짜 주문이 나간 것)을 실제 체결 내역과 대조
    const rows = (await db("real_trades?bingx_order_id=not.is.null&select=id,symbol,bingx_symbol,side,status,quantity,entry_price,bingx_order_id&order=id.asc")) || [];
    const orderMismatches: any[] = [];
    let orderChecked = 0;
    for (const row of rows) {
      try {
        if (!row.bingx_order_id) { orderMismatches.push({ id: row.id, symbol: row.symbol, error: "bingx_order_id 비어있음" }); continue; }
        const raw = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/trade/order", { symbol: row.bingx_symbol, orderId: row.bingx_order_id, recvWindow: 5000 });
        // 응답이 data.order 형태로 중첩되는 경우가 있어 둘 다 확인한다.
        const order = raw?.order ?? raw;
        orderChecked++;
        const execQty = Number(order?.executedQty ?? 0);
        const avgPrice = Number(order?.avgPrice ?? 0);
        const bxStatus = String(order?.status ?? "");
        const qtyDiff = Math.abs(execQty - Number(row.quantity));
        const priceDiffPct = avgPrice > 0 ? Math.abs(avgPrice - Number(row.entry_price)) / avgPrice * 100 : 0;
        if (qtyDiff > 0.0000001 || priceDiffPct > 0.05 || (bxStatus && !["FILLED", "PARTIALLY_FILLED"].includes(bxStatus))) {
          orderMismatches.push({
            id: row.id, symbol: row.symbol,
            db_quantity: Number(row.quantity), bx_executed_qty: execQty,
            db_entry_price: Number(row.entry_price), bx_avg_price: avgPrice,
            bx_order_status: bxStatus,
            raw_keys: Object.keys(order || {}).join(","),
          });
        }
      } catch (e) {
        orderMismatches.push({ id: row.id, symbol: row.symbol, error: e instanceof Error ? e.message : String(e) });
      }
    }

    // 2. DB가 open이라고 믿는 행이 실제로도 거래소에 살아있는 포지션인지, 수량이 맞는지 대조
    const positionMismatches: any[] = [];
    let liveKeys: Record<string, number> = {};
    try {
      const positions = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/positions", { recvWindow: 5000 });
      const posRows = Array.isArray(positions) ? positions : (positions?.positions || []);
      for (const p of posRows) {
        const amt = Math.abs(Number(p.positionAmt ?? p.positionAmount ?? 0));
        if (amt <= 0) continue;
        liveKeys[String(p.symbol || "") + "|" + String(p.positionSide || "")] = amt;
      }
    } catch (e) {
      return Response.json({ ok: false, error: "position fetch failed, audit incomplete: " + (e instanceof Error ? e.message : String(e)) });
    }
    const openRows = (await db("real_trades?status=eq.open&select=id,symbol,bingx_symbol,side,quantity")) || [];
    for (const row of openRows) {
      const posSide = row.side === "long" ? "LONG" : "SHORT";
      const liveQty = liveKeys[row.bingx_symbol + "|" + posSide];
      if (liveQty == null) positionMismatches.push({ id: row.id, symbol: row.symbol, issue: "DB는 open인데 실제 거래소엔 해당 포지션이 없음" });
      else if (Math.abs(liveQty - Number(row.quantity)) > 0.0000001) positionMismatches.push({ id: row.id, symbol: row.symbol, issue: "수량 불일치", db_quantity: Number(row.quantity), bx_live_quantity: liveQty });
    }
    // 반대로 거래소엔 있는데 DB엔 open으로 안 잡힌 포지션도 확인
    const trackedKeys = new Set(openRows.map((r: any) => r.bingx_symbol + "|" + (r.side === "long" ? "LONG" : "SHORT")));
    const untracked = Object.keys(liveKeys).filter((k) => !trackedKeys.has(k)).map((k) => ({ key: k, bx_quantity: liveKeys[k], issue: "거래소엔 포지션이 있는데 DB엔 추적 기록이 없음" }));

    return Response.json({
      ok: true,
      order_rows_checked: orderChecked,
      order_mismatches: orderMismatches,
      open_rows_checked: openRows.length,
      position_mismatches: positionMismatches,
      untracked_live_positions: untracked,
    });
  } catch (e) {
    console.error("audit failed:", e instanceof Error ? e.message : String(e));
    return Response.json({ ok: false, error: "audit failed" }, { status: 502 });
  }
}

// 이미 종료된 과거 실거래 중 fee_usd가 비어있는 건들을 대상으로, 각 거래의 정확한
// 진입~종료 시각 구간으로만 BingX income을 조회해서 수수료/순손익을 다시 채운다.
// 시작~종료 시각으로 범위를 좋혀야 같은 종목의 다른 거래 수수료가 섞여 들어가지 않는다.
async function handleBackfillFees(): Promise<Response> {
  try {
    if (!API_KEY || !SECRET_KEY) return Response.json({ ok: false, error: "BingX secrets not configured" });
    const rows = (await db("real_trades?status=eq.closed&fee_usd=is.null&select=id,bingx_symbol,created_at,closed_at&order=id.asc")) || [];
    const results: any[] = [];
    for (const row of rows) {
      if (!row.closed_at) { results.push({ id: row.id, skipped: "no closed_at" }); continue; }
      try {
        const startMs = Date.parse(row.created_at) - 60000;
        const endMs = Date.parse(row.closed_at) + 60000;
        const income = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/income", { symbol: row.bingx_symbol, startTime: startMs, endTime: endMs, limit: 200 });
        const list = Array.isArray(income) ? income : [];
        const relevant = list.filter((x: any) => ["REALIZED_PNL", "TRADING_FEE", "FUNDING_FEE"].includes(x.incomeType));
        if (!relevant.length) { results.push({ id: row.id, skipped: "no income records in window" }); continue; }
        const realizedPnl = relevant.filter((x: any) => x.incomeType === "REALIZED_PNL").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const tradingFee = relevant.filter((x: any) => x.incomeType === "TRADING_FEE").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const fundingFee = relevant.filter((x: any) => x.incomeType === "FUNDING_FEE").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const netPnl = realizedPnl + tradingFee + fundingFee;
        const feeUsd = -(tradingFee + fundingFee);
        await db(`real_trades?id=eq.${row.id}`, { method: "PATCH", body: JSON.stringify({ fee_usd: feeUsd, net_pnl_usd: netPnl }) });
        results.push({ id: row.id, fee_usd: feeUsd, net_pnl_usd: netPnl });
      } catch (e) {
        results.push({ id: row.id, error: e instanceof Error ? e.message : String(e) });
      }
    }
    return Response.json({ ok: true, backfilled: results });
  } catch (e) {
    console.error("backfill_fees failed:", e instanceof Error ? e.message : String(e));
    return Response.json({ ok: false, error: "backfill failed" }, { status: 502 });
  }
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return Response.json({ ok: false, error: "POST required" }, { status: 405 });
  if (!INTERNAL_KEY || req.headers.get("x-internal-key") !== INTERNAL_KEY) {
    return Response.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let signal: any;
  try { signal = await req.json(); } catch { return Response.json({ ok: false, error: "invalid json" }, { status: 400 }); }

  // coin-collector의 20분 재점검에서 손절/익절이 바뀌면 여기로 온다. 새 주문이 아니라 기존
  // 열려있는 실거래의 조건부 주문(SL/TP)만 취소 후 새 가격으로 다시 건다.
  if (signal?.action === "reprice") return await handleReprice(signal);

  // 과거 종료 건들의 수수료를 한 번 소급 보정한다 (사람이 요청했을 때만 사용, 자동 반복 안 함).
  if (signal?.action === "backfill_fees") return await handleBackfillFees();

  // 전체 실거래 기록을 BingX 실제 체결 내역·실시간 포지션과 하나하나 대조하는 전수검사.
  if (signal?.action === "audit") return await handleAudit();

  // 이미 열려있는데 손절/익절이 안 걸려있는 것으로 확인된 실거래에 즉시 조건부 주문을 걸어준다.
  if (signal?.action === "protect") return await handleProtect(signal);

  // 신호(trade_signals)가 성공/실패/보합으로 종료될 때마다 호출된다. 새 주문 없이 신호만
  // 끝나는 경우(우리 쪽 시뮬레이션이 먼저 손절/익절을 감지한 경우 등)에도 실거래
  // 포지션이 실제로 종료됐는지 즉시 확인해서 real_trades를 최신 상태로 맞추다. 기존에는
  // 새 주문이 들어올 때만 정산이 도아서, 새 신호가 한동안 없으면 이미 끝난 실거래가
  // 계속 '진행 중'으로 남는 빈틈이 있었다.
  if (signal?.action === "sync") {
    await reconcileOpenTrades();
    return Response.json({ ok: true, synced: true });
  }

  try {
    if (!COINS.includes(signal.symbol)) return Response.json({ ok: false, error: "unsupported symbol" }, { status: 400 });
    if (!["long", "short"].includes(signal.side)) return Response.json({ ok: false, error: "invalid side" }, { status: 400 });
    if (!["swing", "tactical"].includes(signal.signal_type)) return Response.json({ ok: false, error: "invalid signal_type" }, { status: 400 });
    if (!(Number(signal.invalidation_price) > 0) || !(Number(signal.target_price) > 0)) {
      await insertRejected(signal, "손절가/목표가 없음");
      return Response.json({ ok: false, error: "missing stop or target price" });
    }

    // 1. 중복 주문 방지: 이미 이 신호로 실거래가 기록됐으면 재실행하지 않는다.
    const dup = await db(`real_trades?signal_id=eq.${signal.id}&select=id&limit=1`);
    if (dup?.length) return Response.json({ ok: true, skipped: "already traded" });

    if (!API_KEY || !SECRET_KEY) {
      await insertRejected(signal, "BingX API 키 미설정");
      return Response.json({ ok: false, error: "BingX secrets not configured" });
    }

    // 2. 긴급 정지 스위치 + 위험 한도 설정 로드
    const stateRows = await db("real_trading_state?id=eq.singleton&select=*&limit=1");
    const state = stateRows?.[0];
    if (!state) { await insertRejected(signal, "설정 없음"); return Response.json({ ok: false, error: "no trading state" }); }
    if (!state.enabled) return Response.json({ ok: true, skipped: "real trading disabled (kill switch)" });

    // 3. 신호 신선도 확인
    const staleMs = STALE_MS[signal.signal_type] ?? 300000;
    if (Date.now() - Date.parse(signal.created_at) > staleMs) {
      await insertRejected(signal, "오래된 신호");
      return Response.json({ ok: true, skipped: "stale signal" });
    }

    // 4. 수집기 정상 동작 확인 (중단 상태면 신규 진입 금지)
    const snap = await db("coin_snapshots?id=eq.live&select=updated_at&limit=1");
    const heartbeat = snap?.[0]?.updated_at ? Date.parse(snap[0].updated_at) : 0;
    if (!heartbeat || Date.now() - heartbeat > COLLECTOR_STALE_MS) {
      await insertRejected(signal, "수집기 중단 상태");
      return Response.json({ ok: true, skipped: "collector stale" });
    }

    // 5. 포지션 모드 확인: 스윙·전술 신호가 같은 심볼에서 반대 방향으로 동시에
    //    열릴 수 있어 Hedge(양방향) 모드가 아니면 실거래를 진행하지 않는다.
    const posMode = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v1/positionSide/dual", {});
    if (!posMode?.dualSidePosition) {
      await insertRejected(signal, "One-way 모드 - Hedge 모드로 전환 필요");
      return Response.json({ ok: false, error: "account must be switched to Hedge (dual-side) position mode on BingX before live trading" });
    }

    // 6. 현재 열려있는 실거래 포지션 기준으로 위험 한도 계산 (먼저 종료된 포지션 정리)
    await reconcileOpenTrades();
    const open = await db("real_trades?status=eq.open&select=symbol,side,margin_usd");
    if (open.length >= state.max_concurrent_positions) {
      await insertRejected(signal, "동시 포지션 한도 초과");
      return Response.json({ ok: true, skipped: "max concurrent positions reached" });
    }
    const sameDir = open.filter((x: any) => x.side === signal.side).length;
    if (sameDir >= state.max_same_direction) {
      await insertRejected(signal, "동일 방향 포지션 한도 초과");
      return Response.json({ ok: true, skipped: "max same-direction positions reached" });
    }
    // 6-0. 같은 종목·같은 방향으로 이미 열려있는 포지션이 있으면 재진입하지 않는다. BingX는
    //      이 경우 새 포지션을 만들지 않고 기존 포지션에 평단가로 합쳤버리는데, 우리 시스템은
    //      신호마다 별도 행으로 손절/익절을 추적하기 때문에 실제로는 포지션이 1개인데 기록은
    //      2개가 되고, 손절/익절 조건부 주문도 두 세트가 걸려 서로 충돌할 위험이 있다.
    if (open.some((x: any) => x.symbol === signal.symbol && x.side === signal.side)) {
      await insertRejected(signal, "동일 종목·방향 포지션 이미 보유 중(평단 섞임 방지)");
      return Response.json({ ok: true, skipped: "already holding same symbol+side position" });
    }

    // 6-1. 실시간 BingX 잔고 조회 — 담보금을 고정 달러가 아니라 "지금 이 순간의 실제 잔고 비율"로 계산한다.
    //      수익이 나서 잔고가 늘면 다음 신호부터 자동으로 담보금도 커진다.
    let equity = 0;
    try {
      const balanceData = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v3/user/balance", { recvWindow: 5000 });
      const balRows = Array.isArray(balanceData) ? balanceData : (Array.isArray(balanceData?.balance) ? balanceData.balance : [balanceData?.balance || balanceData || {}]);
      const usdt = balRows.find((x: any) => String(x?.asset || "").toUpperCase() === "USDT") || balRows[0] || {};
      equity = Number(usdt?.equity ?? usdt?.balance ?? 0);
    } catch (e) {
      console.error("balance fetch failed:", e instanceof Error ? e.message : String(e));
    }
    if (!(equity > 0)) {
      await insertRejected(signal, "실시간 잔고 조회 실패");
      return Response.json({ ok: true, skipped: "balance unavailable" });
    }

    // 6-2. 계좌 회로차단기: 한국시간 하루의 실제 순손실과 최근 연속 손실을 신규 진입 전에 확인한다.
    // rejected/진행중 거래는 제외하고, 수수료·펀딩비가 반영된 net_pnl_usd만 사용한다.
    const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const kstDayStartUtc = new Date(Date.UTC(kstNow.getUTCFullYear(), kstNow.getUTCMonth(), kstNow.getUTCDate()) - 9 * 60 * 60 * 1000);
    const recentClosed = (await db("real_trades?status=eq.closed&net_pnl_usd=not.is.null&select=id,side,signal_type,net_pnl_usd,closed_at&order=closed_at.desc&limit=100")) || [];
    const dailyClosed = recentClosed.filter((x: any) => x.closed_at && Date.parse(x.closed_at) >= kstDayStartUtc.getTime());
    const dailyNetPnl = dailyClosed.reduce((sum: number, x: any) => sum + Number(x.net_pnl_usd || 0), 0);
    let consecutiveLosses = 0;
    for (const x of recentClosed) {
      if (Number(x.net_pnl_usd) < 0) consecutiveLosses++;
      else break;
    }
    const dailyLossLimitPct = Number(state.daily_loss_limit_pct ?? 3.0);
    const maxConsecutiveLosses = Number(state.max_consecutive_losses ?? 4);
    const lossCooldownMinutes = Number(state.loss_cooldown_minutes ?? 360);
    const estimatedDayStartEquity = Math.max(equity, equity - dailyNetPnl);
    const dailyLossLimitUsd = estimatedDayStartEquity * dailyLossLimitPct / 100;
    const lastClosedAt = recentClosed[0]?.closed_at ? Date.parse(recentClosed[0].closed_at) : 0;
    const cooldownUntil = lastClosedAt ? lastClosedAt + lossCooldownMinutes * 60 * 1000 : 0;
    const breakerMetrics = {
      strategy_config: {
        circuit_breaker: true,
        kst_day_start: kstDayStartUtc.toISOString(),
        daily_net_pnl_usd: roundTo(dailyNetPnl, 6),
        daily_loss_limit_usd: roundTo(dailyLossLimitUsd, 6),
        daily_loss_limit_pct: dailyLossLimitPct,
        consecutive_losses: consecutiveLosses,
        max_consecutive_losses: maxConsecutiveLosses,
        loss_cooldown_minutes: lossCooldownMinutes,
        cooldown_until: cooldownUntil ? new Date(cooldownUntil).toISOString() : null,
      },
    };
    if (dailyNetPnl <= -dailyLossLimitUsd) {
      await insertRejected(signal, `일일 손실 회로차단: ${dailyNetPnl.toFixed(2)} USDT / 한도 -${dailyLossLimitUsd.toFixed(2)} USDT (한국시간 자정까지)`, breakerMetrics);
      return Response.json({ ok: true, skipped: "daily loss circuit breaker", circuit_breaker: breakerMetrics.strategy_config });
    }
    if (consecutiveLosses >= maxConsecutiveLosses && Date.now() < cooldownUntil) {
      const remainingMinutes = Math.ceil((cooldownUntil - Date.now()) / 60000);
      await insertRejected(signal, `연속 손실 회로차단: ${consecutiveLosses}연패 / ${maxConsecutiveLosses}회, 재개까지 약 ${remainingMinutes}분`, breakerMetrics);
      return Response.json({ ok: true, skipped: "consecutive loss circuit breaker", circuit_breaker: breakerMetrics.strategy_config });
    }

    // 6-3. 방향별 회로차단기: 반대 방향은 계속 허용하고, 부진한 LONG 또는 SHORT만 잠시 중단한다.
    const directionWindow = recentClosed.filter((x: any) => x.side === signal.side).slice(0, 10);
    const directionPnls = directionWindow.map((x: any) => Number(x.net_pnl_usd));
    const directionWins = directionPnls.filter((x: number) => x > 0);
    const directionLosses = directionPnls.filter((x: number) => x < 0);
    const directionGrossProfit = directionWins.reduce((sum: number, x: number) => sum + x, 0);
    const directionGrossLoss = -directionLosses.reduce((sum: number, x: number) => sum + x, 0);
    const directionProfitFactor = directionGrossLoss > 0 ? directionGrossProfit / directionGrossLoss : (directionGrossProfit > 0 ? 9 : 1);
    const directionExpectancy = directionPnls.length ? directionPnls.reduce((sum: number, x: number) => sum + x, 0) / directionPnls.length : 0;
    let directionConsecutiveLosses = 0;
    for (const pnl of directionPnls) {
      if (pnl < 0) directionConsecutiveLosses++;
      else break;
    }
    const directionMinSamples = Number(state.direction_min_samples ?? 8);
    const directionProfitFactorFloor = Number(state.direction_profit_factor_floor ?? 0.70);
    const directionMaxConsecutiveLosses = Number(state.direction_max_consecutive_losses ?? 3);
    const directionCooldownMinutes = Number(state.direction_cooldown_minutes ?? 360);
    const directionLastClosedAt = directionWindow[0]?.closed_at ? Date.parse(directionWindow[0].closed_at) : 0;
    const directionCooldownUntil = directionLastClosedAt ? directionLastClosedAt + directionCooldownMinutes * 60 * 1000 : 0;
    const latestDirectionWasLoss = directionPnls.length > 0 && directionPnls[0] < 0;
    const directionPersistentlyWeak = directionPnls.length >= directionMinSamples && directionExpectancy < 0 && directionProfitFactor < directionProfitFactorFloor;
    const directionLossStreak = directionConsecutiveLosses >= directionMaxConsecutiveLosses;
    if (latestDirectionWasLoss && (directionPersistentlyWeak || directionLossStreak) && Date.now() < directionCooldownUntil) {
      const remainingMinutes = Math.ceil((directionCooldownUntil - Date.now()) / 60000);
      const sideLabel = signal.side === "long" ? "LONG" : "SHORT";
      const directionMetrics = {
        strategy_config: {
          direction_circuit_breaker: true,
          blocked_side: signal.side,
          sample_size: directionPnls.length,
          expectancy_usd: roundTo(directionExpectancy, 6),
          profit_factor: roundTo(directionProfitFactor, 4),
          profit_factor_floor: directionProfitFactorFloor,
          consecutive_losses: directionConsecutiveLosses,
          max_consecutive_losses: directionMaxConsecutiveLosses,
          cooldown_until: new Date(directionCooldownUntil).toISOString(),
        },
      };
      await insertRejected(signal, `${sideLabel} 방향 임시중단: 기대값 ${directionExpectancy.toFixed(2)} USDT, PF ${directionProfitFactor.toFixed(2)}, ${directionConsecutiveLosses}연패, 재개까지 약 ${remainingMinutes}분`, directionMetrics);
      return Response.json({ ok: true, skipped: "direction circuit breaker", direction: directionMetrics.strategy_config });
    }

    const usedTotal = open.reduce((s: number, x: any) => s + Number(x.margin_usd || 0), 0);
    const usedSymbol = open.filter((x: any) => x.symbol === signal.symbol).reduce((s: number, x: any) => s + Number(x.margin_usd || 0), 0);
    const totalCapUsd = equity * (Number(state.total_margin_cap_pct ?? 70) / 100);
    const perSymbolCapUsd = equity * (Number(state.per_symbol_margin_cap_pct ?? 25) / 100);
    const remainingTotal = Math.max(0, totalCapUsd - usedTotal);
    const remainingSymbol = Math.max(0, perSymbolCapUsd - usedSymbol);

    const leverage = Math.max(1, Math.min(Number(signal.leverage || 1), Number(state.max_leverage)));

    // 6-4. 최근 실전 성과 기반 동적 사이징(6순위): 같은 유형(전술/스윙)의 최근 청산 20건 승률을 보고
    //      잘 맞고 있으면 리스크를 살짝 늘리고, 부진하면 줄인다. 표본 8건 미만이면 아직 못 믿으니 1.0 유지.
    let riskMultiplier = 1.0;
    try {
      const recent = await db(`real_trades?status=eq.closed&signal_type=eq.${signal.signal_type}&side=eq.${signal.side}&select=net_pnl_usd&order=closed_at.desc&limit=20`);
      const closed = (recent || []).filter((x: any) => x.net_pnl_usd != null).map((x: any) => Number(x.net_pnl_usd));
      if (closed.length >= 8) {
        const grossProfit = closed.filter((x: number) => x > 0).reduce((a: number, b: number) => a + b, 0);
        const grossLoss = -closed.filter((x: number) => x < 0).reduce((a: number, b: number) => a + b, 0);
        const expectancy = closed.reduce((a: number, b: number) => a + b, 0) / closed.length;
        const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? 9 : 1);
        const winRate = closed.filter((x: number) => x > 0).length / closed.length;
        riskMultiplier = expectancy < 0 && profitFactor < 0.8 ? 0.55 : expectancy < 0 || profitFactor < 1 ? 0.75 : profitFactor >= 1.5 && winRate >= 0.5 ? 1.1 : 1.0;
      }
    } catch (e) {
      console.error("recent performance lookup failed:", e instanceof Error ? e.message : String(e));
    }

    // 6-5. 리스크 기반 담보금 계산: "이 한 건에서 잃어도 되는 금액(잔고의 N% × 성과배수)" ÷ (손절폭% × 레버리지)
    //      손절폭이 넓을수록, 레버리지가 낮을수록 같은 리스크금액에 담보금이 커진다.
    const entryForRisk = Number(signal.entry_price);
    const stopPct = Math.max(0.001, Math.abs(entryForRisk - Number(signal.invalidation_price)) / entryForRisk);
    const riskPct = (signal.signal_type === "tactical" ? Number(state.tactical_risk_pct ?? 1.0) : Number(state.swing_risk_pct ?? 1.5)) * riskMultiplier;
    const riskUsd = equity * (riskPct / 100);
    const rawMargin = riskUsd / (stopPct * leverage);

    let marginUsd = Math.min(rawMargin, remainingTotal, remainingSymbol);
    if (state.test_mode) marginUsd = Math.min(marginUsd, Number(state.test_margin_usd || marginUsd));
    if (!(marginUsd > 0)) {
      await insertRejected(signal, "담보 여유 없음");
      return Response.json({ ok: true, skipped: "no margin headroom" });
    }

    // 7. 계약 정밀도 조회 후 수량 계산
    const bxSymbol = signal.symbol + "-USDT";
    const contract = await getContract(bxSymbol);
    const qtyPrecision = Number(contract.quantityPrecision ?? 3);
    const pricePrecision = Number(contract.pricePrecision ?? 2);
    const minQty = Number(contract.tradeMinQuantity ?? 0);
    const minUsdt = Number(contract.tradeMinUSDT ?? 2);
    const maxLev = signal.side === "long" ? Number(contract.maxLongLeverage ?? leverage) : Number(contract.maxShortLeverage ?? leverage);
    const finalLeverage = Math.max(1, Math.min(leverage, maxLev));

    const entry = Number(signal.entry_price);
    const notional = marginUsd * finalLeverage;
    const rawQty = notional / entry;
    const quantity = roundDown(rawQty, qtyPrecision);
    if (quantity <= 0 || quantity < minQty || quantity * entry < minUsdt) {
      await insertRejected(signal, "최소 주문 수량 미달");
      return Response.json({ ok: true, skipped: "below exchange minimum order size" });
    }
    const baseStopPrice = roundTo(Number(signal.invalidation_price), pricePrecision);
    const baseTargetPrice = roundTo(Number(signal.target_price), pricePrecision);
    let stopPrice = baseStopPrice, targetPrice = baseTargetPrice;
    const positionSide = signal.side === "long" ? "LONG" : "SHORT";
    const side = signal.side === "long" ? "BUY" : "SELL";

    // 7-1. MFE/MAE 기반 적응형 손절·익절:
    // 같은 전략 세대·유형·방향에서 측정 표본 12건 및 승리 5건이 확보되기 전에는 기존 가격을 그대로 쓴다.
    let adaptiveLevelsApplied = false;
    let adaptiveLevelMeta: Record<string, any> = {
      enabled: !!state.mfe_mae_optimization_enabled,
      sample_size: 0,
      winner_sample_size: 0,
      base_stop_price: baseStopPrice,
      base_target_price: baseTargetPrice,
    };
    if (state.mfe_mae_optimization_enabled !== false) {
      try {
        const epoch = encodeURIComponent(String(signal.strategy_epoch || DEFAULT_STRATEGY_EPOCH));
        const measuredRows = (await db(`real_trades?status=eq.closed&signal_type=eq.${signal.signal_type}&side=eq.${signal.side}&strategy_epoch=eq.${epoch}&measurement_updated_at=not.is.null&last_mark_price=not.is.null&select=net_pnl_usd,mfe_pct,mae_pct&order=closed_at.desc&limit=30`)) || [];
        const validMeasured = measuredRows.filter((x: any) => Number.isFinite(Number(x.mfe_pct)) && Number.isFinite(Number(x.mae_pct)));
        const winners = validMeasured.filter((x: any) => Number(x.net_pnl_usd) > 0);
        const minSamples = Number(state.mfe_mae_min_samples ?? 12);
        const minWins = Number(state.mfe_mae_min_wins ?? 5);
        adaptiveLevelMeta = { ...adaptiveLevelMeta, sample_size: validMeasured.length, winner_sample_size: winners.length, min_samples: minSamples, min_wins: minWins };
        if (validMeasured.length >= minSamples && winners.length >= minWins) {
          const winnerAdverse = winners.map((x: any) => Math.abs(Math.min(0, Number(x.mae_pct))) / 100);
          const winnerFavorable = winners.map((x: any) => Math.max(0, Number(x.mfe_pct)) / 100).filter((x: number) => x > 0);
          const baseStopDistancePct = Math.abs(entry - baseStopPrice) / entry;
          const baseTargetDistancePct = Math.abs(baseTargetPrice - entry) / entry;
          const adverseP75 = percentile(winnerAdverse, 0.75);
          const favorableP50 = percentile(winnerFavorable, 0.50);
          const stopMinFactor = Number(state.adaptive_stop_min_factor ?? 0.80);
          const targetMinFactor = Number(state.adaptive_target_min_factor ?? 0.90);
          const targetMaxFactor = Number(state.adaptive_target_max_factor ?? 1.20);
          // 리스크가 커지지 않도록 손절은 기존보다 절대 넓히지 않는다.
          const stopFactor = clamp((adverseP75 * 1.15) / Math.max(0.000001, baseStopDistancePct), stopMinFactor, 1.0);
          const targetFactor = clamp((favorableP50 * 0.85) / Math.max(0.000001, baseTargetDistancePct), targetMinFactor, targetMaxFactor);
          const adaptiveStopDistance = Math.abs(entry - baseStopPrice) * stopFactor;
          const adaptiveTargetDistance = Math.abs(baseTargetPrice - entry) * targetFactor;
          stopPrice = roundTo(entry + (signal.side === "long" ? -adaptiveStopDistance : adaptiveStopDistance), pricePrecision);
          targetPrice = roundTo(entry + (signal.side === "long" ? adaptiveTargetDistance : -adaptiveTargetDistance), pricePrecision);
          adaptiveLevelsApplied = stopPrice !== baseStopPrice || targetPrice !== baseTargetPrice;
          adaptiveLevelMeta = {
            ...adaptiveLevelMeta, applied: adaptiveLevelsApplied,
            winner_mae_p75_pct: roundTo(adverseP75 * 100, 4),
            winner_mfe_p50_pct: roundTo(favorableP50 * 100, 4),
            stop_factor: roundTo(stopFactor, 4), target_factor: roundTo(targetFactor, 4),
            adaptive_stop_price: stopPrice, adaptive_target_price: targetPrice,
          };
        }
      } catch (adaptiveError) {
        adaptiveLevelMeta = { ...adaptiveLevelMeta, error: adaptiveError instanceof Error ? adaptiveError.message : String(adaptiveError) };
        console.error("MFE/MAE adaptive level lookup failed:", adaptiveLevelMeta.error);
      }
    }

    // 7-1. 비용 차감 기대수익 게이트:
    // 실제 최근 수수료율과 측정된 슬리피지를 우선 사용하고, 표본이 없으면 보수적 기본값을 적용한다.
    let feeRate = 0.001003, oneWaySlippageRate = 0.0004;
    try {
      const costRows = await db("real_trades?status=eq.closed&notional_usd=gt.0&select=fee_usd,notional_usd,slippage_pct&order=closed_at.desc&limit=50");
      const feeRows = (costRows || []).filter((x: any) => Number(x.fee_usd) >= 0 && Number(x.notional_usd) > 0);
      const feeNotional = feeRows.reduce((sum: number, x: any) => sum + Number(x.notional_usd), 0);
      if (feeRows.length >= 8 && feeNotional > 0) {
        feeRate = clamp(feeRows.reduce((sum: number, x: any) => sum + Number(x.fee_usd), 0) / feeNotional, 0.0008, 0.0015);
      }
      const slips = feeRows.map((x: any) => Math.abs(Number(x.slippage_pct || 0)) / 100).filter((x: number) => x > 0).sort((x: number, y: number) => x - y);
      if (slips.length >= 8) oneWaySlippageRate = clamp(slips[Math.floor((slips.length - 1) * 0.75)], 0.0001, 0.0015);
    } catch (costError) {
      console.error("cost history lookup failed:", costError instanceof Error ? costError.message : String(costError));
    }
    const expectedFeeUsdBeforeEntry = notional * feeRate;
    const expectedSlippageUsd = notional * oneWaySlippageRate * 2;
    const expectedTradingCostUsd = expectedFeeUsdBeforeEntry + expectedSlippageUsd;
    const grossTargetUsdBeforeEntry = notional * Math.abs(targetPrice - entry) / entry;
    const grossStopUsdBeforeEntry = notional * Math.abs(entry - stopPrice) / entry;
    const expectedNetProfitBeforeEntry = grossTargetUsdBeforeEntry - expectedTradingCostUsd;
    const expectedNetLossBeforeEntry = grossStopUsdBeforeEntry + expectedTradingCostUsd;
    const expectedNetRrBeforeEntry = expectedNetProfitBeforeEntry / Math.max(0.000001, expectedNetLossBeforeEntry);
    const minimumNetRr = signal.signal_type === "tactical" ? 1.35 : 1.50;
    const minimumCostCoverage = 3.0;
    const costCoverage = grossTargetUsdBeforeEntry / Math.max(0.000001, expectedTradingCostUsd);
    const economics = {
      expected_fee_usd: roundTo(expectedFeeUsdBeforeEntry, 6),
      expected_net_profit_usd: roundTo(expectedNetProfitBeforeEntry, 6),
      expected_net_rr: roundTo(expectedNetRrBeforeEntry, 4),
      strategy_config: {
        risk_multiplier: riskMultiplier, risk_pct: riskPct, stop_pct: stopPct,
        fee_rate: feeRate, one_way_slippage_rate: oneWaySlippageRate,
        expected_trading_cost_usd: roundTo(expectedTradingCostUsd, 6),
        cost_coverage: roundTo(costCoverage, 3), minimum_net_rr: minimumNetRr, mfe_mae_adaptive: adaptiveLevelMeta,
      },
    };
    if (!(expectedNetProfitBeforeEntry > 0) || expectedNetRrBeforeEntry < minimumNetRr || costCoverage < minimumCostCoverage) {
      const reason = `비용 차감 기대수익 부족: 순손익비 ${expectedNetRrBeforeEntry.toFixed(2)}R/${minimumNetRr.toFixed(2)}R, 비용커버 ${costCoverage.toFixed(2)}배/${minimumCostCoverage.toFixed(2)}배`;
      await insertRejected(signal, reason, economics);
      return Response.json({ ok: true, skipped: "low fee-adjusted expectancy", economics });
    }

    // 8. 레버리지 설정 후 시장가 진입 (손절/익절은 부착 파라미터가 조용히 실패하는 사례가 확인되어
    //    더 이상 진입 주문에 첨부하지 않고, 진입 체결 후 완전히 독립된 주문으로 따로 걱고 각각
    //    성공 여부를 직접 확인한다.)
    await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/leverage", { symbol: bxSymbol, side: positionSide, leverage: finalLeverage });

    const entrySubmittedAt = new Date();
    const order = await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
      symbol: bxSymbol,
      side,
      positionSide,
      type: "MARKET",
      quantity,
      clientOrderId: `ciai${signal.id}`,
      recvWindow: 5000,
    });

    const orderId = String(order?.orderID ?? order?.orderId ?? order?.order?.orderID ?? order?.order?.orderId ?? "");
    let actualFillPrice = Number(order?.avgPrice ?? order?.order?.avgPrice ?? 0);
    let actualExecutedQty = Number(order?.executedQty ?? order?.order?.executedQty ?? 0);
    if (orderId && (!(actualFillPrice > 0) || !(actualExecutedQty > 0))) {
      try {
        const rawFill = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/trade/order", { symbol: bxSymbol, orderId, recvWindow: 5000 });
        const fill = rawFill?.order ?? rawFill;
        actualFillPrice = Number(fill?.avgPrice ?? actualFillPrice);
        actualExecutedQty = Number(fill?.executedQty ?? actualExecutedQty);
      } catch (fillError) {
        console.error("entry fill lookup failed:", bxSymbol, fillError instanceof Error ? fillError.message : String(fillError));
      }
    }
    if (!(actualFillPrice > 0)) actualFillPrice = entry;
    if (!(actualExecutedQty > 0)) actualExecutedQty = quantity;
    const entryFilledAt = new Date();
    const effectiveNotional = roundTo(actualExecutedQty * actualFillPrice, 2);
    const estimatedRoundTripFee = roundTo(effectiveNotional * feeRate, 6);
    const estimatedSlippageCost = effectiveNotional * oneWaySlippageRate * 2;
    const grossTargetUsd = effectiveNotional * Math.abs(targetPrice - actualFillPrice) / actualFillPrice;
    const grossStopUsd = effectiveNotional * Math.abs(actualFillPrice - stopPrice) / actualFillPrice;
    const expectedNetProfitUsd = grossTargetUsd - estimatedRoundTripFee - estimatedSlippageCost;
    const expectedNetRr = expectedNetProfitUsd / Math.max(0.000001, grossStopUsd + estimatedRoundTripFee + estimatedSlippageCost);

    // 8-1. 손절/익절을 독립 조건부 주문으로 부착. closePosition 방식이 이 계정 환경에서
    //      "parameter quantity or stopPrice is must" 오류로 계속 실패하는 게 확인되어,
    //      더 안정적인 실제 수량 지정 방식으로 건다 (헤지 모드에서는 positionSide만으로
    //      이미 포지션 축소 방향이 결정되므로 reduceOnly는 보내지 않는다).
    const closeSide = signal.side === "long" ? "SELL" : "BUY";
    let slAttached = false, tpAttached = false, slError = "", tpError = "";
    let stopCreatedAt: string | null = null, targetCreatedAt: string | null = null;
    try {
      await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
        symbol: bxSymbol, side: closeSide, positionSide, type: "STOP_MARKET",
        stopPrice, quantity, workingType: "MARK_PRICE", recvWindow: 5000,
      });
      slAttached = true;
      stopCreatedAt = new Date().toISOString();
    } catch (e) { slError = e instanceof Error ? e.message : String(e); console.error("STOP_MARKET attach failed:", bxSymbol, slError); }
    try {
      await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
        symbol: bxSymbol, side: closeSide, positionSide, type: "TAKE_PROFIT_MARKET",
        stopPrice: targetPrice, quantity, workingType: "MARK_PRICE", recvWindow: 5000,
      });
      tpAttached = true;
      targetCreatedAt = new Date().toISOString();
    } catch (e) { tpError = e instanceof Error ? e.message : String(e); console.error("TAKE_PROFIT_MARKET attach failed:", bxSymbol, tpError); }

    // 손절이 안 걸리면 무방비 레버리지 포지션을 남겨둘 수 없으니 즉시 시장가로 안전 청산한다.
    const lastProtectionAt = targetCreatedAt || stopCreatedAt;
    const protectiveLatencyMs = lastProtectionAt ? Math.max(0, Date.parse(lastProtectionAt) - entryFilledAt.getTime()) : null;

    if (!slAttached) {
      try {
        await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
          symbol: bxSymbol, side: closeSide, positionSide, type: "MARKET", quantity, recvWindow: 5000,
        });
      } catch (e) { console.error("EMERGENCY CLOSE FAILED after stop-loss attach failure:", bxSymbol, e instanceof Error ? e.message : String(e)); }
      await insertRejected(signal, "손절 주문 부착 실패로 안전 청산: " + slError.slice(0, 300));
      return Response.json({ ok: false, error: "stop-loss attach failed, position closed for safety" }, { status: 502 });
    }

    await db("real_trades", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        signal_id: signal.id, symbol: signal.symbol, bingx_symbol: bxSymbol,
        side: signal.side, signal_type: signal.signal_type, status: "open",
        test_mode: !!state.test_mode, margin_usd: marginUsd, leverage: finalLeverage,
        notional_usd: effectiveNotional, quantity: actualExecutedQty, entry_price: actualFillPrice,
        stop_price: stopPrice, target_price: targetPrice,
        base_stop_price: baseStopPrice, base_target_price: baseTargetPrice,
        adaptive_levels_applied: adaptiveLevelsApplied, bingx_order_id: orderId,
        strategy_epoch: signal.strategy_epoch || DEFAULT_STRATEGY_EPOCH,
        collector_version: Number(signal.collector_version || 27), executor_version: EXECUTOR_VERSION,
        signal_model_version: signal.signal_model_version || "signal_v27",
        signal_price: entry, submitted_price: entry,
        slippage_pct: (actualFillPrice / entry - 1) * 100 * (signal.side === "long" ? 1 : -1),
        entry_submitted_at: entrySubmittedAt.toISOString(), entry_filled_at: entryFilledAt.toISOString(),
        stop_order_created_at: stopCreatedAt, target_order_created_at: targetCreatedAt,
        protective_latency_ms: protectiveLatencyMs, protective_verified: slAttached && tpAttached,
        expected_fee_usd: estimatedRoundTripFee, expected_net_profit_usd: expectedNetProfitUsd,
        expected_net_rr: expectedNetRr,
        strategy_config: { risk_multiplier: riskMultiplier, risk_pct: riskPct, stop_pct: stopPct, fee_rate: feeRate, one_way_slippage_rate: oneWaySlippageRate, expected_trading_cost_usd: roundTo(estimatedRoundTripFee + estimatedSlippageCost, 6), minimum_net_rr: minimumNetRr, mfe_mae_adaptive: adaptiveLevelMeta },
      }),
    });

    return Response.json({ ok: true, order_id: orderId, quantity: actualExecutedQty, fill_price: actualFillPrice, slippage_pct: (actualFillPrice / entry - 1) * 100 * (signal.side === "long" ? 1 : -1), margin_usd: marginUsd, leverage: finalLeverage, protective_latency_ms: protectiveLatencyMs });
  } catch (e) {
    console.error("bingx-order-execute failed:", e instanceof Error ? e.message : String(e));
    try { await insertRejected(signal, "실행 오류: " + (e instanceof Error ? e.message : String(e))); } catch { /* ignore */ }
    return Response.json({ ok: false, error: "order execution failed" }, { status: 502 });
  }
});
