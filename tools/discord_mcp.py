import asyncio
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# tools/ 한 단계 위의 프로젝트 루트에 있는 .env 로드
load_dotenv(Path(__file__).parent.parent / ".env")

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

server = Server("discord-notifier")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_discord_message",
            description="Discord 웹훅으로 메시지를 전송합니다. 주식 알림, 포트폴리오 업데이트 등에 사용하세요.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "전송할 메시지 내용",
                    },
                    "username": {
                        "type": "string",
                        "description": "봇 표시 이름 (선택사항)",
                    },
                    "embeds": {
                        "type": "array",
                        "description": "Discord embed 목록 (선택사항)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "color": {"type": "integer", "description": "색상 코드 (10진수). 예: 빨강=16711680, 초록=65280"},
                                "fields": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "value": {"type": "string"},
                                            "inline": {"type": "boolean"},
                                        },
                                        "required": ["name", "value"],
                                    },
                                },
                            },
                        },
                    },
                },
                "required": ["content"],
            },
        ),
        Tool(
            name="send_stock_alert",
            description="주식 알림을 Discord에 전송합니다. 매수/매도 신호, 가격 알림 등에 사용하세요.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "주식 티커 심볼 (예: AAPL, 삼성전자)",
                    },
                    "alert_type": {
                        "type": "string",
                        "enum": ["buy", "sell", "price_alert", "info"],
                        "description": "알림 유형: buy(매수), sell(매도), price_alert(가격알림), info(정보)",
                    },
                    "price": {
                        "type": "number",
                        "description": "현재 주가",
                    },
                    "message": {
                        "type": "string",
                        "description": "추가 메시지 내용",
                    },
                    "change_percent": {
                        "type": "number",
                        "description": "등락률 (%) (선택사항)",
                    },
                },
                "required": ["ticker", "alert_type", "message"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "send_discord_message":
        return await _send_discord_message(arguments)
    elif name == "send_stock_alert":
        return await _send_stock_alert(arguments)
    else:
        raise ValueError(f"알 수 없는 tool: {name}")


async def _send_discord_message(args: dict[str, Any]) -> list[TextContent]:
    payload: dict[str, Any] = {"content": args["content"]}

    if "username" in args:
        payload["username"] = args["username"]
    if "embeds" in args:
        payload["embeds"] = args["embeds"]

    response = requests.post(WEBHOOK_URL, json=payload)

    if response.status_code in (200, 204):
        return [TextContent(type="text", text="Discord 메시지 전송 성공")]
    else:
        return [TextContent(type="text", text=f"전송 실패: HTTP {response.status_code} - {response.text}")]


async def _send_stock_alert(args: dict[str, Any]) -> list[TextContent]:
    alert_type = args["alert_type"]
    ticker = args["ticker"]
    message = args["message"]
    price = args.get("price")
    change_percent = args.get("change_percent")

    color_map = {
        "buy": 65280,       # 초록
        "sell": 16711680,   # 빨강
        "price_alert": 16776960,  # 노랑
        "info": 3447003,    # 파랑
    }
    emoji_map = {
        "buy": "🟢 매수 신호",
        "sell": "🔴 매도 신호",
        "price_alert": "🔔 가격 알림",
        "info": "ℹ️ 정보",
    }

    fields = []
    if price is not None:
        fields.append({"name": "현재가", "value": f"{price:,.2f}", "inline": True})
    if change_percent is not None:
        arrow = "▲" if change_percent >= 0 else "▼"
        fields.append({"name": "등락률", "value": f"{arrow} {abs(change_percent):.2f}%", "inline": True})

    embed = {
        "title": f"{emoji_map[alert_type]} — {ticker}",
        "description": message,
        "color": color_map[alert_type],
    }
    if fields:
        embed["fields"] = fields

    payload = {
        "content": "",
        "embeds": [embed],
    }

    response = requests.post(WEBHOOK_URL, json=payload)

    if response.status_code in (200, 204):
        return [TextContent(type="text", text=f"주식 알림 전송 성공: {ticker} ({alert_type})")]
    else:
        return [TextContent(type="text", text=f"전송 실패: HTTP {response.status_code} - {response.text}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
