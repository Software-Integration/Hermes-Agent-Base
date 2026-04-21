from __future__ import annotations

import json

from ...config import TenantConfig
from ..base import ProviderError


def normalize_telegram_event(provider, tenant: TenantConfig, headers: dict[str, str], query: dict[str, str], body: bytes) -> dict:
    secret = provider.secret_manager.resolve_webhook_secret(provider.get_config(tenant))
    if not secret.ok:
        raise ProviderError(secret.detail)
    expected = str(secret.data.get("secret_token", ""))
    supplied = headers.get("x-telegram-bot-api-secret-token", "")
    if expected and supplied != expected:
        raise ProviderError("invalid_telegram_webhook_signature")
    payload = json.loads(body.decode("utf-8") or "{}") if body else {}
    return {"provider": "telegram", "tenant_id": tenant.tenant_id, "event_type": "update", "payload": payload}

