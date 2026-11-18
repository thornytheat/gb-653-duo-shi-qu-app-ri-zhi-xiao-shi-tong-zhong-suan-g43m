"""M7 对账服务：校验交账输入、驱动幂等存储、重建对账快照。"""
from __future__ import annotations

from app.errors import DomainError
from . import core
from .store import ReconcileStore

REQUIRED_LOG_FIELDS = ("batch_id", "point", "hour")
REQUIRED_RECEIPT_FIELDS = ("batch_id", "point", "hour")


def _require_fields(entity: dict, fields: tuple[str, ...], label: str) -> None:
    missing = [f for f in fields if not str(entity.get(f, "")).strip()]
    if missing:
        raise DomainError(
            "INVALID_VALUE",
            f"{label}缺少必要字段: {', '.join(missing)}",
        )


def snapshot(store: ReconcileStore, points: list[str]) -> dict:
    return core.reconcile(store.logs(), store.receipts(), points)


def ingest_log(store: ReconcileStore, batch: dict) -> dict:
    _require_fields(batch, REQUIRED_LOG_FIELDS, "日志批次")
    accepted = store.add_log(batch)
    return {"accepted": accepted, "duplicate": not accepted, "batch_id": batch["batch_id"]}


def ingest_receipt(store: ReconcileStore, receipt: dict) -> dict:
    _require_fields(receipt, REQUIRED_RECEIPT_FIELDS, "回执")
    accepted = store.add_receipt(receipt)
    return {
        "accepted": accepted,
        "duplicate": not accepted,
        "batch_id": receipt["batch_id"],
        "empty": bool(receipt.get("empty")),
        # 非空回执在对应日志到达前保持挂起。
        "waiting_log": (not receipt.get("empty"))
        and not any(b["batch_id"] == receipt["batch_id"] for b in store.logs()),
    }


def demo_snapshot(points: list[str] | None = None) -> dict:
    """不落库的演示快照，供页面首次渲染。"""
    return core.reconcile(core.SAMPLE_LOGS, core.SAMPLE_RECEIPTS, points or core.SAMPLE_POINTS)
