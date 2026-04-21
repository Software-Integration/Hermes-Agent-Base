from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderError


def build_aws_secret(tenant: TenantConfig, provider) -> dict:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    required = {"aws_access_key_id", "aws_secret_access_key"}
    missing = [key for key in required if key not in secret.data]
    if missing:
        raise ProviderError(f"aws missing fields:{','.join(missing)}")
    return secret.data

