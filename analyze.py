import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
MCP_CONFIG = PROJECT_DIR / "mcp" / "mcp_config.json"
PROMPT_FILE = PROJECT_DIR / "prompt" / "analysis_prompt.md"

ALLOWED_TOOLS = ",".join([
    "Bash",
    "Write",
    "Read",
    "WebSearch",
    "WebFetch",
    "mcp__stock-info__get_stock_info",
    "mcp__stock-info__get_multiple_stocks",
    "mcp__stock-info__get_portfolio",
    "mcp__stock-info__get_exchange_rate",
])


def load_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return "분석시작"


def main():
    today = datetime.now().strftime("%Y%m%d_%H%M")
    print(f"[{today}] 포트폴리오 분석을 시작합니다...")
    print(f"  프롬프트: {PROMPT_FILE.relative_to(PROJECT_DIR)}")
    print(f"  MCP 설정: {MCP_CONFIG.relative_to(PROJECT_DIR)}")
    print(f"  모델: claude-sonnet-4-6")
    print(f"  최대 턴 수: 20")
    print("-" * 60)

    prompt = load_prompt()

    cmd = [
        "claude",
        "-p", prompt,
        "--max-turns", "20",
        "--mcp-config", str(MCP_CONFIG),
        "--allowedTools", ALLOWED_TOOLS,
        "--model", "claude-sonnet-4-6",
        "--dangerously-skip-permissions",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("오류: 'claude' CLI를 찾을 수 없습니다.")
        print("Claude Code가 설치되어 있는지 확인하세요: https://claude.ai/code")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n분석이 중단되었습니다.")
        sys.exit(0)


if __name__ == "__main__":
    main()
