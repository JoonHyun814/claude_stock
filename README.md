# Claude Stock

**Claude AI + 커스텀 MCP 서버 기반 장기 가치 투자 포트폴리오 자동 분석**

[![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Claude](https://img.shields.io/badge/Claude_API-CC785C?style=flat)](https://www.anthropic.com)
[![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-555555?style=flat)](https://modelcontextprotocol.io)

---

## 개요

보유 종목에 대해 장기 가치 투자 관점의 분석을 자동화하는 도구입니다. Claude가 커스텀 **MCP(Model Context Protocol) 서버**를 통해 실시간 주가·재무 데이터를 조회하고, 설정된 분석 프롬프트 전략에 따라 종목별 마크다운 리포트를 작성합니다.

핵심 설계 철학: 하드코딩된 분석 스크립트 대신, Claude에게 도구(실시간 데이터)와 전략(가치 투자 원칙)을 주고 자유롭게 추론하도록 합니다.

---

## 작동 방식

```
analyze.py
    │
    ├── holdings.json 읽기       # 분석할 종목 및 보유 수량
    ├── analysis_prompt.md 로드  # 가치 투자 분석 전략 프롬프트
    └── Claude + MCP 도구 호출
            │
            └── stock_mcp_server.py  # yfinance 기반 커스텀 MCP 서버
                    ├── get_stock_price()
                    ├── get_financials()
                    ├── get_balance_sheet()
                    └── get_info()
                            │
                            └── Claude가 분석 후 리포트 작성 → reports/
```

---

## 프로젝트 구조

```
claude_stock/
├── analyze.py              # 실행 진입점 — 전체 포트폴리오 분석
├── holdings.json           # 보유 종목 (티커 + 수량)
├── mcp/
│   ├── stock_mcp_server.py # yfinance 기반 MCP 서버
│   ├── portfolio.py        # 포트폴리오 가치 단독 확인 스크립트
│   └── mcp_config.json     # MCP 서버 설정
└── prompt/
    └── analysis_prompt.md  # Claude용 가치 투자 분석 지침
```

---

## 실행

```bash
# 전체 포트폴리오 분석 리포트 생성
python analyze.py

# 현재 포트폴리오 가치 빠른 확인
python -X utf8 mcp/portfolio.py
```

---

## 기술 스택

- **Claude API** (Anthropic) — 추론 및 리포트 생성
- **MCP** (Model Context Protocol) — Claude와 데이터 소스 간 구조화된 도구 인터페이스
- **yfinance** — 실시간 및 과거 주가·재무 데이터
- **Python** — 전체 오케스트레이션
