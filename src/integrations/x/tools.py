from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import CREATE_POST_TOOL, LIST_CAMPAIGNS_TOOL


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=LIST_CAMPAIGNS_TOOL,
            description="List X Ads campaigns",
            handler=handler_factory("x", "list_campaigns"),
            capabilities=("ads.x.read",),
            input_schema={"account_id": str},
            max_output_chars=4096,
        ),
        ToolDescriptor(
            name=CREATE_POST_TOOL,
            description="Create an X post",
            handler=handler_factory("x", "create_post"),
            capabilities=("ads.x.write",),
            input_schema={"text": str},
            max_output_chars=4096,
        ),
    ]

