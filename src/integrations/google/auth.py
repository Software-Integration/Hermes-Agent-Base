from __future__ import annotations

from urllib.parse import urlencode

import httpx

from ...config import TenantConfig
from ..base import ProviderError


def build_google_chat_headers(tenant: TenantConfig, provider) -> tuple[dict, dict]:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    base_url = secret.data.get("base_url", "https://chat.googleapis.com")
    if "access_token" not in secret.data:
        raise ProviderError("google access_token missing")
    return {"Authorization": f"Bearer {secret.data['access_token']}", "Content-Type": "application/json"}, {"base_url": base_url, **secret.data}


def google_oauth_start(provider, tenant: TenantConfig, state: str, redirect_uri: str) -> str:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    client_id = str(secret.data.get("client_id", "")).strip()
    if not client_id:
        raise ProviderError("google client_id missing")
    scopes = provider.get_config(tenant).scopes or ["https://www.googleapis.com/auth/chat.bot"]
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def google_exchange_code(provider, tenant: TenantConfig, code: str, redirect_uri: str) -> dict:
    secret = provider.resolve(tenant)
    if not secret.ok:
        raise ProviderError(secret.detail)
    client_id = str(secret.data.get("client_id", "")).strip()
    client_secret = str(secret.data.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        raise ProviderError("google oauth client credentials missing")
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()
