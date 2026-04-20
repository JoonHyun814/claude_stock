import sys
import io
import json
import asyncio
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

HOLDINGS_PATH = Path(__file__).parent.parent / "holdings.json"
TROY_OZ_TO_GRAM = 31.1035
GOLD_TICKER = "GC=F"
USD_KRW_TICKER = "USDKRW=X"

app = Server("stock-info")


def fetch_ticker_data(ticker_symbol: str):
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period="5d")
    if hist.empty:
        return None, None, {}
    info = t.info
    current = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
    return current, prev, info


def format_stock_info(ticker: str, current: float, prev: float, info: dict) -> dict:
    change = current - prev
    pct = (change / prev * 100) if prev else 0
    return {
        "ticker": ticker,
        "current_price": current,
        "prev_close": prev,
        "change": change,
        "change_pct": round(pct, 2),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "pe_ratio": info.get("trailingPE"),
        "pb_ratio": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "market_cap": info.get("marketCap"),
        "avg_volume": info.get("averageVolume"),
        "currency": info.get("currency", ""),
        "short_name": info.get("shortName", ticker),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "fetched_at": datetime.now().isoformat(),
    }


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_stock_info",
            description="티커 심볼로 주식의 현재 가격, 등락률, PER, PBR, 52주 범위 등 핵심 정보를 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "주식 티커 심볼 (예: AAPL, 005380.KS, BRK-B)",
                    }
                },
                "required": ["ticker"],
            },
        ),
        types.Tool(
            name="get_multiple_stocks",
            description="여러 티커 심볼의 현재 정보를 한 번에 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "주식 티커 심볼 목록 (예: ['AAPL', 'MSFT', '005380.KS'])",
                    }
                },
                "required": ["tickers"],
            },
        ),
        types.Tool(
            name="get_portfolio",
            description="holdings.json에 저장된 전체 포트폴리오의 현재 평가금액, 수익률, 구성 현황을 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="get_exchange_rate",
            description="현재 USD/KRW 환율을 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_stock_info":
        ticker = arguments["ticker"].strip().upper()
        current, prev, info = fetch_ticker_data(ticker)
        if current is None:
            result = {"error": f"'{ticker}' 데이터를 가져올 수 없습니다. 티커를 확인해주세요."}
        else:
            result = format_stock_info(ticker, current, prev, info)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "get_multiple_stocks":
        tickers = [t.strip().upper() for t in arguments["tickers"]]
        results = {}
        for ticker in tickers:
            current, prev, info = fetch_ticker_data(ticker)
            if current is None:
                results[ticker] = {"error": "데이터를 가져올 수 없습니다."}
            else:
                results[ticker] = format_stock_info(ticker, current, prev, info)
        return [types.TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

    elif name == "get_exchange_rate":
        current, prev, _ = fetch_ticker_data(USD_KRW_TICKER)
        if current is None:
            result = {"error": "환율 데이터를 가져올 수 없습니다."}
        else:
            change = current - prev
            pct = (change / prev * 100) if prev else 0
            result = {
                "pair": "USD/KRW",
                "rate": round(current, 2),
                "prev_close": round(prev, 2),
                "change": round(change, 2),
                "change_pct": round(pct, 4),
                "fetched_at": datetime.now().isoformat(),
            }
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "get_portfolio":
        if not HOLDINGS_PATH.exists():
            return [types.TextContent(type="text", text=json.dumps({"error": "holdings.json 파일이 없습니다."}))]

        with open(HOLDINGS_PATH, "r", encoding="utf-8") as f:
            holdings = json.load(f)

        usd_krw = None
        fx_cur, _, _ = fetch_ticker_data(USD_KRW_TICKER)
        if fx_cur:
            usd_krw = fx_cur

        portfolio = {
            "fetched_at": datetime.now().isoformat(),
            "usd_krw_rate": round(usd_krw, 2) if usd_krw else None,
            "korean_stocks": [],
            "foreign_stocks": [],
            "gold": None,
            "summary": {},
        }

        total_krw = 0.0
        total_usd = 0.0

        for s in holdings["holdings"]["korean_stocks"]:
            cur, prev, info = fetch_ticker_data(s["ticker"])
            if cur is None:
                portfolio["korean_stocks"].append({"name": s["name"], "ticker": s["ticker"], "error": "데이터 없음"})
                continue
            val = cur * s["quantity"]
            total_krw += val
            stock_data = format_stock_info(s["ticker"], cur, prev, info)
            stock_data.update({"name": s["name"], "quantity": s["quantity"], "total_value_krw": round(val, 0)})
            portfolio["korean_stocks"].append(stock_data)

        for s in holdings["holdings"]["foreign_stocks"]:
            cur, prev, info = fetch_ticker_data(s["ticker"])
            if cur is None:
                portfolio["foreign_stocks"].append({"name": s["name"], "ticker": s["ticker"], "error": "데이터 없음"})
                continue
            val = cur * s["quantity"]
            total_usd += val
            stock_data = format_stock_info(s["ticker"], cur, prev, info)
            stock_data.update({"name": s["name"], "quantity": s["quantity"], "total_value_usd": round(val, 2)})
            portfolio["foreign_stocks"].append(stock_data)

        gold_items = holdings["holdings"]["gold"]
        total_grams = sum(g["quantity"] for g in gold_items)
        gold_oz_cur, gold_oz_prev, _ = fetch_ticker_data(GOLD_TICKER)
        if gold_oz_cur:
            gold_g_cur = gold_oz_cur / TROY_OZ_TO_GRAM
            gold_g_prev = gold_oz_prev / TROY_OZ_TO_GRAM
            gold_total_usd = gold_g_cur * total_grams
            total_usd += gold_total_usd
            portfolio["gold"] = {
                "quantity_grams": total_grams,
                "price_per_gram_usd": round(gold_g_cur, 4),
                "price_per_oz_usd": round(gold_oz_cur, 2),
                "change_per_gram_usd": round(gold_g_cur - gold_g_prev, 4),
                "total_value_usd": round(gold_total_usd, 4),
            }

        portfolio["summary"] = {
            "korean_stocks_total_krw": round(total_krw, 0),
            "foreign_and_gold_total_usd": round(total_usd, 2),
        }
        if usd_krw:
            grand_total = total_krw + total_usd * usd_krw
            portfolio["summary"]["grand_total_krw"] = round(grand_total, 0)

        return [types.TextContent(type="text", text=json.dumps(portfolio, ensure_ascii=False, indent=2))]

    return [types.TextContent(type="text", text=json.dumps({"error": f"알 수 없는 툴: {name}"}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
