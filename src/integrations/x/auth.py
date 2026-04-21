from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderError


def build_x_secret(tenant: TenantConfig, provider) -> dict:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    if "access_token" not in secret.data:
        raise ProviderError("x access_token missing")
    return secret.data

