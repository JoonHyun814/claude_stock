#!/usr/bin/env python3
"""
Usage: python run_claude.py --prompt prompts/long.txt
Claude Code를 비대화형 모드로 실행하여 장기투자 분석 후 Discord 전송.
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser(description="Claude 장기투자 분석 실행기")
    parser.add_argument("--prompt", required=True, help="프롬프트 파일 경로 (e.g., prompts/long.txt)")
    parser.add_argument("--today", default=None, help="프롬프트 {today} 치환 값 (기본: 오늘 KST, YYYY-MM-DD)")
    args = parser.parse_args()

    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"[ERROR] 프롬프트 파일 없음: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    today = args.today or datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    prompt_text = prompt_path.read_text(encoding="utf-8").replace("{today}", today)
    print(f"[INFO] 프롬프트: {prompt_path} ({len(prompt_text):,} chars) | today={today}")

    mcp_config = Path(__file__).parent / ".mcp.json"
    if not mcp_config.exists():
        print(f"[ERROR] MCP 설정 파일 없음: {mcp_config}", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] MCP 설정: {mcp_config}")
    print("[INFO] Claude 분석 시작...")

    result = subprocess.run(
        [
            "claude",
            "--dangerously-skip-permissions",
            "--no-session-persistence",
            "--mcp-config",
            str(mcp_config),
            "--strict-mcp-config",
            "-p",
            prompt_text,
        ],
        text=True,
        encoding="utf-8",
    )

    if result.returncode == 0:
        print("\n[INFO] 완료 — Discord 전송됨")
    else:
        print(f"\n[ERROR] Claude 종료 코드: {result.returncode}", file=sys.stderr)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
