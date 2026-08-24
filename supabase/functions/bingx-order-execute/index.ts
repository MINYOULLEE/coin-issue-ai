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

// real_trades.status='open'인데 실제 BingX 포지션은 이미 손절/익절로 종료된 경우를
// 찾아 'closed'로 정리한다. 이게 없으면 종료된 포지션이 동시 포지션 한도를 영원히
// 차지해서, 초기 몇 건 이후로 신규 진입이 전부 거부되는 문제가 생긴다.
async function reconcileOpenTrades(): Promise<void> {
  let liveKeys = new Set<string>();
  try {
    const positions = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/positions", { recvWindow: 5000 });
    const rows = Array.isArray(positions) ? positions : (positions?.positions || []);
    for (const p of rows) {
      const amt = Number(p.positionAmt ?? p.positionAmount ?? 0);
      if (Math.abs(amt) <= 0) continue;
      const symbol = String(p.symbol || ""), side = String(p.positionSide || (amt >= 0 ? "LONG" : "SHORT"));
      liveKeys.add(symbol + "|" + side);
    }
  } catch (e) {
    // 포지션 조회 자체가 실패하면 잘못 닫아버릴 위험이 있으니 이번 실행은 정산을 건너뛴다.
    console.error("reconcile: position fetch failed, skipping:", e instanceof Error ? e.message : String(e));
    return;
  }
  let openRows: any[] = [];
  try {
    openRows = await db("real_trades?status=eq.open&select=id,symbol,bingx_symbol,side,created_at");
  } catch (e) {
    console.error("reconcile: failed to load open trades:", e instanceof Error ? e.message : String(e));
    return;
  }
  for (const row of openRows) {
    const posSide = row.side === "long" ? "LONG" : "SHORT";
    if (liveKeys.has(row.bingx_symbol + "|" + posSide)) continue;
    let netPnl: number | null = null, feeUsd: number | null = null;
    try {
      const startMs = Date.parse(row.created_at) - 60000;
      const income = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/user/income", { symbol: row.bingx_symbol, startTime: startMs, limit: 200 });
      const list = Array.isArray(income) ? income : [];
      const relevant = list.filter((x: any) => ["REALIZED_PNL", "TRADING_FEE", "FUNDING_FEE"].includes(x.incomeType));
      if (relevant.length) {
        // 실현손익/수수료(체결)/펀딩비를 따로 합산한다. 수수료는 수동 시장가 청산이든 손절·익절 자동
        // 체결이든 거래소 income 기록에 실제로 찍힌 값을 그대로 쓰므로 종료 방식과 무관하게 정확하다.
        const realizedPnl = relevant.filter((x: any) => x.incomeType === "REALIZED_PNL").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const tradingFee = relevant.filter((x: any) => x.incomeType === "TRADING_FEE").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        const fundingFee = relevant.filter((x: any) => x.incomeType === "FUNDING_FEE").reduce((s: number, x: any) => s + Number(x.income || 0), 0);
        netPnl = realizedPnl + tradingFee + fundingFee;
        feeUsd = -(tradingFee + fundingFee); // BingX는 수수료를 음수로 내려주므로 부호를 뒤집어 "낸 비용"으로 저장
      }
    } catch (e) {
      console.error("reconcile: income fetch failed for", row.bingx_symbol, e instanceof Error ? e.message : String(e));
    }
    try {
      await db("real_trades?id=eq." + row.id, {
        method: "PATCH",
        body: JSON.stringify({ status: "closed", closed_at: new Date().toISOString(), net_pnl_usd: netPnl, fee_usd: feeUsd, close_reason: "거래소 포지션 종료 확인(자동 정산)" }),
      });
    } catch (e) {
      console.error("reconcile: failed to close real_trades row", row.id, e instanceof Error ? e.message : String(e));
    }
  }
}

