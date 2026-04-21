from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import SEND_TEMPLATE_TOOL, SEND_TEXT_TOOL


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=SEND_TEXT_TOOL,
            description="Send a WhatsApp text message",
            handler=handler_factory("whatsapp", "send_text"),
            capabilities=("comm.whatsapp.send",),
            input_schema={"to": str, "text": str},
            max_output_chars=4096,
        ),
        ToolDescriptor(
            name=SEND_TEMPLATE_TOOL,
            description="Send a WhatsApp template message",
            handler=handler_factory("whatsapp", "send_template"),
            capabilities=("comm.whatsapp.send",),
            input_schema={"to": str, "template_name": str, "language_code": str},
            max_output_chars=4096,
        ),
    ]

