from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable

from ..context.policy import ToolPolicyViolation


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    handler: Callable[[dict], dict]
    capabilities: tuple[str, ...] = ()
    input_schema: dict[str, type] = field(default_factory=dict)
    max_output_chars: int = 4096


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDescriptor] = {}

    def register(self, tool: ToolDescriptor) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDescriptor:
        if name not in self._tools:
            raise ToolPolicyViolation(f"tool_not_allowed:{name}")
        return self._tools[name]

    def all_names(self) -> Iterable[str]:
        return self._tools.keys()

    @staticmethod
    def validate_arguments(tool: ToolDescriptor, arguments: dict[str, Any]) -> None:
        for key, expected_type in tool.input_schema.items():
            if key not in arguments:
                raise ToolPolicyViolation(f"missing_tool_argument:{tool.name}:{key}")
            if not isinstance(arguments[key], expected_type):
                raise ToolPolicyViolation(f"invalid_tool_argument_type:{tool.name}:{key}")

    def execute(self, tenant_allowed: list[str], name: str, arguments: dict) -> dict:
        if name not in tenant_allowed:
            raise ToolPolicyViolation(f"tool_not_in_tenant_allowlist:{name}")
        tool = self.get(name)
        self.validate_arguments(tool, arguments)
        return tool.handler(arguments)
