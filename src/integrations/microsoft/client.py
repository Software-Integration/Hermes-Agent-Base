from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_graph_headers
from .tools import descriptors
from .webhook import normalize_teams_event


class MicrosoftProvider(ProviderBase):
    name = "microsoft"
    webhook_supported = True

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        headers, secret = build_graph_headers(tenant, self)
        if action == "send_message":
            chat_id = arguments["chat_id"]
            payload = {"body": {"content": arguments["text"]}}
            url = f"{secret['base_url'].rstrip('/')}/v1.0/chats/{chat_id}/messages"
            return {"ok": True, "provider": self.name, "response": self.request_json("POST", url, {"access_token": secret["access_token"]}, payload)}
        raise ProviderError(f"unknown action {action}")

    def normalize_webhook(self, tenant, headers, query, body):
        return normalize_teams_event(self, tenant, headers, query, body)

