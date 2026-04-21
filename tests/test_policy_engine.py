import pytest

from src.config import TenantConfig, settings
from src.services.policy_engine import PolicyDecision, PolicyEngine


@pytest.mark.asyncio
async def test_policy_engine_allows_chat_when_opa_allows(monkeypatch):
    engine = PolicyEngine()
    tenant = TenantConfig(tenant_id="tenant-a", api_key="key", allowed_model_classes=["default"])

    async def fake_query(payload):
        return PolicyDecision(True, "chat_allowed", "opa", "v-test")

    monkeypatch.setattr(engine, "_query_opa", fake_query)
    decision = await engine.authorize_chat(tenant, "")
    assert decision.allowed is True
    assert decision.policy_version == "v-test"


@pytest.mark.asyncio
async def test_policy_engine_fails_closed_when_opa_unavailable(monkeypatch):
    engine = PolicyEngine()
    tenant = TenantConfig(tenant_id="tenant-a", api_key="key", allowed_tools=["math.evaluate"])

    async def fake_query(payload):
        return None

    monkeypatch.setattr(engine, "_query_opa", fake_query)
    monkeypatch.setattr(settings, "opa_required", True)
    decision = await engine.authorize_tool(tenant, "math.evaluate")
    assert decision.allowed is False
    assert decision.reason == "opa_unavailable"


@pytest.mark.asyncio
async def test_policy_engine_local_denies_model_class(monkeypatch):
    engine = PolicyEngine()
    tenant = TenantConfig(tenant_id="tenant-a", api_key="key", allowed_model_classes=["anthropic"])

    async def fake_query(payload):
        return None

    monkeypatch.setattr(engine, "_query_opa", fake_query)
    monkeypatch.setattr(settings, "opa_required", False)
    decision = await engine.authorize_chat(tenant, "openai/gpt-5")
    assert decision.allowed is False
    assert decision.reason == "model_class_not_allowed"
