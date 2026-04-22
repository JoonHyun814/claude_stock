# Stock MCP Tools

주식 투자 분석을 위한 Claude Code MCP 서버 모음입니다.

---

## 설치

```bash
pip install -r tools/requirements.txt
```

## MCP 등록

`.claude/mcp_servers.json`에 이미 등록되어 있습니다.  
Claude Code 재시작 후 자동으로 활성화됩니다.

---

## MCP 서버 목록

### 1. `discord_mcp.py` — Discord 알림

Discord 웹훅으로 메시지 및 주식 알림을 전송합니다.

**필요 환경변수**
```
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/...
```

| Tool | 설명 |
|------|------|
| `send_discord_message` | 일반 텍스트 / embed 메시지 전송. username·embeds 옵션 지원 |
| `send_stock_alert` | 매수·매도·가격알림·정보 유형별 색상 embed 자동 생성 |

**`send_stock_alert` alert_type**

| 값 | 색상 | 용도 |
|----|------|------|
| `buy` | 초록 | 매수 신호 |
| `sell` | 빨강 | 매도 신호 |
| `price_alert` | 노랑 | 가격 돌파 알림 |
| `info` | 파랑 | 일반 정보 |

---

### 2. `alphavantage_mcp.py` — Alpha Vantage 시장 데이터

Alpha Vantage API 기반 주가·기술지표·원자재 데이터.

**필요 환경변수**
```
ALPHA_VANTAGE_API_KEY=your_api_key
```
> API 키 발급: https://www.alphavantage.co/support/#api-key  
> 무료 플랜: 25회/일, 5회/분

| Tool | 플랜 | 설명 |
|------|------|------|
| `get_ohlcv` | 무료 | daily·weekly·monthly OHLCV. intraday(1m~60m)는 유료 전용 |
| `get_rsi` | 무료 | RSI(기본 14기간). 과매수(≥70)·과매도(≤30) 신호 포함 |
| `get_macd` | **유료** | MACD 라인·시그널·히스토그램. 무료 대안은 `macd_mcp.py` 사용 |
| `get_market_status` | 무료 | 전 세계 주요 시장 개장·폐장 상태 |
| `get_commodity_price` | 무료 | WTI·브렌트·천연가스·구리·알루미늄·밀·옥수수·면화·설탕·커피 |

**지원 원자재**

| 티커 | 품목 | 단위 |
|------|------|------|
| `WTI` | 서부텍사스 원유 | $/배럴 |
| `BRENT` | 브렌트 원유 | $/배럴 |
| `NATURAL_GAS` | 천연가스 | $/MMBtu |
| `COPPER` | 구리 | $/톤 |
| `ALUMINUM` | 알루미늄 | $/톤 |
| `WHEAT` | 밀 | $/톤 |
| `CORN` | 옥수수 | $/톤 |
| `COTTON` | 면화 | $/파운드 |
| `SUGAR` | 설탕 | $/파운드 |
| `COFFEE` | 커피 | $/파운드 |

---

### 3. `yfinance_mcp.py` — Yahoo Finance 실시간 주가

yfinance 기반. **API 키 불필요, 완전 무료.**  
미국·한국·글로벌 거래소 지원.

> 한국 주식 티커: 코스피는 `.KS`, 코스닥은 `.KQ` 접미사  
> 예) 삼성전자 `005930.KS` / 카카오 `035720.KQ`

| Tool | 설명 |
|------|------|
| `get_realtime_price` | 현재가·등락률·거래량·시총·52주 고저가. 복수 심볼 지원 |
| `get_intraday_ohlcv` | 1m~90m 분봉 OHLCV. 1분봉=최근 7일, 5~90분봉=최근 60일 |
| `get_stock_info` | PER·PBR·EPS·베타·배당수익률·섹터·산업군 등 펀더멘털 |
| `get_multi_quote` | 최대 20종목 현재가 일괄 비교 |

**`get_intraday_ohlcv` 조회 가능 기간**

| interval | 최대 기간 |
|----------|-----------|
| `1m` | 7일 |
| `2m` · `5m` · `15m` · `30m` · `90m` | 60일 |
| `60m` | 730일 |

---

### 4. `macd_mcp.py` — 무료 MACD 분석

yfinance + pandas EMA 직접 계산. **API 키 불필요, 완전 무료.**  
Alpha Vantage MACD(유료)의 무료 대안.

**MACD 계산 공식**
```
MACD line   = EMA(fast) - EMA(slow)
Signal line = EMA(signal, MACD line)
Histogram   = MACD line - Signal line
```

| Tool | 설명 |
|------|------|
| `get_macd` | 단일 종목 MACD 상세. 날짜별 MACD·시그널·히스토그램 + 크로스 감지 |
| `get_macd_multi` | 최대 10종목 MACD 현황 일괄 비교 |

**크로스 신호 감지**

| 조건 | 신호 |
|------|------|
| 히스토그램 음→양 전환 | 골든크로스 (상승 전환) |
| 히스토그램 양→음 전환 | 데드크로스 (하락 전환) |
| 히스토그램 > 0 유지 | 상승 추세 |
| 히스토그램 < 0 유지 | 하락 추세 |

**기본 파라미터 (변경 가능)**

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `fast` | 12 | 단기 EMA 기간 |
| `slow` | 26 | 장기 EMA 기간 |
| `signal` | 9 | 시그널 EMA 기간 |
| `interval` | `1d` | 봉 주기 |
| `period` | `6mo` | 데이터 조회 기간 |

