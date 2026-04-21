from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..config import TenantConfig, settings


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    source: str
    policy_version: str = "local-fallback"


class PolicyEngine:
    def __init__(self) -> None:
        self._base_url = settings.opa_url.rstrip("/")

    async def _query_opa(self, payload: dict[str, Any]) -> PolicyDecision | None:
        if not self._base_url:
            return None
        url = f"{self._base_url}/v1/data/hermes/authz/decision"
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                response = await client.post(url, json={"input": payload})
                response.raise_for_status()
                data = response.json().get("result", {})
                return PolicyDecision(
                    allowed=bool(data.get("allow", False)),
                    reason=str(data.get("reason", "opa_no_reason")),
                    source=str(data.get("source", "opa")),
                    policy_version=str(data.get("policy_version", "opa")),
                )
        except Exception:
            return None

    @staticmethod
    def _model_class(model_name: str) -> str:
        model_name = (model_name or "").strip()
        if not model_name:
            return "default"
        if "/" in model_name:
            return model_name.split("/", 1)[0]
        return "default"

    def _fallback_decision(
        self,
        tenant: TenantConfig,
        action: str,
        tool_name: str = "",
        capabilities: tuple[str, ...] = (),
        model_name: str = "",
        dependency_failed: bool = False,
    ) -> PolicyDecision:
        if dependency_failed and settings.opa_required:
            return PolicyDecision(False, "opa_unavailable", "critical_dependency", "unavailable")
        if tenant.status != "active":
            return PolicyDecision(False, f"tenant_{tenant.status}", "local", "local-fallback")
        if action == "tool.execute":
            if capabilities and not all(cap in tenant.allowed_capabilities for cap in capabilities):
                return PolicyDecision(False, "capability_not_allowed", "local", "local-fallback")
            if tool_name and tool_name in tenant.allowed_tools:
                return PolicyDecision(True, "tool_allowed", "local", "local-fallback")
            return PolicyDecision(False, "tool_not_allowed", "local", "local-fallback")
        if self._model_class(model_name) not in tenant.allowed_model_classes:
            return PolicyDecision(False, "model_class_not_allowed", "local", "local-fallback")
        return PolicyDecision(True, "chat_allowed", "local", "local-fallback")

    async def authorize_chat(self, tenant: TenantConfig, model_name: str) -> PolicyDecision:
        payload = {
            "tenant_id": tenant.tenant_id,
            "action": "chat.invoke",
            "environment": settings.environment,
            "resource": {"tenant_id": tenant.tenant_id, "model_class": self._model_class(model_name)},
            "tenant": {
                "status": tenant.status,
                "allowed_tools": tenant.allowed_tools,
                "allowed_model_classes": tenant.allowed_model_classes,
            },
        }
        result = await self._query_opa(payload)
        if result is None:
            return self._fallback_decision(
                tenant,
                action="chat.invoke",
                model_name=model_name,
                dependency_failed=True,
            )
        return result

    async def authorize_tool(
        self,
        tenant: TenantConfig,
        tool_name: str,
        capabilities: tuple[str, ...] = (),
    ) -> PolicyDecision:
        payload = {
            "tenant_id": tenant.tenant_id,
            "action": "tool.execute",
            "environment": settings.environment,
            "resource": {
                "tenant_id": tenant.tenant_id,
                "tool": tool_name,
                "capabilities": list(capabilities),
            },
            "tenant": {
                "status": tenant.status,
                "allowed_tools": tenant.allowed_tools,
                "allowed_capabilities": tenant.allowed_capabilities,
                "allowed_model_classes": tenant.allowed_model_classes,
            },
        }
        result = await self._query_opa(payload)
        if result is None:
            return self._fallback_decision(
                tenant,
                action="tool.execute",
                tool_name=tool_name,
                capabilities=capabilities,
                dependency_failed=True,
            )
        return result
