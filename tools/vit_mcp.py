"""
Value Investing Tools (VIT) MCP
- DCF 모델링: 잉여현금흐름 기반 내재가치 산출
- WACC 계산: CAPM + 부채비용
- 피어 벤치마킹: 섹터 동종업체 비교
- 데이터 품질 플래그: 신뢰도 경고
- 안전마진(MoS) 판단

데이터 소스: yfinance (무료, API 키 불필요)
"""
import asyncio
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("value-investing-tools")

MARKET_RISK_PREMIUM = 0.055  # 미국 주식 역사적 초과수익률 5.5%


# ── 유틸 ───────────────────────────────────────────────────────────────────────

def _ok(t: str) -> list[TextContent]:  return [TextContent(type="text", text=t)]
def _err(t: str) -> list[TextContent]: return [TextContent(type="text", text=f"오류: {t}")]

def _f(v, d=2, suffix="") -> str:
    return "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) \
           else f"{v:,.{d}f}{suffix}"

def _fl(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)): return "N/A"
    for u, dv in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(v) >= dv: return f"{v/dv:.2f}{u}"
    return f"{v:,.0f}"

def _pct(v) -> str:
    return "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) \
           else f"{v*100:.2f}%"


# ── 공통 데이터 로더 ───────────────────────────────────────────────────────────

def _get_rf() -> float:
    """10년 미국 국채 수익률 (소수)."""
    try:
        return yf.Ticker("^TNX").fast_info.last_price / 100
    except Exception:
        return 0.043  # 취득 실패 시 기본값 4.3%

def _load(symbol: str) -> dict:
    """종목의 핵심 재무 데이터를 딕셔너리로 반환."""
    t    = yf.Ticker(symbol)
    info = t.info
    fi   = t.fast_info
    cf   = t.cashflow
    bs   = t.balance_sheet
    inc  = t.income_stmt

    def _row(df: pd.DataFrame, key: str):
        return df.loc[key].dropna() if key in df.index else pd.Series(dtype=float)

    # FCF 히스토리 (최근 4개년, 오래된 것 → 최신 순 정렬)
    fcf_series = _row(cf, "Free Cash Flow").sort_index()
    fcf_values = [v for v in fcf_series.values if not np.isnan(v)]

    # 대차대조표
    total_debt   = _row(bs, "Total Debt").iloc[0]   if "Total Debt"   in bs.index else np.nan
    equity       = _row(bs, "Common Stock Equity").iloc[0] if "Common Stock Equity" in bs.index else np.nan
    cash         = _row(bs, "Cash Cash Equivalents And Short Term Investments").iloc[0] \
                   if "Cash Cash Equivalents And Short Term Investments" in bs.index else np.nan

    # 세율 (Tax Provision / Pretax Income)
    tax_prov   = _row(inc, "Tax Provision").iloc[0]  if "Tax Provision"  in inc.index else np.nan
    pretax_inc = _row(inc, "Pretax Income").iloc[0]  if "Pretax Income"  in inc.index else np.nan
    tax_rate   = (tax_prov / pretax_inc) if (not np.isnan(tax_prov) and pretax_inc and pretax_inc != 0) else 0.21

    # 이자비용
    int_exp = _row(inc, "Interest Expense Non Operating").iloc[0] \
              if "Interest Expense Non Operating" in inc.index else np.nan
    if np.isnan(int_exp):
        int_exp = _row(inc, "Interest Expense").iloc[0] if "Interest Expense" in inc.index else np.nan

    return {
        "symbol":           symbol.upper(),
        "name":             info.get("shortName", symbol),
        "sector":           info.get("sector", ""),
        "industry":         info.get("industry", ""),
        "current_price":    fi.last_price,
        "shares":           info.get("sharesOutstanding") or fi.shares,
        "beta":             info.get("beta"),
        "market_cap":       fi.market_cap,
        "fcf_values":       fcf_values,          # 오래된 → 최신
        "total_debt":       total_debt,
        "equity":           equity,
        "cash":             cash,
        "tax_rate":         tax_rate,
        "interest_expense": abs(int_exp) if not np.isnan(int_exp) else np.nan,
        # 추가 info 필드 (피어 벤치마킹용)
        "trailingPE":       info.get("trailingPE"),
        "forwardPE":        info.get("forwardPE"),
        "priceToBook":      info.get("priceToBook"),
        "returnOnEquity":   info.get("returnOnEquity"),
        "returnOnAssets":   info.get("returnOnAssets"),
        "profitMargins":    info.get("profitMargins"),
        "grossMargins":     info.get("grossMargins"),
        "revenueGrowth":    info.get("revenueGrowth"),
        "dividendYield":    info.get("dividendYield"),
        "debtToEquity":     info.get("debtToEquity"),
        "ebitda":           info.get("ebitda"),
        "enterpriseValue":  info.get("enterpriseValue"),
    }