---

### 5. `financialdatasets_mcp.py` — Financial Datasets 재무제표·스크리닝

Financial Datasets API 기반 재무제표·기업 뉴스·암호화폐·펀더멘털 스크리닝.  
미국 상장 주식 17,000+ 종목, 30년 이상 히스토리 지원.

**필요 환경변수**
```
FINANCIAL_DATASETS_API_KEY=your_api_key
```
> API 키 발급: https://financialdatasets.ai  
> 상태 확인: 401 = 키 오류, 402 = 플랜 한도 초과

| Tool | 설명 |
|------|------|
| `get_income_statement` | 손익계산서 — 매출·영업이익·순이익·EPS·이익률 |
| `get_balance_sheet` | 대차대조표 — 총자산·총부채·자기자본·현금·부채비율(D/E) |
| `get_cash_flow` | 현금흐름표 — 영업·투자·재무 현금흐름·CapEx·잉여현금흐름(FCF) |
| `get_company_news` | 기업 뉴스 — ticker 생략 시 전체 시장 뉴스. 최대 10건 |
| `get_crypto_price` | 암호화폐 OHLC — BTC·ETH·SOL 등 day·week·month 단위 |
| `screen_stocks` | 펀더멘털 스크리닝 — 재무 지표 조건 기반 종목 필터링 |

**재무제표 공통 파라미터**

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `period` | `annual` | 연간 (기본값) |
| `period` | `quarterly` | 분기별 |
| `period` | `ttm` | 최근 12개월 합산 |
| `limit` | 정수 | 반환 기간 수 (기본 4) |

**`screen_stocks` 주요 필터 필드**

| 필드 | 설명 |
|------|------|
| `revenue` | 매출액 |
| `net_income` | 순이익 |
| `free_cash_flow` | 잉여현금흐름 |
| `total_assets` | 총자산 |
| `total_liabilities` | 총부채 |
| `debt_to_equity` | 부채비율 |
| `return_on_equity` | ROE |
| `return_on_assets` | ROA |
| `price_to_earnings_ratio` | PER |
| `price_to_book_ratio` | PBR |
| `earnings_per_share` | EPS |
| `revenue_growth` | 매출 성장률 |
| `net_income_growth` | 순이익 성장률 |

연산자: `gt`(>) · `lt`(<) · `gte`(≥) · `lte`(≤) · `eq`(=)

---

### 6. `free_screener_mcp.py` — 무료 암호화폐·주식 스크리너

yfinance 기반. **API 키 불필요, 완전 무료.**  
Financial Datasets의 `get_crypto_price`·`screen_stocks` 유료 기능의 무료 대안.

| Tool | 설명 |
|------|------|
| `get_crypto_price` | BTC·ETH·SOL 등 현재가·등락률·시총·거래량. 복수 심볼 동시 조회 |
| `get_crypto_ohlcv` | 암호화폐 OHLCV — 1분봉~월봉, 1일~2년 기간 |
| `screen_stocks` | S&P 500 / NASDAQ 100 펀더멘털 스크리닝. ThreadPool 병렬 조회 |

**`screen_stocks` 필터 필드**

| 분류 | 필드 | 설명 |
|------|------|------|
| 가격/규모 | `marketCap` | 시가총액 (달러) |
| 가격/규모 | `lastPrice` | 현재가 |
| 가격/규모 | `yearChange` | 52주 수익률 (소수. 0.3 = 30%) |
| 가치지표 | `trailingPE` | PER (TTM) |
| 가치지표 | `forwardPE` | 선행 PER |
| 가치지표 | `priceToBook` | PBR |
| 수익성 | `returnOnEquity` | ROE (소수. 0.2 = 20%) |
| 수익성 | `returnOnAssets` | ROA |
| 수익성 | `grossMargins` | 매출총이익률 |
| 수익성 | `profitMargins` | 순이익률 |
| 성장성 | `revenueGrowth` | 매출 성장률 |
| 성장성 | `earningsGrowth` | 이익 성장률 |
| 안정성 | `beta` | 베타 |
| 안정성 | `debtToEquity` | 부채비율 |
| 안정성 | `dividendYield` | 배당수익률 (소수) |

**성능 가이드**

| `scan_limit` | 예상 소요 시간 |
|---|---|
| 50 | ~3초 |
| 100 (기본) | ~6초 |
| 200 | ~12초 |
| 503 (전체) | ~30초 |

---

## 환경변수 요약

| 변수 | 필요 MCP | 비고 |
|------|----------|------|
| `DISCORD_WEBHOOK_URL` | discord_mcp | Discord 채널 웹훅 URL |
| `ALPHA_VANTAGE_API_KEY` | alphavantage_mcp | 무료 키 발급 가능 |
| `FINANCIAL_DATASETS_API_KEY` | financialdatasets_mcp | https://financialdatasets.ai 발급 |
| — | yfinance_mcp | 불필요 |
| — | macd_mcp | 불필요 |
| — | free_screener_mcp | 불필요 |

`.env.example`을 복사해 `.env`를 생성하세요.

```bash
cp .env.example .env
```

---

## 의존성

```
mcp>=1.0.0
requests>=2.31.0
python-dotenv>=1.0.0
yfinance>=0.2.0
pandas
numpy
```
