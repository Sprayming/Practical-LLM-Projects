from typing import List, Dict
from collections import Counter
from app.models import Order


def compute_kpi(orders: List[Order]) -> Dict:
    """计算核心 KPI"""
    if not orders:
        return {}

    total = len(orders)
    completed = [o for o in orders if o.status == "completed"]
    cancelled = [o for o in orders if o.status == "cancelled"]

    completed_count = len(completed)
    cancelled_count = len(cancelled)
    total_revenue = sum(o.fare for o in completed)
    total_distance = sum(o.distance_km for o in completed)
    total_duration = sum(o.duration_min for o in completed)
    active_drivers = len(set(o.driver_id for o in orders))
    ratings = [o.rating for o in completed if o.rating is not None]

    # 高峰时段
    hour_counter = Counter(o.pickup_time.hour for o in orders)
    peak_hour = hour_counter.most_common(1)[0][0] if hour_counter else 0

    return {
        "total_orders": total,
        "completed_orders": completed_count,
        "cancelled_orders": cancelled_count,
        "cancelled_rate": round(cancelled_count / total * 100, 2) if total else 0,
        "total_revenue": round(total_revenue, 2),
        "avg_fare": round(total_revenue / completed_count, 2) if completed_count else 0,
        "avg_distance": round(total_distance / completed_count, 2) if completed_count else 0,
        "avg_duration": round(total_duration / completed_count, 1) if completed_count else 0,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
        "active_drivers": active_drivers,
        "peak_hour": f"{peak_hour}:00-{peak_hour+1}:00",
    }


def revenue_analysis(orders: List[Order]) -> Dict:
    """收入分析"""
    completed = [o for o in orders if o.status == "completed"]
    if not completed:
        return {"daily_revenue": {}, "fare_distribution": {}, "revenue_per_km": 0}

    # 每日收入
    daily = {}
    for o in completed:
        day = o.pickup_time.strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + o.fare

    # 客单价分布（频数）
    dist = {"<10": 0, "10-20": 0, "20-50": 0, "50-100": 0, ">100": 0}
    for o in completed:
        if o.fare < 10: dist["<10"] += 1
        elif o.fare < 20: dist["10-20"] += 1
        elif o.fare < 50: dist["20-50"] += 1
        elif o.fare < 100: dist["50-100"] += 1
        else: dist[">100"] += 1

    avg_per_km = sum(o.fare for o in completed) / sum(o.distance_km for o in completed) if completed else 0

    return {
        "daily_revenue": daily,
        "fare_distribution": dist,
        "revenue_per_km": round(avg_per_km, 2),
    }
