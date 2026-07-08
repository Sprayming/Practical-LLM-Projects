from typing import List
from app.models import Order
from app.data import get_orders, set_orders


def clean_orders() -> int:
    """清洗全部订单数据，返回清洗掉的条数"""
    orders = get_orders()
    before = len(orders)

    cleaned = []
    for o in orders:
        # 剔除异常状态
        if o.status not in ("completed", "cancelled"):
            continue
        # 剔除无效距离或金额
        if o.distance_km <= 0 or o.fare <= 0:
            continue
        # 剔除评分越界
        if o.rating is not None and (o.rating < 0 or o.rating > 5):
            o.rating = None
        cleaned.append(o)

    set_orders(cleaned)
    return before - len(cleaned)


def filter_by_date(orders: List[Order], date_start: str, date_end: str) -> List[Order]:
    """按日期范围过滤订单"""
    if not date_start and not date_end:
        return orders

    result = orders
    if date_start:
        start = pd.to_datetime(date_start)
        result = [o for o in result if o.pickup_time >= start]
    if date_end:
        end = pd.to_datetime(date_end)
        result = [o for o in result if o.pickup_time <= end]
    return result


import pandas as pd


def hours_breakdown(orders: List[Order]) -> dict:
    """按小时统计订单分布"""
    hourly = {h: 0 for h in range(24)}
    for o in orders:
        h = o.pickup_time.hour
        hourly[h] = hourly.get(h, 0) + 1
    peak_hour = max(hourly, key=hourly.get)
    return {"hourly": hourly, "peak_hour": peak_hour}
