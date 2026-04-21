from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderError


def build_whatsapp_secret(tenant: TenantConfig, provider) -> dict:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    required = {"access_token", "phone_number_id"}
    missing = [key for key in required if key not in secret.data]
    if missing:
        raise ProviderError(f"whatsapp missing fields:{','.join(missing)}")
    return secret.data

