"""
Financial Datasets MCP — https://financialdatasets.ai
손익계산서, 대차대조표, 현금흐름표, 기업 뉴스, 암호화폐 가격, 펀더멘털 스크리너.
API 키 발급: https://financialdatasets.ai
"""
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

API_KEY = os.environ["FINANCIAL_DATASETS_API_KEY"]
BASE_URL = "https://api.financialdatasets.ai"

server = Server("financial-datasets")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"X-API-KEY": API_KEY}


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=15)
    if r.status_code == 401:
        raise RuntimeError("API 키가 유효하지 않습니다. .env의 FINANCIAL_DATASETS_API_KEY를 확인하세요.")
    if r.status_code == 402:
        raise RuntimeError("플랜 한도 초과 또는 유료 기능입니다. https://financialdatasets.ai/pricing 참고.")
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> dict:
    r = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=body, timeout=15)
    if r.status_code == 401:
        raise RuntimeError("API 키 오류 또는 이 기능은 유료 플랜 전용입니다. https://financialdatasets.ai/pricing 참고.")
    if r.status_code == 402:
        raise RuntimeError("플랜 한도 초과 또는 유료 기능입니다. https://financialdatasets.ai/pricing 참고.")
    r.raise_for_status()
    return r.json()


def _ok(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


def _err(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"오류: {text}")]


def _fmt(val, decimals=2, suffix="") -> str:
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        return f"{val:,.{decimals}f}{suffix}"
    return str(val)


def _fmt_large(val) -> str:
    if val is None:
        return "N/A"
    for unit, divisor in [("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if abs(val) >= divisor:
            return f"{val/divisor:.2f}{unit}"
    return f"{val:.2f}"


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_income_statement",
            description=(
                "손익계산서를 반환합니다. 매출·영업이익·순이익·EPS·영업이익률 포함. "
                "연간(annual)·분기(quarterly)·TTM 지원. 미국 상장 주식 전용."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "티커 심볼 (예: AAPL, NVDA, TSLA)"},
                    "period": {
                        "type": "string",
                        "enum": ["annual", "quarterly", "ttm"],
                        "default": "annual",
                        "description": "기간 유형 (기본 annual)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 4,
                        "description": "반환할 기간 수 (기본 4, 연간=최근 4년 / 분기=최근 4분기)",
                    },
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_balance_sheet",
            description=(
                "대차대조표를 반환합니다. 총자산·총부채·자기자본·현금·부채비율 포함. "
                "연간·분기·TTM 지원."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {
                        "type": "string",
                        "enum": ["annual", "quarterly", "ttm"],
                        "default": "annual",
                    },
                    "limit": {"type": "integer", "default": 4},
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_cash_flow",
            description=(
                "현금흐름표를 반환합니다. 영업·투자·재무 현금흐름과 잉여현금흐름(FCF) 포함. "
                "연간·분기·TTM 지원."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {
                        "type": "string",
                        "enum": ["annual", "quarterly", "ttm"],
                        "default": "annual",
                    },
                    "limit": {"type": "integer", "default": 4},
                },
                "required": ["ticker"],
            },
        ),
        Tool(
            name="get_company_news",
            description=(
                "기업 뉴스를 반환합니다. ticker를 생략하면 전체 시장 뉴스를 반환합니다. "
                "출처: Motley Fool, Reuters, Investing.com 등."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "티커 심볼 (생략 시 전체 시장 뉴스)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "description": "반환할 뉴스 수 (기본 5, 최대 10)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_crypto_price",
            description=(
                "암호화폐 과거 OHLC 가격을 반환합니다. "
                "BTC, ETH, SOL 등 주요 코인 지원. "
                "⚠️ 유료 플랜 전용 엔드포인트일 수 있습니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "암호화폐 심볼 (예: BTC, ETH, SOL, XRP, BNB)",
                    },
                    "interval": {
                        "type": "string",
                        "enum": ["day", "week", "month"],
                        "default": "day",
                        "description": "캔들 주기",
                    },
                    "interval_multiplier": {
                        "type": "integer",
                        "default": 1,
                        "description": "주기 배수 (예: interval=day, multiplier=7 → 7일봉)",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "조회 시작일 (YYYY-MM-DD)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "조회 종료일 (YYYY-MM-DD)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "반환할 캔들 수 (기본 10)",
                    },
                },
                "required": ["ticker", "start_date", "end_date"],
            },
        ),
        Tool(
            name="screen_stocks",
            description=(
                "펀더멘털 기반 주식 스크리닝. 재무 지표 조건을 설정해 종목을 필터링합니다. "
                "장기 투자를 위한 재무 건전성·성장성 스크리닝에 활용하세요. "
                "⚠️ 유료 플랜 전용 엔드포인트일 수 있습니다.\n"
                "주요 필터 필드: revenue, net_income, operating_income, gross_profit, "
                "total_assets, total_liabilities, total_equity, cash_and_equivalents, "
                "free_cash_flow, earnings_per_share, price_to_earnings_ratio, "
                "price_to_book_ratio, debt_to_equity, return_on_equity, return_on_assets, "
                "revenue_growth, net_income_growth\n"
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
                                "field": {"type": "string", "description": "필터 필드명"},
                                "operator": {
                                    "type": "string",
                                    "enum": ["gt", "lt", "gte", "lte", "eq"],
                                    "description": "비교 연산자",
                                },
                                "value": {"type": "number", "description": "비교 기준값"},
                            },
                            "required": ["field", "operator", "value"],
                        },
                    },
                    "period": {
                        "type": "string",
                        "enum": ["annual", "quarterly", "ttm"],
                        "default": "ttm",
                        "description": "기준 기간 (기본 ttm=최근 12개월)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "반환할 종목 수 (기본 10)",
                    },
                },
                "required": ["filters"],
            },
        ),
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "get_income_statement":
            return _get_income_statement(arguments)
        elif name == "get_balance_sheet":
            return _get_balance_sheet(arguments)
        elif name == "get_cash_flow":
            return _get_cash_flow(arguments)
        elif name == "get_company_news":
            return _get_company_news(arguments)
        elif name == "get_crypto_price":
            return _get_crypto_price(arguments)
        elif name == "screen_stocks":
            return _screen_stocks(arguments)
        else:
            return _err(f"알 수 없는 tool: {name}")
    except RuntimeError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"요청 실패: {e}")


