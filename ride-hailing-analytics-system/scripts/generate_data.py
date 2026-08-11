#!/usr/bin/env python3
"""
网约车运营数据模拟生成器

生成真实的网约车运营数据，包括：
- 司机信息（不同等级、城市、活跃度）
- 卡券类型（不同面值、有效期、使用条件）
- 卡券发放记录（不同时间、司机、状态）
- 订单记录（不同金额、时段、区域）
- 核销记录（卡券使用）

使用方式：
    python scripts/generate_data.py --days 30 --drivers 100 --orders 5000
"""

import sqlite3
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
import hashlib

# ==================== 配置 ====================

# 城市配置
CITIES = [
    {"name": "北京", "weight": 25},
    {"name": "上海", "weight": 20},
    {"name": "广州", "weight": 15},
    {"name": "深圳", "weight": 15},
    {"name": "杭州", "weight": 10},
    {"name": "成都", "weight": 8},
    {"name": "武汉", "weight": 7},
]

# 司机等级
DRIVER_LEVELS = [
    {"level": "新手", "weight": 20, "order_multiplier": 0.5},
    {"level": "普通", "weight": 40, "order_multiplier": 1.0},
    {"level": "资深", "weight": 25, "order_multiplier": 1.5},
    {"level": "金牌", "weight": 10, "order_multiplier": 2.0},
    {"level": "钻石", "weight": 5, "order_multiplier": 3.0},
]

# 卡券类型（内部 dict 仍用 value/min_order/validity_days 便于阅读，落库时映射到真实列名）
COUPON_TYPES = [
    {"name": "新人券", "value": 5, "min_order": 10, "validity_days": 7, "weight": 15, "category": "新人"},
    {"name": "满减券", "value": 10, "min_order": 30, "validity_days": 14, "weight": 25, "category": "满减"},
    {"name": "折扣券", "value": 15, "min_order": 50, "validity_days": 7, "weight": 20, "category": "折扣"},
    {"name": "大额券", "value": 20, "min_order": 80, "validity_days": 3, "weight": 15, "category": "满减"},
    {"name": "节日券", "value": 30, "min_order": 100, "validity_days": 1, "weight": 10, "category": "节日"},
    {"name": "会员券", "value": 50, "min_order": 150, "validity_days": 30, "weight": 10, "category": "会员"},
    {"name": "专属券", "value": 100, "min_order": 200, "validity_days": 7, "weight": 5, "category": "专属"},
]

# 时段分布（高峰时段权重更高）
TIME_DISTRIBUTION = {
    "early_morning": {"hours": range(0, 6), "weight": 5},    # 凌晨
    "morning": {"hours": range(6, 9), "weight": 25},         # 早高峰
    "forenoon": {"hours": range(9, 12), "weight": 15},       # 上午
    "noon": {"hours": range(12, 14), "weight": 20},          # 午间
    "afternoon": {"hours": range(14, 17), "weight": 15},     # 下午
    "evening": {"hours": range(17, 20), "weight": 30},       # 晚高峰
    "night": {"hours": range(20, 24), "weight": 10},         # 夜间
}

# 订单金额分布
ORDER_AMOUNT_RANGES = [
    {"min": 8, "max": 20, "weight": 30},     # 短途
    {"min": 20, "max": 50, "weight": 35},    # 中途
    {"min": 50, "max": 100, "weight": 20},   # 长途
    {"min": 100, "max": 200, "weight": 10},  # 跨城
    {"min": 200, "max": 500, "weight": 5},   # 远途
]


# ==================== 工具函数 ====================

def weighted_choice(items, key="weight"):
    """带权重的随机选择"""
    weights = [item[key] for item in items]
    return random.choices(items, weights=weights, k=1)[0]


def generate_phone():
    """生成手机号"""
    prefixes = ["138", "139", "158", "159", "186", "187", "188"]
    return random.choice(prefixes) + "".join([str(random.randint(0, 9)) for _ in range(8)])


def generate_name():
    """生成中文姓名"""
    surnames = ["张", "王", "李", "赵", "刘", "陈", "杨", "黄", "吴", "周"]
    names = ["伟", "强", "磊", "洋", "勇", "军", "杰", "涛", "明", "超",
             "秀英", "敏", "静", "丽", "强", "磊", "洋", "勇", "军", "杰"]
    return random.choice(surnames) + random.choice(names)


def generate_plate():
    """生成车牌号"""
    provinces = ["京", "沪", "粤", "浙", "苏", "川", "鄂"]
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return random.choice(provinces) + random.choice(letters) + "".join(
        [random.choice("0123456789" + letters) for _ in range(5)]
    )


# ==================== 数据生成 ====================

