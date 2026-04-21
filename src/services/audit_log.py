from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from ..config import settings


class AuditLogger:
    def __init__(self) -> None:
        self._lock = Lock()
        self._path = Path(settings.app_data_dir) / "audit" / "events.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _redact_value(value: Any) -> Any:
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                low_key = str(key).lower()
                if "token" in low_key or "api_key" in low_key or "authorization" in low_key:
                    out[key] = "[redacted]"
                elif low_key in {"content", "prompt", "messages", "final_response"}:
                    out[key] = "[redacted]"
                else:
                    out[key] = AuditLogger._redact_value(item)
            return out
        if isinstance(value, list):
            return [AuditLogger._redact_value(item) for item in value]
        return value

    def write(self, event_type: str, payload: dict[str, Any]) -> None:
        body = payload
        if settings.audit_redaction_level == "strict":
            body = self._redact_value(payload)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": body,
        }
        line = json.dumps(record, ensure_ascii=True)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def prune(self) -> None:
        if not self._path.exists():
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days)
        kept: list[str] = []
        with self._lock:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                    ts = datetime.fromisoformat(record["ts"])
                    if ts >= cutoff:
                        kept.append(line)
                except Exception:
                    continue
            self._path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
