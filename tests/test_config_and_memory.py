import json

from src.config import ConfigValidationError, EnvTenantConfigProvider, Settings
from src.context.memory_store import ChatMessage, TenantMemoryStore


def test_env_provider_rejects_missing_api_key():
    provider = EnvTenantConfigProvider('{"tenant-a":{"name":"bad"}}')
    try:
        provider.load()
    except ConfigValidationError as exc:
        assert "missing api_key" in str(exc)
    else:
        raise AssertionError("expected ConfigValidationError")


def test_settings_reject_demo_values_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRETS_BACKEND", "secret_env")
    monkeypatch.setenv("SECRETS_TENANTS_JSON", '{"tenant-demo":{"api_key":"demo-key"}}')
    cfg = Settings()
    assert cfg.is_ready_for_traffic is False
    assert any("demo" in item for item in cfg.config_errors)


def test_memory_store_persists_preview_only(monkeypatch, tmp_path):
    monkeypatch.setattr("src.context.memory_store.settings.app_data_dir", str(tmp_path))
    store = TenantMemoryStore(max_turns=10)
    content = "secret message " * 20
    store.append("tenant-a", ChatMessage(role="user", content=content))
    data = json.loads((tmp_path / "tenant-memory" / "tenant-a.json").read_text(encoding="utf-8"))
    persisted = data["history"][0]
    assert persisted["content"] != content
    assert persisted["classification"] == "message_preview"


def test_memory_store_handles_corruption(monkeypatch, tmp_path):
    monkeypatch.setattr("src.context.memory_store.settings.app_data_dir", str(tmp_path))
    tenant_dir = tmp_path / "tenant-memory"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "tenant-a.json").write_text("{broken", encoding="utf-8")
    store = TenantMemoryStore(max_turns=10)
    assert store.get_history("tenant-a") == []
