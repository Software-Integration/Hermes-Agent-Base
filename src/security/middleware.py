from dataclasses import dataclass
from secrets import compare_digest
from typing import Dict

from fastapi import Header, HTTPException, Request, status

from ..config import TenantConfig, settings
from ..services.state_store import TenantStateStore


@dataclass
class TenantContext:
    tenant: TenantConfig
    headers: Dict[str, str]
    rate_limit_remaining: int = 0
    rate_limit_reset_after_seconds: int = 0
    tenant_status: str = "unknown"
    auth_source: str = "tenant_provider"
    policy_version: str = "unbound"


state_store = TenantStateStore()


async def get_tenant(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    authorization: str = Header(..., alias="Authorization"),
) -> TenantContext:
    if not settings.is_ready_for_traffic:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "config_not_ready", "reason": "; ".join(settings.config_errors)},
        )
    if x_tenant_id not in settings.tenants:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "invalid_tenant", "reason": "invalid tenant id"},
        )

    tenant = settings.tenants[x_tenant_id]
    token = authorization.replace("Bearer ", "", 1) if authorization.startswith("Bearer ") else authorization
    if not compare_digest(token, tenant.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "invalid_api_key", "reason": "invalid api key"},
        )

    rate = state_store.check_rate_limit(tenant.tenant_id, tenant.rate_limit_per_minute)
    if not rate.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "rate_limit_exceeded",
                "reason": f"rate limit exceed for tenant {tenant.tenant_id}",
                "source": rate.source,
            },
        )

    return TenantContext(
        tenant=tenant,
        headers=dict(request.headers),
        rate_limit_remaining=rate.remaining,
        rate_limit_reset_after_seconds=rate.reset_after_seconds,
        tenant_status=tenant.status,
        auth_source=settings.tenant_provider.source,
    )
