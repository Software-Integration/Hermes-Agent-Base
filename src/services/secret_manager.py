from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..config import ProviderConfig, settings

try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None

try:
    from azure.identity import ClientSecretCredential, DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
except Exception:  # pragma: no cover
    ClientSecretCredential = None
    DefaultAzureCredential = None
    SecretClient = None

try:
    from google.cloud import secretmanager as gcp_secretmanager
except Exception:  # pragma: no cover
    gcp_secretmanager = None


@dataclass(frozen=True)
class SecretResult:
    ok: bool
    data: dict[str, Any]
    detail: str


class SecretManager:
    def __init__(self) -> None:
        try:
            self._stub = json.loads(settings.provider_secrets_json or "{}")
        except Exception:
            self._stub = {}

    @staticmethod
    def _parse_json(value: str) -> dict[str, Any]:
        if not value:
            return {}
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {"value": parsed}

    def _resolve_stub(self, ref: str) -> SecretResult:
        if ref not in self._stub:
            return SecretResult(False, {}, f"missing_stub_secret:{ref}")
        return SecretResult(True, dict(self._stub[ref]), "resolved")

    def _resolve_aws(self, provider: ProviderConfig) -> SecretResult:
        if boto3 is None:
            return SecretResult(False, {}, "boto3_not_installed")
        try:
            client = boto3.client("secretsmanager", region_name=provider.region or None)
            response = client.get_secret_value(SecretId=provider.secret_ref)
            return SecretResult(True, self._parse_json(response.get("SecretString", "")), "resolved")
        except Exception as exc:
            return SecretResult(False, {}, str(exc))

    def _resolve_azure(self, provider: ProviderConfig) -> SecretResult:
        if SecretClient is None:
            return SecretResult(False, {}, "azure_sdk_not_installed")
        try:
            vault_name, secret_name = provider.secret_ref.split("/", 1)
            vault_url = f"https://{vault_name}.vault.azure.net"
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            client = SecretClient(vault_url=vault_url, credential=credential)
            secret = client.get_secret(secret_name)
            return SecretResult(True, self._parse_json(secret.value or ""), "resolved")
        except Exception as exc:
            return SecretResult(False, {}, str(exc))

    def _resolve_gcp(self, provider: ProviderConfig) -> SecretResult:
        if gcp_secretmanager is None:
            return SecretResult(False, {}, "gcp_secretmanager_not_installed")
        try:
            client = gcp_secretmanager.SecretManagerServiceClient()
            response = client.access_secret_version(name=provider.secret_ref)
            payload = response.payload.data.decode("utf-8")
            return SecretResult(True, self._parse_json(payload), "resolved")
        except Exception as exc:
            return SecretResult(False, {}, str(exc))

    def resolve(self, provider: ProviderConfig) -> SecretResult:
        backend = provider.secret_backend
        if backend == "aws_secrets_manager":
            return self._resolve_aws(provider)
        if backend == "azure_key_vault":
            return self._resolve_azure(provider)
        if backend == "gcp_secret_manager":
            return self._resolve_gcp(provider)
        return self._resolve_stub(provider.secret_ref)

    def resolve_webhook_secret(self, provider: ProviderConfig) -> SecretResult:
        if not provider.webhook_secret_ref:
            return SecretResult(False, {}, "webhook_secret_missing")
        shadow = ProviderConfig(
            enabled=provider.enabled,
            secret_backend=provider.secret_backend,
            secret_ref=provider.webhook_secret_ref,
            webhook_secret_ref="",
            capabilities=provider.capabilities,
            scopes=provider.scopes,
            region=provider.region,
            account_id=provider.account_id,
            project_id=provider.project_id,
            approval_state=provider.approval_state,
            metadata=provider.metadata,
        )
        return self.resolve(shadow)

    def _upsert_stub(self, ref: str, payload: dict[str, Any]) -> SecretResult:
        current = dict(self._stub.get(ref, {}))
        current.update(payload)
        self._stub[ref] = current
        return SecretResult(True, current, "updated")

    def _upsert_aws(self, provider: ProviderConfig, payload: dict[str, Any]) -> SecretResult:
        if boto3 is None:
            return SecretResult(False, {}, "boto3_not_installed")
        client = boto3.client("secretsmanager", region_name=provider.region or None)
        body = json.dumps(payload)
        try:
            client.describe_secret(SecretId=provider.secret_ref)
            client.put_secret_value(SecretId=provider.secret_ref, SecretString=body)
        except Exception:
            try:
                client.create_secret(Name=provider.secret_ref, SecretString=body)
            except Exception as exc:
                return SecretResult(False, {}, str(exc))
        return SecretResult(True, payload, "updated")

    def _upsert_azure(self, provider: ProviderConfig, payload: dict[str, Any]) -> SecretResult:
        if SecretClient is None:
            return SecretResult(False, {}, "azure_sdk_not_installed")
        try:
            vault_name, secret_name = provider.secret_ref.split("/", 1)
            vault_url = f"https://{vault_name}.vault.azure.net"
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            client = SecretClient(vault_url=vault_url, credential=credential)
            client.set_secret(secret_name, json.dumps(payload))
            return SecretResult(True, payload, "updated")
        except Exception as exc:
            return SecretResult(False, {}, str(exc))

    def _upsert_gcp(self, provider: ProviderConfig, payload: dict[str, Any]) -> SecretResult:
        if gcp_secretmanager is None:
            return SecretResult(False, {}, "gcp_secretmanager_not_installed")
        try:
            client = gcp_secretmanager.SecretManagerServiceClient()
            client.add_secret_version(
                parent=provider.secret_ref.rsplit("/versions/", 1)[0] if "/versions/" in provider.secret_ref else provider.secret_ref,
                payload={"data": json.dumps(payload).encode("utf-8")},
            )
            return SecretResult(True, payload, "updated")
        except Exception as exc:
            return SecretResult(False, {}, str(exc))

    def upsert(self, provider: ProviderConfig, payload: dict[str, Any]) -> SecretResult:
        backend = provider.secret_backend
        if backend == "aws_secrets_manager":
            return self._upsert_aws(provider, payload)
        if backend == "azure_key_vault":
            return self._upsert_azure(provider, payload)
        if backend == "gcp_secret_manager":
            return self._upsert_gcp(provider, payload)
        return self._upsert_stub(provider.secret_ref, payload)
