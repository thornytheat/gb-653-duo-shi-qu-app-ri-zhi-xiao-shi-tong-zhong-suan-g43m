"""M7 对账存储：仅追加原始交账事件，幂等由唯一约束保证。

同 ``batch_id`` 的日志/回执无论重传多少次只落一行，
因此处理失败后重试不会让错误数重复增加。
"""
from __future__ import annotations

import json
import sqlite3


class ReconcileStore:
    def __init__(self, path: str):
        self.path = path
        with self.connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS reconcile_events (
                       kind TEXT NOT NULL,
                       batch_id TEXT NOT NULL,
                       point TEXT NOT NULL,
                       hour TEXT NOT NULL,
                       payload TEXT NOT NULL,
                       PRIMARY KEY (kind, batch_id)
                   )"""
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def add_log(self, batch: dict) -> bool:
        """插入日志批次；重复 batch_id 被忽略。返回是否为首次接收。"""
        with self.connect() as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO reconcile_events VALUES ('log', ?, ?, ?, ?)",
                (batch["batch_id"], batch["point"], batch["hour"],
                 json.dumps(batch, ensure_ascii=False, sort_keys=True)),
            )
            return cur.rowcount == 1

    def add_receipt(self, receipt: dict) -> bool:
        """插入回执；重复 batch_id 被忽略。返回是否为首次接收。"""
        with self.connect() as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO reconcile_events VALUES ('receipt', ?, ?, ?, ?)",
                (receipt["batch_id"], receipt["point"], receipt["hour"],
                 json.dumps(receipt, ensure_ascii=False, sort_keys=True)),
            )
            return cur.rowcount == 1

    def logs(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM reconcile_events WHERE kind='log' ORDER BY batch_id"
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def receipts(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM reconcile_events WHERE kind='receipt' ORDER BY batch_id"
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]
