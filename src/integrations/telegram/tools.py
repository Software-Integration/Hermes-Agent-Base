from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import SEND_MESSAGE_TOOL


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=SEND_MESSAGE_TOOL,
            description="Send a Telegram message",
            handler=handler_factory("telegram", "send_message"),
            capabilities=("comm.telegram.send",),
            input_schema={"chat_id": str, "text": str},
            max_output_chars=4096,
        )
    ]

