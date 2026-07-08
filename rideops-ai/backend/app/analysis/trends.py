from typing import List, Dict
from collections import defaultdict
from app.models import Order


def daily_trends(orders: List[Order]) -> List[Dict]:
    """每日订单量趋势"""
    daily = defaultdict(int)
    for o in orders:
        day = o.pickup_time.strftime("%Y-%m-%d")
        daily[day] += 1

    # 按日期排序
    sorted_days = sorted(daily.items())
    result = []
    prev = None
    for day, count in sorted_days:
        change = round((count - prev) / prev * 100, 2) if prev and prev > 0 else 0
        result.append({"date": day, "value": count, "change_rate": change})
        prev = count
    return result


def weekly_pattern(orders: List[Order]) -> Dict:
    """周度模式（周一到周日）"""
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekly = {i: {"orders": 0, "revenue": 0.0, "count": 0} for i in range(7)}
    for o in [o for o in orders if o.status == "completed"]:
        wd = o.pickup_time.weekday()  # 0=周一
        weekly[wd]["orders"] += 1
        weekly[wd]["revenue"] += o.fare
        weekly[wd]["count"] += 1

    result = {}
    for wd, data in weekly.items():
        result[weekday_names[wd]] = {
            "orders": data["orders"],
            "revenue": round(data["revenue"], 2),
        }
    return result


def hour_heatmap(orders: List[Order]) -> Dict:
    """时段热度分析"""
    weekday_hours = {h: 0 for h in range(24)}
    weekend_hours = {h: 0 for h in range(24)}
    for o in orders:
        h = o.pickup_time.hour
        wd = o.pickup_time.weekday()
        if wd < 5:  # 工作日
            weekday_hours[h] += 1
        else:
            weekend_hours[h] += 1

    return {"weekday": dict(sorted(weekday_hours.items())), "weekend": dict(sorted(weekend_hours.items()))}
