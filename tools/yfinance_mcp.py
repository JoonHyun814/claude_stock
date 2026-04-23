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
        Tool(
            name="get_financials",
            description=(
                "종목의 다개년 재무제표를 반환합니다. financial-datasets 대안으로 사용 가능. "
                "손익계산서(매출·영업이익·순이익), 대차대조표(자산·부채·자기자본), "
                "현금흐름표(영업CF·설비투자·FCF) — 최근 4개년 연간 데이터. "
                "ROE, D/E, 매출 CAGR, 영업이익률도 자동 계산. "
                "API 키 불필요. 미국·한국 주식 모두 지원."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼 (예: AAPL, 005930.KS)"},
                },
                "required": ["symbol"],
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
        elif name == "get_financials":
            return _get_financials(arguments)
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


def _get_financials(args: dict) -> list[TextContent]:
    import pandas as pd

    symbol = args["symbol"].upper()
    t = yf.Ticker(symbol)

    try:
        inc = t.financials          # 손익계산서 (행=항목, 열=연도)
        bal = t.balance_sheet       # 대차대조표
        cf  = t.cashflow            # 현금흐름표
    except Exception as e:
        return _err(f"{symbol} 재무제표 조회 실패: {e}")

    if inc is None or inc.empty:
        return _err(f"{symbol} 재무제표 없음 (비상장 또는 지원 안 됨)")

    def _v(df, *keys):
        for k in keys:
            for idx in df.index:
                if k.lower() in str(idx).lower():
                    row = df.loc[idx]
                    return row
        return None

    def _num(val):
        try:
            v = float(val)
            return None if pd.isna(v) else v
        except Exception:
            return None

    def _fmt(val, decimals=2):
        if val is None:
            return "N/A"
        if abs(val) >= 1e12:
            return f"{val/1e12:.{decimals}f}T"
        if abs(val) >= 1e9:
            return f"{val/1e9:.{decimals}f}B"
        if abs(val) >= 1e6:
            return f"{val/1e6:.{decimals}f}M"
        return f"{val:,.{decimals}f}"

    years = [str(c)[:4] for c in inc.columns]

    # 손익계산서 항목
    rev_row    = _v(inc, "Total Revenue", "Revenue")
    op_row     = _v(inc, "Operating Income", "Ebit")
    net_row    = _v(inc, "Net Income")

    # 대차대조표 항목
    asset_row  = _v(bal, "Total Assets")
    liab_row   = _v(bal, "Total Liabilities Net Minority Interest", "Total Liabilities")
    eq_row     = _v(bal, "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity")
    debt_row   = _v(bal, "Total Debt", "Long Term Debt")

    # 현금흐름 항목
    ocf_row    = _v(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex_row  = _v(cf, "Capital Expenditure", "Purchase Of Ppe")

    lines = [f"[{symbol}] 다개년 재무제표 (연간, 최근 {len(years)}년)\n"]

    # ── 손익계산서 ─────────────────────────────────────────────
    lines.append("■ 손익계산서")
    header = f"  {'항목':<18} " + "  ".join(f"{y:>10}" for y in years)
    lines.append(header)

    def _row_line(label, row):
        if row is None:
            return f"  {label:<18} " + "  ".join(f"{'N/A':>10}" for _ in years)
        vals = [_fmt(_num(row.iloc[i])) for i in range(len(years))]
        return f"  {label:<18} " + "  ".join(f"{v:>10}" for v in vals)

    lines.append(_row_line("매출", rev_row))
    lines.append(_row_line("영업이익", op_row))
    lines.append(_row_line("순이익", net_row))

    # 영업이익률
    margin_vals = []
    for i in range(len(years)):
        r = _num(rev_row.iloc[i]) if rev_row is not None else None
        o = _num(op_row.iloc[i])  if op_row  is not None else None
        margin_vals.append(f"{o/r*100:.1f}%" if (r and o and r != 0) else "N/A")
    lines.append(f"  {'영업이익률':<18} " + "  ".join(f"{v:>10}" for v in margin_vals))

    # 매출 CAGR (최신 vs 최고 과거)
    rev_vals = [_num(rev_row.iloc[i]) for i in range(len(years))] if rev_row is not None else []
    rev_vals = [v for v in rev_vals if v is not None]
    if len(rev_vals) >= 2:
        n = len(rev_vals) - 1
        cagr = ((rev_vals[0] / rev_vals[-1]) ** (1 / n) - 1) * 100
        lines.append(f"\n  매출 CAGR ({n}년): {cagr:.1f}%")

    # ── 대차대조표 ─────────────────────────────────────────────
    lines.append("\n■ 대차대조표")
    lines.append(header)
    lines.append(_row_line("총자산", asset_row))
    lines.append(_row_line("총부채", liab_row))
    lines.append(_row_line("자기자본", eq_row))
    lines.append(_row_line("총부채(이자)", debt_row))

    # D/E 비율 & ROE
    de_vals, roe_vals = [], []
    for i in range(len(years)):
        eq  = _num(eq_row.iloc[i])   if eq_row   is not None else None
        lib = _num(liab_row.iloc[i]) if liab_row is not None else None
        net = _num(net_row.iloc[i])  if net_row  is not None else None
        de_vals.append(f"{lib/eq:.2f}x"    if (eq and lib and eq != 0) else "N/A")
        roe_vals.append(f"{net/eq*100:.1f}%" if (eq and net and eq != 0) else "N/A")

    lines.append(f"  {'D/E 비율':<18} " + "  ".join(f"{v:>10}" for v in de_vals))
    lines.append(f"  {'ROE':<18} " + "  ".join(f"{v:>10}" for v in roe_vals))

    # ── 현금흐름표 ─────────────────────────────────────────────
    lines.append("\n■ 현금흐름표")
    lines.append(header)
    lines.append(_row_line("영업 CF", ocf_row))
    lines.append(_row_line("설비투자(CapEx)", capex_row))

    # FCF = 영업CF - |CapEx|
    fcf_vals = []
    for i in range(len(years)):
        o = _num(ocf_row.iloc[i])   if ocf_row   is not None else None
        c = _num(capex_row.iloc[i]) if capex_row is not None else None
        if o is not None and c is not None:
            fcf_vals.append(_fmt(o - abs(c)))
        else:
            fcf_vals.append("N/A")
    lines.append(f"  {'FCF':<18} " + "  ".join(f"{v:>10}" for v in fcf_vals))

    lines.append("\n※ financial-datasets 미지원 종목의 대체 데이터 (yfinance, 최근 4개년)")
    return _ok("\n".join(lines))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
