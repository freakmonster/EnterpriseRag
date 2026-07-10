# Admin API 路由 — 配额管理 + 成本追踪统计
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config.quota_defaults import QUOTA_DEFAULTS
from services.quota import list_role_quotas, update_role_quota, reset_role_quota
from services import stats

router = APIRouter()


class RoleQuotaRequest(BaseModel):
    daily_requests: int = Field(..., ge=1)
    daily_tokens: int = Field(..., ge=1)
    rpm_requests: int = Field(..., ge=1)


# ── 角色配额管理 ──────────────────────────────────────────

@router.get("/quota/roles")
def get_quota_roles():
    return list_role_quotas()


@router.put("/quota/roles/{role}")
def put_role_quota(role: str, req: RoleQuotaRequest):
    if role not in QUOTA_DEFAULTS:
        raise HTTPException(status_code=400, detail=f"无效角色: {role}")
    update_role_quota(role, req.daily_requests, req.daily_tokens, req.rpm_requests)
    return {"status": "ok"}


@router.delete("/quota/roles/{role}")
def delete_role_quota(role: str):
    if role not in QUOTA_DEFAULTS:
        raise HTTPException(status_code=400, detail=f"无效角色: {role}")
    reset_role_quota(role)
    return {"status": "ok"}


# ── 成本追踪统计 ──────────────────────────────────────────

@router.get("/stats/overview")
def get_stats_overview(from_: str | None = Query(None, alias="from"), to: str | None = None):
    return stats.get_overview(from_, to)


@router.get("/stats/trend")
def get_stats_trend(from_: str | None = Query(None, alias="from"), to: str | None = None):
    return stats.get_trend(from_, to)


@router.get("/stats/trend-hourly")
def get_stats_trend_hourly():
    return stats.get_trend_hourly()


@router.get("/stats/aggregation")
def get_stats_aggregation(from_: str | None = Query(None, alias="from"), to: str | None = None):
    return stats.get_aggregation(from_, to)


@router.get("/pricing")
def get_pricing():
    path = Path(__file__).parent.parent / "shared" / "tracking" / "pricing.json"
    return json.loads(path.read_text(encoding="utf-8"))