# ── WACC ──────────────────────────────────────────────────────────────────────

def _calc_wacc(d: dict, rf: float, erp: float) -> tuple[float | None, list[str]]:
    """(wacc, flags) 반환."""
    flags = []
    beta  = d["beta"]
    debt  = d["total_debt"]
    eq    = d["equity"]
    tx    = d["tax_rate"]
    int_e = d["interest_expense"]

    if beta is None:
        flags.append("⚠️ Beta 데이터 없음 — Beta=1.0 적용")
        beta = 1.0

    ke = rf + beta * erp  # 자기자본비용 (CAPM)

    if np.isnan(debt) or np.isnan(eq):
        flags.append("⚠️ 부채/자본 데이터 없음 — WACC = 자기자본비용만 사용")
        return ke, flags

    if eq <= 0:
        flags.append("⚠️ 자기자본이 음수 — WACC 신뢰도 낮음")

    total = debt + eq
    we    = eq   / total  if total > 0 else 1.0
    wd    = debt / total  if total > 0 else 0.0

    if np.isnan(int_e) or debt == 0:
        kd = rf + 0.02  # 이자 데이터 없으면 무위험+2%
        flags.append("⚠️ 이자비용 데이터 없음 — 부채비용 = Rf+2% 추정")
    else:
        kd = int_e / debt

    wacc = ke * we + kd * (1 - tx) * wd
    return wacc, flags


# ── DCF ───────────────────────────────────────────────────────────────────────

def _calc_dcf(d: dict, wacc: float, g1: float, g_terminal: float,
              years: int) -> tuple[float | None, list[str]]:
    """(intrinsic_value_per_share, flags) 반환."""
    flags  = []
    fcf_v  = d["fcf_values"]   # 오래된 → 최신
    shares = d["shares"]
    debt   = d["total_debt"]
    cash   = d["cash"]

    if len(fcf_v) < 2:
        return None, ["❌ FCF 데이터 부족 (최소 2년 필요)"]

    base_fcf = fcf_v[-1]  # 가장 최근 FCF

    if base_fcf <= 0:
        flags.append("⚠️ 최근 FCF 음수 — DCF 신뢰도 낮음 (절대값 사용)")
        base_fcf = abs(base_fcf)

    # FCF 역사적 성장률 계산
    if len(fcf_v) >= 2 and fcf_v[0] > 0 and fcf_v[-1] > 0:
        hist_growth = (fcf_v[-1] / fcf_v[0]) ** (1 / (len(fcf_v) - 1)) - 1
        if hist_growth < 0:
            flags.append(f"⚠️ FCF 하락 추세 (역사적 성장률 {hist_growth*100:.1f}%)")
        if hist_growth > 0.5:
            flags.append(f"⚠️ FCF 성장률 과대 추정 위험 (역사적 {hist_growth*100:.1f}% → 입력 {g1*100:.1f}% 사용)")
    else:
        flags.append("⚠️ FCF 성장률 계산 불가 (음수 포함) — 입력값 사용")

    if g_terminal >= wacc:
        flags.append(f"❌ 영구성장률({g_terminal*100:.1f}%) ≥ WACC({wacc*100:.1f}%) — 모델 성립 불가")
        return None, flags

    # FCF 프로젝션
    projected = []
    for i in range(1, years + 1):
        projected.append(base_fcf * (1 + g1) ** i)

    # 터미널 밸류 (고든 성장 모델)
    fcf_terminal = projected[-1] * (1 + g_terminal)
    terminal_val = fcf_terminal / (wacc - g_terminal)

    # 현재 가치 할인
    pv_fcf = sum(fcf / (1 + wacc) ** i for i, fcf in enumerate(projected, 1))
    pv_tv  = terminal_val / (1 + wacc) ** years

    enterprise_value = pv_fcf + pv_tv

    # 자기자본 가치 = EV + 현금 - 부채
    net_cash = (cash if not np.isnan(cash) else 0) - (debt if not np.isnan(debt) else 0)
    equity_value = enterprise_value + net_cash

    if not shares or shares <= 0:
        return None, flags + ["❌ 발행주식수 데이터 없음"]

    iv_per_share = equity_value / shares
    return iv_per_share, flags


