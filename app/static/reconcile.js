// M7 对账结清页面交账交互：提交后展示是否幂等去重，并刷新提示。
document.querySelectorAll("[data-reconcile]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const kind = btn.dataset.reconcile;
    const payloadText = document.getElementById(`${kind}-payload`).value;
    const out = document.getElementById(`${kind}-result`);
    let payload;
    try {
      payload = JSON.parse(payloadText);
    } catch (e) {
      out.textContent = "JSON 解析失败：" + e.message;
      return;
    }
    out.textContent = "提交中";
    try {
      const res = await fetch(`/api/reconcile/${kind}s`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json();
      if (!res.ok) {
        out.textContent = `[${body.error}] ${body.message}`;
        return;
      }
      const state = body.state;
      out.textContent = JSON.stringify(
        {
          accepted: body.accepted,
          duplicate: body.duplicate,
          batch_id: body.batch_id,
          watermark: state.watermark,
          settled_hours: state.settled_hour_count,
          pending_hours: state.pending_hour_count,
          provisional_errors: state.provisional_error_total,
          settled_errors: state.settled_error_total,
        },
        null,
        2
      );
      // 状态已变化，提示复核人刷新查看新的结清表格。
      out.textContent += "\n\n点击右上角“刷新”查看最新小时结清状态。";
    } catch (e) {
      out.textContent = "请求失败，请重试";
    }
  });
});
