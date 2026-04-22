"""
Free Crypto & Stock Screener MCP
- 암호화폐 가격/OHLCV: yfinance (무료, API 키 불필요)
- 주식 스크리너: S&P 500 / NASDAQ 100 + yfinance info 병렬 조회
"""
import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("free-screener")

_SP500_CACHE:   list[str] = []
_NDX100_CACHE:  list[str] = []
_CACHE_TS: float = 0
_CACHE_TTL = 3600  # 1시간

_UA = {"User-Agent": "Mozilla/5.0"}


# ── 유틸 ───────────────────────────────────────────────────────────────────────

def _ok(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]

def _err(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"오류: {text}")]

def _fmt(v, d=2, suffix="") -> str:
    if v is None: return "N/A"
    return f"{v:,.{d}f}{suffix}"

def _fmt_large(v) -> str:
    if v is None: return "N/A"
    for u, dv in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(v) >= dv: return f"{v/dv:.2f}{u}"
    return f"{v:,.0f}"

def _pct(v) -> str:
    return "N/A" if v is None else f"{v*100:.2f}%"


# ── 유니버스 로더 ──────────────────────────────────────────────────────────────

def _load_sp500() -> list[str]:
    global _SP500_CACHE, _CACHE_TS
    if _SP500_CACHE and time.time() - _CACHE_TS < _CACHE_TTL:
        return _SP500_CACHE
    html = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers=_UA, timeout=10,
    ).text
    df = pd.read_html(io.StringIO(html))[0]
    tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
    _SP500_CACHE = tickers
    _CACHE_TS = time.time()
    return tickers

def _load_nasdaq100() -> list[str]:
    global _NDX100_CACHE
    if _NDX100_CACHE:
        return _NDX100_CACHE
    html = requests.get(
        "https://en.wikipedia.org/wiki/Nasdaq-100",
        headers=_UA, timeout=10,
    ).text
    tables = pd.read_html(io.StringIO(html))
    # "Ticker" 또는 "Symbol" 컬럼이 있는 테이블 찾기
    for t in tables:
        for col in t.columns:
            if str(col).lower() in ("ticker", "symbol"):
                tickers = t[col].dropna().str.strip().tolist()
                if len(tickers) > 80:
                    _NDX100_CACHE = [s.replace(".", "-") for s in tickers]
                    return _NDX100_CACHE
    raise RuntimeError("NASDAQ 100 목록을 파싱할 수 없습니다.")


# ── 스크리너 필터 ──────────────────────────────────────────────────────────────

_OPS = {
    "gt":  lambda a, b: a is not None and a > b,
    "lt":  lambda a, b: a is not None and a < b,
    "gte": lambda a, b: a is not None and a >= b,
    "lte": lambda a, b: a is not None and a <= b,
    "eq":  lambda a, b: a is not None and a == b,
}

def _fetch_stock(symbol: str) -> dict | None:
    try:
        t = yf.Ticker(symbol)
        fi = t.fast_info
        info = t.info
        return {
            "ticker":         symbol,
            "name":           info.get("shortName", ""),
            "sector":         info.get("sector", ""),
            "industry":       info.get("industry", ""),
            "marketCap":      fi.market_cap,
            "lastPrice":      fi.last_price,
            "yearChange":     fi.year_change,
            "trailingPE":     info.get("trailingPE"),
            "forwardPE":      info.get("forwardPE"),
            "priceToBook":    info.get("priceToBook"),
            "beta":           info.get("beta"),
            "dividendYield":  info.get("dividendYield"),
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnAssets": info.get("returnOnAssets"),
            "debtToEquity":   info.get("debtToEquity"),
            "grossMargins":   info.get("grossMargins"),
            "profitMargins":  info.get("profitMargins"),
            "revenueGrowth":  info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
        }
    except Exception:
        return None

def _matches(stock: dict, filters: list[dict]) -> bool:
    for f in filters:
        field = f["field"]
        op    = f["operator"]
        val   = f["value"]
        if not _OPS.get(op, lambda a, b: False)(stock.get(field), val):
            return False
    return True


