from __future__ import annotations

import hashlib
import hmac
import json

from ...config import TenantConfig
from ..base import ProviderError


def normalize_whatsapp_event(provider, tenant: TenantConfig, headers: dict[str, str], query: dict[str, str], body: bytes) -> dict:
    cfg = provider.get_config(tenant)
    secret = provider.secret_manager.resolve_webhook_secret(cfg)
    if not secret.ok:
        raise ProviderError(secret.detail)
    if query.get("hub.mode") == "subscribe":
        verify_token = str(secret.data.get("verify_token", ""))
        if verify_token and query.get("hub.verify_token") != verify_token:
            raise ProviderError("invalid_whatsapp_verify_token")
        return {"provider": "whatsapp", "tenant_id": tenant.tenant_id, "event_type": "verification", "challenge": query.get("hub.challenge", "")}
    app_secret = str(secret.data.get("app_secret", ""))
    signature = headers.get("x-hub-signature-256", "").replace("sha256=", "")
    if app_secret:
        digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if signature and not hmac.compare_digest(digest, signature):
            raise ProviderError("invalid_whatsapp_webhook_signature")
    payload = json.loads(body.decode("utf-8") or "{}") if body else {}
    return {"provider": "whatsapp", "tenant_id": tenant.tenant_id, "event_type": "message", "payload": payload}

