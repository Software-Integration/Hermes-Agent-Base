import pytest
from fastapi.testclient import TestClient

from src.context.memory_store import ChatMessage
from src.config import settings
from src.main import app, audit_logger, hermes_adapter, memory_store, policy_engine, semantic_index
from src.services.policy_engine import PolicyDecision


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "config_errors", [])
    monkeypatch.setattr(settings, "environment", "development")
    memory_store._base_dir = tmp_path / "tenant-memory"
    memory_store._base_dir.mkdir(parents=True, exist_ok=True)
    audit_logger._path = tmp_path / "audit" / "events.jsonl"
    audit_logger._path.parent.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as test_client:
        yield test_client


def _headers(tenant_id="tenant-a", token="key-a"):
    return {"X-Tenant-Id": tenant_id, "Authorization": f"Bearer {token}"}


def test_chat_happy_path(client, monkeypatch):
    async def fake_auth(tenant, model_name):
        return PolicyDecision(True, "chat_allowed", "test", "v-test")

    async def fake_invoke(*args, **kwargs):
        return {"final_response": "ok", "messages": [], "api_calls": 1, "completed": True}

    monkeypatch.setattr(policy_engine, "authorize_chat", fake_auth)
    monkeypatch.setattr(semantic_index, "search", lambda *args, **kwargs: ([], False))
    monkeypatch.setattr(semantic_index, "upsert_messages", lambda *args, **kwargs: False)
    monkeypatch.setattr(hermes_adapter, "invoke", fake_invoke)
    response = client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hello"}]}, headers=_headers())
    assert response.status_code == 200
    assert response.json()["final_response"] == "ok"


def test_chat_denies_when_opa_down(client, monkeypatch):
    async def fake_auth(tenant, model_name):
        return PolicyDecision(False, "opa_unavailable", "critical_dependency", "unavailable")

    monkeypatch.setattr(policy_engine, "authorize_chat", fake_auth)
    response = client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hello"}]}, headers=_headers())
    assert response.status_code == 403
    assert response.json()["error_code"] == "policy_denied"


def test_tool_allowlist_deny(client):
    response = client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "hello"}], "requested_tools": ["not.allowed"]},
        headers=_headers(),
    )
    assert response.status_code == 403


def test_cross_tenant_wipe_denied(client):
    response = client.delete("/v1/tenants/tenant-b/state", headers=_headers("tenant-a", "key-a"))
    assert response.status_code == 403
    assert response.json()["error_code"] == "tenant_scope_violation"


def test_wipe_clears_tenant_memory(client):
    memory_store.append("tenant-a", ChatMessage(role="user", content="hello"))
    response = client.delete("/v1/tenants/tenant-a/state", headers=_headers())
    assert response.status_code == 200
    assert memory_store.get_history("tenant-a") == []
