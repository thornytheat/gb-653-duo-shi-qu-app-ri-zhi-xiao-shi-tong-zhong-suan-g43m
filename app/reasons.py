REASONS = {
    "BAD_COLUMNS": "字段数量不符", "EMPTY_VALUE": "必要值为空",
    "DUPLICATE_CONFLICT": "同一业务键取值冲突", "TRUNCATED": "尾记录不完整",
    "INVALID_VALUE": "值不符合定义", "STALE_VERSION": "提交版本已过期",
    "SETTLED": "小时全部应交点已交齐并结清", "PENDING": "存在未交齐采集点，暂计不结清",
}

def reason(code: str) -> str:
    return REASONS.get(code, "未登记原因")
