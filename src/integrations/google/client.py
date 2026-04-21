from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_google_chat_headers
from .tools import descriptors
from .webhook import normalize_google_chat_event


class GoogleProvider(ProviderBase):
    name = "google"
    webhook_supported = True

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        headers, secret = build_google_chat_headers(tenant, self)
        if action == "send_message":
            space = arguments["space"]
            payload = {"text": arguments["text"]}
            url = f"{secret['base_url'].rstrip('/')}/v1/{space}/messages"
            return {"ok": True, "provider": self.name, "response": self.request_json("POST", url, {"access_token": secret["access_token"]}, payload)}
        raise ProviderError(f"unknown action {action}")

    def normalize_webhook(self, tenant, headers, query, body):
        return normalize_google_chat_event(self, tenant, headers, query, body)

