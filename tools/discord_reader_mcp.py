"""
Discord Reader MCP
- Discord Bot API로 채널 메시지를 읽어옵니다.
- 웹훅(Webhook)은 쓰기 전용이므로 메시지 읽기에는 Bot 토큰이 필요합니다.

Bot 토큰 발급:
  1. https://discord.com/developers/applications 에서 앱 생성
  2. Bot 탭 → Token 복사 → .env에 DISCORD_BOT_TOKEN 설정
  3. OAuth2 → URL Generator → bot 권한 → Read Message History, View Channels 체크
  4. 생성된 URL로 서버에 봇 초대
  5. 채널 ID: Discord에서 채널 우클릭 → "채널 ID 복사" (개발자 모드 활성화 필요)
     설정 → 고급 → 개발자 모드 ON 후 채널 우클릭
"""
import asyncio
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

load_dotenv(Path(__file__).parent.parent / ".env")

BOT_TOKEN          = os.environ["DISCORD_BOT_TOKEN"]
HOLDINGS_CHANNEL_ID = os.environ.get("DISCORD_HOLDINGS_CHANNEL_ID", "")

BASE_URL = "https://discord.com/api/v10"
server   = Server("discord-reader")


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"Authorization": f"Bot {BOT_TOKEN}"}


def _get_messages(channel_id: str, limit: int) -> list[dict]:
    r = requests.get(
        f"{BASE_URL}/channels/{channel_id}/messages",
        headers=_headers(),
        params={"limit": limit},
        timeout=10,
    )
    if r.status_code == 401:
        raise RuntimeError("Bot 토큰이 유효하지 않습니다. .env의 DISCORD_BOT_TOKEN을 확인하세요.")
    if r.status_code == 403:
        raise RuntimeError("채널 읽기 권한이 없습니다. 봇에 Read Message History 권한을 부여하세요.")
    if r.status_code == 404:
        raise RuntimeError(f"채널을 찾을 수 없습니다 (ID: {channel_id}). DISCORD_HOLDINGS_CHANNEL_ID를 확인하세요.")
    r.raise_for_status()
    return r.json()


def _fmt_message(msg: dict, idx: int) -> list[str]:
    author   = msg.get("author", {})
    username = author.get("global_name") or author.get("username", "알 수 없음")
    content  = msg.get("content", "").strip()
    ts       = msg.get("timestamp", "")[:19].replace("T", " ")

    lines = [f"  [{idx}] {username}  ({ts} UTC)"]

    if content:
        # 긴 메시지는 500자로 잘라냄
        if len(content) > 500:
            content = content[:500] + "…"
        for line in content.split("\n"):
            lines.append(f"       {line}")

    # 첨부 파일
    attachments = msg.get("attachments", [])
    if attachments:
        lines.append(f"       [첨부] {', '.join(a.get('filename','?') for a in attachments)}")

    # embed 제목
    embeds = msg.get("embeds", [])
    for e in embeds:
        if e.get("title"):
            lines.append(f"       [embed] {e['title']}")

    return lines


def _ok(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]

def _err(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=f"오류: {text}")]


# ── Tools ──────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_holdings_messages",
            description=(
                "Discord 'holdings' 채널의 최근 메시지를 읽어옵니다. "
                "채널 ID는 .env의 DISCORD_HOLDINGS_CHANNEL_ID로 설정하세요. "
                "Bot 토큰(DISCORD_BOT_TOKEN) 필요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "가져올 메시지 수 (기본 10, 최대 100)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_latest_holding",
            description=(
                "Discord 'holdings' 채널의 가장 최근 메시지 1건만 반환합니다. "
                "최신 보유 종목 정보를 빠르게 확인할 때 사용하세요."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_channel_messages",
            description=(
                "지정한 채널 ID에서 메시지를 읽어옵니다. "
                "채널 ID는 Discord에서 채널 우클릭 → '채널 ID 복사'로 확인하세요 "
                "(설정 → 고급 → 개발자 모드 활성화 필요)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord 채널 ID (18자리 숫자)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "가져올 메시지 수 (기본 10, 최대 100)",
                    },
                },
                "required": ["channel_id"],
            },
        ),
    ]


