from __future__ import annotations

import hashlib
import os
from pathlib import Path
from threading import Lock
from typing import Iterable

import numpy as np

from ..config import settings

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models
except Exception:  # pragma: no cover - optional dependency safety
    QdrantClient = None
    qdrant_models = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency safety
    SentenceTransformer = None


class SemanticContextIndex:
    def __init__(self) -> None:
        self._embedder = None
        self._embed_lock = Lock()
        self._vector_size = None
        self._embedder_error = ""
        self._runtime_paths = self._prepare_runtime_dirs()
        self._client = self._build_client()
        self._collection_name = "tenant_memory"
        self._fallback_docs: dict[str, list[tuple[str, np.ndarray]]] = {}
        self._degraded = False

    def _prepare_runtime_dirs(self) -> dict[str, Path]:
        base = Path(settings.app_data_dir)
        home_dir = Path(os.getenv("HOME", str(base / "home")))
        hf_home = Path(os.getenv("HF_HOME", str(base / "hf-home")))
        transformers_cache = Path(
            os.getenv("TRANSFORMERS_CACHE", str(base / "transformers-cache"))
        )
        for path in (base, home_dir, hf_home, transformers_cache):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception:
                continue
        os.environ["HOME"] = str(home_dir)
        os.environ["HF_HOME"] = str(hf_home)
        os.environ["TRANSFORMERS_CACHE"] = str(transformers_cache)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub"))
        return {
            "home": home_dir,
            "hf_home": hf_home,
            "transformers_cache": transformers_cache,
        }

    def _build_client(self):
        if QdrantClient is None:
            return None
        try:
            url = settings.qdrant_url
            if url:
                return QdrantClient(url=url, check_compatibility=False)
        except Exception:
            pass
        try:
            path = Path(settings.app_data_dir) / "qdrant-local"
            path.mkdir(parents=True, exist_ok=True)
            self._degraded = True
            return QdrantClient(path=str(path), check_compatibility=False)
        except Exception:
            return None

    @staticmethod
    def _preview(content: str, limit: int = 96) -> str:
        text = " ".join(str(content).split())
        return text[:limit]

    @staticmethod
    def _point_id(tenant_id: str, role: str, content: str) -> str:
        digest = hashlib.sha256(f"{tenant_id}:{role}:{content}".encode("utf-8")).hexdigest()
        return digest

    def _mark_degraded(self, reason: str, disable_client: bool = False) -> None:
        self._degraded = True
        if reason:
            self._embedder_error = reason
        if disable_client:
            self._client = None

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        if SentenceTransformer is None:
            self._mark_degraded("sentence_transformers_unavailable")
            return None
        with self._embed_lock:
            if self._embedder is None:
                try:
                    self._embedder = SentenceTransformer(settings.embedding_model)
                    probe = self._embedder.encode(["probe"], normalize_embeddings=True)
                    self._vector_size = int(probe.shape[1])
                    self._embedder_error = ""
                except Exception as exc:
                    self._embedder = None
                    self._vector_size = None
                    self._mark_degraded(str(exc))
        return self._embedder

    def _embed(self, texts: list[str]) -> np.ndarray | None:
        model = self._get_embedder()
        if model is None:
            return None
        try:
            return np.asarray(model.encode(texts, normalize_embeddings=True))
        except Exception as exc:
            self._embedder = None
            self._vector_size = None
            self._mark_degraded(str(exc))
            return None

    def _ensure_collection(self) -> bool:
        if self._client is None or qdrant_models is None:
            return False
        if self._vector_size is None:
            probe = self._embed(["warmup"])
            if probe is None:
                return False
        try:
            collections = self._client.get_collections().collections
            names = {item.name for item in collections}
            if self._collection_name not in names:
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=int(self._vector_size or 384),
                        distance=qdrant_models.Distance.COSINE,
                    ),
                )
            return True
        except Exception as exc:
            self._mark_degraded(str(exc), disable_client=True)
            return False

    def status(self) -> dict[str, bool]:
        return {
            "qdrant_available": self._client is not None,
            "embedder_available": self._get_embedder() is not None,
            "degraded": self._degraded,
        }

    def probe_embedder(self) -> tuple[bool, str, bool]:
        model = self._get_embedder()
        if model is not None:
            return True, settings.embedding_model, False
        detail = self._embedder_error or "embedder_unavailable"
        if settings.allow_degraded_retrieval:
            return False, f"degraded:{detail}", True
        return False, detail, False

    def upsert_messages(self, tenant_id: str, messages: Iterable[dict]) -> bool:
        payloads = []
        texts = []
        for msg in messages:
            role = str(msg.get("role", "user"))
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            payloads.append(
                {
                    "tenant_id": tenant_id,
                    "role": role,
                    "content_preview": self._preview(content),
                    "classification": "message_preview",
                    "id": self._point_id(tenant_id, role, content),
                }
            )
            texts.append(content)

        if not texts:
            return False

        embeddings = self._embed(texts)
        if embeddings is None:
            return False

        if self._ensure_collection():
            try:
                points = [
                    qdrant_models.PointStruct(
                        id=payload["id"],
                        vector=embeddings[idx].tolist(),
                        payload=payload,
                    )
                    for idx, payload in enumerate(payloads)
                ]
                self._client.upsert(collection_name=self._collection_name, points=points, wait=False)
                return False
            except Exception as exc:
                self._mark_degraded(str(exc), disable_client=True)

        bucket = self._fallback_docs.setdefault(tenant_id, [])
        for idx, payload in enumerate(payloads):
            bucket.append((payload["content_preview"], embeddings[idx]))
        if len(bucket) > 256:
            self._fallback_docs[tenant_id] = bucket[-256:]
        return True

    def search(self, tenant_id: str, query: str, limit: int | None = None) -> tuple[list[str], bool]:
        query = (query or "").strip()
        if not query:
            return [], False
        top_k = limit or settings.semantic_top_k
        query_vec = self._embed([query])
        if query_vec is None:
            return [], True

        if self._ensure_collection():
            try:
                hits = self._client.query_points(
                    collection_name=self._collection_name,
                    query=query_vec[0].tolist(),
                    limit=top_k,
                    query_filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="tenant_id",
                                match=qdrant_models.MatchValue(value=tenant_id),
                            )
                        ]
                    ),
                )
                points = hits.points if hasattr(hits, "points") else hits
                return [
                    str(item.payload.get("content_preview", "")).strip()
                    for item in points
                    if getattr(item, "payload", None) and item.payload.get("content_preview")
                ], False
            except Exception as exc:
                self._mark_degraded(str(exc), disable_client=True)

        if not settings.allow_degraded_retrieval:
            return [], True
        docs = self._fallback_docs.get(tenant_id, [])
        if not docs:
            return [], True
        scores = []
        for content_preview, vector in docs:
            score = float(np.dot(query_vec[0], vector))
            scores.append((score, content_preview))
        scores.sort(key=lambda item: item[0], reverse=True)
        return [content for _, content in scores[:top_k]], True

    def clear_tenant(self, tenant_id: str) -> None:
        self._fallback_docs.pop(tenant_id, None)
        if self._client is not None and qdrant_models is not None:
            try:
                self._client.delete(
                    collection_name=self._collection_name,
                    points_selector=qdrant_models.FilterSelector(
                        filter=qdrant_models.Filter(
                            must=[
                                qdrant_models.FieldCondition(
                                    key="tenant_id",
                                    match=qdrant_models.MatchValue(value=tenant_id),
                                )
                            ]
                        )
                    ),
                )
            except Exception as exc:
                self._mark_degraded(str(exc), disable_client=True)
