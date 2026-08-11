from __future__ import annotations
from fastapi import APIRouter
from loguru import logger

from app.models import DashboardResponse
from app.db.connection import get_connection

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/", response_model=DashboardResponse)
async def get_dashboard():
    """获取运营仪表盘数据（实时查询数据库）"""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 卡券总数与核销总数
        total_coupons = cursor.execute("SELECT COUNT(*) FROM coupons").fetchone()[0]
        total_redemptions = cursor.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0]
        redemption_rate = (total_redemptions / total_coupons * 100) if total_coupons > 0 else 0.0

        # 各卡券类型核销表现
        rows = cursor.execute("""
            SELECT ct.name, ct.face_value,
                   COUNT(DISTINCT c.id) AS total,
                   COUNT(DISTINCT r.id) AS redeemed
            FROM coupon_types ct
            LEFT JOIN coupons c ON c.coupon_type_id = ct.id
            LEFT JOIN redemptions r ON r.coupon_id = c.id
            GROUP BY ct.id, ct.name, ct.face_value
            ORDER BY ct.id
        """).fetchall()
        coupon_performance = [
            {
                "coupon_type": row["name"],
                "face_value": row["face_value"],
                "total": row["total"],
                "redeemed": row["redeemed"],
                "redemption_rate": (row["redeemed"] / row["total"] * 100) if row["total"] > 0 else 0.0,
            }
            for row in rows
        ]

        # 司机活跃度统计（按订单数排序取前 5）
        driver_rows = cursor.execute("""
            SELECT d.name, d.city, COUNT(o.id) AS order_count,
                   COALESCE(SUM(o.order_amount), 0) AS total_amount
            FROM drivers d
            LEFT JOIN orders o ON o.driver_id = d.id
            GROUP BY d.id, d.name, d.city
            ORDER BY order_count DESC
            LIMIT 5
        """).fetchall()
        driver_stats = {
            row["name"]: {
                "city": row["city"],
                "order_count": row["order_count"],
                "total_amount": round(row["total_amount"], 2),
            }
            for row in driver_rows
        }

        return DashboardResponse(
            total_coupons=total_coupons,
            total_redemptions=total_redemptions,
            redemption_rate=round(redemption_rate, 2),
            coupon_performance=coupon_performance,
            driver_stats=driver_stats,
        )
    except Exception as e:
        logger.error("仪表盘查询失败: {}", e)
        return DashboardResponse(
            total_coupons=0,
            total_redemptions=0,
            redemption_rate=0.0,
            coupon_performance=[],
            driver_stats={},
        )
    finally:
        conn.close()
