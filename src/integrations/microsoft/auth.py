from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import TenantConfig
from ..base import ProviderError


def build_graph_headers(tenant: TenantConfig, provider) -> tuple[dict, dict]:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    base_url = secret.data.get("base_url", "https://graph.microsoft.com")
    if "access_token" not in secret.data:
        raise ProviderError("microsoft access_token missing")
    return {"Authorization": f"Bearer {secret.data['access_token']}", "Content-Type": "application/json"}, {"base_url": base_url, **secret.data}


def microsoft_oauth_start(provider, tenant: TenantConfig, state: str, redirect_uri: str) -> str:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    client_id = str(secret.data.get("client_id", "")).strip()
    tenant_authority = str(secret.data.get("authority_tenant", "common")).strip() or "common"
    if not client_id:
        raise ProviderError("microsoft client_id missing")
    scopes = provider.get_config(tenant).scopes or ["https://graph.microsoft.com/.default"]
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "state": state,
        }
    )
    return f"https://login.microsoftonline.com/{tenant_authority}/oauth2/v2.0/authorize?{query}"


def microsoft_exchange_code(provider, tenant: TenantConfig, code: str, redirect_uri: str) -> dict:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    client_id = str(secret.data.get("client_id", "")).strip()
    client_secret = str(secret.data.get("client_secret", "")).strip()
    tenant_authority = str(secret.data.get("authority_tenant", "common")).strip() or "common"
    scopes = provider.get_config(tenant).scopes or ["https://graph.microsoft.com/.default"]
    if not client_id or not client_secret:
        raise ProviderError("microsoft oauth client credentials missing")
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            f"https://login.microsoftonline.com/{tenant_authority}/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": " ".join(scopes),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()