def _get_income_statement(args: dict) -> list[TextContent]:
    ticker = args["ticker"].upper()
    period = args.get("period", "annual")
    limit = int(args.get("limit", 4))

    data = _get("/financials/income-statements", {"ticker": ticker, "period": period, "limit": limit})
    items = data.get("income_statements", [])
    if not items:
        return _err(f"{ticker} 손익계산서 데이터 없음")

    lines = [f"[{ticker}] 손익계산서 ({period}) — {len(items)}개\n"]
    for s in items:
        rev = s.get("revenue")
        op_inc = s.get("operating_income")
        net_inc = s.get("net_income")
        gross = s.get("gross_profit")
        eps = s.get("earnings_per_share")
        op_margin = (op_inc / rev * 100) if (op_inc and rev) else None
        net_margin = (net_inc / rev * 100) if (net_inc and rev) else None

        lines += [
            f"  ── {s.get('report_period', '')} ({s.get('period', '')})",
            f"     매출액       : {_fmt_large(rev)}",
            f"     매출총이익    : {_fmt_large(gross)}",
            f"     영업이익      : {_fmt_large(op_inc)}  ({_fmt(op_margin, 1, '%')})",
            f"     순이익        : {_fmt_large(net_inc)}  ({_fmt(net_margin, 1, '%')})",
            f"     EPS           : {_fmt(eps, 2)}",
            "",
        ]

    return _ok("\n".join(lines))


def _get_balance_sheet(args: dict) -> list[TextContent]:
    ticker = args["ticker"].upper()
    period = args.get("period", "annual")
    limit = int(args.get("limit", 4))

    data = _get("/financials/balance-sheets", {"ticker": ticker, "period": period, "limit": limit})
    items = data.get("balance_sheets", [])
    if not items:
        return _err(f"{ticker} 대차대조표 데이터 없음")

    lines = [f"[{ticker}] 대차대조표 ({period}) — {len(items)}개\n"]
    for s in items:
        assets = s.get("total_assets")
        liab = s.get("total_liabilities")
        equity = s.get("shareholders_equity")
        cash = s.get("cash_and_equivalents")
        debt = s.get("total_debt")
        dte = (liab / equity) if (liab and equity) else None

        lines += [
            f"  ── {s.get('report_period', '')} ({s.get('period', '')})",
            f"     총자산        : {_fmt_large(assets)}",
            f"     총부채        : {_fmt_large(liab)}",
            f"     자기자본      : {_fmt_large(equity)}",
            f"     현금·현금성   : {_fmt_large(cash)}",
            f"     총차입금      : {_fmt_large(debt)}",
            f"     부채비율(D/E) : {_fmt(dte, 2, 'x')}",
            "",
        ]

    return _ok("\n".join(lines))


