"""M7 批次对账结清 —— 纯函数领域逻辑。

术语
----
- point  采集点（对应 zones.csv 里的 service）。
- hour   归属小时桶，左闭右开 UTC 小时，键形如 ``2026-11-15T01:00:00Z``。
- batch  一个采集点对一个小时的一次交账，由 ``batch_id`` 唯一标识。
- 非空批次：日志批次 + 同号回执配对后才算该点该小时“已交”。
- 空批回执：``empty=true`` 的回执，无需日志，单独即算该点该小时“已交”。

水位规则：从被引用的最早小时起逐小时判断，遇到第一个未结清小时即停止，
水位停在该小时；水位不能越过任何未结清小时。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 演示用样例：两个采集点 pay/search、两个小时。
# 小时 01 两点交齐 -> 结清；小时 02 仅 pay 交账（含 1 条错误），search 断流 -> 暂计未结清。
SAMPLE_POINTS = ["pay", "search"]
SAMPLE_LOGS = [
    {
        "batch_id": "b-pay-01",
        "point": "pay",
        "hour": "2026-11-15T01:00:00Z",
        "events": [
            {"timestamp": "2026-11-15T01:05:00Z", "status": 200},
            {"timestamp": "2026-11-15T01:20:00Z", "status": 500},
        ],
    },
    {
        "batch_id": "b-pay-02",
        "point": "pay",
        "hour": "2026-11-15T02:00:00Z",
        "events": [
            {"timestamp": "2026-11-15T02:10:00Z", "status": 503},
        ],
    },
]
SAMPLE_RECEIPTS = [
    {"batch_id": "b-pay-01", "point": "pay", "hour": "2026-11-15T01:00:00Z", "empty": False},
    {"batch_id": "b-search-01", "point": "search", "hour": "2026-11-15T01:00:00Z", "empty": True},
    {"batch_id": "b-pay-02", "point": "pay", "hour": "2026-11-15T02:00:00Z", "empty": False},
]


def hour_key(timestamp: str) -> str:
    """把任意带偏移的 ISO 时间归一到所属 UTC 小时桶（左闭右开）。"""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:00:00Z")


def next_hour(hour: str) -> str:
    dt = datetime.fromisoformat(hour.replace("Z", "+00:00"))
    return (dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:00:00Z")


def is_error(event: dict) -> bool:
    return int(event.get("status", 0)) >= 500


def batch_errors(batch: dict) -> int:
    return sum(1 for event in batch.get("events", []) if is_error(event))


def _index(logs: list[dict], receipts: list[dict]):
    log_by_id = {b["batch_id"]: b for b in logs}
    receipt_by_id = {r["batch_id"]: r for r in receipts}
    return log_by_id, receipt_by_id


def reconcile(logs: list[dict], receipts: list[dict], points: list[str]) -> dict:
    """由全部已收日志批次与回执计算对账快照（纯函数，无副作用）。"""
    log_by_id, receipt_by_id = _index(logs, receipts)
    expected = list(points)

    # 挂起：非空回执先于（或缺少）对应日志。
    pending_receipts = sorted(
        rid for rid, r in receipt_by_id.items()
        if not r.get("empty") and rid not in log_by_id
    )
    # 已收日志但尚未收到回执的批次。
    pending_logs = sorted(bid for bid in log_by_id if bid not in receipt_by_id)

    # 每个 (hour, point) 的交账状态。
    # delivered：空批回执，或 日志+回执 配对成功。
    delivered: dict[tuple[str, str], dict] = {}
    provisional_errors: dict[str, int] = {}

    for batch in logs:
        hour, point = batch["hour"], batch["point"]
        provisional_errors[hour] = provisional_errors.get(hour, 0) + batch_errors(batch)
        if batch["batch_id"] in receipt_by_id:
            delivered[(hour, point)] = {"via": "LOG_RECEIPT", "batch_id": batch["batch_id"]}

    for receipt in receipts:
        hour, point = receipt["hour"], receipt["point"]
        if receipt.get("empty"):
            # 空批回执：无需日志，单独即交齐。
            delivered.setdefault((hour, point), {"via": "EMPTY_RECEIPT", "batch_id": receipt["batch_id"]})

    referenced = set(provisional_errors) | {r["hour"] for r in receipts}
    hours: list[dict] = []
    settled_hours = 0
    settled_errors = 0

    if referenced:
        cursor = min(referenced)
        last = max(referenced)
        while cursor <= last:
            delivered_points = sorted(p for (h, p) in delivered if h == cursor)
            missing_points = sorted(p for p in expected if p not in delivered_points)
            errors_here = provisional_errors.get(cursor, 0)
            finalized = not missing_points  # 所有应交点交齐才结清
            if finalized:
                settled_hours += 1
                settled_errors += errors_here
            hours.append({
                "hour": cursor,
                "status": "SETTLED" if finalized else "PENDING",
                "delivered_points": delivered_points,
                "missing_points": missing_points,
                "provisional_errors": errors_here,
                "settled_errors": errors_here if finalized else 0,
            })
            cursor = next_hour(cursor)

    # 水位：从最早被引用小时起，连续结清到的最远位置；首个未结清小时即水位，不可跳过。
    watermark = None
    if referenced:
        watermark = min(referenced)
        for item in hours:
            if item["status"] == "SETTLED":
                watermark = next_hour(item["hour"])
            else:
                break

    return {
        "status": "READY",
        "points": expected,
        "watermark": watermark,
        "first_hour": min(referenced) if referenced else None,
        "hours": hours,
        "settled_hour_count": settled_hours,
        "pending_hour_count": len(hours) - settled_hours,
        "provisional_error_total": sum(provisional_errors.values()),
        "settled_error_total": settled_errors,
        "log_batch_count": len(logs),
        "receipt_count": len(receipts),
        "pending_receipts": pending_receipts,
        "pending_logs": pending_logs,
    }
