from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    enabled: bool = False
    secret_backend: str = "stub"
    secret_ref: str = ""
    webhook_secret_ref: str = ""
    capabilities: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    region: str = ""
    account_id: str = ""
    project_id: str = ""
    approval_state: str = "approved"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ProviderConfig":
        return cls(
            enabled=bool(payload.get("enabled", False)),
            secret_backend=str(payload.get("secret_backend", "stub")).strip().lower(),
            secret_ref=str(payload.get("secret_ref", "")).strip(),
            webhook_secret_ref=str(payload.get("webhook_secret_ref", "")).strip(),
            capabilities=[str(item) for item in payload.get("capabilities", [])],
            scopes=[str(item) for item in payload.get("scopes", [])],
            region=str(payload.get("region", "")).strip(),
            account_id=str(payload.get("account_id", "")).strip(),
            project_id=str(payload.get("project_id", "")).strip(),
            approval_state=str(payload.get("approval_state", "approved")).strip().lower(),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class TenantConfig:
    tenant_id: str
    api_key: str
    name: str = ""
    status: str = "active"
    allowed_tools: list[str] = field(default_factory=list)
    allowed_capabilities: list[str] = field(default_factory=list)
    allowed_model_classes: list[str] = field(default_factory=lambda: ["default"])
    context_char_limit: int = 8000
    rate_limit_per_minute: int = 120
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, tenant_id: str, payload: dict[str, Any]) -> "TenantConfig":
        if "api_key" not in payload:
            raise ConfigValidationError(f"tenant {tenant_id} missing api_key")
        provider_payload = dict(payload.get("providers", {}))
        providers = {
            str(name): ProviderConfig.from_payload(dict(provider_cfg))
            for name, provider_cfg in provider_payload.items()
        }
        allowed_capabilities = [str(item) for item in payload.get("allowed_capabilities", [])]
        if not allowed_capabilities:
            for provider_cfg in providers.values():
                allowed_capabilities.extend(provider_cfg.capabilities)
        return cls(
            tenant_id=tenant_id,
            api_key=str(payload["api_key"]),
            name=str(payload.get("name", tenant_id)),
            status=str(payload.get("status", "active")).lower(),
            allowed_tools=[str(item) for item in payload.get("allowed_tools", [])],
            allowed_capabilities=sorted(set(allowed_capabilities)),
            allowed_model_classes=[
                str(item) for item in payload.get("allowed_model_classes", ["default"])
            ],
            context_char_limit=int(payload.get("context_char_limit", 8000)),
            rate_limit_per_minute=int(payload.get("rate_limit_per_minute", 120)),
            providers=providers,
            metadata=dict(payload.get("metadata", {})),
        )


class TenantConfigProvider:
    source = "unknown"

    def load(self) -> dict[str, TenantConfig]:
        raise NotImplementedError


class EnvTenantConfigProvider(TenantConfigProvider):
    source = "env"

    def __init__(self, raw_json: str) -> None:
        self._raw_json = raw_json

    def load(self) -> dict[str, TenantConfig]:
        if not self._raw_json.strip():
            return {}
        parsed = json.loads(self._raw_json)
        return {
            tenant_id: TenantConfig.from_payload(tenant_id, payload)
            for tenant_id, payload in parsed.items()
        }


class FileTenantConfigProvider(TenantConfigProvider):
    source = "file"

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load(self) -> dict[str, TenantConfig]:
        if not self._path.exists():
            raise ConfigValidationError(f"tenant config file not found: {self._path}")
        parsed = json.loads(self._path.read_text(encoding="utf-8"))
        return {
            tenant_id: TenantConfig.from_payload(tenant_id, payload)
            for tenant_id, payload in parsed.items()
        }


