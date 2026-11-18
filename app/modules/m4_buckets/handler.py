from fastapi import APIRouter, Body, Request
from .service import execute
from ..m7_reconcile import service as reconcile_service
router = APIRouter(tags=["M4-小时分桶"])

@router.get("/buckets")
def page(request: Request):
    data = execute()
    settlement = reconcile_service.snapshot(
        request.app.state.reconcile_store, request.app.state.settings.points
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "m4_buckets.html",
        {"title": "小时分桶", "data": data, "settlement": settlement},
    )

@router.post("/api/buckets/rebuild")
def api(payload: dict = Body(default={})):
    return execute(payload or None)