# ── Handlers ───────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "get_holdings_messages":
            return _holdings_messages(arguments)
        elif name == "get_latest_holding":
            return _latest_holding()
        elif name == "get_channel_messages":
            return _channel_messages(arguments)
        else:
            return _err(f"알 수 없는 tool: {name}")
    except RuntimeError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"요청 실패: {e}")


INTENT_WARNING = (
    "\n\n[!] 메시지 내용이 비어 있습니다.\n"
    "    원인: Discord 'Message Content Intent'가 비활성화되어 있습니다.\n"
    "    해결:\n"
    "      1. https://discord.com/developers/applications 접속\n"
    "      2. 봇 애플리케이션 선택 → [Bot] 탭\n"
    "      3. 'Privileged Gateway Intents' 섹션에서\n"
    "         'Message Content Intent' 토글을 ON\n"
    "      4. [Save Changes] 클릭 후 Claude Code 재시작"
)


def _has_intent_problem(msgs: list[dict]) -> bool:
    """모든 메시지 content가 비어 있으면 Intent 미설정으로 판단."""
    return bool(msgs) and all(not m.get("content", "").strip() for m in msgs)


def _holdings_messages(args: dict) -> list[TextContent]:
    if not HOLDINGS_CHANNEL_ID:
        return _err(".env에 DISCORD_HOLDINGS_CHANNEL_ID가 설정되지 않았습니다.")
    limit = min(int(args.get("limit", 10)), 100)
    msgs  = _get_messages(HOLDINGS_CHANNEL_ID, limit)

    if not msgs:
        return _ok("[holdings 채널] 메시지가 없습니다.")

    lines = [f"[holdings 채널] 최근 {len(msgs)}개 메시지\n"]
    for i, msg in enumerate(msgs, 1):
        lines.extend(_fmt_message(msg, i))
        lines.append("")

    result = "\n".join(lines)
    if _has_intent_problem(msgs):
        result += INTENT_WARNING

    return _ok(result)


def _latest_holding() -> list[TextContent]:
    if not HOLDINGS_CHANNEL_ID:
        return _err(".env에 DISCORD_HOLDINGS_CHANNEL_ID가 설정되지 않았습니다.")
    msgs = _get_messages(HOLDINGS_CHANNEL_ID, 1)

    if not msgs:
        return _ok("[holdings 채널] 메시지가 없습니다.")

    msg      = msgs[0]
    author   = msg.get("author", {})
    username = author.get("global_name") or author.get("username", "알 수 없음")
    content  = msg.get("content", "").strip()
    ts       = msg.get("timestamp", "")[:19].replace("T", " ")

    lines = [
        "[holdings 채널] 최신 메시지",
        f"  작성자: {username}",
        f"  시각:   {ts} UTC",
        f"  내용:",
    ]
    for line in (content or "(내용 없음 — Intent 미설정 가능)").split("\n"):
        lines.append(f"    {line}")

    embeds = msg.get("embeds", [])
    if embeds:
        lines.append("  embed:")
        for e in embeds:
            if e.get("title"):       lines.append(f"    제목: {e['title']}")
            if e.get("description"): lines.append(f"    내용: {e['description'][:200]}")

    result = "\n".join(lines)
    if not content and not embeds:
        result += INTENT_WARNING

    return _ok(result)


def _channel_messages(args: dict) -> list[TextContent]:
    channel_id = args["channel_id"].strip()
    limit      = min(int(args.get("limit", 10)), 100)
    msgs       = _get_messages(channel_id, limit)

    if not msgs:
        return _ok(f"[채널 {channel_id}] 메시지가 없습니다.")

    lines = [f"[채널 {channel_id}] 최근 {len(msgs)}개 메시지\n"]
    for i, msg in enumerate(msgs, 1):
        lines.extend(_fmt_message(msg, i))
        lines.append("")

    result = "\n".join(lines)
    if _has_intent_problem(msgs):
        result += INTENT_WARNING

    return _ok(result)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
