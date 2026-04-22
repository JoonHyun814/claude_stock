"""
MCP 서버 통합 테스트 — 결과를 Discord로 전송
"""
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv(Path(".env"))

DISCORD_URL   = os.environ["DISCORD_WEBHOOK_URL"]
AV_KEY        = os.environ["ALPHA_VANTAGE_API_KEY"]
FD_KEY        = os.environ["FINANCIAL_DATASETS_API_KEY"]
AV_BASE       = "https://www.alphavantage.co/query"
FD_BASE       = "https://api.financialdatasets.ai"

# ── 색상 상수 ──────────────────────────────────────────────────────────────────
GREEN  = 0x2ECC71
RED    = 0xE74C3C
BLUE   = 0x3498DB
YELLOW = 0xF1C40F
PURPLE = 0x9B59B6
GRAY   = 0x95A5A6

# ── 유틸 ───────────────────────────────────────────────────────────────────────
def fl(v, d=2):
    if v is None: return "N/A"
    for u, dv in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(v) >= dv: return f"{v/dv:.{d}f}{u}"
    return f"{v:,.{d}f}"

def send_embed(embed: dict):
    requests.post(DISCORD_URL, json={"embeds": [embed]}, timeout=10)
    time.sleep(0.5)  # Discord rate limit 방지

def result_line(ok: bool, label: str, detail: str = "") -> str:
    icon = "✅" if ok else "❌"
    return f"{icon} **{label}**{': ' + detail if detail else ''}"

def run_test(label: str, fn):
    """fn() 실행 후 (success, elapsed, value_or_error) 반환."""
    t0 = time.time()
    try:
        val = fn()
        return True, round(time.time() - t0, 2), val
    except Exception as e:
        return False, round(time.time() - t0, 2), str(e)

# ══════════════════════════════════════════════════════════════════════════════
# 1. Discord MCP
# ══════════════════════════════════════════════════════════════════════════════
def test_discord():
    results = []

    ok, t, _ = run_test("send_discord_message", lambda: requests.post(
        DISCORD_URL, json={"content": "🤖 MCP 통합 테스트 시작!"}, timeout=10
    ).raise_for_status())
    results.append((ok, "send_discord_message", f"{t}s"))

    ok, t, _ = run_test("send_stock_alert", lambda: requests.post(
        DISCORD_URL,
        json={"embeds": [{"title": "🟢 매수 신호 — TEST", "description": "테스트 알림", "color": GREEN}]},
        timeout=10,
    ).raise_for_status())
    results.append((ok, "send_stock_alert", f"{t}s"))

    return results

# ══════════════════════════════════════════════════════════════════════════════
# 2. Alpha Vantage MCP
# ══════════════════════════════════════════════════════════════════════════════
def av_get(params):
    params["apikey"] = AV_KEY
    r = requests.get(AV_BASE, params=params, timeout=15)
    d = r.json()
    if "Note" in d or "Information" in d:
        raise RuntimeError(list(d.values())[0][:60])
    return d

def test_alphavantage():
    results = []
    time.sleep(1.2)

    ok, t, val = run_test("get_ohlcv (AAPL daily)", lambda: av_get(
        {"function": "TIME_SERIES_DAILY", "symbol": "AAPL", "outputsize": "compact"}
    ))
    detail = ""
    if ok:
        series = val.get("Time Series (Daily)", {})
        date, v = next(iter(series.items()))
        detail = f"AAPL {date} C:{v['4. close']}"
    results.append((ok, "get_ohlcv", detail or val[:60] if not ok else detail))
    time.sleep(1.2)

    ok, t, val = run_test("get_rsi (AAPL)", lambda: av_get(
        {"function": "RSI", "symbol": "AAPL", "interval": "daily", "time_period": 14, "series_type": "close"}
    ))
    detail = ""
    if ok:
        rsi_data = val.get("Technical Analysis: RSI", {})
        date, v = next(iter(rsi_data.items()))
        detail = f"RSI({date})={float(v['RSI']):.2f}"
    results.append((ok, "get_rsi", detail or (val[:60] if not ok else detail)))
    time.sleep(1.2)

    ok, t, val = run_test("get_market_status", lambda: av_get({"function": "MARKET_STATUS"}))
    detail = ""
    if ok:
        markets = val.get("markets", [])
        us = next((m for m in markets if "United States" in m.get("region", "")), None)
        if us:
            detail = f"US={us.get('current_status','?')}, 총 {len(markets)}개국"
    results.append((ok, "get_market_status", detail or (val[:60] if not ok else detail)))
    time.sleep(1.2)

    ok, t, val = run_test("get_commodity_price (WTI)", lambda: av_get(
        {"function": "WTI", "interval": "monthly"}
    ))
    detail = ""
    if ok:
        entries = val.get("data", [])
        if entries:
            e = entries[0]
            detail = f"WTI {e['date']}={e['value']} {val.get('unit','')}"
    results.append((ok, "get_commodity_price", detail or (val[:60] if not ok else detail)))

    return results

