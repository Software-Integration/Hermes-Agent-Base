from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import SEND_MESSAGE_TOOL


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=SEND_MESSAGE_TOOL,
            description="Send a message to Google Chat",
            handler=handler_factory("google", "send_message"),
            capabilities=("collab.google_chat.write",),
            input_schema={"space": str, "text": str},
            max_output_chars=4096,
        )
    ]

