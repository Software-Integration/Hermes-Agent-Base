from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from ..config import settings

try:
    import valkey
except Exception:  # pragma: no cover - optional dependency safety
    valkey = None


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_after_seconds: int
    source: str
    degraded: bool


class TenantStateStore:
    def __init__(self) -> None:
        self._client = None
        self._fallback_lock = Lock()
        self._fallback_buckets: dict[str, dict] = defaultdict(
            lambda: {"ts": monotonic(), "count": 0}
        )
        if valkey is not None and settings.valkey_url:
            try:
                self._client = valkey.from_url(settings.valkey_url, decode_responses=True)
            except Exception:
                self._client = None

    def valkey_available(self) -> bool:
        return self._client is not None

    def _fallback_rate_limit(self, tenant_id: str, limit: int, window_seconds: int) -> RateLimitResult:
        with self._fallback_lock:
            bucket = self._fallback_buckets[tenant_id]
            now = monotonic()
            if now - bucket["ts"] >= window_seconds:
                bucket["ts"] = now
                bucket["count"] = 0
            bucket["count"] += 1
            allowed = bucket["count"] <= limit
            remaining = max(0, limit - bucket["count"])
            reset_after = max(0, int(window_seconds - (now - bucket["ts"])))
            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_after_seconds=reset_after,
                source="memory",
                degraded=True,
            )

    def check_rate_limit(self, tenant_id: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
        if self._client is None:
            return self._fallback_rate_limit(tenant_id, limit, window_seconds)

        try:
            key = f"tenant:{tenant_id}:ratelimit:{window_seconds}"
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if int(count) == 1:
                self._client.expire(key, window_seconds)
                ttl = window_seconds
            ttl = window_seconds if ttl is None or int(ttl) < 0 else int(ttl)
            count = int(count)
            return RateLimitResult(
                allowed=count <= limit,
                remaining=max(0, limit - count),
                reset_after_seconds=ttl,
                source="valkey",
                degraded=False,
            )
        except Exception:
            self._client = None
            return self._fallback_rate_limit(tenant_id, limit, window_seconds)

    def clear_tenant_state(self, tenant_id: str) -> None:
        if self._client is not None:
            try:
                keys = list(self._client.scan_iter(match=f"tenant:{tenant_id}:*"))
                if keys:
                    self._client.delete(*keys)
            except Exception:
                self._client = None
        with self._fallback_lock:
            self._fallback_buckets.pop(tenant_id, None)
