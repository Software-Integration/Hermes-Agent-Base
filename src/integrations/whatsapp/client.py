from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_whatsapp_secret
from .tools import descriptors
from .webhook import normalize_whatsapp_event


class WhatsAppProvider(ProviderBase):
    name = "whatsapp"
    webhook_supported = True

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        secret = build_whatsapp_secret(tenant, self)
        url = f"https://graph.facebook.com/v23.0/{secret['phone_number_id']}/messages"
        if action == "send_text":
            payload = {"messaging_product": "whatsapp", "to": arguments["to"], "type": "text", "text": {"body": arguments["text"]}}
        elif action == "send_template":
            payload = {"messaging_product": "whatsapp", "to": arguments["to"], "type": "template", "template": {"name": arguments["template_name"], "language": {"code": arguments["language_code"]}}}
        else:
            raise ProviderError(f"unknown action {action}")
        return {"ok": True, "provider": self.name, "response": self.request_json("POST", url, {"access_token": secret["access_token"]}, payload)}

    def normalize_webhook(self, tenant, headers, query, body):
        return normalize_whatsapp_event(self, tenant, headers, query, body)