# ── 데이터 품질 플래그 ─────────────────────────────────────────────────────────

def _quality_flags(d: dict) -> list[str]:
    flags = []
    fcf_v = d["fcf_values"]

    if not fcf_v:
        flags.append("❌ FCF 데이터 없음")
    elif any(v < 0 for v in fcf_v):
        neg_cnt = sum(1 for v in fcf_v if v < 0)
        flags.append(f"⚠️ FCF 음수 연도 {neg_cnt}개 — 사업 현금창출력 점검 필요")

    if not np.isnan(d["total_debt"]) and not np.isnan(d["equity"]):
        dte = d["total_debt"] / d["equity"] if d["equity"] > 0 else float("inf")
        if dte > 3:
            flags.append(f"⚠️ 부채비율 높음 (D/E={dte:.1f}x) — 재무 레버리지 위험")
        if d["equity"] <= 0:
            flags.append("❌ 자기자본 음수 — 기술적 부도 상태")

    if d["beta"] is None:
        flags.append("⚠️ Beta 데이터 없음")
    elif d["beta"] > 2:
        flags.append(f"⚠️ 고베타({d['beta']:.2f}) — 높은 변동성")

    if len(fcf_v) < 4:
        flags.append(f"⚠️ FCF 히스토리 {len(fcf_v)}년 — 4년 이상 권장")

    if not flags:
        flags.append("✅ 데이터 품질 양호")

    return flags


# ── 안전마진 판단 ──────────────────────────────────────────────────────────────

def _mos_label(mos_pct: float) -> str:
    if mos_pct >= 40:   return "강력 매수 (MoS ≥ 40%)"
    if mos_pct >= 20:   return "매수 (MoS 20~40%)"
    if mos_pct >= 0:    return "보유 (MoS 0~20%)"
    if mos_pct >= -20:  return "과대평가 (0~20% 초과)"
    return "심각한 과대평가 (20%+ 초과)"


# ══════════════════════════════════════════════════════════════════════════════
# Tool definitions
# ══════════════════════════════════════════════════════════════════════════════

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="calc_wacc",
            description=(
                "WACC(가중평균자본비용)를 계산합니다.\n"
                "자기자본비용: CAPM = Rf + β × ERP\n"
                "부채비용: 이자비용 / 총부채 × (1 - 세율)\n"
                "Rf: 미국 10년 국채 수익률 자동 조회. API 키 불필요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "티커 심볼 (예: AAPL, MSFT)"},
                    "equity_risk_premium": {
                        "type": "number",
                        "default": 0.055,
                        "description": "시장 위험 프리미엄 (기본 5.5% = 0.055)",
                    },
                    "rf_override": {
                        "type": "number",
                        "description": "위험무위험수익률 직접 입력 (생략 시 ^TNX 자동 조회)",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="calc_dcf",
            description=(
                "DCF(현금흐름할인법)으로 주식 내재가치를 계산합니다.\n"
                "FCF 히스토리 → 성장률 적용 → 터미널 밸류 → WACC 할인 → 주당 내재가치.\n"
                "안전마진(Margin of Safety) 자동 계산 포함. API 키 불필요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "growth_rate": {
                        "type": "number",
                        "default": 0.08,
                        "description": "예측 기간 FCF 성장률 (기본 8% = 0.08)",
                    },
                    "terminal_growth_rate": {
                        "type": "number",
                        "default": 0.03,
                        "description": "영구 성장률 (기본 3% = 0.03, GDP 성장률 수준)",
                    },
                    "projection_years": {
                        "type": "integer",
                        "default": 10,
                        "description": "현금흐름 예측 기간 (기본 10년)",
                    },
                    "wacc_override": {
                        "type": "number",
                        "description": "WACC 직접 입력 (생략 시 자동 계산)",
                    },
                    "equity_risk_premium": {
                        "type": "number",
                        "default": 0.055,
                        "description": "시장 위험 프리미엄 (기본 5.5%)",
                    },
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="peer_benchmark",
            description=(
                "대상 종목과 동종업체(피어)를 주요 밸류에이션·수익성 지표로 비교합니다.\n"
                "PER·PBR·ROE·순이익률·EV/EBITDA·배당수익률 등 포함.\n"
                "피어 평균 대비 저평가/고평가 여부를 분석합니다."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "분석 대상 티커"},
                    "peers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "비교할 동종업체 티커 목록 (2~8개 권장)",
                    },
                },
                "required": ["symbol", "peers"],
            },
        ),
        Tool(
            name="value_summary",
            description=(
                "종합 가치투자 분석 리포트를 생성합니다.\n"
                "WACC 계산 → DCF 내재가치 → 안전마진 → 데이터 품질 플래그 → 투자 판단.\n"
                "버핏·그레이엄 스타일 장기 가치투자 평가에 최적화."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "growth_rate": {
                        "type": "number",
                        "default": 0.08,
                        "description": "FCF 성장률 가정 (기본 8%)",
                    },
                    "terminal_growth_rate": {
                        "type": "number",
                        "default": 0.03,
                        "description": "영구 성장률 (기본 3%)",
                    },
                    "projection_years": {
                        "type": "integer",
                        "default": 10,
                    },
                    "equity_risk_premium": {
                        "type": "number",
                        "default": 0.055,
                    },
                    "peers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "비교 동종업체 (선택사항)",
                    },
                },
                "required": ["symbol"],
            },
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Tool handlers
# ══════════════════════════════════════════════════════════════════════════════

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "calc_wacc":        return _handle_wacc(arguments)
        if name == "calc_dcf":         return _handle_dcf(arguments)
        if name == "peer_benchmark":   return _handle_peer(arguments)
        if name == "value_summary":    return _handle_summary(arguments)
        return _err(f"알 수 없는 tool: {name}")
    except Exception as e:
        return _err(str(e))