// coin-collector의 20분 재점검에서 손절/익절이 바뀌었을 때 호출된다. 기존 SL/TP 조건부 주문을
// 취소하고 새 가격으로 다시 등록한다. closePosition을 써서 수량 오차와 무관하게 포지션 전체를 정리한다.
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
    for (const row of rows) {
      const bxSymbol = String(row.bingx_symbol), positionSide = row.side === "long" ? "LONG" : "SHORT", closeSide = row.side === "long" ? "SELL" : "BUY";
      try {
        const openOrders = await fetchSigned(API_KEY, SECRET_KEY, "GET", "/openApi/swap/v2/trade/openOrders", { symbol: bxSymbol, recvWindow: 5000 });
        const list = Array.isArray(openOrders) ? openOrders : (openOrders?.orders || []);
        const mine = list.filter((o: any) => String(o.positionSide) === positionSide);
        const hasSl = mine.some((o: any) => String(o.type) === "STOP_MARKET");
        const hasTp = mine.some((o: any) => String(o.type) === "TAKE_PROFIT_MARKET");
        if (hasSl && hasTp) { results.push({ id: row.id, symbol: row.symbol, skipped: "already protected" }); continue; }

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

  // 이미 열려있는데 손절/익절이 안 걸려있는 것으로 확인된 실거래에 즉시 조건부 주문을 걸어준다.
  if (signal?.action === "protect") return await handleProtect(signal);

  // 신호(trade_signals)가 성공/실패/보합으로 종료될 때마다 호출된다. 새 주문 없이 신호만
  // 끝나는 경우(우리 쪽 시뮬레이션이 먼저 손절/익절을 감지한 경우 등)에도 실거래
  // 포지션이 실제로 종료됐는지 즉시 확인해서 real_trades를 최신 상태로 맞춘다. 기존에는
  // 새 주문이 들어올 때만 정산이 돌아서, 새 신호가 한동안 없으면 이미 끝난 실거래가
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
    //      이 경우 새 포지션을 만들지 않고 기존 포지션에 평단가로 합쳐버리는데, 우리 시스템은
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

    const usedTotal = open.reduce((s: number, x: any) => s + Number(x.margin_usd || 0), 0);
    const usedSymbol = open.filter((x: any) => x.symbol === signal.symbol).reduce((s: number, x: any) => s + Number(x.margin_usd || 0), 0);
    const totalCapUsd = equity * (Number(state.total_margin_cap_pct ?? 70) / 100);
    const perSymbolCapUsd = equity * (Number(state.per_symbol_margin_cap_pct ?? 25) / 100);
    const remainingTotal = Math.max(0, totalCapUsd - usedTotal);
    const remainingSymbol = Math.max(0, perSymbolCapUsd - usedSymbol);

    const leverage = Math.max(1, Math.min(Number(signal.leverage || 1), Number(state.max_leverage)));

    // 6-2. 최근 실전 성과 기반 동적 사이징(6순위): 같은 유형(전술/스윙)의 최근 청산 20건 승률을 보고
    //      잘 맞고 있으면 리스크를 살짝 늘리고, 부진하면 줄인다. 표본 8건 미만이면 아직 못 믿으니 1.0 유지.
    let riskMultiplier = 1.0;
    try {
      const recent = await db(`real_trades?status=eq.closed&signal_type=eq.${signal.signal_type}&select=net_pnl_usd&order=closed_at.desc&limit=20`);
      const closed = (recent || []).filter((x: any) => x.net_pnl_usd != null);
      if (closed.length >= 8) {
        const winRate = closed.filter((x: any) => Number(x.net_pnl_usd) > 0).length / closed.length;
        riskMultiplier = winRate >= 0.6 ? 1.2 : winRate >= 0.5 ? 1.0 : winRate >= 0.35 ? 0.8 : 0.6;
      }
    } catch (e) {
      console.error("recent performance lookup failed:", e instanceof Error ? e.message : String(e));
    }

    // 6-3. 리스크 기반 담보금 계산: "이 한 건에서 잃어도 되는 금액(잔고의 N% × 성과배수)" ÷ (손절폭% × 레버리지)
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
    const stopPrice = roundTo(Number(signal.invalidation_price), pricePrecision);
    const targetPrice = roundTo(Number(signal.target_price), pricePrecision);
    const positionSide = signal.side === "long" ? "LONG" : "SHORT";
    const side = signal.side === "long" ? "BUY" : "SELL";

    // 8. 레버리지 설정 후 시장가 진입 (손절/익절은 부착 파라미터가 조용히 실패하는 사례가 확인되어
    //    더 이상 진입 주문에 첨부하지 않고, 진입 체결 후 완전히 독립된 주문으로 따로 걸고 각각
    //    성공 여부를 직접 확인한다.)
    await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/leverage", { symbol: bxSymbol, side: positionSide, leverage: finalLeverage });

    const order = await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
      symbol: bxSymbol,
      side,
      positionSide,
      type: "MARKET",
      quantity,
      clientOrderId: `ciai${signal.id}`,
      recvWindow: 5000,
    });

    // 8-1. 손절/익절을 독립 조건부 주문으로 부착. closePosition 방식이 이 계정 환경에서
    //      "parameter quantity or stopPrice is must" 오류로 계속 실패하는 게 확인되어,
    //      더 안정적인 실제 수량 지정 방식으로 건다 (헤지 모드에서는 positionSide만으로
    //      이미 포지션 축소 방향이 결정되므로 reduceOnly는 보내지 않는다).
    const closeSide = signal.side === "long" ? "SELL" : "BUY";
    let slAttached = false, tpAttached = false, slError = "", tpError = "";
    try {
      await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
        symbol: bxSymbol, side: closeSide, positionSide, type: "STOP_MARKET",
        stopPrice, quantity, workingType: "MARK_PRICE", recvWindow: 5000,
      });
      slAttached = true;
    } catch (e) { slError = e instanceof Error ? e.message : String(e); console.error("STOP_MARKET attach failed:", bxSymbol, slError); }
    try {
      await fetchSigned(API_KEY, SECRET_KEY, "POST", "/openApi/swap/v2/trade/order", {
        symbol: bxSymbol, side: closeSide, positionSide, type: "TAKE_PROFIT_MARKET",
        stopPrice: targetPrice, quantity, workingType: "MARK_PRICE", recvWindow: 5000,
      });
      tpAttached = true;
    } catch (e) { tpError = e instanceof Error ? e.message : String(e); console.error("TAKE_PROFIT_MARKET attach failed:", bxSymbol, tpError); }

    // 손절이 안 걸리면 무방비 레버리지 포지션을 남겨둘 수 없으니 즉시 시장가로 안전 청산한다.
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
        notional_usd: roundTo(quantity * entry, 2), quantity, entry_price: entry,
        stop_price: stopPrice, target_price: targetPrice,
        bingx_order_id: String(order?.orderID ?? order?.orderId ?? order?.order?.orderID ?? order?.order?.orderId ?? ""),
      }),
    });

    return Response.json({ ok: true, order_id: String(order?.orderID ?? order?.orderId ?? ""), quantity, margin_usd: marginUsd, leverage: finalLeverage });
  } catch (e) {
    console.error("bingx-order-execute failed:", e instanceof Error ? e.message : String(e));
    try { await insertRejected(signal, "실행 오류: " + (e instanceof Error ? e.message : String(e))); } catch { /* ignore */ }
    return Response.json({ ok: false, error: "order execution failed" }, { status: 502 });
  }
});
