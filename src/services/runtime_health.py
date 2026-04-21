from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import settings
from ..context.semantic_index import SemanticContextIndex
from ..integrations.registry import IntegrationManager
from ..sandbox.executor import SandboxExecutor

try:
    import valkey
except Exception:  # pragma: no cover
    valkey = None

try:
    from qdrant_client import QdrantClient
except Exception:  # pragma: no cover
    QdrantClient = None


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    detail: str
    required: bool


class RuntimeHealth:
    def __init__(
        self,
        semantic_index: SemanticContextIndex | None = None,
        sandbox: SandboxExecutor | None = None,
        integrations: IntegrationManager | None = None,
    ) -> None:
        self._semantic_index = semantic_index
        self._sandbox = sandbox
        self._integrations = integrations

    async def check_opa(self) -> DependencyStatus:
        if not settings.opa_url:
            return DependencyStatus("opa", False, "opa_url not configured", settings.opa_required)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.opa_url.rstrip('/')}/health")
                return DependencyStatus("opa", response.is_success, str(response.status_code), settings.opa_required)
        except Exception as exc:
            return DependencyStatus("opa", False, str(exc), settings.opa_required)

    def check_valkey(self) -> DependencyStatus:
        if valkey is None:
            return DependencyStatus("valkey", False, "client not installed", False)
        try:
            client = valkey.from_url(settings.valkey_url, decode_responses=True)
            pong = client.ping()
            return DependencyStatus("valkey", bool(pong), "pong", False)
        except Exception as exc:
            return DependencyStatus("valkey", False, str(exc), False)

    def check_qdrant(self) -> DependencyStatus:
        if QdrantClient is None:
            return DependencyStatus("qdrant", False, "client not installed", False)
        try:
            client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
            collections = client.get_collections()
            count = len(getattr(collections, "collections", []) or [])
            return DependencyStatus("qdrant", True, f"collections={count}", False)
        except Exception as exc:
            path = Path(settings.app_data_dir) / "qdrant-local"
            if path.exists():
                return DependencyStatus("qdrant", False, "remote unavailable; local fallback ready", False)
            return DependencyStatus("qdrant", False, str(exc), False)

    def check_embedder(self) -> DependencyStatus:
        if self._semantic_index is None:
            return DependencyStatus("embedder", False, "semantic index not configured", not settings.allow_degraded_retrieval)
        ok, detail, degraded_ready = self._semantic_index.probe_embedder()
        required = not settings.allow_degraded_retrieval
        if ok:
            return DependencyStatus("embedder", True, detail, required)
        if degraded_ready:
            return DependencyStatus("embedder", False, detail, False)
        return DependencyStatus("embedder", False, detail, required)

    def check_tenant_config(self) -> DependencyStatus:
        if settings.config_errors:
            return DependencyStatus("tenant_config", False, "; ".join(settings.config_errors), True)
        return DependencyStatus(
            "tenant_config",
            True,
            f"{len(settings.tenants)} tenants loaded from {settings.tenant_provider.source}",
            True,
        )

    def check_sandbox(self) -> DependencyStatus:
        if settings.environment == "production" and settings.sandbox_runtime == "runsc" and Path("/proc").exists() is False:
            return DependencyStatus("sandbox", False, "runsc expected on linux production host", True)
        if self._sandbox is None:
            return DependencyStatus("sandbox", False, "sandbox executor not configured", True)
        ok, detail = self._sandbox.probe()
        return DependencyStatus("sandbox", ok, detail, True)

    def check_integrations(self) -> list[DependencyStatus]:
        if self._integrations is None:
            return []
        return self._integrations.provider_dependency_statuses(settings.tenants)
