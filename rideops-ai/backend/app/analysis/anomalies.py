from typing import List, Dict
from collections import defaultdict
import numpy as np
from app.models import Order


def detect_anomalies(orders: List[Order], threshold: float = 2.0) -> List[Dict]:
    """基于标准差检测每日数据异常"""
    daily = defaultdict(lambda: {"orders": 0, "revenue": 0.0, "cancelled": 0, "ratings": []})

    for o in orders:
        day = o.pickup_time.strftime("%Y-%m-%d")
        daily[day]["orders"] += 1
        if o.status == "completed":
            daily[day]["revenue"] += o.fare
            if o.rating is not None:
                daily[day]["ratings"].append(o.rating)
        elif o.status == "cancelled":
            daily[day]["cancelled"] += 1

    days = sorted(daily.keys())
    if len(days) < 3:
        return []

    # 对订单量做异常检测
    values = [daily[d]["orders"] for d in days]
    mean = np.mean(values)
    std = np.std(values)

    anomalies = []
    for i, day in enumerate(days):
        d = daily[day]
        cancel_rate = round(d["cancelled"] / d["orders"] * 100, 2) if d["orders"] else 0
        for metric_name, actual, expected in [
            ("订单量", d["orders"], mean),
            ("取消率", cancel_rate, 0),
        ]:
            if std == 0:
                continue
            dev = (actual - expected) / std
            if abs(dev) > threshold:
                severity = "high" if abs(dev) > 3 * threshold else "medium"
                anomalies.append({
                    "date": day,
                    "metric": metric_name,
                    "actual_value": round(actual, 2),
                    "expected_value": round(expected, 2),
                    "deviation": round(dev, 2),
                    "severity": severity,
                    "suggestion": f"{metric_name}异常，建议排查原因",
                })

    return anomalies
