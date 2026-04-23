# Stock Analysis — Claude Code 프로젝트 가이드

## MCP 서버 구조

### 소스 코드 위치: `tools/`
MCP 서버는 모두 `tools/` 디렉터리의 Python 파일로 구현된다.

| 파일 | MCP 서버 ID | 역할 |
|------|------------|------|
| `tools/discord_mcp.py` | `discord-notifier` | Discord 웹훅으로 분석 결과 전송 |
| `tools/discord_reader_mcp.py` | `discord-reader` | #holdings 채널에서 보유 종목 읽기 |
| `tools/financialdatasets_mcp.py` | `financial-datasets` | 재무제표, 뉴스 (손익/대차/현금흐름) |
| `tools/vit_mcp.py` | `value-investing-tools` | DCF 내재가치, WACC, 동종업체 비교 |
| `tools/yfinance_mcp.py` | `yfinance` | 현재가, OHLCV, 종목 정보 |
| `tools/macd_mcp.py` | `macd-analyzer` | MACD, 기술적 신호 분석 |
| `tools/alphavantage_mcp.py` | `alphavantage` | RSI, 시세, 상품 가격, 시장 상태 |
| `tools/free_screener_mcp.py` | `free-screener` | 종목 스크리너, S&P 500 필터 |

### 서버 등록: `.mcp.json`
MCP 서버를 추가하거나 제거할 때는 프로젝트 루트의 `.mcp.json`을 수정한다.
각 서버는 `command`(실행 명령)와 `args`(스크립트 경로)로 등록된다.

```json
{
  "mcpServers": {
    "server-id": {
      "command": "python",
      "args": ["tools/server_script.py"]
    }
  }
}
```

### 도구 허가(Permissions): `.claude/settings.local.json`
Claude가 MCP 도구를 허가 없이 자동 호출하려면 `.claude/settings.local.json`의
`permissions.allow` 배열에 도구명을 추가한다. 형식: `mcp__{서버ID}__{툴명}`

새 MCP 서버를 추가했다면 해당 서버의 도구도 이 목록에 추가해야 한다.

---

## 환경 변수: `.env`

```
DISCORD_WEBHOOK_URL       # 분석 결과 전송용 웹훅
DISCORD_BOT_TOKEN         # #holdings 채널 읽기용 봇 토큰
DISCORD_HOLDINGS_CHANNEL_ID
ALPHA_VANTAGE_API_KEY
FINANCIAL_DATASETS_API_KEY
```

---

## 프롬프트 실행

### 장기투자 분석 (`prompts/long.txt`)
```bash
python run_claude.py --prompt prompts/long.txt
```
Discord #holdings 보유 종목 → 재무 건전성(5개년) · DCF 내재가치 · 기술적 신호 · 뉴스 심리 분석 → Discord 전송.

### 통합 결정 (`prompts/decision.txt`) ← 핵심 실행 프롬프트
```bash
python run_claude.py --prompt prompts/decision.txt
```
거시 환경 파악 → 보유 종목별 장기(DCF)+단기(RSI/MACD) 통합 판단으로 액션 결정 → 신규 종목 국외 2+국내 2 추천 → Discord 요약. long.txt + short.txt + new.txt를 하나로 압축한 버전.

### 신규 종목 발굴 (`prompts/new.txt`)
```bash
python run_claude.py --prompt prompts/new.txt
```
뉴스·섹터 ETF에서 투자 테마 도출 → S&P 500/NASDAQ 스크리닝으로 국외 3종목 + 테마 기반 국내 3종목 발굴 → Discord 추천.

### 단기 모멘텀 매매 (`prompts/short.txt`)
```bash
python run_claude.py --prompt prompts/short.txt
```
Discord #holdings 미국 주식 → 200일 SMA 추세 필터 · RSI 과매도 탈출 · MACD 골든크로스 스캔
→ 손절/익절/포지션 사이징 계산 → 매매 신호 Discord 전송. 월 3% 수익 목표.

### MCP 통합 테스트
```bash
python test_mcp_all.py
```

---

## 전략 문서: `tactics/`
투자 전략 및 분석 기준은 `tactics/` 디렉터리에서 관리한다.
- `tactics/log.md` — 장기 투자 전략 (우량주 스크리닝 기준, DCF 모델 기준)
