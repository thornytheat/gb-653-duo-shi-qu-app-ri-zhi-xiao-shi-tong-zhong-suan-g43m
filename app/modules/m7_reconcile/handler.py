from fastapi import APIRouter, Body, Request
from . import service

router = APIRouter(tags=["M7-对账结清"])


@router.get("/reconcile")
def page(request: Request):
    data = service.snapshot(
        request.app.state.reconcile_store, request.app.state.settings.points
    )
    # 空库时展示演示数据，让页面首次打开即可看到结清/暂计对比。
    if data["hours"]:
        view = data
    else:
        view = service.demo_snapshot(request.app.state.settings.points)
    return request.app.state.templates.TemplateResponse(
        request, "m7_reconcile.html", {"title": "对账结清", "data": data, "view": view}
    )


@router.get("/api/reconcile/state")
def state(request: Request):
    return service.snapshot(
        request.app.state.reconcile_store, request.app.state.settings.points
    )


@router.post("/api/reconcile/logs")
def receive_logs(request: Request, payload: dict = Body(...)):
    result = service.ingest_log(request.app.state.reconcile_store, payload)
    return {
        **result,
        "state": service.snapshot(
            request.app.state.reconcile_store, request.app.state.settings.points
        ),
    }


@router.post("/api/reconcile/receipts")
def receive_receipts(request: Request, payload: dict = Body(...)):
    result = service.ingest_receipt(request.app.state.reconcile_store, payload)
    return {
        **result,
        "state": service.snapshot(
            request.app.state.reconcile_store, request.app.state.settings.points
        ),
    }
