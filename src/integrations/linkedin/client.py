from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_linkedin_secret
from .tools import descriptors


class LinkedInProvider(ProviderBase):
    name = "linkedin"
    approval_required = True

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        cfg = self.get_config(tenant)
        if cfg.approval_state != "approved":
            return {"ok": False, "error_code": "provider_not_approved", "reason": cfg.approval_state}
        secret = build_linkedin_secret(tenant, self)
        if action == "list_campaigns":
            account_id = arguments["account_id"]
            url = f"https://api.linkedin.com/rest/adAccounts/{account_id}/adCampaigns"
            return {"ok": True, "provider": self.name, "response": self.request_json("GET", url, {"access_token": secret["access_token"]})}
        raise ProviderError(f"unknown action {action}")

