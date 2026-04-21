from __future__ import annotations

import json

from ..config import settings
from .wallet_store import WalletStore

try:
    import stripe
except Exception:  # pragma: no cover
    stripe = None


class PaymentService:
    def __init__(self, wallet_store: WalletStore) -> None:
        self.wallet_store = wallet_store
        if stripe is not None and settings.stripe_secret_key:
            stripe.api_key = settings.stripe_secret_key

    @property
    def configured(self) -> bool:
        return stripe is not None and bool(settings.stripe_secret_key)

    def create_topup_checkout_session(self, tenant_id: str, amount_cents: int, currency: str = "usd") -> dict:
        if not self.configured:
            raise RuntimeError("stripe_not_configured")
        if amount_cents <= 0:
            raise ValueError("invalid_topup_amount")
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            success_url=settings.stripe_success_url,
            cancel_url=settings.stripe_cancel_url,
            metadata={"tenant_id": tenant_id, "wallet_topup_cents": str(amount_cents), "kind": "wallet_topup"},
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency,
                        "unit_amount": amount_cents,
                        "product_data": {"name": f"Hermes wallet top-up for {tenant_id}"},
                    },
                }
            ],
        )
        return {"id": session["id"], "url": session["url"], "amount_cents": amount_cents, "currency": currency}

    def verify_and_process_webhook(self, body: bytes, signature: str) -> dict:
        if not self.configured or not settings.stripe_webhook_secret:
            raise RuntimeError("stripe_webhook_not_configured")
        event = stripe.Webhook.construct_event(body, signature, settings.stripe_webhook_secret)
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            metadata = session.get("metadata", {}) or {}
            if metadata.get("kind") == "wallet_topup":
                tenant_id = str(metadata.get("tenant_id", ""))
                amount_cents = int(metadata.get("wallet_topup_cents", "0"))
                balance = self.wallet_store.credit(
                    tenant_id,
                    amount_cents,
                    reference=str(session.get("id", "")),
                    kind="stripe_topup",
                )
                return {"ok": True, "event_type": event["type"], "tenant_id": tenant_id, "balance_cents": balance.balance_cents}
        return {"ok": True, "event_type": event["type"], "ignored": True}
