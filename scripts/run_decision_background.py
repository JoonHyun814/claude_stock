#!/usr/bin/env python3
r"""
Background scheduler: run decision analysis at KST 09:00 / 13:00 / 20:00 daily.

Usage (run in background):
    .\unsloth_env\Scripts\Activate.ps1
    Start-Process -NoNewWindow python -ArgumentList "scripts/run_decision_background.py"

    # or from bash:
    nohup python scripts/run_decision_background.py > logs/scheduler.log 2>&1 &

Logs: logs/scheduler.log (scheduler events), logs/decision_YYYYMMDD_HHMMSS.log (per-run output)
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

KST = ZoneInfo("Asia/Seoul")
SCHEDULE_HOURS = [9, 13, 19]

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
DEFAULT_PROMPT_PATH = "prompts/decision.txt"


def log(msg: str) -> None:
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    print(f"[{ts}] {msg}", flush=True)


def next_run(now_kst: datetime) -> datetime:
    for h in SCHEDULE_HOURS:
        candidate = now_kst.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate > now_kst:
            return candidate
    tomorrow = now_kst + timedelta(days=1)
    return tomorrow.replace(hour=SCHEDULE_HOURS[0], minute=0, second=0, microsecond=0)


def run_once(prompt_path: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"decision_{stamp}.log"
    log(f"START decision analysis ({prompt_path}) -> {log_file.name}")
    with log_file.open("w", encoding="utf-8") as f:
        result = subprocess.run(
            [sys.executable, "run_claude.py", "--prompt", prompt_path],
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
    log(f"END exit={result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision analysis background scheduler")
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT_PATH,
        help=f"프롬프트 파일 경로 (기본: {DEFAULT_PROMPT_PATH})",
    )
    args = parser.parse_args()
    prompt_path = args.prompt

    log(f"Scheduler started - triggers at KST {SCHEDULE_HOURS} daily")
    log(f"Python: {sys.executable}")
    log(f"Project root: {ROOT}")
    log(f"Prompt: {prompt_path}")
    while True:
        now = datetime.now(KST)
        nxt = next_run(now)
        sleep_sec = (nxt - now).total_seconds()
        log(f"Next run: {nxt:%Y-%m-%d %H:%M:%S KST} (sleep {sleep_sec:.0f}s = {sleep_sec/3600:.2f}h)")
        time.sleep(sleep_sec)
        try:
            run_once(prompt_path)
        except Exception as e:
            log(f"ERROR: {e!r}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Scheduler stopped (KeyboardInterrupt)")