# ══════════════════════════════════════════════════════════════════════════════
# 3. yfinance MCP
# ══════════════════════════════════════════════════════════════════════════════
def test_yfinance():
    results = []

    ok, t, val = run_test("get_realtime_price (NVDA)", lambda: _yf_realtime("NVDA"))
    results.append((ok, "get_realtime_price", val))

    ok, t, val = run_test("get_intraday_ohlcv (AAPL 5m)", lambda: _yf_intraday("AAPL", "5m"))
    results.append((ok, "get_intraday_ohlcv", val))

    ok, t, val = run_test("get_stock_info (MSFT)", lambda: _yf_info("MSFT"))
    results.append((ok, "get_stock_info", val))

    ok, t, val = run_test("get_multi_quote", lambda: _yf_multi(["AAPL","GOOGL","AMZN","TSLA","NVDA"]))
    results.append((ok, "get_multi_quote", val))

    ok, t, val = run_test("한국주식 (005930.KS)", lambda: _yf_realtime("005930.KS"))
    results.append((ok, "한국주식 (삼성전자)", val))

    return results

def _yf_realtime(sym):
    fi = yf.Ticker(sym).fast_info
    price = fi.last_price
    prev = fi.regular_market_previous_close or fi.previous_close
    pct = (price - prev) / prev * 100 if prev else 0
    arrow = "▲" if pct >= 0 else "▼"
    return f"{sym} {price:,.2f} {fi.currency} {arrow}{abs(pct):.2f}%"

def _yf_intraday(sym, interval):
    df = yf.Ticker(sym).history(period="1d", interval=interval)
    if df.empty:
        return f"{sym} 장 마감 (데이터 없음)"
    r = df.iloc[-1]
    return f"{sym} 최근봉 C:{r['Close']:.2f} V:{int(r['Volume']):,}"

def _yf_info(sym):
    info = yf.Ticker(sym).info
    return f"PER:{info.get('trailingPE','N/A')}  PBR:{info.get('priceToBook','N/A')}  섹터:{info.get('sector','N/A')}"

def _yf_multi(syms):
    out = []
    for s in syms:
        fi = yf.Ticker(s).fast_info
        price = fi.last_price
        prev = fi.regular_market_previous_close or fi.previous_close
        pct = (price - prev) / prev * 100 if prev else 0
        out.append(f"{s} {pct:+.1f}%")
    return " | ".join(out)

# ══════════════════════════════════════════════════════════════════════════════
# 4. MACD MCP
# ══════════════════════════════════════════════════════════════════════════════
def _ema(s, span): return s.ewm(span=span, adjust=False).mean()

def _calc_macd(close, fast=12, slow=26, signal=9):
    macd = _ema(close, fast) - _ema(close, slow)
    sig  = _ema(macd, signal)
    hist = macd - sig
    return pd.DataFrame({"MACD": macd, "Signal": sig, "Histogram": hist})

def _cross(hist):
    prev, curr = hist.iloc[-2], hist.iloc[-1]
    if prev < 0 and curr >= 0: return "골든크로스"
    if prev >= 0 and curr < 0: return "데드크로스"
    return "상승추세" if curr > 0 else "하락추세"

def test_macd():
    results = []

    ok, t, val = run_test("get_macd (AAPL daily)", lambda: _macd_single("AAPL"))
    results.append((ok, "get_macd (AAPL)", val))

    ok, t, val = run_test("get_macd_multi", lambda: _macd_multi(["AAPL","NVDA","MSFT","TSLA","005930.KS"]))
    results.append((ok, "get_macd_multi", val))

    return results

def _macd_single(sym):
    df = yf.Ticker(sym).history(period="6mo", interval="1d")
    m = _calc_macd(df["Close"])
    last = m.iloc[-1]
    signal = _cross(m["Histogram"])
    return f"MACD:{last['MACD']:.3f} Hist:{last['Histogram']:.3f} [{signal}]"

def _macd_multi(syms):
    out = []
    for s in syms:
        df = yf.Ticker(s).history(period="6mo", interval="1d")
        m = _calc_macd(df["Close"])
        out.append(f"{s}:{_cross(m['Histogram'])}")
    return "\n".join(out)

# ══════════════════════════════════════════════════════════════════════════════
# 5. Financial Datasets MCP
# ══════════════════════════════════════════════════════════════════════════════
def fd_get(path, params={}):
    r = requests.get(f"{FD_BASE}{path}", headers={"X-API-KEY": FD_KEY}, params=params, timeout=15)
    if r.status_code == 401: raise RuntimeError("API키 오류 또는 유료 플랜 전용")
    r.raise_for_status()
    return r.json()

