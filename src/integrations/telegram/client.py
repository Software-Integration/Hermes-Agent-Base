from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_telegram_secret
from .tools import descriptors
from .webhook import normalize_telegram_event


class TelegramProvider(ProviderBase):
    name = "telegram"
    webhook_supported = True

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        secret = build_telegram_secret(tenant, self)
        if action == "send_message":
            url = f"https://api.telegram.org/bot{secret['bot_token']}/sendMessage"
            return {"ok": True, "provider": self.name, "response": self.request_json("POST", url, {"access_token": secret["bot_token"]}, {"chat_id": arguments["chat_id"], "text": arguments["text"]})}
        raise ProviderError(f"unknown action {action}")

    def normalize_webhook(self, tenant, headers, query, body):
        return normalize_telegram_event(self, tenant, headers, query, body)