def generate_drivers(conn, count: int):
    """生成司机数据（写入 city / driver_level，供评测集维度下钻使用）"""
    logger.info("生成 {} 条司机数据...", count)
    cursor = conn.cursor()

    drivers = []
    for i in range(1, count + 1):
        city = weighted_choice(CITIES)
        level = weighted_choice(DRIVER_LEVELS)

        # 注册时间（最近90天内）
        days_ago = random.randint(0, 90)
        register_date = datetime.now() - timedelta(days=days_ago)

        # 最后活跃时间
        last_active_days = random.randint(0, min(days_ago, 30))
        last_active = datetime.now() - timedelta(days=last_active_days)

        driver = {
            "id": i,
            "name": generate_name(),
            "phone": generate_phone(),
            "city": city["name"],
            "level": level["level"],
            "register_date": register_date.strftime("%Y-%m-%d"),
        }
        drivers.append(driver)

        cursor.execute("""
            INSERT OR REPLACE INTO drivers (id, name, phone, city, driver_level, register_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (driver["id"], driver["name"], driver["phone"], driver["city"],
              driver["level"], driver["register_date"]))

    conn.commit()
    logger.info("司机数据生成完成")
    return drivers


def generate_coupon_types(conn):
    """生成卡券类型数据（真实列名：face_value / valid_days）"""
    logger.info("生成卡券类型数据...")
    cursor = conn.cursor()

    for i, ct in enumerate(COUPON_TYPES, 1):
        cursor.execute("""
            INSERT OR REPLACE INTO coupon_types (id, name, face_value, min_order_amount, valid_days, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (i, ct["name"], ct["value"], ct["min_order"], ct["validity_days"], ct["category"]))

    conn.commit()
    logger.info("卡券类型数据生成完成")


def generate_coupons(conn, count: int, drivers: list):
    """生成卡券发放记录（真实列名：issued_at / expired_at / driver_id NOT NULL）"""
    logger.info("生成 {} 条卡券发放记录...", count)
    cursor = conn.cursor()

    coupons = []
    for i in range(1, count + 1):
        # 随机选择卡券类型
        ct = weighted_choice(COUPON_TYPES)
        ct_id = COUPON_TYPES.index(ct) + 1

        # 发放时间（最近60天内）
        days_ago = random.randint(0, 60)
        issue_date = datetime.now() - timedelta(days=days_ago)

        # 有效期
        valid_until = issue_date + timedelta(days=ct["validity_days"])

        # 状态：已使用/已过期/未使用
        if valid_until < datetime.now():
            # 已过期的卡券，大部分未使用
            status = random.choices(["unused", "expired"], weights=[20, 80])[0]
        else:
            # 未过期的卡券
            status = random.choices(["unused", "used"], weights=[60, 40])[0]

        # driver_id 必填（schema 为 NOT NULL）；drivers 可为 list（取 id）或 int（司机数量，随机 1..n）
        if isinstance(drivers, int):
            driver_id = random.randint(1, drivers) if drivers > 0 else 1
        else:
            driver_id = random.choice(drivers)["id"] if drivers else 1

        coupon = {
            "id": i,
            "coupon_type_id": ct_id,
            "driver_id": driver_id,
            "issued_at": issue_date.strftime("%Y-%m-%d %H:%M:%S"),
            "expired_at": valid_until.strftime("%Y-%m-%d"),
            "status": status,
        }
        coupons.append(coupon)

        cursor.execute("""
            INSERT OR REPLACE INTO coupons (id, coupon_type_id, driver_id, issued_at, expired_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (coupon["id"], coupon["coupon_type_id"], coupon["driver_id"],
              coupon["issued_at"], coupon["expired_at"], coupon["status"]))

    conn.commit()
    logger.info("卡券发放记录生成完成")
    return coupons


def generate_orders(conn, count: int, drivers: list):
    """生成订单记录（真实列名：order_time / order_amount）"""
    logger.info("生成 {} 条订单记录...", count)
    cursor = conn.cursor()

    orders = []
    for i in range(1, count + 1):
        # 随机选择司机
        driver = random.choice(drivers)

        # 随机选择时段
        time_period = weighted_choice(list(TIME_DISTRIBUTION.values()))
        hour = random.choice(list(time_period["hours"]))

        # 随机选择日期（最近30天）
        days_ago = random.randint(0, 30)
        order_date = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23) - hour)

        # 订单金额
        amount_range = weighted_choice(ORDER_AMOUNT_RANGES)
        amount = round(random.uniform(amount_range["min"], amount_range["max"]), 2)

        # 订单状态
        status = random.choices(
            ["completed", "cancelled", "refunded"],
            weights=[85, 10, 5]
        )[0]

        order = {
            "id": i,
            "driver_id": driver["id"],
            "order_time": order_date.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount,
            "status": status,
            "city": driver["city"],
        }
        orders.append(order)

        cursor.execute("""
            INSERT OR REPLACE INTO orders (id, driver_id, order_amount, order_time, status)
            VALUES (?, ?, ?, ?, ?)
        """, (order["id"], order["driver_id"], order["amount"],
              order["order_time"], order["status"]))

    conn.commit()
    logger.info("订单记录生成完成")
    return orders


def generate_redemptions(conn, coupons: list, orders: list):
    """生成核销记录（真实列名：redeemed_at）"""
    logger.info("生成核销记录...")
    cursor = conn.cursor()

    # 筛选已使用的卡券
    used_coupons = [c for c in coupons if c["status"] == "used"]

    redemptions = []
    for i, coupon in enumerate(used_coupons, 1):
        # 随机选择关联的订单
        order = random.choice(orders) if orders else None

        # 核销时间（在订单时间之后）
        if order:
            order_time = datetime.strptime(order["order_time"], "%Y-%m-%d %H:%M:%S")
            redemption_time = order_time + timedelta(minutes=random.randint(1, 30))
        else:
            redemption_time = datetime.now() - timedelta(days=random.randint(0, 30))

        redemption = {
            "id": i,
            "coupon_id": coupon["id"],
            "order_id": order["id"] if order else None,
            "redeemed_at": redemption_time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        redemptions.append(redemption)

        cursor.execute("""
            INSERT OR REPLACE INTO redemptions (id, coupon_id, order_id, redeemed_at)
            VALUES (?, ?, ?, ?)
        """, (redemption["id"], redemption["coupon_id"], redemption["order_id"],
              redemption["redeemed_at"]))

    conn.commit()
    logger.info("核销记录生成完成，共 {} 条", len(redemptions))
    return redemptions


def generate_business_data(conn, days: int):
    """生成业务统计数据（用于仪表盘，真实列名 face_value）"""
    logger.info("生成业务统计数据...")
    cursor = conn.cursor()

    # 统计各卡券类型的核销率
    cursor.execute("""
        SELECT ct.id, ct.face_value,
               COUNT(DISTINCT c.id) as total_coupons,
               COUNT(DISTINCT r.id) as total_redemptions
        FROM coupon_types ct
        LEFT JOIN coupons c ON c.coupon_type_id = ct.id
        LEFT JOIN redemptions r ON r.coupon_id = c.id
        GROUP BY ct.id, ct.face_value
    """)

    stats = cursor.fetchall()
    logger.info("业务统计完成")
    return stats


# ==================== 主函数 ====================

def main():
    parser = argparse.ArgumentParser(description="网约车运营数据模拟生成器")
    parser.add_argument("--days", type=int, default=30, help="生成天数（默认30天）")
    parser.add_argument("--drivers", type=int, default=100, help="司机数量（默认100）")
    parser.add_argument("--orders", type=int, default=5000, help="订单数量（默认5000）")
    parser.add_argument("--coupons", type=int, default=3000, help="卡券数量（默认3000）")
    parser.add_argument("--db", type=str, default="data/ride_hailing.db", help="数据库路径")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（可复现）")

    args = parser.parse_args()

    # 设置随机种子
    if args.seed is not None:
        random.seed(args.seed)
        logger.info("使用随机种子: {}", args.seed)

    # 创建数据库目录
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 连接数据库
    conn = sqlite3.connect(str(db_path))

    # 创建表（如果不存在）
    schema_path = Path(__file__).resolve().parent.parent / "data" / "schema_sqlite.sql"
    if schema_path.exists():
        schema = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema)

    try:
        # 生成数据
        drivers = generate_drivers(conn, args.drivers)
        generate_coupon_types(conn)
        coupons = generate_coupons(conn, args.coupons, drivers)
        orders = generate_orders(conn, args.orders, drivers)
        redemptions = generate_redemptions(conn, coupons, orders)

        # 生成业务统计
        stats = generate_business_data(conn, args.days)

        # 打印统计信息
        logger.info("=" * 50)
        logger.info("数据生成完成！")
        logger.info("=" * 50)
        logger.info("司机数量: {}", len(drivers))
        logger.info("卡券类型: {} 种", len(COUPON_TYPES))
        logger.info("卡券发放: {} 条", len(coupons))
        logger.info("订单记录: {} 条", len(orders))
        logger.info("核销记录: {} 条", len(redemptions))
        logger.info("=" * 50)

        # 打印卡券核销率
        logger.info("卡券核销率统计:")
        for row in stats:
            ct_id, face_value, total, redeemed = row
            rate = (redeemed / total * 100) if total > 0 else 0
            logger.info("  {}元券: {} / {} ({:.1f}%)", face_value, redeemed, total, rate)

    except Exception as e:
        logger.error("数据生成失败: {}", e)
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info("数据已保存到: {}", db_path)


if __name__ == "__main__":
    main()
