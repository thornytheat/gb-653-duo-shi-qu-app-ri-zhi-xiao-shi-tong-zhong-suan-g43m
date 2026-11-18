"""M7 对账 HTTP 接口与幂等重试测试。"""
from app.modules.m7_reconcile.store import ReconcileStore
from app.modules.m7_reconcile import service

H1 = "2026-11-15T01:00:00Z"
H2 = "2026-11-15T02:00:00Z"
POINTS = ["pay", "search"]


def log_batch(batch_id, point, hour, statuses):
    return {
        "batch_id": batch_id,
        "point": point,
        "hour": hour,
        "events": [{"timestamp": hour, "status": s} for s in statuses],
    }


def test_retry_same_log_batch_does_not_double_count(tmp_path):
    store = ReconcileStore(str(tmp_path / "r.db"))
    batch = log_batch("b1", "pay", H1, [500, 503])

    first = service.ingest_log(store, batch)
    assert first["accepted"] is True and first["duplicate"] is False

    # 处理失败后重试：同一 batch_id 重传被幂等忽略。
    retry = service.ingest_log(store, batch)
    assert retry["accepted"] is False and retry["duplicate"] is True

    state = service.snapshot(store, POINTS)
    assert state["log_batch_count"] == 1
    # 两条错误只计一次，没有翻倍。
    assert state["provisional_error_total"] == 2


def test_retry_receipt_is_idempotent(tmp_path):
    store = ReconcileStore(str(tmp_path / "r.db"))
    receipt = {"batch_id": "e1", "point": "search", "hour": H1, "empty": True}
    assert service.ingest_receipt(store, receipt)["accepted"] is True
    again = service.ingest_receipt(store, receipt)
    assert again["accepted"] is False and again["duplicate"] is True
    assert service.snapshot(store, POINTS)["receipt_count"] == 1


def test_out_of_order_receipt_then_log_full_flow(client):
    # 1) 非空回执先到：等待日志，H1 不能结清。
    r1 = client.post("/api/reconcile/receipts", json={
        "batch_id": "b1", "point": "pay", "hour": H1, "empty": False})
    assert r1.status_code == 200
    body = r1.json()
    assert body["waiting_log"] is True
    assert "b1" in body["state"]["pending_receipts"]
    assert body["state"]["watermark"] == H1

    # 2) 对应日志后到：配对，但 search 未交，仍暂计。
    r2 = client.post("/api/reconcile/logs", json=log_batch("b1", "pay", H1, [500]))
    state = r2.json()["state"]
    assert state["pending_receipts"] == []
    hour1 = next(h for h in state["hours"] if h["hour"] == H1)
    assert hour1["status"] == "PENDING"
    assert hour1["provisional_errors"] == 1
    assert hour1["missing_points"] == ["search"]

    # 3) search 空批回执交齐 -> 结清，水位推进。
    r3 = client.post("/api/reconcile/receipts", json={
        "batch_id": "e1", "point": "search", "hour": H1, "empty": True})
    state = r3.json()["state"]
    hour1 = next(h for h in state["hours"] if h["hour"] == H1)
    assert hour1["status"] == "SETTLED"
    assert hour1["settled_errors"] == 1
    assert state["watermark"] == H2


def test_empty_receipt_alone_settles_point(client):
    client.post("/api/reconcile/logs", json=log_batch("b1", "pay", H1, [200]))
    client.post("/api/reconcile/receipts", json={
        "batch_id": "b1", "point": "pay", "hour": H1, "empty": False})
    resp = client.post("/api/reconcile/receipts", json={
        "batch_id": "e1", "point": "search", "hour": H1, "empty": True})
    state = resp.json()["state"]
    assert state["settled_hour_count"] == 1
    assert state["watermark"] == H2


def test_watermark_blocked_by_gap_across_api(client):
    # H1 全交、H2 仅 pay、H3 全交：水位必须停在 H2。
    client.post("/api/reconcile/logs", json=log_batch("p1", "pay", H1, [200]))
    client.post("/api/reconcile/receipts", json={"batch_id": "p1", "point": "pay", "hour": H1})
    client.post("/api/reconcile/receipts", json={"batch_id": "e1", "point": "search", "hour": H1, "empty": True})

    client.post("/api/reconcile/logs", json=log_batch("p2", "pay", H2, [500]))
    client.post("/api/reconcile/receipts", json={"batch_id": "p2", "point": "pay", "hour": H2})

    h3 = "2026-11-15T03:00:00Z"
    client.post("/api/reconcile/logs", json=log_batch("p3", "pay", h3, [200]))
    client.post("/api/reconcile/receipts", json={"batch_id": "p3", "point": "pay", "hour": h3})
    client.post("/api/reconcile/logs", json=log_batch("s3", "search", h3, [200]))
    client.post("/api/reconcile/receipts", json={"batch_id": "s3", "point": "search", "hour": h3})

    state = client.get("/api/reconcile/state").json()
    assert state["watermark"] == H2
    statuses = {h["hour"]: h["status"] for h in state["hours"]}
    assert statuses[H1] == "SETTLED"
    assert statuses[H2] == "PENDING"
    assert statuses[h3] == "SETTLED"


def test_missing_field_returns_domain_error(client):
    resp = client.post("/api/reconcile/logs", json={"point": "pay", "hour": H1})
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_VALUE"


def test_state_endpoint_and_page_render(client):
    assert client.get("/api/reconcile/state").status_code == 200
    page = client.get("/reconcile")
    assert page.status_code == 200
    assert "panel" in page.text
    assert "小时结清水位" in page.text


def test_buckets_page_shows_settlement_status(client):
    # 交一个完整结清小时后，M4 分桶页应能看出该小时已结清。
    client.post("/api/reconcile/logs", json=log_batch("b1", "pay", H1, [200]))
    client.post("/api/reconcile/receipts", json={"batch_id": "b1", "point": "pay", "hour": H1})
    client.post("/api/reconcile/receipts", json={
        "batch_id": "e1", "point": "search", "hour": H1, "empty": True})
    html = client.get("/buckets").text
    assert "小时结清状态" in html
    assert "已结清" in html


def test_retry_via_api_keeps_error_count_stable(client):
    batch = log_batch("b1", "pay", H1, [500, 500, 200])
    client.post("/api/reconcile/logs", json=batch)
    client.post("/api/reconcile/logs", json=batch)  # 失败重试
    client.post("/api/reconcile/logs", json=batch)  # 再次重试
    state = client.get("/api/reconcile/state").json()
    assert state["log_batch_count"] == 1
    assert state["provisional_error_total"] == 2