# ── Tools ──────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_crypto_price",
            description=(
                "암호화폐 현재가 및 주요 지표를 반환합니다. "
                "API 키 불필요, 완전 무료. "
                "BTC·ETH·SOL·XRP·BNB·ADA·DOGE 등 주요 코인 지원. "
                "ticker에 USD 페어 자동 적용 (BTC → BTC-USD)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "코인 심볼 목록. 예: [\"BTC\", \"ETH\", \"SOL\"]",
                    },
                    "quote_currency": {
                        "type": "string",
                        "default": "USD",
                        "description": "기준 통화 (기본 USD)",
                    },
                },
                "required": ["symbols"],
            },
        ),
        Tool(
            name="get_crypto_ohlcv",
            description=(
                "암호화폐 OHLCV 과거 데이터를 반환합니다. "
                "1분봉부터 월봉까지 지원. API 키 불필요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "코인 심볼. 예: BTC, ETH, SOL",
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "30m", "60m", "1d", "1wk", "1mo"],
                        "default": "1d",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"],
                        "default": "1mo",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "반환할 캔들 수 (기본 10, 최대 50)",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="screen_stocks",
            description=(
                "S&P 500 / NASDAQ 100 종목을 펀더멘털 조건으로 필터링합니다. "
                "API 키 불필요, 완전 무료. ThreadPool 병렬 조회로 속도 최적화.\n"
                "필터 필드:\n"
                "  가격/규모: marketCap, lastPrice, yearChange\n"
                "  가치지표: trailingPE, forwardPE, priceToBook\n"
                "  수익성:   returnOnEquity, returnOnAssets, grossMargins, profitMargins\n"
                "  성장성:   revenueGrowth, earningsGrowth\n"
                "  안정성:   beta, debtToEquity, dividendYield\n"
                "연산자: gt(>), lt(<), gte(>=), lte(<=), eq(=)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "array",
                        "description": "필터 조건 목록",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field":    {"type": "string"},
                                "operator": {"type": "string", "enum": ["gt","lt","gte","lte","eq"]},
                                "value":    {"type": "number"},
                            },
                            "required": ["field", "operator", "value"],
                        },
                    },
                    "universe": {
                        "type": "string",
                        "enum": ["sp500", "nasdaq100"],
                        "default": "sp500",
                        "description": "스캔 대상 유니버스 (기본 sp500)",
                    },
                    "scan_limit": {
                        "type": "integer",
                        "default": 100,
                        "description": "스캔할 종목 수 (기본 100, 최대 503). 많을수록 느림",
                    },
                    "result_limit": {
                        "type": "integer",
                        "default": 15,
                        "description": "반환할 결과 수 (기본 15)",
                    },
                    "sort_by": {
                        "type": "string",
                        "default": "marketCap",
                        "description": "정렬 기준 필드 (기본 marketCap)",
                    },
                    "sort_desc": {
                        "type": "boolean",
                        "default": True,
                        "description": "내림차순 정렬 여부 (기본 True)",
                    },
                },
                "required": ["filters"],
            },
        ),
    ]


# ── Tool handlers ──────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "get_crypto_price":
            return _get_crypto_price(arguments)
        elif name == "get_crypto_ohlcv":
            return _get_crypto_ohlcv(arguments)
        elif name == "screen_stocks":
            return _screen_stocks(arguments)
        else:
            return _err(f"알 수 없는 tool: {name}")
    except Exception as e:
        return _err(str(e))


def _get_crypto_price(args: dict) -> list[TextContent]:
    symbols = args["symbols"]
    quote   = args.get("quote_currency", "USD").upper()

    lines = [f"[암호화폐 현재가] 기준통화: {quote}\n"]
    lines.append(f"  {'심볼':<12} {'현재가':>14} {'등락률':>8} {'시총':>10} {'거래량':>14}")
    lines.append("  " + "─" * 62)

    for sym in symbols:
        sym = sym.upper()
        ticker = sym if "-" in sym else f"{sym}-{quote}"
        try:
            t     = yf.Ticker(ticker)
            fi    = t.fast_info
            price = fi.last_price
            prev  = fi.previous_close or fi.regular_market_previous_close
            pct   = (price - prev) / prev * 100 if (price and prev) else 0
            arrow = "▲" if pct >= 0 else "▼"
            # 암호화폐는 fast_info.market_cap이 없을 수 있어 info에서 fallback
            mcap  = fi.market_cap or t.info.get("marketCap")
            lines.append(
                f"  {sym:<12} {price:>14,.4f} "
                f"{arrow}{abs(pct):>6.2f}% "
                f"{_fmt_large(mcap):>10} "
                f"{fi.last_volume:>14,.0f}"
            )
        except Exception as e:
            lines.append(f"  {sym:<12} 조회 실패: {e}")

    return _ok("\n".join(lines))


