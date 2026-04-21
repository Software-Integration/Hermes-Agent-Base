from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import SEND_MESSAGE_TOOL


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=SEND_MESSAGE_TOOL,
            description="Send a message to Microsoft Teams",
            handler=handler_factory("microsoft", "send_message"),
            capabilities=("collab.teams.write",),
            input_schema={"chat_id": str, "text": str},
            max_output_chars=4096,
        )
    ]

