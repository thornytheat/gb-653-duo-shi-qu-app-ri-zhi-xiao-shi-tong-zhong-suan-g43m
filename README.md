# 多时区应用日志小时桶重算

        面向一线复核人员的单服务数据工作台。样例数据随仓库提供，结论保留行号、原因码和原值。

        ## 业务模块

        - M1 日志采信：`/api/logs/import`
- M2 时间解析：`/api/time/normalize`
- M3 事件去重：`/api/events/dedupe`
- M4 小时分桶：`/api/buckets/rebuild`
- M5 迟到修订：`/api/watermark/advance`
- M6 批次对账：`/api/export/buckets.csv`
- M7 对账结清：`/api/reconcile/logs`、`/api/reconcile/receipts`、`/api/reconcile/state`（页面 `/reconcile`）

        ## 核心规则

        事件先归一到 UTC，DST 重叠时保留 fold；小时桶右端开，水位只能前进且迟到事件仍进入修订。

        ## M7 对账结清规则

        - 每个小时按 `RECONCILE_POINTS` 配置的采集点交账，所有应交点交齐才结清。
        - 非空批次必须「日志 + 同 `batch_id` 回执」配对才算交；`empty=true` 的空批回执单独即交齐。
        - 回执与日志可乱序到达：非空回执先到时进入挂起队列，等对应日志补齐再配对。
        - 断流时已收日志的错误数只作暂计错误，未交齐不进入已结错误合计。
        - 水位停在首个未结清小时，不会跳过缺口；缺口补齐后水位连续推进。
        - 小时分桶页（`/buckets`）与对账页（`/reconcile`）都展示每小时「已结清 / 暂计未结」。
        - 日志与回执按 `(kind, batch_id)` 唯一落库，处理失败后重试幂等，错误数不重复增加。

        ## 启动

        ```bash
        docker compose up --build
        ```

        浏览器访问 `http://localhost:18212`。运行测试：

        ```bash
        docker compose exec -T app pytest -q
        ```

        ## 样例流程

        依次运行六个模块；最后在批次页复核输入、有效、隔离与输出合计。同一输入摘要重复执行时复用原 `run_id`。

        ## 已知不覆盖

        不处理加密文件与需要外部密钥的对象；不连接真实生产存储。
