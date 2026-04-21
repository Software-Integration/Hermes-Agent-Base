from fastapi.testclient import TestClient

from src.config import ProviderConfig, settings
from src.main import app, payment_service, wallet_store


def _headers():
    return {"X-Tenant-Id": "tenant-a", "Authorization": "Bearer key-a"}


def test_router_catalog_exposes_tenant_providers(monkeypatch):
    tenant = settings.tenants["tenant-a"]
    tenant.providers["telegram"] = ProviderConfig(enabled=True, secret_backend="stub", secret_ref="stub/tg", capabilities=["comm.telegram.send"])
    with TestClient(app) as client:
        response = client.get("/v1/router/catalog", headers=_headers())
    assert response.status_code == 200
    assert response.json()["providers"][0]["provider"] == "telegram"


def test_wallet_endpoint_reads_balance(tmp_path, monkeypatch):
    wallet_store._dir = tmp_path
    wallet_store.credit("tenant-a", 500, "seed", kind="seed")
    with TestClient(app) as client:
        response = client.get("/v1/billing/wallet", headers=_headers())
    assert response.status_code == 200
    assert response.json()["balance_cents"] == 500


def test_router_execute_bills_tenant(monkeypatch, tmp_path):
    wallet_store._dir = tmp_path
    wallet_store.credit("tenant-a", 1000, "seed", kind="seed")
    monkeypatch.setattr(settings, "router_pricing", {"telegram.send_message": 25})
    monkeypatch.setattr(
        "src.integrations.registry.IntegrationManager.execute",
        lambda self, provider, action, tenant, arguments, execution_scope="tenant": {"ok": True, "provider": provider, "action": action},
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/router/execute",
            json={"provider": "telegram", "action": "send_message", "execution_scope": "tenant", "arguments": {"chat_id": "1", "text": "hi"}},
            headers=_headers(),
        )
    assert response.status_code == 200
    assert response.json()["billed_cents"] == 25
    assert wallet_store.get_balance("tenant-a").balance_cents == 975


def test_platform_scope_requires_admin_key(monkeypatch, tmp_path):
    wallet_store._dir = tmp_path
    monkeypatch.setattr(settings, "platform_admin_api_key", "admin-key")
    with TestClient(app) as client:
        response = client.post(
            "/v1/router/execute",
            json={"provider": "telegram", "action": "send_message", "execution_scope": "platform", "arguments": {"chat_id": "1", "text": "hi"}},
            headers=_headers(),
        )
    assert response.status_code == 401


def test_billing_topup_requires_stripe(monkeypatch):
    monkeypatch.setattr("src.services.payment_service.stripe", None)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/v1/billing/topups/checkout-session", json={"amount_cents": 500}, headers=_headers())
    assert response.status_code == 500
