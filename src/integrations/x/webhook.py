from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderError


def normalize_x_event(provider, tenant: TenantConfig, headers: dict[str, str], query: dict[str, str], body: bytes) -> dict:
    raise ProviderError("x_webhook_not_supported")

