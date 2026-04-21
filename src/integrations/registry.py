from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable

from fastapi import HTTPException, Request, status

from ..config import TenantConfig
from ..services.audit_log import AuditLogger
from ..services.metrics import SecurityMetrics
from ..services.secret_manager import SecretManager
from ..tools.tool_registry import ToolDescriptor, ToolRegistry
from .aws.client import AWSProvider
from .google.client import GoogleProvider
from .linkedin.client import LinkedInProvider
from .microsoft.client import MicrosoftProvider
from .telegram.client import TelegramProvider
from .whatsapp.client import WhatsAppProvider
from .x.client import XProvider


@dataclass(frozen=True)
class ProviderDependencyStatus:
    name: str
    ok: bool
    detail: str
    required: bool


class IntegrationManager:
    def __init__(self, audit_logger: AuditLogger, metrics: SecurityMetrics) -> None:
        self.audit_logger = audit_logger
        self.metrics = metrics
        self.secret_manager = SecretManager()
        self.providers = {
            "google": GoogleProvider(self.secret_manager),
            "microsoft": MicrosoftProvider(self.secret_manager),
            "aws": AWSProvider(self.secret_manager),
            "telegram": TelegramProvider(self.secret_manager),
            "whatsapp": WhatsAppProvider(self.secret_manager),
            "linkedin": LinkedInProvider(self.secret_manager),
            "x": XProvider(self.secret_manager),
        }

    def _build_handler(self, provider_name: str, action: str) -> Callable[[dict], dict]:
        def _handler(arguments: dict) -> dict:
            tenant = arguments.pop("_tenant", None)
            if tenant is None or not isinstance(tenant, TenantConfig):
                return {"ok": False, "error_code": "tenant_context_missing", "reason": "tenant context missing"}
            provider = self.providers[provider_name]
            try:
                return provider.execute(action, tenant, arguments)
            except Exception as exc:
                return {"ok": False, "error_code": "provider_execution_failed", "reason": str(exc)}

        return _handler

    def register_tools(self, registry: ToolRegistry) -> None:
        for provider in self.providers.values():
            for descriptor in provider.tool_descriptors(self._build_handler):
                registry.register(descriptor)

    def _scoped_tenant(self, tenant: TenantConfig, provider_name: str, execution_scope: str) -> TenantConfig:
        if execution_scope == "platform":
            provider_cfg = settings.platform_providers.get(provider_name)
            if provider_cfg is None or not provider_cfg.enabled:
                raise RuntimeError(f"platform_provider_not_configured:{provider_name}")
            return TenantConfig(
                tenant_id=f"platform::{tenant.tenant_id}",
                api_key=tenant.api_key,
                name=tenant.name,
                status=tenant.status,
                allowed_tools=tenant.allowed_tools,
                allowed_capabilities=tenant.allowed_capabilities,
                allowed_model_classes=tenant.allowed_model_classes,
                context_char_limit=tenant.context_char_limit,
                rate_limit_per_minute=tenant.rate_limit_per_minute,
                providers={provider_name: provider_cfg},
                metadata=tenant.metadata,
            )
        return tenant

    def execute(
        self,
        provider_name: str,
        action: str,
        tenant: TenantConfig,
        arguments: dict[str, Any],
        execution_scope: str = "tenant",
    ) -> dict:
        if provider_name not in self.providers:
            return {"ok": False, "error_code": "provider_not_supported", "reason": provider_name}
        scoped_tenant = self._scoped_tenant(tenant, provider_name, execution_scope)
        provider = self.providers[provider_name]
        return provider.execute(action, scoped_tenant, dict(arguments))

    def provider_dependency_statuses(self, tenants: dict[str, TenantConfig]) -> list[ProviderDependencyStatus]:
        statuses: list[ProviderDependencyStatus] = []
        for name, provider in self.providers.items():
            enabled = [tenant for tenant in tenants.values() if provider.get_config(tenant).enabled]
            if not enabled:
                statuses.append(ProviderDependencyStatus(f"provider.{name}", True, "no enabled tenants", False))
                continue
            auth_ok = True
            tooling_ok = True
            webhook_ok = True
            details = []
            for tenant in enabled:
                health = provider.health(tenant)
                auth_ok = auth_ok and health.auth_ok
                tooling_ok = tooling_ok and health.tooling_ok
                webhook_ok = webhook_ok and (health.webhook_ok or not provider.webhook_supported)
                details.append(f"{tenant.tenant_id}:{health.approval_state}:{health.detail}")
            ok = auth_ok and tooling_ok and webhook_ok
            statuses.append(ProviderDependencyStatus(f"provider.{name}", ok, ";".join(details), False))
        return statuses

    async def handle_webhook(self, provider_name: str, request: Request):
        tenant_id = request.query_params.get("tenant_id", request.headers.get("X-Tenant-Id", ""))
        from ..config import settings

        if tenant_id not in settings.tenants:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error_code": "invalid_tenant", "reason": "tenant_id required"})
        provider = self.providers[provider_name]
        tenant = settings.tenants[tenant_id]
        body = await request.body()
        query = dict(request.query_params)
        headers = {str(k): str(v) for k, v in request.headers.items()}
        event = provider.normalize_webhook(tenant, headers, query, body)
        self.audit_logger.write("provider_webhook", {"tenant_id": tenant_id, "provider": provider_name, "event": event})
        return {"ok": True, "provider": provider_name, "event": event}
