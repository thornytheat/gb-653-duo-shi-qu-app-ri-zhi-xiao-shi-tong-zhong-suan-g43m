"""M7 对账结清领域逻辑测试。

覆盖对账规则：
- 所有应交点交齐才结清，空批回执算交齐；
- 回执/日志乱序，回执先到挂起等日志；
- 断流时只给暂计错误、不结清；
- 水位不能跳过未结清小时；
- 重试去重在存储层测试（见 test_m7_reconcile_api.py）。
"""
from app.modules.m7_reconcile.core import (
    SAMPLE_LOGS,
    SAMPLE_RECEIPTS,
    hour_key,
    next_hour,
    reconcile,
)

POINTS = ["pay", "search"]
H1 = "2026-11-15T01:00:00Z"
H2 = "2026-11-15T02:00:00Z"
H3 = "2026-11-15T03:00:00Z"


def log(batch_id, point, hour, statuses):
    return {
        "batch_id": batch_id,
        "point": point,
        "hour": hour,
        "events": [{"timestamp": hour, "status": s} for s in statuses],
    }


def receipt(batch_id, point, hour, empty=False):
    return {"batch_id": batch_id, "point": point, "hour": hour, "empty": empty}


def by_hour(state, hour):
    return next(row for row in state["hours"] if row["hour"] == hour)


def test_hour_key_buckets_right_end_open():
    # 左闭右开：整点归入新桶，59 分仍属旧桶（与 M4 一致）。
    assert hour_key("2026-11-15T01:59:59Z") == H1
    assert hour_key("2026-11-15T02:00:00Z") == H2
    assert next_hour(H1) == H2


def test_all_points_delivered_settles_and_empty_receipt_counts():
    # pay 走 日志+回执；search 只有空批回执，也算交齐 -> 整小时结清。
    state = reconcile(
        [log("b1", "pay", H1, [200, 500])],
        [receipt("b1", "pay", H1), receipt("e1", "search", H1, empty=True)],
        POINTS,
    )
    row = by_hour(state, H1)
    assert row["status"] == "SETTLED"
    assert row["missing_points"] == []
    assert row["settled_errors"] == 1
    assert state["settled_hour_count"] == 1
    assert state["watermark"] == H2  # 结清后水位推进到下一小时


def test_receipt_first_waits_for_log_then_settles():
    # 乱序：非空回执先到、日志未到 -> 挂起，小时不能结清。
    waiting = reconcile([], [receipt("b1", "pay", H1)], POINTS)
    assert "b1" in waiting["pending_receipts"]
    assert by_hour(waiting, H1)["status"] == "PENDING"
    assert waiting["watermark"] == H1  # 水位停在首个未结清小时

    # 对应日志补齐后配对成功；search 再交空批即整小时结清。
    settled = reconcile(
        [log("b1", "pay", H1, [500])],
        [receipt("b1", "pay", H1), receipt("e1", "search", H1, empty=True)],
        POINTS,
    )
    assert settled["pending_receipts"] == []
    assert by_hour(settled, H1)["status"] == "SETTLED"


def test_log_without_receipt_is_provisional_only():
    # 断流：只有 pay 的日志（含 1 个错误）且回执未到，search 完全未交。
    state = reconcile([log("b1", "pay", H1, [500, 200])], [], POINTS)
    row = by_hour(state, H1)
    assert row["status"] == "PENDING"
    assert row["provisional_errors"] == 1  # 当班可看暂计错误数
    assert row["settled_errors"] == 0      # 未交齐不结清
    # pay 缺回执、search 整体未交，两点都未完成交账。
    assert row["missing_points"] == ["pay", "search"]
    assert state["provisional_error_total"] == 1
    assert state["settled_error_total"] == 0
    assert "b1" in state["pending_logs"]


def test_watermark_never_skips_unsettled_hour():
    # H1 结清，但 H2 因 search 断流未结清；即使 H3 已交齐，水位也不能越过 H2。
    logs = [
        log("p1", "pay", H1, [200]),
        log("p2", "pay", H2, [500]),
        log("p3", "pay", H3, [200]),
        log("s3", "search", H3, [200]),
    ]
    receipts = [
        receipt("p1", "pay", H1),
        receipt("e1", "search", H1, empty=True),
        receipt("p2", "pay", H2),
        receipt("p3", "pay", H3),
        receipt("s3", "search", H3),
    ]
    state = reconcile(logs, receipts, POINTS)
    assert by_hour(state, H1)["status"] == "SETTLED"
    assert by_hour(state, H2)["status"] == "PENDING"
    assert by_hour(state, H3)["status"] == "SETTLED"
    assert state["watermark"] == H2  # 停在缺口小时，未跳到 H3 之后
    assert state["settled_hour_count"] == 2
    assert state["settled_error_total"] == 0  # H2 的错误未结，不计入已结


def test_hour_fills_gap_continuously_advances_watermark():
    # 先让 H1 结清、H2 挂起；补齐 H2 后水位应连续推过 H2。
    logs = [log("p1", "pay", H1, [200]), log("p2", "pay", H2, [200])]
    receipts = [
        receipt("p1", "pay", H1),
        receipt("e1", "search", H1, empty=True),
        receipt("p2", "pay", H2),
    ]
    state = reconcile(logs, receipts, POINTS)
    assert state["watermark"] == H2
    # search 补交 H2（空批），缺口填平。
    receipts.append(receipt("e2", "search", H2, empty=True))
    filled = reconcile(logs, receipts, POINTS)
    assert by_hour(filled, H2)["status"] == "SETTLED"
    assert filled["watermark"] == H3


def test_status_499_is_not_error_500_plus_is():
    state = reconcile(
        [log("b1", "pay", H1, [499, 500, 503])],
        [receipt("b1", "pay", H1), receipt("e1", "search", H1, empty=True)],
        POINTS,
    )
    assert by_hour(state, H1)["provisional_errors"] == 2


def test_sample_scenario_shape():
    state = reconcile(SAMPLE_LOGS, SAMPLE_RECEIPTS, ["pay", "search"])
    assert by_hour(state, H1)["status"] == "SETTLED"
    assert by_hour(state, H2)["status"] == "PENDING"
    assert state["watermark"] == H2
    # pay 在 H2 有一条 503，断流下只能暂计。
    assert by_hour(state, H2)["provisional_errors"] == 1
    assert state["settled_error_total"] == 1  # 仅 H1 那条 500 已结


def test_empty_world():
    state = reconcile([], [], POINTS)
    assert state["hours"] == []
    assert state["watermark"] is None
