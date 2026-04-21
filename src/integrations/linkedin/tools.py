from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import LIST_CAMPAIGNS_TOOL


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=LIST_CAMPAIGNS_TOOL,
            description="List LinkedIn campaigns",
            handler=handler_factory("linkedin", "list_campaigns"),
            capabilities=("ads.linkedin.read",),
            input_schema={"account_id": str},
            max_output_chars=4096,
        )
    ]

