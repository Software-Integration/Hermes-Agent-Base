from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderError


def normalize_linkedin_event(provider, tenant: TenantConfig, headers: dict[str, str], query: dict[str, str], body: bytes) -> dict:
    raise ProviderError("linkedin_webhook_not_supported")

