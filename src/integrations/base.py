from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import ProviderConfig, TenantConfig
from ..services.secret_manager import SecretManager, SecretResult


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    enabled: bool
    auth_ok: bool
    webhook_ok: bool
    tooling_ok: bool
    approval_state: str
    detail: str


class ProviderError(RuntimeError):
    pass


class ProviderBase:
    name = "provider"
    approval_required = False
    webhook_supported = False

    def __init__(self, secret_manager: SecretManager) -> None:
        self.secret_manager = secret_manager

    def get_config(self, tenant: TenantConfig) -> ProviderConfig:
        return tenant.providers.get(self.name, ProviderConfig())

    def resolve(self, tenant: TenantConfig) -> SecretResult:
        return self.secret_manager.resolve(self.get_config(tenant))

    def health(self, tenant: TenantConfig) -> ProviderHealth:
        cfg = self.get_config(tenant)
        if not cfg.enabled:
            return ProviderHealth(self.name, False, False, False, False, "disabled", "provider disabled")
        secret = self.resolve(tenant)
        approval_state = cfg.approval_state
        auth_ok = secret.ok
        webhook_ok = True
        if self.webhook_supported:
            webhook_ok = self.secret_manager.resolve_webhook_secret(cfg).ok
        tooling_ok = auth_ok and (approval_state == "approved" or not self.approval_required)
        detail = secret.detail if not secret.ok else "configured"
        if self.approval_required and approval_state != "approved":
            tooling_ok = False
            detail = approval_state
        return ProviderHealth(self.name, True, auth_ok, webhook_ok, tooling_ok, approval_state, detail)

    @staticmethod
    def _hmac_ok(secret: str, body: bytes, supplied: str) -> bool:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, supplied)

    @staticmethod
    def _auth_header(secret: dict[str, Any]) -> dict[str, str]:
        access_token = str(secret.get("access_token", "")).strip()
        if not access_token:
            raise ProviderError("access_token missing")
        return {"Authorization": f"Bearer {access_token}"}

    def request_json(
        self,
        method: str,
        url: str,
        secret: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", **self._auth_header(secret)}
        with httpx.Client(timeout=20.0) as client:
            response = client.request(method, url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json() if response.content else {}

    def normalize_webhook(
        self,
        tenant: TenantConfig,
        headers: dict[str, str],
        query: dict[str, str],
        body: bytes,
    ) -> dict[str, Any]:
        if not self.webhook_supported:
            raise ProviderError("webhook_not_supported")
        return {"provider": self.name, "tenant_id": tenant.tenant_id, "headers": headers, "query": query}
