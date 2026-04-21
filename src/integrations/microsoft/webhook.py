from __future__ import annotations

import json

from ...config import TenantConfig
from ..base import ProviderError


def normalize_teams_event(provider, tenant: TenantConfig, headers: dict[str, str], query: dict[str, str], body: bytes) -> dict:
    secret = provider.secret_manager.resolve_webhook_secret(provider.get_config(tenant))
    if not secret.ok:
        raise ProviderError(secret.detail)
    supplied = headers.get("x-integration-signature", "")
    expected = str(secret.data.get("shared_secret", ""))
    if expected and supplied != expected:
        raise ProviderError("invalid_microsoft_webhook_signature")
    payload = json.loads(body.decode("utf-8") or "{}") if body else {}
    return {"provider": "microsoft", "tenant_id": tenant.tenant_id, "event_type": payload.get("type", "unknown"), "payload": payload}

