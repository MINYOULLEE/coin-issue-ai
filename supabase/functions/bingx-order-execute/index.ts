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
      const url = method === "GET"
        ? `${base}${path}?${canonical}&signature=${signature}`
        : `${base}${path}`;
      const body = method === "GET" ? undefined : `${canonical}&signature=${signature}`;
      const res = await fetch(url, {
        method,
        headers: {
          "X-BX-APIKEY": apiKey,
          "X-SOURCE-KEY": "BX-AI-SKILL",
          ...(method !== "GET" ? { "Content-Type": "application/x-www-form-urlencoded" } : {}),
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
  if (!r.ok) throw new Error("db " + path + " " + r.status + " " + await r.text());
  return r.status === 204 ? null : await r.json();
}

async function insertRejected(signal: any, reason: string) {
  try {
    await db("real_trades", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        signal_id: signal.id, symbol: signal.symbol, bingx_symbol: signal.symbol + "-USDT",
        side: signal.side, signal_type: signal.signal_type, status: "rejected",
        test_mode: true, margin_usd: 0, leverage: 0, notional_usd: 0, quantity: 0,
        entry_price: signal.entry_price, stop_price: signal.invalidation_price, target_price: signal.target_price,
        reject_reason: reason.slice(0, 500),
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

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return Response.json({ ok: false, error: "POST required" }, { status: 405 });
  if (!INTERNAL_KEY || req.headers.get("x-internal-key") !== INTERNAL_KEY) {
    return Response.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let signal: any;
  try { signal = await req.json(); } catch { return Response.json({ ok: false, error: "invalid json" }, { status: 400 }); }

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

    // 6. 현재 열려있는 실거래 포지션 기준으로 위험 한도 계산
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
    const usedTotal = open.reduce((s: number, x: any) => s + Number(x.margin_usd || 0), 0);
    const usedSymbol = open.filter((x: any) => x.symbol === signal.symbol).reduce((s: number, x: any) => s + Number(x.margin_usd || 0), 0);
    const remainingTotal = Math.max(0, Number(state.total_margin_cap_usd) - usedTotal);
    const remainingSymbol = Math.max(0, Number(state.per_symbol_margin_cap_usd) - usedSymbol);

    let marginUsd: number;
    if (state.test_mode) {
      marginUsd = Math.min(Number(state.test_margin_usd), remainingTotal, remainingSymbol);
    } else {
      marginUsd = Math.min(Number(signal.margin_usd || 0), remainingTotal, remainingSymbol);
    }
    if (!(marginUsd > 0)) {
      await insertRejected(signal, "담보 여유 없음");
      return Response.json({ ok: true, skipped: "no margin headroom" });
    }
    const leverage = Math.max(1, Math.min(Number(signal.leverage || 1), Number(state.max_leverage)));

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
    const stopPrice = roundTo(Number(signal.invalidation_price), pricePrecision);
    const targetPrice = roundTo(Number(signal.target_price), pricePrecision);
    const positionSide = signal.side === "long" ? "LONG" : "SHORT";
    const side = signal.side === "long" ? "BUY" : "SELL";

    // 8. 레버리지 설정 후 주문 전송 (시장가 진입 + 손절/익절 동시 첨부)
    await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/leverage", { symbol: bxSymbol, side: positionSide, leverage: finalLeverage });

    const order = await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
      symbol: bxSymbol,
      side,
      positionSide,
      type: "MARKET",
      quantity,
      clientOrderId: `ciai${signal.id}`,
      stopLoss: JSON.stringify({ type: "STOP_MARKET", stopPrice, workingType: "MARK_PRICE" }),
      takeProfit: JSON.stringify({ type: "TAKE_PROFIT_MARKET", stopPrice: targetPrice, workingType: "MARK_PRICE" }),
      recvWindow: 5000,
    });

    await db("real_trades", {
      method: "POST",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify({
        signal_id: signal.id, symbol: signal.symbol, bingx_symbol: bxSymbol,
        side: signal.side, signal_type: signal.signal_type, status: "open",
        test_mode: !!state.test_mode, margin_usd: marginUsd, leverage: finalLeverage,
        notional_usd: roundTo(quantity * entry, 2), quantity, entry_price: entry,
        stop_price: stopPrice, target_price: targetPrice,
        bingx_order_id: String(order?.orderID ?? order?.orderId ?? ""),
      }),
    });

    return Response.json({ ok: true, order_id: String(order?.orderID ?? order?.orderId ?? ""), quantity, margin_usd: marginUsd, leverage: finalLeverage });
  } catch (e) {
    console.error("bingx-order-execute failed:", e instanceof Error ? e.message : String(e));
    try { await insertRejected(signal, "실행 오류: " + (e instanceof Error ? e.message : String(e))); } catch { /* ignore */ }
    return Response.json({ ok: false, error: "order execution failed" }, { status: 502 });
  }
});
