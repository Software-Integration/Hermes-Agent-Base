from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from ..config import settings


class OAuthStateService:
    def __init__(self) -> None:
        self._secret = settings.oauth_state_secret or "dev-oauth-state-secret"

    def create(self, tenant_id: str, provider: str) -> str:
        payload = {"tenant_id": tenant_id, "provider": provider, "ts": int(time.time())}
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        sig = hmac.new(self._secret.encode("utf-8"), body, hashlib.sha256).hexdigest().encode("utf-8")
        token = base64.urlsafe_b64encode(body + b"." + sig).decode("utf-8")
        return token

    def verify(self, token: str, max_age_seconds: int = 900) -> dict[str, str]:
        raw = base64.urlsafe_b64decode(token.encode("utf-8"))
        body, sig = raw.rsplit(b".", 1)
        expected = hmac.new(self._secret.encode("utf-8"), body, hashlib.sha256).hexdigest().encode("utf-8")
        if not hmac.compare_digest(sig, expected):
            raise ValueError("invalid_oauth_state_signature")
        payload = json.loads(body.decode("utf-8"))
        if int(time.time()) - int(payload.get("ts", 0)) > max_age_seconds:
            raise ValueError("oauth_state_expired")
        return {"tenant_id": str(payload["tenant_id"]), "provider": str(payload["provider"])}
