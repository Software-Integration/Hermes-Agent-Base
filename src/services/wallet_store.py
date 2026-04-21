from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from ..config import settings


@dataclass(frozen=True)
class WalletBalance:
    tenant_id: str
    balance_cents: int
    currency: str
    transactions: list[dict]


class WalletStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._dir = Path(settings.app_data_dir) / "wallets"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str) -> Path:
        return self._dir / f"{tenant_id}.json"

    def _load(self, tenant_id: str) -> dict:
        path = self._path(tenant_id)
        if not path.exists():
            return {"tenant_id": tenant_id, "balance_cents": 0, "currency": "usd", "transactions": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"tenant_id": tenant_id, "balance_cents": 0, "currency": "usd", "transactions": []}

    def _save(self, tenant_id: str, data: dict) -> None:
        self._path(tenant_id).write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")

    def get_balance(self, tenant_id: str) -> WalletBalance:
        with self._lock:
            data = self._load(tenant_id)
            return self._to_balance(tenant_id, data)

    @staticmethod
    def _to_balance(tenant_id: str, data: dict) -> WalletBalance:
        return WalletBalance(
            tenant_id=tenant_id,
            balance_cents=int(data.get("balance_cents", 0)),
            currency=str(data.get("currency", "usd")),
            transactions=list(data.get("transactions", [])),
        )

    def credit(self, tenant_id: str, amount_cents: int, reference: str, kind: str = "topup") -> WalletBalance:
        with self._lock:
            data = self._load(tenant_id)
            data["balance_cents"] = int(data.get("balance_cents", 0)) + int(amount_cents)
            data.setdefault("transactions", []).append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "kind": kind,
                    "amount_cents": int(amount_cents),
                    "reference": reference,
                }
            )
            self._save(tenant_id, data)
            return self._to_balance(tenant_id, data)

    def debit(self, tenant_id: str, amount_cents: int, reference: str, kind: str = "usage") -> WalletBalance:
        with self._lock:
            data = self._load(tenant_id)
            current = int(data.get("balance_cents", 0))
            if current < int(amount_cents):
                raise ValueError("insufficient_balance")
            data["balance_cents"] = current - int(amount_cents)
            data.setdefault("transactions", []).append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "kind": kind,
                    "amount_cents": -int(amount_cents),
                    "reference": reference,
                }
            )
            self._save(tenant_id, data)
            return self._to_balance(tenant_id, data)