def _get_cash_flow(args: dict) -> list[TextContent]:
    ticker = args["ticker"].upper()
    period = args.get("period", "annual")
    limit = int(args.get("limit", 4))

    data = _get("/financials/cash-flow-statements", {"ticker": ticker, "period": period, "limit": limit})
    items = data.get("cash_flow_statements", [])
    if not items:
        return _err(f"{ticker} 현금흐름표 데이터 없음")

    lines = [f"[{ticker}] 현금흐름표 ({period}) — {len(items)}개\n"]
    for s in items:
        op = s.get("net_cash_flow_from_operations")
        inv = s.get("net_cash_flow_from_investing")
        fin = s.get("net_cash_flow_from_financing")
        fcf = s.get("free_cash_flow")
        capex = s.get("capital_expenditure")

        lines += [
            f"  ── {s.get('report_period', '')} ({s.get('period', '')})",
            f"     영업 현금흐름  : {_fmt_large(op)}",
            f"     투자 현금흐름  : {_fmt_large(inv)}",
            f"     재무 현금흐름  : {_fmt_large(fin)}",
            f"     설비투자(CapEx): {_fmt_large(capex)}",
            f"     잉여현금흐름   : {_fmt_large(fcf)}",
            "",
        ]

    return _ok("\n".join(lines))


def _get_company_news(args: dict) -> list[TextContent]:
    ticker = args.get("ticker", "")
    limit = min(int(args.get("limit", 5)), 10)

    params: dict = {"limit": limit}
    if ticker:
        params["ticker"] = ticker.upper()

    data = _get("/news", params)
    items = data.get("news", [])
    if not items:
        return _err("뉴스 데이터 없음")

    label = f"[{ticker.upper()} 뉴스]" if ticker else "[전체 시장 뉴스]"
    lines = [f"{label} — {len(items)}건\n"]
    for i, n in enumerate(items, 1):
        lines += [
            f"  {i}. {n.get('title', 'N/A')}",
            f"     출처: {n.get('source', 'N/A')}  |  {n.get('date', '')[:10]}",
            f"     URL: {n.get('url', 'N/A')}",
            "",
        ]

    return _ok("\n".join(lines))


def _get_crypto_price(args: dict) -> list[TextContent]:
    ticker = args["ticker"].upper()
    # BTC → BTC-USD 자동 변환 (페어 미지정 시 USD 기본)
    if "-" not in ticker:
        ticker = f"{ticker}-USD"
    interval = args.get("interval", "day")
    multiplier = int(args.get("interval_multiplier", 1))
    start = args["start_date"]
    end = args["end_date"]
    limit = int(args.get("limit", 10))

    data = _get("/crypto/prices", {
        "ticker": ticker,
        "interval": interval,
        "interval_multiplier": multiplier,
        "start_date": start,
        "end_date": end,
        "limit": limit,
    })

    prices = data.get("prices", [])
    if not prices:
        return _err(f"{ticker} 암호화폐 가격 데이터 없음")

    interval_label = f"{multiplier}{interval}"
    lines = [f"[{ticker}] 암호화폐 OHLC ({interval_label}) {start} ~ {end} — {len(prices)}개\n"]
    lines.append(f"  {'날짜':<12} {'시가':>12} {'고가':>12} {'저가':>12} {'종가':>12}")
    lines.append("  " + "-" * 55)
    for p in prices:
        lines.append(
            f"  {str(p.get('time',''))[:10]:<12} "
            f"{_fmt(p.get('open'), 2):>12} "
            f"{_fmt(p.get('high'), 2):>12} "
            f"{_fmt(p.get('low'), 2):>12} "
            f"{_fmt(p.get('close'), 2):>12}"
        )

    return _ok("\n".join(lines))


def _screen_stocks(args: dict) -> list[TextContent]:
    filters = args["filters"]
    period = args.get("period", "ttm")
    limit = int(args.get("limit", 10))

    data = _post("/financials/search/screener", {
        "filters": filters,
        "period": period,
        "limit": limit,
    })

    results = data.get("search_results", [])
    if not results:
        return _ok("조건에 맞는 종목이 없습니다. 필터 조건을 완화해보세요.")

    filter_summary = "  조건: " + ", ".join(
        f"{f['field']} {f['operator']} {f['value']}" for f in filters
    )
    lines = [
        f"[펀더멘털 스크리닝] ({period}) — {len(results)}종목 발견",
        filter_summary,
        "",
        f"  {'티커':<10} {'기간':<12} {'통화':>5}",
        "  " + "-" * 30,
    ]
    for r in results:
        lines.append(
            f"  {r.get('ticker',''):<10} {r.get('report_period',''):<12} {r.get('currency',''):>5}"
        )

    return _ok("\n".join(lines))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