class SecretTenantConfigProvider(TenantConfigProvider):
    source = "secret_env"

    def __init__(self, env_key: str) -> None:
        self._env_key = env_key

    def load(self) -> dict[str, TenantConfig]:
        raw = os.getenv(self._env_key, "").strip()
        if not raw:
            raise ConfigValidationError(f"missing secret tenant config in {self._env_key}")
        parsed = json.loads(raw)
        return {
            tenant_id: TenantConfig.from_payload(tenant_id, payload)
            for tenant_id, payload in parsed.items()
        }


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "Hermes Commercial Foundation")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.environment = os.getenv("ENVIRONMENT", "development").strip().lower()
        self.secrets_backend = os.getenv("SECRETS_BACKEND", "env").strip().lower()
        self.sandbox_runtime = os.getenv("SANDBOX_RUNTIME", "runc").strip().lower()
        self.opa_required = os.getenv("OPA_REQUIRED", "true").lower() == "true"
        self.allow_degraded_retrieval = (
            os.getenv("ALLOW_DEGRADED_RETRIEVAL", "true").lower() == "true"
        )
        self.audit_redaction_level = os.getenv("AUDIT_REDACTION_LEVEL", "strict").strip().lower()
        self.audit_retention_days = int(os.getenv("AUDIT_RETENTION_DAYS", "30"))

        self.hermes_base_url = os.getenv("HERMES_BASE_URL", "").strip()
        self.hermes_api_key = os.getenv("HERMES_API_KEY", "").strip()
        self.hermes_model = os.getenv("HERMES_MODEL", "").strip()
        self.hermes_source_dir = os.getenv(
            "HERMES_SOURCE_DIR",
            str(Path(__file__).resolve().parent.parent / "hermes-agent"),
        )
        self.request_timeout = float(os.getenv("HERMES_TIMEOUT", "20"))

        self.sandbox_mode = os.getenv("SANDBOX_MODE", "LOCAL").upper()
        self.sandbox_image = os.getenv("SANDBOX_IMAGE", "python:3.11-slim").strip()
        self.sandbox_seccomp_profile = os.getenv(
            "SANDBOX_SECCOMP_PROFILE",
            str(Path(__file__).resolve().parent.parent / "sandbox" / "seccomp" / "default.json"),
        ).strip()
        self.valkey_url = os.getenv("VALKEY_URL", "valkey://valkey:6379/0").strip()
        self.qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333").strip()
        self.opa_url = os.getenv("OPA_URL", "http://opa:8181").strip()
        self.app_data_dir = os.getenv(
            "APP_DATA_DIR",
            str(Path(__file__).resolve().parent.parent / "data"),
        )
        self.embedding_model = os.getenv(
            "EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        ).strip()
        self.semantic_top_k = int(os.getenv("SEMANTIC_TOP_K", "3"))
        self.default_context_turns = int(os.getenv("DEFAULT_CONTEXT_TURNS", "14"))
        self.max_tool_args_bytes = int(os.getenv("MAX_TOOL_ARGS_BYTES", "4096"))
        self.max_context_recap_words = int(os.getenv("MAX_CONTEXT_RECAP_WORDS", "220"))
        self.tenant_config_file = os.getenv("TENANTS_FILE", "").strip()
        self.secret_tenants_env_key = os.getenv("SECRET_TENANTS_ENV_KEY", "SECRETS_TENANTS_JSON")
        self.provider_secrets_json = os.getenv("PROVIDER_SECRETS_JSON", "{}").strip()
        self.platform_providers_json = os.getenv("PLATFORM_PROVIDERS_JSON", "{}").strip()
        self.platform_admin_api_key = os.getenv("PLATFORM_ADMIN_API_KEY", "").strip()
        self.router_pricing_json = os.getenv("ROUTER_PRICING_JSON", "{}").strip()
        self.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
        self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        self.stripe_success_url = os.getenv("STRIPE_SUCCESS_URL", "https://example.com/billing/success").strip()
        self.stripe_cancel_url = os.getenv("STRIPE_CANCEL_URL", "https://example.com/billing/cancel").strip()
        self.app_base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
        self.oauth_state_secret = os.getenv("OAUTH_STATE_SECRET", "").strip()

        self.tenant_provider = self._build_tenant_provider()
        self.tenants = self.tenant_provider.load()
        self.platform_providers = self._load_platform_providers()
        self.router_pricing = self._load_router_pricing()
        self.config_errors = self._validate_configuration()

    def _build_tenant_provider(self) -> TenantConfigProvider:
        if self.secrets_backend == "file":
            if not self.tenant_config_file:
                raise ConfigValidationError("TENANTS_FILE is required when SECRETS_BACKEND=file")
            return FileTenantConfigProvider(self.tenant_config_file)
        if self.secrets_backend == "secret_env":
            return SecretTenantConfigProvider(self.secret_tenants_env_key)
        return EnvTenantConfigProvider(os.getenv("TENANTS_JSON", "").strip())

    def _load_platform_providers(self) -> dict[str, ProviderConfig]:
        if not self.platform_providers_json.strip():
            return {}
        parsed = json.loads(self.platform_providers_json)
        return {
            str(name): ProviderConfig.from_payload(dict(payload))
            for name, payload in parsed.items()
        }

    def _load_router_pricing(self) -> dict[str, int]:
        if not self.router_pricing_json.strip():
            return {}
        parsed = json.loads(self.router_pricing_json)
        return {str(key): int(value) for key, value in parsed.items()}

    def _validate_configuration(self) -> list[str]:
        errors: list[str] = []

        if self.environment == "production" and self.secrets_backend == "env":
            errors.append("production environment cannot use env tenant backend")
        if self.environment == "production" and self.sandbox_mode == "LOCAL":
            errors.append("production environment cannot use LOCAL sandbox mode")
        if self.environment == "production" and self.opa_required and not self.opa_url:
            errors.append("production environment requires OPA_URL")
        if self.environment == "production" and os.name == "nt":
            errors.append("production environment requires linux host for hardened sandbox runtime")
        if not self.tenants:
            errors.append("no tenant configuration loaded")

        for tenant_id, tenant in self.tenants.items():
            if tenant_id == "tenant-demo":
                errors.append("demo tenant is not allowed")
            if tenant.api_key == "demo-key":
                errors.append(f"tenant {tenant_id} uses demo api key")
            if tenant.status not in {"active", "disabled", "suspended"}:
                errors.append(f"tenant {tenant_id} has invalid status {tenant.status}")
            for provider_name, provider_cfg in tenant.providers.items():
                if provider_cfg.enabled and not provider_cfg.secret_ref:
                    errors.append(f"tenant {tenant_id} provider {provider_name} missing secret_ref")
                if provider_cfg.approval_state not in {
                    "approved",
                    "configured_but_not_approved",
                    "disabled",
                    "oauth_not_completed",
                }:
                    errors.append(
                        f"tenant {tenant_id} provider {provider_name} has invalid approval_state {provider_cfg.approval_state}"
                    )
                if self.environment == "production" and provider_cfg.enabled:
                    if provider_cfg.secret_backend not in {
                        "aws_secrets_manager",
                        "azure_key_vault",
                        "gcp_secret_manager",
                    }:
                        errors.append(
                            f"tenant {tenant_id} provider {provider_name} must use cloud secret backend in production"
                        )
        for provider_name, provider_cfg in self.platform_providers.items():
            if provider_cfg.enabled and not provider_cfg.secret_ref:
                errors.append(f"platform provider {provider_name} missing secret_ref")
        if self.environment == "production" and not self.platform_admin_api_key:
            errors.append("production environment requires PLATFORM_ADMIN_API_KEY for internal routing")
        if self.environment == "production" and not self.oauth_state_secret:
            errors.append("production environment requires OAUTH_STATE_SECRET")

        return errors

    @property
    def is_ready_for_traffic(self) -> bool:
        return not self.config_errors


settings = Settings()