def _get_crypto_ohlcv(args: dict) -> list[TextContent]:
    sym      = args["symbol"].upper()
    interval = args.get("interval", "1d")
    period   = args.get("period", "1mo")
    limit    = min(int(args.get("limit", 10)), 50)

    ticker = sym if "-" in sym else f"{sym}-USD"
    df = yf.Ticker(ticker).history(period=period, interval=interval)

    if df.empty:
        return _err(f"{ticker} 데이터 없음")

    df = df.tail(limit)
    lines = [f"[{ticker}] OHLCV {interval} ({period}) — 최근 {len(df)}개\n"]
    lines.append(f"  {'날짜/시간':<22} {'시가':>10} {'고가':>10} {'저가':>10} {'종가':>10} {'거래량':>16}")
    lines.append("  " + "─" * 82)

    for dt, row in df.iterrows():
        lines.append(
            f"  {str(dt)[:19]:<22} "
            f"{row['Open']:>10.2f} {row['High']:>10.2f} "
            f"{row['Low']:>10.2f} {row['Close']:>10.2f} "
            f"{int(row['Volume']):>16,}"
        )

    return _ok("\n".join(lines))


def _screen_stocks(args: dict) -> list[TextContent]:
    filters      = args["filters"]
    universe     = args.get("universe", "sp500")
    scan_limit   = min(int(args.get("scan_limit", 100)), 503)
    result_limit = int(args.get("result_limit", 15))
    sort_by      = args.get("sort_by", "marketCap")
    sort_desc    = bool(args.get("sort_desc", True))

    # 유니버스 로드
    if universe == "nasdaq100":
        all_tickers = _load_nasdaq100()
    else:
        all_tickers = _load_sp500()

    tickers = all_tickers[:scan_limit]

    # 병렬 데이터 수집 (ThreadPool)
    stocks: list[dict] = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_stock, t): t for t in tickers}
        for fut in as_completed(futures):
            result = fut.result()
            if result and _matches(result, filters):
                stocks.append(result)

    if not stocks:
        filter_desc = ", ".join(f"{f['field']} {f['operator']} {f['value']}" for f in filters)
        return _ok(f"조건에 맞는 종목 없음 ({filter_desc})\n스캔: {len(tickers)}개 중 0개 통과")

    # 정렬
    stocks.sort(key=lambda x: x.get(sort_by) or 0, reverse=sort_desc)
    stocks = stocks[:result_limit]

    # 필터 요약
    filter_desc = " & ".join(f"{f['field']} {f['operator']} {f['value']}" for f in filters)
    lines = [
        f"[{universe.upper()} 스크리닝] {filter_desc}",
        f"스캔: {len(tickers)}종목 → {len(stocks)}종목 통과 (정렬: {sort_by} {'↓' if sort_desc else '↑'})\n",
        f"  {'티커':<8} {'종목명':<22} {'섹터':<18} {'시총':>8} {'PE':>7} {'PB':>6} {'ROE':>7} {'순익률':>7} {'배당':>6}",
        "  " + "─" * 92,
    ]

    for s in stocks:
        lines.append(
            f"  {s['ticker']:<8} {(s['name'] or '')[:21]:<22} "
            f"{(s['sector'] or '')[:17]:<18} "
            f"{_fmt_large(s['marketCap']):>8} "
            f"{_fmt(s['trailingPE'], 1):>7} "
            f"{_fmt(s['priceToBook'], 1):>6} "
            f"{_pct(s['returnOnEquity']):>7} "
            f"{_pct(s['profitMargins']):>7} "
            f"{_pct(s['dividendYield']):>6}"
        )

    return _ok("\n".join(lines))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