def _handle_wacc(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    erp    = float(args.get("equity_risk_premium", 0.055))
    rf_ov  = args.get("rf_override")

    d  = _load(symbol)
    rf = float(rf_ov) if rf_ov is not None else _get_rf()
    wacc, flags = _calc_wacc(d, rf, erp)

    beta   = d["beta"] or 1.0
    ke     = rf + beta * erp
    debt   = d["total_debt"]
    eq     = d["equity"]
    int_e  = d["interest_expense"]
    tx     = d["tax_rate"]

    kd_pre  = (int_e / debt) if (not np.isnan(int_e) and not np.isnan(debt) and debt > 0) else rf + 0.02
    kd_post = kd_pre * (1 - tx)
    total   = (debt if not np.isnan(debt) else 0) + (eq if not np.isnan(eq) else 0)
    we      = (eq / total) if (total > 0 and not np.isnan(eq)) else 1.0
    wd      = 1 - we

    lines = [
        f"[{symbol}] WACC 계산",
        f"  {d['name']}  |  섹터: {d['sector']}",
        "",
        "  ▶ 자기자본비용 (CAPM)",
        f"    Rf (무위험수익률)    : {rf*100:.3f}%",
        f"    β (베타)            : {_f(beta)}",
        f"    ERP (시장위험프리미엄): {erp*100:.1f}%",
        f"    Ke = Rf + β×ERP    : {ke*100:.3f}%",
        "",
        "  ▶ 부채비용",
        f"    총부채              : {_fl(debt)}",
        f"    이자비용            : {_fl(int_e)}",
        f"    세율                : {tx*100:.1f}%",
        f"    Kd(세전)            : {kd_pre*100:.3f}%",
        f"    Kd(세후)            : {kd_post*100:.3f}%",
        "",
        "  ▶ 자본구조",
        f"    자기자본            : {_fl(eq)}  ({we*100:.1f}%)",
        f"    총부채              : {_fl(debt)}  ({wd*100:.1f}%)",
        "",
        f"  ══ WACC = {wacc*100:.3f}% ══",
        "",
        "  데이터 플래그:",
    ] + [f"    {f}" for f in flags]

    return _ok("\n".join(lines))


def _handle_dcf(args: dict) -> list[TextContent]:
    symbol  = args["symbol"].upper()
    g1      = float(args.get("growth_rate", 0.08))
    g_t     = float(args.get("terminal_growth_rate", 0.03))
    years   = int(args.get("projection_years", 10))
    erp     = float(args.get("equity_risk_premium", 0.055))
    wacc_ov = args.get("wacc_override")

    d  = _load(symbol)
    rf = _get_rf()

    if wacc_ov is not None:
        wacc       = float(wacc_ov)
        wacc_flags = ["(WACC 직접 입력)"]
    else:
        wacc, wacc_flags = _calc_wacc(d, rf, erp)

    iv, dcf_flags = _calc_dcf(d, wacc, g1, g_t, years)
    q_flags       = _quality_flags(d)
    price         = d["current_price"]

    fcf_v   = d["fcf_values"]
    base    = abs(fcf_v[-1]) if fcf_v else 0
    proj    = [base * (1 + g1) ** i for i in range(1, years + 1)]

    lines = [
        f"[{symbol}] DCF 내재가치 분석",
        f"  {d['name']}  |  섹터: {d['sector']}",
        "",
        "  ▶ 입력 가정",
        f"    WACC              : {wacc*100:.3f}%",
        f"    FCF 성장률        : {g1*100:.1f}%",
        f"    영구 성장률       : {g_t*100:.1f}%",
        f"    예측 기간         : {years}년",
        "",
        "  ▶ FCF 히스토리 (오래된→최신)",
    ]
    for i, v in enumerate(fcf_v):
        lines.append(f"    Year-{len(fcf_v)-i}  {_fl(v)}")

    lines += [
        "",
        f"  ▶ FCF 예측 (기준 FCF: {_fl(base)})",
        f"    {'연도':<6} {'FCF':>12}",
        "    " + "─" * 20,
    ]
    for i, p in enumerate(proj[:5], 1):   # 앞 5년만 표시
        lines.append(f"    {i}년    {_fl(p):>12}")
    if years > 5:
        lines.append(f"    ...   (중략)")
        lines.append(f"    {years}년    {_fl(proj[-1]):>12}")

    lines.append("")

    if iv is not None:
        mos    = (iv - price) / iv * 100 if iv > 0 else float("-inf")
        label  = _mos_label(mos)
        lines += [
            f"  ══ 결과 ══",
            f"    주당 내재가치  : {_f(iv)} USD",
            f"    현재 주가      : {_f(price)} USD",
            f"    안전마진(MoS)  : {mos:+.1f}%  →  {label}",
        ]
    else:
        lines.append("  ❌ 내재가치 계산 실패")

    all_flags = wacc_flags + dcf_flags + q_flags
    lines += ["", "  ▶ 데이터 품질 플래그"] + [f"    {f}" for f in all_flags]

    return _ok("\n".join(lines))


def _handle_peer(args: dict) -> list[TextContent]:
    symbol = args["symbol"].upper()
    peers  = [p.upper() for p in args["peers"]]
    all_s  = [symbol] + peers

    metrics = [
        ("trailingPE",    "PER(TTM)",   lambda v: _f(v, 1)),
        ("forwardPE",     "PER(Fwd)",   lambda v: _f(v, 1)),
        ("priceToBook",   "PBR",        lambda v: _f(v, 2)),
        ("returnOnEquity","ROE",        lambda v: _pct(v)),
        ("profitMargins", "순이익률",   lambda v: _pct(v)),
        ("grossMargins",  "매출총이익",  lambda v: _pct(v)),
        ("revenueGrowth", "매출성장",   lambda v: _pct(v)),
        ("dividendYield", "배당",       lambda v: _pct(v)),
        ("debtToEquity",  "D/E",        lambda v: _f(v, 1)),
        ("beta",          "Beta",       lambda v: _f(v, 2)),
    ]

    rows: dict[str, dict] = {}
    for s in all_s:
        try:
            rows[s] = _load(s)
        except Exception:
            rows[s] = {}

    lines = [f"[피어 벤치마킹] {symbol} vs {', '.join(peers)}\n"]

    # 헤더
    header_cols = ["지표"] + [f"{s:>10}" for s in all_s] + [f"{'피어평균':>10}"]
    lines.append("  " + "  ".join(header_cols))
    lines.append("  " + "─" * (14 + 13 * len(all_s)))

    for field, label, fmt in metrics:
        vals = {s: rows[s].get(field) for s in all_s}
        peer_nums = [vals[s] for s in peers if vals[s] is not None]
        peer_avg  = np.mean(peer_nums) if peer_nums else None

        row = [f"{label:<12}"] + [f"{fmt(vals[s]):>10}" for s in all_s] + [f"{fmt(peer_avg):>10}"]
        lines.append("  " + "  ".join(row))

    # 저평가 요약
    lines += ["", "  ▶ 저평가 지표 (대상 < 피어 평균)"]
    undervalued = []
    for field, label, fmt in metrics:
        tv  = rows[symbol].get(field)
        pvs = [rows[s].get(field) for s in peers if rows[s].get(field) is not None]
        if not pvs or tv is None: continue
        pavg = np.mean(pvs)
        # PER, PBR, D/E, Beta는 낮을수록 유리
        low_better = field in ("trailingPE","forwardPE","priceToBook","debtToEquity","beta")
        if low_better and tv < pavg:
            undervalued.append(f"    ✅ {label}: {fmt(tv)} < 피어평균 {fmt(pavg)}")
        elif not low_better and tv > pavg:
            undervalued.append(f"    ✅ {label}: {fmt(tv)} > 피어평균 {fmt(pavg)}")

    lines += undervalued if undervalued else ["    해당 없음"]
    return _ok("\n".join(lines))


def _handle_summary(args: dict) -> list[TextContent]:
    symbol  = args["symbol"].upper()
    g1      = float(args.get("growth_rate", 0.08))
    g_t     = float(args.get("terminal_growth_rate", 0.03))
    years   = int(args.get("projection_years", 10))
    erp     = float(args.get("equity_risk_premium", 0.055))
    peers   = [p.upper() for p in args.get("peers", [])]

    d     = _load(symbol)
    rf    = _get_rf()
    wacc, wacc_flags = _calc_wacc(d, rf, erp)
    iv, dcf_flags    = _calc_dcf(d, wacc, g1, g_t, years)
    q_flags          = _quality_flags(d)
    price            = d["current_price"]

    all_flags = wacc_flags + dcf_flags + q_flags
    bad_flags = [f for f in all_flags if f.startswith("❌")]
    warn_flags = [f for f in all_flags if f.startswith("⚠️")]

    mos_str = label = "계산 불가"
    if iv is not None:
        mos   = (iv - price) / iv * 100 if iv > 0 else float("-inf")
        mos_str = f"{mos:+.1f}%"
        label = _mos_label(mos)

    lines = [
        f"╔══ [{symbol}] 가치투자 종합 분석 ══╗",
        f"  {d['name']}",
        f"  섹터: {d['sector']}  |  산업: {d['industry']}",
        f"  시가총액: {_fl(d['market_cap'])}  |  현재가: {_f(price)} USD",
        "",
        "━━ WACC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  Rf={rf*100:.2f}%  β={_f(d['beta'])}  ERP={erp*100:.1f}%",
        f"  자기자본비용(Ke) : {(rf + (d['beta'] or 1.0)*erp)*100:.3f}%",
        f"  WACC            : {wacc*100:.3f}%",
        "",
        "━━ DCF 내재가치 ━━━━━━━━━━━━━━━━━━━━━━",
        f"  FCF 히스토리    : {' → '.join(_fl(v) for v in d['fcf_values'])}",
        f"  성장률 가정     : {g1*100:.1f}% ({years}년) → 영구 {g_t*100:.1f}%",
        f"  주당 내재가치   : {_f(iv)} USD",
        f"  현재 주가       : {_f(price)} USD",
        f"  안전마진(MoS)   : {mos_str}",
        f"  투자 판단       : {label}",
        "",
        "━━ 주요 밸류에이션 ━━━━━━━━━━━━━━━━━━━",
        f"  PER(TTM)  : {_f(d['trailingPE'], 1)}  |  PBR: {_f(d['priceToBook'], 2)}",
        f"  ROE       : {_pct(d['returnOnEquity'])}  |  순이익률: {_pct(d['profitMargins'])}",
        f"  배당수익률: {_pct(d['dividendYield'])}  |  D/E: {_f(d['debtToEquity'], 1)}",
        f"  매출성장  : {_pct(d['revenueGrowth'])}  |  이익성장: {_pct(d.get('earningsGrowth'))}",
    ]

    if bad_flags:
        lines += ["", "━━ 데이터 오류 ━━━━━━━━━━━━━━━━━━━━━━━"] + [f"  {f}" for f in bad_flags]
    if warn_flags:
        lines += ["", "━━ 경고 플래그 ━━━━━━━━━━━━━━━━━━━━━━━"] + [f"  {f}" for f in warn_flags]

    if peers:
        lines += ["", "━━ 피어 요약 ━━━━━━━━━━━━━━━━━━━━━━━━━"]
        for ps in peers:
            try:
                pd_ = _load(ps)
                lines.append(
                    f"  {ps:<8} PER:{_f(pd_['trailingPE'],1):>6}  "
                    f"ROE:{_pct(pd_['returnOnEquity']):>7}  "
                    f"순이익률:{_pct(pd_['profitMargins']):>7}"
                )
            except Exception:
                lines.append(f"  {ps}: 조회 실패")

    lines.append("╚" + "═" * 40 + "╝")
    return _ok("\n".join(lines))


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
