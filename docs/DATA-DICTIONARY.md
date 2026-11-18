# 数据字典

| 字段 | 类型 | 可空 | 定义 |
|---|---|---:|---|
| `run_id` | string | 否 | 输入摘要派生的稳定运行编号 |
| `source_line` | integer | 否 | 原文件物理行号 |
| `reason_code` | string | 是 | 隔离或冲突的稳定原因码 |
| `raw_value` | string | 是 | 未归一的原始证据 |
| `normalized_value` | string | 是 | 按项目规则得到的值 |
| `rule_version` | string | 否 | 计算规则版本 |
| `batch_id` | string | 否 | M7 交账批次稳定编号，日志与回执靠它配对，重传幂等去重 |
| `point` | string | 否 | M7 采集点标识（对应 `RECONCILE_POINTS` / zones.csv 的 service） |
| `hour` | string | 否 | M7 归属 UTC 小时桶键，形如 `2026-11-15T01:00:00Z`，左闭右开 |
| `empty` | boolean | 是 | M7 回执为空批标记；`true` 时无需日志，该点该小时单独算交齐 |

字符串编号逐字保留。金额与计量值用 `Decimal`。时间值带偏移并以 UTC 参与比较。区间统一采用左闭右开。
