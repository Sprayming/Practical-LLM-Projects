from __future__ import annotations
from datetime import date, timedelta
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

        # 司机总数
        total_drivers = cursor.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]

        # 订单金额分布（分桶）
        amt = cursor.execute("""
            SELECT
              SUM(CASE WHEN order_amount < 20 THEN 1 ELSE 0 END),
              SUM(CASE WHEN order_amount >= 20 AND order_amount < 50 THEN 1 ELSE 0 END),
              SUM(CASE WHEN order_amount >= 50 AND order_amount < 100 THEN 1 ELSE 0 END),
              SUM(CASE WHEN order_amount >= 100 AND order_amount < 200 THEN 1 ELSE 0 END),
              SUM(CASE WHEN order_amount >= 200 THEN 1 ELSE 0 END)
            FROM orders
        """).fetchone()
        order_amount_distribution = [
            {"label": "0-20", "count": amt[0] or 0},
            {"label": "20-50", "count": amt[1] or 0},
            {"label": "50-100", "count": amt[2] or 0},
            {"label": "100-200", "count": amt[3] or 0},
            {"label": "200+", "count": amt[4] or 0},
        ]

        # 各券种发放量
        cv_rows = cursor.execute("""
            SELECT ct.name, COUNT(c.id) AS cnt
            FROM coupon_types ct
            LEFT JOIN coupons c ON c.coupon_type_id = ct.id
            GROUP BY ct.id, ct.name
            ORDER BY ct.id
        """).fetchall()
        coupon_value_distribution = [{"name": r["name"], "count": r["cnt"]} for r in cv_rows]

        # 核销状态分布（已核销 / 未核销）
        redemption_status = {
            "redeemed": total_redemptions,
            "unredeemed": total_coupons - total_redemptions,
        }

        # 近14天日期基准（补齐缺失日，保证折线连续）
        base_dates = [(date.today() - timedelta(days=i)).strftime("%m-%d") for i in range(13, -1, -1)]

        # 近14天订单趋势
        ot_rows = cursor.execute("""
            SELECT substr(order_time, 1, 10) AS d, COUNT(*) AS c
            FROM orders
            WHERE order_time >= date('now', '-13 days')
            GROUP BY d ORDER BY d
        """).fetchall()
        ot_map = {r["d"][5:]: r["c"] for r in ot_rows}
        order_trend_14d = [{"date": d, "count": ot_map.get(d, 0)} for d in base_dates]

        # 近14天核销趋势
        rt_rows = cursor.execute("""
            SELECT substr(redeemed_at, 1, 10) AS d, COUNT(*) AS c
            FROM redemptions
            WHERE redeemed_at >= date('now', '-13 days')
            GROUP BY d ORDER BY d
        """).fetchall()
        rt_map = {r["d"][5:]: r["c"] for r in rt_rows}
        redemption_trend_14d = [{"date": d, "count": rt_map.get(d, 0)} for d in base_dates]

        # 司机活跃度 Top10（按订单数）
        da_rows = cursor.execute("""
            SELECT d.name, COUNT(o.id) AS order_count, COALESCE(SUM(o.order_amount), 0) AS total_amount
            FROM drivers d
            LEFT JOIN orders o ON o.driver_id = d.id
            GROUP BY d.id, d.name
            ORDER BY order_count DESC
            LIMIT 10
        """).fetchall()
        driver_activity = [
            {"name": r["name"], "order_count": r["order_count"], "total_amount": round(r["total_amount"], 2)}
            for r in da_rows
        ]

        return DashboardResponse(
            total_coupons=total_coupons,
            total_redemptions=total_redemptions,
            redemption_rate=round(redemption_rate, 2),
            coupon_performance=coupon_performance,
            driver_stats=driver_stats,
            total_drivers=total_drivers,
            order_amount_distribution=order_amount_distribution,
            coupon_value_distribution=coupon_value_distribution,
            redemption_status=redemption_status,
            order_trend_14d=order_trend_14d,
            redemption_trend_14d=redemption_trend_14d,
            driver_activity=driver_activity,
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
