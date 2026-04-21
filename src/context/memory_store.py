from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Deque, List

from ..config import settings


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class TenantMemoryStore:
    def __init__(self, max_turns: int = 200) -> None:
        self.max_turns = max_turns
        self._data: dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=self.max_turns))
        self._summary_cache: dict[str, str] = {}
        self._loaded: set[str] = set()
        self._lock = Lock()
        self._base_dir = Path(settings.app_data_dir) / "tenant-memory"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _preview(content: str, limit: int = 96) -> str:
        text = " ".join(str(content).split())
        return text[:limit]

    @staticmethod
    def _digest(role: str, content: str) -> str:
        return hashlib.sha256(f"{role}:{content}".encode("utf-8")).hexdigest()

    def _tenant_file(self, tenant_id: str) -> Path:
        return self._base_dir / f"{tenant_id}.json"

    def _persistable(self, message: dict) -> dict:
        content = str(message.get("content", ""))
        role = str(message.get("role", "user"))
        return {
            "role": role,
            "content": self._preview(content),
            "sha256": self._digest(role, content),
            "classification": "message_preview",
        }

    def _ensure_loaded(self, tenant_id: str) -> None:
        if tenant_id in self._loaded:
            return
        with self._lock:
            if tenant_id in self._loaded:
                return
            path = self._tenant_file(tenant_id)
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    for msg in payload.get("history", [])[-self.max_turns :]:
                        self._data[tenant_id].append(
                            {
                                "role": str(msg.get("role", "user")),
                                "content": str(msg.get("content", "")),
                            }
                        )
                    self._summary_cache[tenant_id] = str(payload.get("summary", ""))
                except Exception:
                    pass
            self._loaded.add(tenant_id)

    def _persist(self, tenant_id: str) -> None:
        path = self._tenant_file(tenant_id)
        payload = {
            "summary": self._summary_cache.get(tenant_id, ""),
            "history": [self._persistable(item) for item in self._data[tenant_id]],
        }
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def append(self, tenant_id: str, message: ChatMessage) -> None:
        self._ensure_loaded(tenant_id)
        with self._lock:
            self._data[tenant_id].append({"role": message.role, "content": message.content})
            self._persist(tenant_id)

    def get_history(self, tenant_id: str, limit: int = 40) -> List[dict]:
        self._ensure_loaded(tenant_id)
        if limit <= 0:
            return []
        return list(self._data[tenant_id])[-limit:]

    def set_summary(self, tenant_id: str, summary: str) -> None:
        self._ensure_loaded(tenant_id)
        with self._lock:
            self._summary_cache[tenant_id] = self._preview(summary, limit=240)
            self._persist(tenant_id)

    def get_summary(self, tenant_id: str) -> str:
        self._ensure_loaded(tenant_id)
        return self._summary_cache.get(tenant_id, "")

    def clear(self, tenant_id: str) -> None:
        self._ensure_loaded(tenant_id)
        with self._lock:
            self._data[tenant_id].clear()
            self._summary_cache.pop(tenant_id, None)
            path = self._tenant_file(tenant_id)
            if path.exists():
                path.unlink()