def test_financialdatasets():
    results = []

    ok, t, val = run_test("get_income_statement (AAPL)", lambda: _fd_income("AAPL"))
    results.append((ok, "get_income_statement", val))

    ok, t, val = run_test("get_balance_sheet (AAPL)", lambda: _fd_balance("AAPL"))
    results.append((ok, "get_balance_sheet", val))

    ok, t, val = run_test("get_cash_flow (AAPL)", lambda: _fd_cashflow("AAPL"))
    results.append((ok, "get_cash_flow", val))

    ok, t, val = run_test("get_company_news (NVDA)", lambda: _fd_news("NVDA"))
    results.append((ok, "get_company_news", val))

    ok, t, val = run_test("get_crypto_price (BTC-USD)", lambda: fd_get(
        "/crypto/prices", {"ticker":"BTC-USD","interval":"day","interval_multiplier":1,
                           "start_date":"2026-04-20","end_date":"2026-04-22","limit":2}
    ))
    results.append((ok, "get_crypto_price", "유료 플랜 전용" if not ok else str(val)[:40]))

    ok, t, val = run_test("screen_stocks", lambda: requests.post(
        f"{FD_BASE}/financials/search/screener",
        headers={"X-API-KEY": FD_KEY},
        json={"filters":[{"field":"net_income","operator":"gt","value":10_000_000_000}],"period":"ttm","limit":5},
        timeout=15,
    ).json())
    results.append((ok, "screen_stocks", "유료 플랜 전용" if not ok else str(val)[:40]))

    return results

def _fd_income(sym):
    d = fd_get("/financials/income-statements", {"ticker": sym, "period": "annual", "limit": 1})
    s = d["income_statements"][0]
    return f"매출:{fl(s.get('revenue'))} 순익:{fl(s.get('net_income'))} EPS:{s.get('earnings_per_share')}"

def _fd_balance(sym):
    d = fd_get("/financials/balance-sheets", {"ticker": sym, "period": "annual", "limit": 1})
    s = d["balance_sheets"][0]
    eq = s.get("shareholders_equity"); liab = s.get("total_liabilities")
    dte = f"{liab/eq:.2f}x" if (eq and liab) else "N/A"
    return f"자산:{fl(s.get('total_assets'))} 자본:{fl(eq)} D/E:{dte}"

def _fd_cashflow(sym):
    d = fd_get("/financials/cash-flow-statements", {"ticker": sym, "period": "annual", "limit": 1})
    s = d["cash_flow_statements"][0]
    return f"영업CF:{fl(s.get('net_cash_flow_from_operations'))} FCF:{fl(s.get('free_cash_flow'))}"

def _fd_news(sym):
    d = fd_get("/news", {"ticker": sym, "limit": 1})
    n = d["news"][0]
    return f"[{n.get('date','')[:10]}] {n.get('title','')[:50]}"

# ══════════════════════════════════════════════════════════════════════════════
# Discord 전송
# ══════════════════════════════════════════════════════════════════════════════
def make_embed(title: str, color: int, results: list[tuple]) -> dict:
    passed = sum(1 for ok, _, _ in results if ok)
    total  = len(results)

    fields = []
    for ok, label, detail in results:
        icon = "✅" if ok else "❌"
        fields.append({
            "name": f"{icon} {label}",
            "value": f"```{detail}```" if detail else "완료",
            "inline": False,
        })

    return {
        "title": f"{title}  ({passed}/{total} 통과)",
        "color": GREEN if passed == total else (YELLOW if passed > 0 else RED),
        "fields": fields,
        "footer": {"text": f"테스트 시각: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }

# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════
def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("테스트 시작...")

    # 헤더 메시지
    requests.post(DISCORD_URL, json={"content": "## MCP 서버 통합 테스트 결과"}, timeout=10)
    time.sleep(0.5)

    suites = [
        ("[Discord MCP]",             BLUE,   test_discord),
        ("[Alpha Vantage MCP]",        PURPLE, test_alphavantage),
        ("[yfinance MCP]",             GREEN,  test_yfinance),
        ("[MACD Analyzer MCP]",        YELLOW, test_macd),
        ("[Financial Datasets MCP]",   BLUE,   test_financialdatasets),
    ]

    total_pass = total_fail = 0
    for title, color, fn in suites:
        print(f"  -> {title} 테스트 중...")
        results = fn()
        embed = make_embed(title, color, results)
        send_embed(embed)
        passed = sum(1 for ok, _, _ in results if ok)
        total_pass += passed
        total_fail += len(results) - passed

    # 최종 요약
    grand_total = total_pass + total_fail
    summary_color = GREEN if total_fail == 0 else (YELLOW if total_pass > 0 else RED)
    send_embed({
        "title": f"최종 결과: {total_pass}/{grand_total} 통과",
        "description": (
            f"성공: **{total_pass}개**\n"
            f"실패: **{total_fail}개**\n\n"
            "실패 항목은 유료 플랜 전용 엔드포인트이거나 API 한도 초과일 수 있습니다."
        ),
        "color": summary_color,
        "footer": {"text": "Stock MCP Suite — Claude Code"},
    })

    print(f"\n완료: {total_pass}/{grand_total} 통과")

if __name__ == "__main__":
    main()
