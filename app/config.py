from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    db_path: str = "./data/loghour.db"
    reconcile_db_path: str = "./data/reconcile.db"
    rule_version: str = "2026.11"
    timezone: str = "Asia/Shanghai"
    # 每个小时必须交账的采集点；全部交齐该小时才允许结清。
    points: tuple[str, ...] = ("pay", "search")

    @classmethod
    def from_env(cls):
        raw_points = os.getenv("RECONCILE_POINTS")
        points = tuple(p.strip() for p in raw_points.split(",")) if raw_points else cls.points
        return cls(
            db_path=os.getenv("DB_PATH", cls.db_path),
            reconcile_db_path=os.getenv("RECONCILE_DB_PATH", cls.reconcile_db_path),
            rule_version=os.getenv("RULE_VERSION", cls.rule_version),
            points=points,
        )
