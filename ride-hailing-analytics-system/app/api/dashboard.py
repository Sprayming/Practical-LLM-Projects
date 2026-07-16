from __future__ import annotations
from fastapi import APIRouter
from app.models import DashboardResponse

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/", response_model=DashboardResponse)
async def get_dashboard():
    return DashboardResponse(
        total_coupons=0,
        total_redemptions=0,
        redemption_rate=0.0,
        coupon_performance=[],
        driver_stats={},
    )
