from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderError


def build_telegram_secret(tenant: TenantConfig, provider) -> dict:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    if "bot_token" not in secret.data:
        raise ProviderError("telegram bot_token missing")
    return secret.data

