import json
import subprocess

import numpy as np
import pytest

from src.config import settings
from src.context.policy import ToolPolicyViolation
from src.context.semantic_index import SemanticContextIndex
from src.sandbox.executor import SandboxExecutor
from src.tools.tool_registry import ToolDescriptor


def _dummy_tool(arguments):
    return {"ok": True, "echo": arguments}


@pytest.mark.asyncio
async def test_sandbox_rejects_large_payload():
    executor = SandboxExecutor(mode="LOCAL")
    tool = ToolDescriptor(name="dummy", description="dummy", handler=_dummy_tool)
    large = {"blob": "x" * (settings.max_tool_args_bytes + 10)}
    with pytest.raises(ToolPolicyViolation):
        await executor.run(tool, large)


@pytest.mark.asyncio
async def test_sandbox_returns_invalid_json_error(monkeypatch):
    executor = SandboxExecutor(mode="CONTAINER")
    tool = ToolDescriptor(name="dummy", description="dummy", handler=_dummy_tool)

    class Completed:
        returncode = 0
        stdout = "not-json"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Completed())
    result = await executor.run(tool, {})
    assert result.ok is False
    assert result.payload["error_code"] == "invalid_sandbox_output"


@pytest.mark.asyncio
async def test_sandbox_handles_runtime_unavailable(monkeypatch):
    executor = SandboxExecutor(mode="CONTAINER")
    tool = ToolDescriptor(name="dummy", description="dummy", handler=_dummy_tool)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing docker")))
    result = await executor.run(tool, {})
    assert result.ok is False
    assert result.payload["error_code"] == "sandbox_runtime_unavailable"


def test_sandbox_probe_reports_runtime_unavailable(monkeypatch):
    executor = SandboxExecutor(mode="CONTAINER")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing docker")))
    ok, detail = executor.probe()
    assert ok is False
    assert "missing docker" in detail


def test_semantic_index_keeps_tenant_boundaries(monkeypatch):
    index = SemanticContextIndex()
    monkeypatch.setattr(index, "_embed", lambda texts: np.asarray([[1.0, 0.0]]))
    monkeypatch.setattr(settings, "allow_degraded_retrieval", True)
    index._client = None
    index._fallback_docs = {
        "tenant-a": [("tenant-a-preview", np.asarray([1.0, 0.0]))],
        "tenant-b": [("tenant-b-preview", np.asarray([0.0, 1.0]))],
    }
    results, degraded = index.search("tenant-a", "hello", limit=1)
    assert degraded is True
    assert results == ["tenant-a-preview"]


def test_semantic_index_upsert_uses_preview(monkeypatch):
    index = SemanticContextIndex()
    monkeypatch.setattr(index, "_embed", lambda texts: np.asarray([[1.0, 0.0]]))
    monkeypatch.setattr(index, "_ensure_collection", lambda: False)
    degraded = index.upsert_messages("tenant-a", [{"role": "user", "content": "very secret raw content"}])
    assert degraded is True
    assert index._fallback_docs["tenant-a"][0][0] == "very secret raw content"[:160]


def test_semantic_index_probe_degrades_when_embedder_fails(monkeypatch):
    index = SemanticContextIndex()
    monkeypatch.setattr("src.context.semantic_index.SentenceTransformer", object())
    monkeypatch.setattr(settings, "allow_degraded_retrieval", True)
    monkeypatch.setattr(index, "_get_embedder", lambda: None)
    index._embedder_error = "boom"
    ok, detail, degraded_ready = index.probe_embedder()
    assert ok is False
    assert degraded_ready is True
    assert "boom" in detail


def test_semantic_index_clear_tenant_does_not_require_embedder(monkeypatch):
    index = SemanticContextIndex()
    called = {"delete": False}

    class Client:
        def delete(self, **kwargs):
            called["delete"] = True

    monkeypatch.setattr("src.context.semantic_index.qdrant_models", type("QdrantModels", (), {"FilterSelector": lambda **kwargs: kwargs, "Filter": lambda **kwargs: kwargs, "FieldCondition": lambda **kwargs: kwargs, "MatchValue": lambda **kwargs: kwargs}))
    index._client = Client()
    index.clear_tenant("tenant-a")
    assert called["delete"] is True
