import asyncio
from typing import Any

import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("yfinance")


def _ok(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


def _err(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"오류: {text}")]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_realtime_price",
            description=(
                "주식/ETF/지수의 현재가 및 당일 핵심 지표를 반환합니다. "
                "API 키 불필요. 미국·한국·글로벌 거래소 모두 지원. "
                "한국 주식은 티커에 .KS(코스피) 또는 .KQ(코스닥) 접미사를 붙이세요. "
                "예: 삼성전자=005930.KS, 카카오=035720.KQ"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "티커 목록. 예: [\"AAPL\", \"NVDA\", \"005930.KS\"]",
                    },
                },
                "required": ["symbols"],
            },
        ),
        Tool(
            name="get_intraday_ohlcv",
            description=(
                "분봉/시간봉 OHLCV 데이터를 반환합니다. Alpha Vantage intraday 무료 대안. "
                "1분봉은 최근 7일, 5분~90분봉은 최근 60일까지 조회 가능."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼"},
                    "interval": {
                        "type": "string",
                        "enum": ["1m", "2m", "5m", "15m", "30m", "60m", "90m"],
                        "default": "5m",
                        "description": "봉 주기 (기본 5m)",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["1d", "5d", "1mo"],
                        "default": "1d",
                        "description": "조회 기간 (기본 1d=당일)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "반환할 최근 캔들 수 (기본 20, 최대 100)",
                        "default": 20,
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_stock_info",
            description=(
                "종목의 펀더멘털 정보를 반환합니다. "
                "시가총액, PER, PBR, 52주 고저가, 베타, 배당수익률, 섹터, 산업군 등."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼"},
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_multi_quote",
            description=(
                "여러 종목의 현재가를 한 번에 비교합니다. "
                "포트폴리오 모니터링이나 섹터 비교에 활용하세요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "티커 목록 (최대 20개)",
                    },
                },
                "required": ["symbols"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "get_realtime_price":
            return _get_realtime_price(arguments)
        elif name == "get_intraday_ohlcv":
            return _get_intraday_ohlcv(arguments)
        elif name == "get_stock_info":
            return _get_stock_info(arguments)
        elif name == "get_multi_quote":
            return _get_multi_quote(arguments)
        else:
            return _err(f"알 수 없는 tool: {name}")
    except Exception as e:
        return _err(str(e))


def _fmt_num(val, decimals=2) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.{decimals}f}"


def _fmt_large(val) -> str:
    """시가총액 등 큰 숫자를 조 단위로 포맷."""
    if val is None:
        return "N/A"
    if val >= 1e12:
        return f"{val/1e12:.2f}T"
    if val >= 1e9:
        return f"{val/1e9:.2f}B"
    if val >= 1e6:
        return f"{val/1e6:.2f}M"
    return f"{val:,.0f}"


def _get_realtime_price(args: dict) -> list[TextContent]:
    symbols = [s.upper() for s in args["symbols"]]
    lines = []

    for symbol in symbols:
        t = yf.Ticker(symbol)
        fi = t.fast_info

        price = fi.last_price
        if price is None:
            lines.append(f"[{symbol}] 데이터 없음")
            continue

        prev_close = fi.regular_market_previous_close or fi.previous_close
        change = price - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        arrow = "▲" if change >= 0 else "▼"

        lines.append(
            f"[{symbol}]  현재가: {_fmt_num(price)} {fi.currency or ''}\n"
            f"  {arrow} {abs(change):.2f} ({abs(change_pct):.2f}%)  "
            f"시가: {_fmt_num(fi.open)}  고: {_fmt_num(fi.day_high)}  저: {_fmt_num(fi.day_low)}\n"
            f"  거래량: {fi.last_volume:,}  시총: {_fmt_large(fi.market_cap)}\n"
            f"  52주 고: {_fmt_num(fi.year_high)}  52주 저: {_fmt_num(fi.year_low)}"
        )

    return _ok("\n\n".join(lines))


def _get_intraday_ohlcv(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    interval = args.get("interval", "5m")
    period = args.get("period", "1d")
    limit = min(int(args.get("limit", 20)), 100)

    t = yf.Ticker(symbol)
    df = t.history(period=period, interval=interval)

    if df.empty:
        return _err(f"{symbol} 데이터 없음 (장 마감 또는 잘못된 심볼)")

    df = df.tail(limit)
    lines = [f"[{symbol}] {interval} OHLCV ({period}) — 최근 {len(df)}개\n"]

    for dt, row in df.iterrows():
        dt_str = str(dt)[:19]
        lines.append(
            f"  {dt_str}  O:{row['Open']:.2f}  H:{row['High']:.2f}  "
            f"L:{row['Low']:.2f}  C:{row['Close']:.2f}  V:{int(row['Volume']):,}"
        )

    return _ok("\n".join(lines))


def _get_stock_info(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    t = yf.Ticker(symbol)
    info = t.info

    if not info or info.get("quoteType") is None:
        return _err(f"{symbol} 정보 없음")

    fi = t.fast_info
    price = fi.last_price
    prev_close = fi.regular_market_previous_close or fi.previous_close
    change_pct = ((price - prev_close) / prev_close * 100) if (price and prev_close) else 0
    arrow = "▲" if change_pct >= 0 else "▼"

    dividend = info.get("dividendYield")
    div_str = f"{dividend*100:.2f}%" if dividend else "없음"

    forward_pe = info.get("forwardPE")
    trailing_pe = info.get("trailingPE")
    pbr = info.get("priceToBook")
    beta = info.get("beta")
    eps = info.get("trailingEps")

    lines = [
        f"[{symbol}] {info.get('longName', symbol)}",
        f"  거래소: {info.get('exchange','')}  섹터: {info.get('sector','N/A')}  산업: {info.get('industry','N/A')}",
        "",
        f"  현재가   : {_fmt_num(price)} {info.get('currency','')}  {arrow} {abs(change_pct):.2f}%",
        f"  시가총액  : {_fmt_large(info.get('marketCap'))}",
        f"  52주 고저 : {_fmt_num(fi.year_high)}  /  {_fmt_num(fi.year_low)}",
        f"  거래량    : {info.get('volume',0):,}  (평균: {info.get('averageVolume',0):,})",
        "",
        f"  PER(TTM)  : {_fmt_num(trailing_pe)}  |  PER(Forward): {_fmt_num(forward_pe)}",
        f"  PBR       : {_fmt_num(pbr)}  |  EPS: {_fmt_num(eps)}",
        f"  베타      : {_fmt_num(beta)}",
        f"  배당수익률: {div_str}",
        f"  50일MA    : {_fmt_num(fi.fifty_day_average)}  |  200일MA: {_fmt_num(fi.two_hundred_day_average)}",
    ]

    return _ok("\n".join(lines))


def _get_multi_quote(args: dict) -> list[TextContent]:
    symbols = [s.upper() for s in args["symbols"][:20]]

    rows = []
    for symbol in symbols:
        try:
            fi = yf.Ticker(symbol).fast_info
            price = fi.last_price
            if price is None:
                rows.append(f"  {symbol:<12} N/A")
                continue
            prev = fi.regular_market_previous_close or fi.previous_close
            pct = ((price - prev) / prev * 100) if prev else 0
            arrow = "▲" if pct >= 0 else "▼"
            rows.append(
                f"  {symbol:<12} {price:>10.2f} {fi.currency or '':>4}  "
                f"{arrow} {abs(pct):>5.2f}%  시총: {_fmt_large(fi.market_cap)}"
            )
        except Exception:
            rows.append(f"  {symbol:<12} 조회 실패")

    header = f"{'티커':<12} {'현재가':>10} {'통화':>4}  {'등락':>8}  시가총액"
    lines = [f"[멀티 시세 — {len(symbols)}종목]\n", header, "-" * 55] + rows
    return _ok("\n".join(lines))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
