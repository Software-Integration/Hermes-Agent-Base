from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_x_secret
from .tools import descriptors


class XProvider(ProviderBase):
    name = "x"
    approval_required = True

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        cfg = self.get_config(tenant)
        if cfg.approval_state != "approved":
            return {"ok": False, "error_code": "provider_not_approved", "reason": cfg.approval_state}
        secret = build_x_secret(tenant, self)
        if action == "list_campaigns":
            account_id = arguments["account_id"]
            url = f"https://ads-api.x.com/12/accounts/{account_id}/campaigns"
            return {"ok": True, "provider": self.name, "response": self.request_json("GET", url, {"access_token": secret["access_token"]})}
        if action == "create_post":
            url = "https://api.x.com/2/tweets"
            return {"ok": True, "provider": self.name, "response": self.request_json("POST", url, {"access_token": secret["access_token"]}, {"text": arguments["text"]})}
        raise ProviderError(f"unknown action {action}")

