"""
Free MACD MCP — yfinance + pandas (no API key required)

MACD formula:
  MACD line   = EMA(fast) - EMA(slow)
  Signal line = EMA(signal) of MACD line
  Histogram   = MACD line - Signal line
"""
import asyncio
from typing import Any

import pandas as pd
import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("macd-analyzer")


def _ok(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


def _err(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"오류: {text}")]


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _calc_macd(close: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "MACD": macd_line,
        "Signal": signal_line,
        "Histogram": histogram,
    })


def _detect_cross(hist: pd.Series) -> str:
    """마지막 두 봉의 히스토그램 부호로 교차 감지."""
    if len(hist) < 2:
        return "데이터 부족"
    prev, curr = hist.iloc[-2], hist.iloc[-1]
    if prev < 0 and curr >= 0:
        return "골든크로스 (상승 전환)"
    if prev >= 0 and curr < 0:
        return "데드크로스 (하락 전환)"
    return "상승 추세" if curr > 0 else "하락 추세"


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_macd",
            description=(
                "yfinance 기반 완전 무료 MACD 분석. API 키 불필요. "
                "MACD 라인·시그널 라인·히스토그램·골든/데드크로스 감지. "
                "미국·한국(.KS/.KQ)·글로벌 거래소 모두 지원."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "티커 심볼. 예: AAPL, NVDA, 005930.KS",
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "30m", "60m", "1d", "1wk"],
                        "default": "1d",
                        "description": "봉 주기 (기본 1d=일봉)",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["5d", "1mo", "3mo", "6mo", "1y", "2y"],
                        "default": "6mo",
                        "description": "데이터 조회 기간 (기본 6mo). 단기 봉일수록 짧은 기간 권장",
                    },
                    "fast": {
                        "type": "integer",
                        "default": 12,
                        "description": "단기 EMA 기간 (기본 12)",
                    },
                    "slow": {
                        "type": "integer",
                        "default": 26,
                        "description": "장기 EMA 기간 (기본 26)",
                    },
                    "signal": {
                        "type": "integer",
                        "default": 9,
                        "description": "시그널 EMA 기간 (기본 9)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "반환할 최근 데이터 수 (기본 10, 최대 50)",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_macd_multi",
            description=(
                "여러 종목의 MACD 상태를 한 번에 비교합니다. "
                "각 종목의 최신 MACD 값과 크로스 신호를 요약해 반환합니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "티커 목록 (최대 10개). 예: [\"AAPL\", \"NVDA\", \"005930.KS\"]",
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "30m", "60m", "1d", "1wk"],
                        "default": "1d",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["5d", "1mo", "3mo", "6mo", "1y", "2y"],
                        "default": "6mo",
                    },
                    "fast": {"type": "integer", "default": 12},
                    "slow": {"type": "integer", "default": 26},
                    "signal": {"type": "integer", "default": 9},
                },
                "required": ["symbols"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "get_macd":
            return _get_macd(arguments)
        elif name == "get_macd_multi":
            return _get_macd_multi(arguments)
        else:
            return _err(f"알 수 없는 tool: {name}")
    except Exception as e:
        return _err(str(e))


def _get_macd(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    interval = args.get("interval", "1d")
    period = args.get("period", "6mo")
    fast = int(args.get("fast", 12))
    slow = int(args.get("slow", 26))
    signal = int(args.get("signal", 9))
    limit = min(int(args.get("limit", 10)), 50)

    df = yf.Ticker(symbol).history(period=period, interval=interval)
    if df.empty:
        return _err(f"{symbol} 데이터 없음 (심볼 확인 또는 장 마감)")

    # EMA 수렴을 위해 slow*3 이상 데이터 필요
    min_rows = slow * 3
    if len(df) < min_rows:
        return _err(f"데이터 부족: {len(df)}개 (최소 {min_rows}개 필요). period를 늘려주세요.")

    macd_df = _calc_macd(df["Close"], fast, slow, signal)
    recent = macd_df.tail(limit)
    cross_signal = _detect_cross(macd_df["Histogram"])

    lines = [
        f"[{symbol}] MACD({fast},{slow},{signal}) {interval} — 최근 {len(recent)}개",
        f"현재 신호: {cross_signal}",
        "",
        f"  {'날짜/시간':<22} {'MACD':>10} {'Signal':>10} {'Histogram':>10}  상태",
        "  " + "-" * 65,
    ]

    for dt, row in recent.iterrows():
        dt_str = str(dt)[:19]
        hist = row["Histogram"]
        bar = "▲" if hist > 0 else "▼"
        lines.append(
            f"  {dt_str:<22} {row['MACD']:>10.4f} {row['Signal']:>10.4f} {hist:>10.4f}  {bar}"
        )

    # 최신 클로즈 가격도 추가
    last_close = df["Close"].iloc[-1]
    lines.append(f"\n  최근 종가: {last_close:,.4f}")

    return _ok("\n".join(lines))


def _get_macd_multi(args: dict) -> list[TextContent]:
    symbols = [s.upper() for s in args["symbols"][:10]]
    interval = args.get("interval", "1d")
    period = args.get("period", "6mo")
    fast = int(args.get("fast", 12))
    slow = int(args.get("slow", 26))
    signal = int(args.get("signal", 9))

    header = f"[MACD({fast},{slow},{signal}) 멀티 비교 — {interval} / {period}]\n"
    col = f"  {'티커':<14} {'MACD':>10} {'Signal':>10} {'Histogram':>10}  신호"
    rows = [header, col, "  " + "-" * 62]

    for symbol in symbols:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
            if df.empty or len(df) < slow * 3:
                rows.append(f"  {symbol:<14} 데이터 부족")
                continue

            macd_df = _calc_macd(df["Close"], fast, slow, signal)
            last = macd_df.iloc[-1]
            cross = _detect_cross(macd_df["Histogram"])
            rows.append(
                f"  {symbol:<14} {last['MACD']:>10.4f} {last['Signal']:>10.4f} "
                f"{last['Histogram']:>10.4f}  {cross}"
            )
        except Exception as e:
            rows.append(f"  {symbol:<14} 오류: {e}")

    return _ok("\n".join(rows))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
