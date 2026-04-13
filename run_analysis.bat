@echo off
chcp 65001 > nul
set CLAUDE_CONFIG_DIR=%CD%\.claude_session

if not exist reports mkdir reports

echo ============================================================
echo   포트폴리오 자동 분석 시작
echo   %DATE% %TIME%
echo ============================================================
echo.

claude -p "분석시작" --dangerously-skip-permissions

echo.
echo ============================================================
echo   분석 완료. reports\ 폴더를 확인하세요.
echo ============================================================
