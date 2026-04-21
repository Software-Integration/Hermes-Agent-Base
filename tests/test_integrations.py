import json

from fastapi.testclient import TestClient

from src.config import ProviderConfig, TenantConfig
from src.integrations.google.client import GoogleProvider
from src.integrations.registry import IntegrationManager
from src.integrations.telegram.client import TelegramProvider
from src.integrations.whatsapp.client import WhatsAppProvider
from src.main import app
from src.services.audit_log import AuditLogger
from src.services.metrics import SecurityMetrics
from src.services.secret_manager import SecretManager


def _tenant_with_provider(name: str, provider_cfg: ProviderConfig) -> TenantConfig:
    return TenantConfig(
        tenant_id="tenant-a",
        api_key="key-a",
        allowed_tools=["comm.telegram.send_message", "comm.whatsapp.send_text", "collab.google_chat.send_message"],
        allowed_capabilities=["comm.telegram.send", "comm.whatsapp.send", "collab.google_chat.write"],
        providers={name: provider_cfg},
    )


def test_secret_manager_resolves_stub(monkeypatch):
    monkeypatch.setattr("src.services.secret_manager.settings.provider_secrets_json", '{"stub/google":{"access_token":"abc"}}')
    manager = SecretManager()
    result = manager.resolve(ProviderConfig(enabled=True, secret_backend="stub", secret_ref="stub/google"))
    assert result.ok is True
    assert result.data["access_token"] == "abc"


def test_google_provider_health_reports_missing_secret():
    provider = GoogleProvider(SecretManager())
    tenant = _tenant_with_provider("google", ProviderConfig(enabled=True, secret_backend="stub", secret_ref="missing"))
    health = provider.health(tenant)
    assert health.auth_ok is False
    assert health.detail.startswith("missing_stub_secret")


def test_telegram_webhook_signature(monkeypatch):
    monkeypatch.setattr(
        "src.services.secret_manager.settings.provider_secrets_json",
        '{"stub/telegram":{"bot_token":"token"},"stub/telegram-webhook":{"secret_token":"verify-me"}}',
    )
    provider = TelegramProvider(SecretManager())
    tenant = _tenant_with_provider(
        "telegram",
        ProviderConfig(enabled=True, secret_backend="stub", secret_ref="stub/telegram", webhook_secret_ref="stub/telegram-webhook"),
    )
    event = provider.normalize_webhook(
        tenant,
        {"x-telegram-bot-api-secret-token": "verify-me"},
        {},
        json.dumps({"update_id": 1}).encode("utf-8"),
    )
    assert event["provider"] == "telegram"


def test_whatsapp_webhook_verification(monkeypatch):
    monkeypatch.setattr(
        "src.services.secret_manager.settings.provider_secrets_json",
        '{"stub/wa":{"access_token":"x","phone_number_id":"1"},"stub/wa-hook":{"verify_token":"vtok"}}',
    )
    provider = WhatsAppProvider(SecretManager())
    tenant = _tenant_with_provider(
        "whatsapp",
        ProviderConfig(enabled=True, secret_backend="stub", secret_ref="stub/wa", webhook_secret_ref="stub/wa-hook"),
    )
    event = provider.normalize_webhook(
        tenant,
        {},
        {"hub.mode": "subscribe", "hub.verify_token": "vtok", "hub.challenge": "ok"},
        b"",
    )
    assert event["challenge"] == "ok"


def test_integration_manager_reports_access_gated_provider():
    manager = IntegrationManager(audit_logger=AuditLogger(), metrics=SecurityMetrics())
    tenant = TenantConfig(
        tenant_id="tenant-a",
        api_key="key-a",
        providers={
            "linkedin": ProviderConfig(
                enabled=True,
                secret_backend="stub",
                secret_ref="missing",
                approval_state="configured_but_not_approved",
                capabilities=["ads.linkedin.read"],
            )
        },
    )
    statuses = manager.provider_dependency_statuses({"tenant-a": tenant})
    linkedin = [item for item in statuses if item.name == "provider.linkedin"][0]
    assert linkedin.ok is False
    assert "configured_but_not_approved" in linkedin.detail
