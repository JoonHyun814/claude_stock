# Stock Investment Analysis

장기 가치 투자 관점의 포트폴리오 자동 분석 프로젝트입니다.

## 구조

```
├── mcp/
│   ├── mcp_config.json       # MCP 서버 설정
│   ├── stock_mcp_server.py   # yfinance 기반 실시간 주가 조회 MCP 서버
│   └── portfolio.py          # 포트폴리오 단독 확인용 스크립트
├── prompt/
│   └── analysis_prompt.md    # 분석 프롬프트 (analyze.py가 읽어서 -p 로 전달)
├── reports/                  # 분석 결과 마크다운 저장
├── holdings.json             # 보유 종목 및 수량
└── analyze.py                # 실행 진입점
```

## 실행

```bash
python analyze.py
```

## 포트폴리오 단독 확인

```bash
python -X utf8 mcp/portfolio.py
```
