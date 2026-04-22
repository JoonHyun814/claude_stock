import asyncio
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.environ["ALPHA_VANTAGE_API_KEY"]
BASE_URL = "https://www.alphavantage.co/query"

server = Server("alphavantage")


def _get(params: dict) -> dict:
    params["apikey"] = API_KEY
    r = requests.get(BASE_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if "Note" in data:
        raise RuntimeError("API 호출 한도 초과 (무료: 25회/일, 5회/분). 잠시 후 다시 시도하세요.")
    if "Information" in data:
        msg = data["Information"]
        if "premium endpoint" in msg:
            raise RuntimeError("이 기능은 Alpha Vantage 유료 플랜 전용 엔드포인트입니다. https://www.alphavantage.co/premium/ 에서 구독 후 이용 가능합니다.")
        raise RuntimeError("API 호출 한도 초과 (무료: 25회/일). 잠시 후 다시 시도하세요.")
    return data


def _ok(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


def _err(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"오류: {text}")]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_ohlcv",
            description=(
                "주식/ETF의 OHLCV(시가·고가·저가·종가·거래량) 데이터를 반환합니다. "
                "daily/weekly/monthly는 무료 플랜 사용 가능. "
                "1min~60min intraday는 유료 플랜 전용입니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼 (예: AAPL, MSFT, SPY)"},
                    "interval": {
                        "type": "string",
                        "enum": ["1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"],
                        "description": "데이터 주기. intraday는 1min~60min, 그 외는 daily/weekly/monthly",
                        "default": "daily",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최근 캔들 수 (기본 10, 최대 30)",
                        "default": 10,
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_rsi",
            description="RSI(상대강도지수) 값을 반환합니다. 14기간이 기본값이며 일봉 기준입니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼 (예: AAPL)"},
                    "interval": {
                        "type": "string",
                        "enum": ["1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"],
                        "default": "daily",
                    },
                    "time_period": {
                        "type": "integer",
                        "description": "RSI 계산 기간 (기본 14)",
                        "default": 14,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최근 데이터 수 (기본 5, 최대 20)",
                        "default": 5,
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_macd",
            description=(
                "MACD(이동평균 수렴·확산) 값을 반환합니다. "
                "MACD 라인, 시그널 라인, 히스토그램을 포함합니다. "
                "⚠️ Alpha Vantage 유료 플랜 전용 엔드포인트입니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼 (예: AAPL)"},
                    "interval": {
                        "type": "string",
                        "enum": ["1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"],
                        "default": "daily",
                    },
                    "fast_period": {"type": "integer", "default": 12, "description": "단기 EMA 기간"},
                    "slow_period": {"type": "integer", "default": 26, "description": "장기 EMA 기간"},
                    "signal_period": {"type": "integer", "default": 9, "description": "시그널 EMA 기간"},
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최근 데이터 수 (기본 5, 최대 20)",
                        "default": 5,
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_market_status",
            description=(
                "전 세계 주요 시장(미국·유럽·아시아 등)의 현재 개장/폐장 상태를 반환합니다. "
                "장 시작·마감 시간, 현지 시각 포함."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_commodity_price",
            description=(
                "원자재 가격을 반환합니다. "
                "에너지(WTI·브렌트·천연가스), 금속(구리·알루미늄), "
                "농산물(밀·옥수수·면화·설탕·커피) 지원."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "commodity": {
                        "type": "string",
                        "enum": [
                            "WTI", "BRENT", "NATURAL_GAS",
                            "COPPER", "ALUMINUM",
                            "WHEAT", "CORN", "COTTON", "SUGAR", "COFFEE",
                        ],
                        "description": (
                            "원자재 종류: "
                            "WTI(서부텍사스 원유), BRENT(브렌트 원유), NATURAL_GAS(천연가스), "
                            "COPPER(구리), ALUMINUM(알루미늄), "
                            "WHEAT(밀), CORN(옥수수), COTTON(면화), SUGAR(설탕), COFFEE(커피)"
                        ),
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly"],
                        "default": "monthly",
                        "description": "데이터 주기 (기본 monthly)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최근 데이터 수 (기본 5, 최대 20)",
                        "default": 5,
                    },
                },
                "required": ["commodity"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "get_ohlcv":
            return _get_ohlcv(arguments)
        elif name == "get_rsi":
            return _get_rsi(arguments)
        elif name == "get_macd":
            return _get_macd(arguments)
        elif name == "get_market_status":
            return _get_market_status()
        elif name == "get_commodity_price":
            return _get_commodity_price(arguments)
        else:
            return _err(f"알 수 없는 tool: {name}")
    except RuntimeError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"요청 실패: {e}")


def _get_ohlcv(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    interval = args.get("interval", "daily")
    limit = min(int(args.get("limit", 10)), 30)

    intraday_intervals = {"1min", "5min", "15min", "30min", "60min"}

    if interval in intraday_intervals:
        params = {"function": "TIME_SERIES_INTRADAY", "symbol": symbol, "interval": interval, "outputsize": "compact"}
        data = _get(params)
        series_key = f"Time Series ({interval})"
    elif interval == "daily":
        params = {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"}
        data = _get(params)
        series_key = "Time Series (Daily)"
    elif interval == "weekly":
        params = {"function": "TIME_SERIES_WEEKLY", "symbol": symbol}
        data = _get(params)
        series_key = "Weekly Time Series"
    else:  # monthly
        params = {"function": "TIME_SERIES_MONTHLY", "symbol": symbol}
        data = _get(params)
        series_key = "Monthly Time Series"

    if series_key not in data:
        return _err(f"데이터 없음: {symbol}")

    series = data[series_key]
    recent = list(series.items())[:limit]

    lines = [f"[{symbol}] OHLCV ({interval}) — 최근 {len(recent)}개\n"]
    for date, v in recent:
        lines.append(
            f"  {date}  O:{v['1. open']}  H:{v['2. high']}  L:{v['3. low']}  C:{v['4. close']}  V:{int(v['5. volume']):,}"
        )
    return _ok("\n".join(lines))


def _get_rsi(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    interval = args.get("interval", "daily")
    time_period = int(args.get("time_period", 14))
    limit = min(int(args.get("limit", 5)), 20)

    params = {
        "function": "RSI",
        "symbol": symbol,
        "interval": interval,
        "time_period": time_period,
        "series_type": "close",
    }
    data = _get(params)

    key = "Technical Analysis: RSI"
    if key not in data:
        return _err(f"RSI 데이터 없음: {symbol}")

    recent = list(data[key].items())[:limit]
    lines = [f"[{symbol}] RSI({time_period}) {interval} — 최근 {len(recent)}개\n"]
    for date, v in recent:
        rsi_val = float(v["RSI"])
        signal = "과매수(70↑)" if rsi_val >= 70 else ("과매도(30↓)" if rsi_val <= 30 else "중립")
        lines.append(f"  {date}  RSI: {rsi_val:.2f}  [{signal}]")
    return _ok("\n".join(lines))


def _get_macd(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    interval = args.get("interval", "daily")
    fast = int(args.get("fast_period", 12))
    slow = int(args.get("slow_period", 26))
    signal = int(args.get("signal_period", 9))
    limit = min(int(args.get("limit", 5)), 20)

    params = {
        "function": "MACD",
        "symbol": symbol,
        "interval": interval,
        "fastperiod": fast,
        "slowperiod": slow,
        "signalperiod": signal,
        "series_type": "close",
    }
    data = _get(params)

    key = "Technical Analysis: MACD"
    if key not in data:
        return _err(f"MACD 데이터 없음: {symbol}")

    recent = list(data[key].items())[:limit]
    lines = [f"[{symbol}] MACD({fast},{slow},{signal}) {interval} — 최근 {len(recent)}개\n"]
    for date, v in recent:
        macd_val = float(v["MACD"])
        sig_val = float(v["MACD_Signal"])
        hist_val = float(v["MACD_Hist"])
        trend = "상승" if hist_val > 0 else "하락"
        lines.append(
            f"  {date}  MACD:{macd_val:.4f}  Signal:{sig_val:.4f}  Hist:{hist_val:.4f}  [{trend}]"
        )
    return _ok("\n".join(lines))


def _get_market_status() -> list[TextContent]:
    data = _get({"function": "MARKET_STATUS"})

    markets = data.get("markets", [])
    if not markets:
        return _err("시장 상태 데이터 없음")

    lines = ["[전 세계 시장 상태]\n"]
    for m in markets:
        status_icon = "🟢" if m.get("current_status") == "open" else "🔴"
        lines.append(
            f"  {status_icon} {m.get('market_type',''):<12} {m.get('region',''):<20} "
            f"{m.get('primary_exchanges',''):<25} "
            f"현지시각: {m.get('local_open','')}~{m.get('local_close','')}  "
            f"({m.get('current_status','')})"
        )
    return _ok("\n".join(lines))


def _get_commodity_price(args: dict) -> list[TextContent]:
    commodity = args["commodity"].upper()
    interval = args.get("interval", "monthly")
    limit = min(int(args.get("limit", 5)), 20)

    name_map = {
        "WTI": "서부텍사스 원유(WTI)",
        "BRENT": "브렌트 원유(BRENT)",
        "NATURAL_GAS": "천연가스",
        "COPPER": "구리",
        "ALUMINUM": "알루미늄",
        "WHEAT": "밀",
        "CORN": "옥수수",
        "COTTON": "면화",
        "SUGAR": "설탕",
        "COFFEE": "커피",
    }

    params = {"function": commodity, "interval": interval}
    data = _get(params)

    entries = data.get("data", [])
    if not entries:
        return _err(f"원자재 데이터 없음: {commodity}")

    recent = entries[:limit]
    unit = data.get("unit", "")
    lines = [f"[{name_map.get(commodity, commodity)}] {interval} — 최근 {len(recent)}개  (단위: {unit})\n"]
    for e in recent:
        val = e.get("value", "N/A")
        display = f"{float(val):,.4f}" if val and val != "." else "N/A"
        lines.append(f"  {e.get('date','')}  {display}")
    return _ok("\n".join(lines))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
