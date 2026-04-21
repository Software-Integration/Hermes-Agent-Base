from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from ..integrations.registry import IntegrationManager
from ..services.wallet_store import WalletStore


@dataclass(frozen=True)
class RouteResult:
    provider: str
    action: str
    execution_scope: str
    billed_cents: int
    payload: dict


class RouterService:
    def __init__(self, integration_manager: IntegrationManager, wallet_store: WalletStore) -> None:
        self.integration_manager = integration_manager
        self.wallet_store = wallet_store

    def price_for(self, provider: str, action: str) -> int:
        return int(settings.router_pricing.get(f"{provider}.{action}", 0))

    def execute(
        self,
        tenant,
        provider: str,
        action: str,
        arguments: dict,
        execution_scope: str,
    ) -> RouteResult:
        execution_scope = execution_scope.lower()
        billed_cents = 0
        if execution_scope == "tenant":
            billed_cents = self.price_for(provider, action)
            if billed_cents > 0:
                self.wallet_store.debit(tenant.tenant_id, billed_cents, reference=f"{provider}.{action}", kind="route_usage")
        payload = self.integration_manager.execute(provider, action, tenant, arguments, execution_scope=execution_scope)
        return RouteResult(provider=provider, action=action, execution_scope=execution_scope, billed_cents=billed_cents, payload=payload)
