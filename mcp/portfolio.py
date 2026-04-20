import sys
import io
import json
import yfinance as yf
from datetime import datetime
from pathlib import Path

# Windows 터미널 UTF-8 출력 설정
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TROY_OZ_TO_GRAM = 31.1035
GOLD_TICKER = "GC=F"
USD_KRW_TICKER = "USDKRW=X"

# mcp/ 안에서 실행하든 루트에서 실행하든 holdings.json을 찾도록
_DEFAULT_HOLDINGS = Path(__file__).parent.parent / "holdings.json"


def load_holdings(filepath=None):
    path = Path(filepath) if filepath else _DEFAULT_HOLDINGS
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_ticker_data(ticker_symbol):
    t = yf.Ticker(ticker_symbol)
    hist = t.history(period="5d")
    if hist.empty:
        return None, None, None
    info = t.info
    current = hist["Close"].iloc[-1]
    prev = hist["Close"].iloc[-2] if len(hist) >= 2 else current
    return current, prev, info


def change_str(change, pct, currency=""):
    sign = "+" if change >= 0 else ""
    arrow = "▲" if change >= 0 else "▼"
    return f"{arrow} {sign}{change:,.2f} {currency} ({sign}{pct:.2f}%)"


def range_bar(current, low, high, width=20):
    if high == low:
        return "[" + "-" * width + "]"
    pos = int((current - low) / (high - low) * width)
    pos = max(0, min(width, pos))
    bar = "[" + "-" * pos + "●" + "-" * (width - pos) + "]"
    return bar


def print_section(title):
    print()
    print("=" * 62)
    print(f"  {title}")
    print("=" * 62)


def print_stock(name, ticker, quantity, current, prev, info, currency="KRW"):
    change = current - prev
    pct = (change / prev * 100) if prev else 0
    total_value = current * quantity

    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    div_yield = info.get("dividendYield")
    avg_vol = info.get("averageVolume")
    mkt_cap = info.get("marketCap")

    fmt = "," if currency == "KRW" else ",.2f"

    print(f"\n  [{name}]  {ticker}  |  보유: {quantity}주")
    print(f"  현재가   : {current:{fmt}} {currency}")
    print(f"  전일 대비: {change_str(change, pct, currency)}")
    print(f"  보유 평가: {total_value:{fmt}} {currency}  (={quantity}주 × {current:{fmt}})")

    if high52 and low52:
        bar = range_bar(current, low52, high52)
        print(f"  52주 범위: {low52:{fmt}} {bar} {high52:{fmt}}")

    details = []
    if pe:
        details.append(f"P/E {pe:.1f}")
    if pb:
        details.append(f"P/B {pb:.1f}")
    if div_yield:
        details.append(f"배당률 {div_yield*100:.2f}%")
    if avg_vol:
        details.append(f"평균거래량 {avg_vol:,}")
    if details:
        print(f"  기타     : {' | '.join(details)}")

    return total_value


def print_gold(quantity_grams, usd_to_krw=None):
    current_oz, prev_oz, info = fetch_ticker_data(GOLD_TICKER)
    if current_oz is None:
        print("\n  [금 현물] 데이터를 가져올 수 없습니다.")
        return 0, 0

    current_g = current_oz / TROY_OZ_TO_GRAM
    prev_g = prev_oz / TROY_OZ_TO_GRAM
    change_g = current_g - prev_g
    pct = (change_g / prev_g * 100) if prev_g else 0
    total_usd = current_g * quantity_grams

    print(f"\n  [금 현물 1g × {quantity_grams}]  GC=F (선물 기준)")
    print(f"  현재가 (1g) : ${current_g:.4f} / ${current_oz:,.2f} per troy oz")
    print(f"  전일 대비   : {change_str(change_g, pct, 'USD')}")
    print(f"  보유 평가   : ${total_usd:.4f} USD  ({quantity_grams}g × ${current_g:.4f})")

    if usd_to_krw:
        total_krw = total_usd * usd_to_krw
        print(f"                 ({total_krw:,.0f} KRW  환율 {usd_to_krw:,.0f} 기준)")

    return total_usd, change_g * quantity_grams


def main():
    print(f"\n{'':=<62}")
    print(f"  포트폴리오 현황  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'':=<62}")

    holdings = load_holdings()

    # USD/KRW 환율 조회
    usd_krw = None
    try:
        fx_cur, _, _ = fetch_ticker_data(USD_KRW_TICKER)
        if fx_cur:
            usd_krw = fx_cur
            print(f"\n  USD/KRW 환율: {usd_krw:,.2f}")
    except Exception:
        pass

    total_krw = 0.0
    total_usd = 0.0

    # ── 국내 주식 ──────────────────────────────────────────────
    print_section("국내 주식 (KRW)")
    for s in holdings["holdings"]["korean_stocks"]:
        cur, prev, info = fetch_ticker_data(s["ticker"])
        if cur is None:
            print(f"\n  [{s['name']}] 데이터를 가져올 수 없습니다. (ticker: {s['ticker']})")
            continue
        val = print_stock(s["name"], s["ticker"], s["quantity"], cur, prev, info, "KRW")
        total_krw += val

    print(f"\n  국내 주식 소계: {total_krw:,.0f} KRW")

    # ── 해외 주식 ──────────────────────────────────────────────
    print_section("해외 주식 (USD)")
    for s in holdings["holdings"]["foreign_stocks"]:
        cur, prev, info = fetch_ticker_data(s["ticker"])
        if cur is None:
            print(f"\n  [{s['name']}] 데이터를 가져올 수 없습니다. (ticker: {s['ticker']})")
            continue
        val = print_stock(s["name"], s["ticker"], s["quantity"], cur, prev, info, "USD")
        total_usd += val

    print(f"\n  해외 주식 소계: ${total_usd:,.2f} USD")
    if usd_krw:
        print(f"                 ({total_usd * usd_krw:,.0f} KRW 환산)")

    # ── 금 현물 ───────────────────────────────────────────────
    print_section("금 현물 (USD)")
    gold_items = holdings["holdings"]["gold"]
    total_grams = sum(g["quantity"] for g in gold_items)
    gold_usd, _ = print_gold(total_grams, usd_to_krw=usd_krw)
    total_usd += gold_usd

    # ── 포트폴리오 총합 ────────────────────────────────────────
    print_section("포트폴리오 총합")
    print(f"\n  국내 주식    : {total_krw:>14,.0f} KRW")
    print(f"  해외+금 합계 : {total_usd:>14,.2f} USD")
    if usd_krw:
        grand_total_krw = total_krw + (total_usd * usd_krw)
        print(f"  ─────────────────────────────────────")
        print(f"  총 평가금액  : {grand_total_krw:>14,.0f} KRW  (환율 {usd_krw:,.0f} 기준)")
    print()


if __name__ == "__main__":
    main()
