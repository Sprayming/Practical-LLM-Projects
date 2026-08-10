import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from loguru import logger
from openai import OpenAI
from app.config import settings


class ReportGenerator:
    """运营报告生成器"""
    
    def __init__(self):
        self.db_path = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_core_metrics(self, days: int = 7) -> Dict:
        """获取核心指标"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            metrics = {}
            
            # 时间范围
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            # 总订单数
            cursor.execute("""
                SELECT COUNT(*) FROM orders 
                WHERE DATE(order_time) BETWEEN ? AND ?
            """, (start_date, end_date))
            metrics["total_orders"] = cursor.fetchone()[0]
            
            # 完成订单数
            cursor.execute("""
                SELECT COUNT(*) FROM orders 
                WHERE status = 'completed' 
                AND DATE(order_time) BETWEEN ? AND ?
            """, (start_date, end_date))
            metrics["completed_orders"] = cursor.fetchone()[0]
            
            # 订单完成率
            metrics["completion_rate"] = (
                metrics["completed_orders"] / metrics["total_orders"] * 100
                if metrics["total_orders"] > 0 else 0
            )
            
            # 总订单金额
            cursor.execute("""
                SELECT SUM(amount) FROM orders 
                WHERE status = 'completed' 
                AND DATE(order_time) BETWEEN ? AND ?
            """, (start_date, end_date))
            result = cursor.fetchone()[0]
            metrics["total_amount"] = result if result else 0
            
            # 平均订单金额
            metrics["avg_order_amount"] = (
                metrics["total_amount"] / metrics["completed_orders"]
                if metrics["completed_orders"] > 0 else 0
            )
            
            # 活跃司机数
            cursor.execute("""
                SELECT COUNT(DISTINCT driver_id) FROM orders 
                WHERE DATE(order_time) BETWEEN ? AND ?
            """, (start_date, end_date))
            metrics["active_drivers"] = cursor.fetchone()[0]
            
            # 总卡券发放数
            cursor.execute("""
                SELECT COUNT(*) FROM coupons 
                WHERE DATE(issued_at) BETWEEN ? AND ?
            """, (start_date, end_date))
            metrics["total_coupons"] = cursor.fetchone()[0]
            
            # 已使用卡券数
            cursor.execute("""
                SELECT COUNT(*) FROM coupons 
                WHERE status = 'used' 
                AND DATE(issued_at) BETWEEN ? AND ?
            """, (start_date, end_date))
            metrics["used_coupons"] = cursor.fetchone()[0]
            
            # 卡券使用率
            metrics["coupon_usage_rate"] = (
                metrics["used_coupons"] / metrics["total_coupons"] * 100
                if metrics["total_coupons"] > 0 else 0
            )
            
            return metrics
        finally:
            conn.close()
    
    def get_trend_data(self, days: int = 7) -> List[Dict]:
        """获取趋势数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            trend = []
            
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                
                # 当日订单数
                cursor.execute("""
                    SELECT COUNT(*) FROM orders 
                    WHERE DATE(order_time) = ? AND status = 'completed'
                """, (date,))
                orders = cursor.fetchone()[0]
                
                # 当日订单金额
                cursor.execute("""
                    SELECT SUM(amount) FROM orders 
                    WHERE DATE(order_time) = ? AND status = 'completed'
                """, (date,))
                amount = cursor.fetchone()[0] or 0
                
                # 当日活跃司机
                cursor.execute("""
                    SELECT COUNT(DISTINCT driver_id) FROM orders 
                    WHERE DATE(order_time) = ?
                """, (date,))
                drivers = cursor.fetchone()[0]
                
                trend.append({
                    "date": date,
                    "orders": orders,
                    "amount": round(amount, 2),
                    "drivers": drivers,
                })
            
            return list(reversed(trend))
        finally:
            conn.close()
    
    def get_coupon_analysis(self) -> List[Dict]:
        """获取卡券分析"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    ct.name as coupon_name,
                    ct.value as coupon_value,
                    COUNT(DISTINCT c.id) as total_issued,
                    COUNT(DISTINCT r.id) as total_redeemed,
                    ROUND(COUNT(DISTINCT r.id) * 100.0 / COUNT(DISTINCT c.id), 2) as redemption_rate
                FROM coupon_types ct
                LEFT JOIN coupons c ON c.coupon_type_id = ct.id
                LEFT JOIN redemptions r ON r.coupon_id = c.id
                GROUP BY ct.id, ct.name, ct.value
                ORDER BY ct.value
            """)
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_top_drivers(self, limit: int = 10) -> List[Dict]:
        """获取TOP司机"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    d.name as driver_name,
                    COUNT(o.id) as order_count,
                    SUM(o.order_amount) as total_amount,
                    AVG(o.order_amount) as avg_amount
                FROM drivers d
                JOIN orders o ON o.driver_id = d.id
                WHERE o.status = 'completed'
                GROUP BY d.id, d.name
                ORDER BY total_amount DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_hourly_distribution(self) -> List[Dict]:
        """获取时段分布"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    CAST(strftime('%H', order_time) AS INTEGER) as hour,
                    COUNT(*) as order_count,
                    SUM(amount) as total_amount
                FROM orders
                WHERE status = 'completed'
                GROUP BY hour
                ORDER BY hour
            """)
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def generate_report(self, period: str = "week") -> str:
        """
        生成运营报告
        
        Args:
            period: 报告周期（week/month）
        
        Returns:
            报告内容（Markdown格式）
        """
        # 确定时间范围
        if period == "week":
            days = 7
            period_name = "周"
        else:
            days = 30
            period_name = "月"
        
        # 获取数据
        metrics = self.get_core_metrics(days)
        trend = self.get_trend_data(days)
        coupon_analysis = self.get_coupon_analysis()
        top_drivers = get_top_drivers(5)
        hourly_dist = get_hourly_distribution()
        
        # 生成报告
        report = self._build_report(
            period_name=period_name,
            metrics=metrics,
            trend=trend,
            coupon_analysis=coupon_analysis,
            top_drivers=top_drivers,
            hourly_dist=hourly_dist
        )
        
        return report
    
    def _build_report(self, period_name: str, metrics: Dict, trend: List[Dict],
                      coupon_analysis: List[Dict], top_drivers: List[Dict],
                      hourly_dist: List[Dict]) -> str:
        """构建报告内容"""
        
        # 计算趋势
        if len(trend) >= 2:
            orders_trend = trend[-1]["orders"] - trend[-2]["orders"]
            amount_trend = trend[-1]["amount"] - trend[-2]["amount"]
        else:
            orders_trend = 0
            amount_trend = 0
        
        report = f"""# 网约车运营{period_name}报

**报告周期**：{(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')} 至 {datetime.now().strftime('%Y-%m-%d')}
**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## 一、核心指标

| 指标 | 数值 | 趋势 |
|------|------|------|
| 总订单数 | {metrics['total_orders']:,} | {'↑' if orders_trend > 0 else '↓'} {abs(orders_trend)} |
| 完成订单数 | {metrics['completed_orders']:,} | - |
| 订单完成率 | {metrics['completion_rate']:.1f}% | - |
| 总订单金额 | ¥{metrics['total_amount']:,.2f} | {'↑' if amount_trend > 0 else '↓'} ¥{abs(amount_trend):,.2f} |
| 平均订单金额 | ¥{metrics['avg_order_amount']:.2f} | - |
| 活跃司机数 | {metrics['active_drivers']:,} | - |
| 卡券发放数 | {metrics['total_coupons']:,} | - |
| 卡券使用率 | {metrics['coupon_usage_rate']:.1f}% | - |

---

## 二、趋势分析

### 近7日订单趋势

| 日期 | 订单数 | 金额 | 活跃司机 |
|------|--------|------|----------|
"""
        
        for day in trend:
            report += f"| {day['date']} | {day['orders']:,} | ¥{day['amount']:,.2f} | {day['drivers']} |\n"
        
        report += """
---

## 三、卡券分析

| 卡券类型 | 面值 | 发放数 | 核销数 | 核销率 |
|----------|------|--------|--------|--------|
"""
        
        for coupon in coupon_analysis:
            report += f"| {coupon['coupon_name']} | ¥{coupon['coupon_value']} | {coupon['total_issued']:,} | {coupon['total_redeemed']:,} | {coupon['redemption_rate']}% |\n"
        
        report += """
---

## 四、TOP司机

| 排名 | 司机 | 订单数 | 总金额 | 平均金额 |
|------|------|--------|--------|----------|
"""
        
        for i, driver in enumerate(top_drivers, 1):
            report += f"| {i} | {driver['driver_name']} | {driver['order_count']:,} | ¥{driver['total_amount']:,.2f} | ¥{driver['avg_amount']:.2f} |\n"
        
        report += """
---

## 五、时段分布

| 时段 | 订单数 | 金额 |
|------|--------|------|
"""
        
        for hour in hourly_dist:
            h = hour['hour']
            if 6 <= h < 9:
                period = "早高峰"
            elif 17 <= h < 20:
                period = "晚高峰"
            elif 12 <= h < 14:
                period = "午间"
            elif 0 <= h < 6:
                period = "凌晨"
            else:
                period = "其他"
            
            report += f"| {h:02d}:00 ({period}) | {hour['order_count']:,} | ¥{hour['total_amount']:,.2f} |\n"
        
        report += f"""
---

## 六、运营建议

基于本{period_name}数据分析，提出以下建议：

1. **卡券策略优化**
   - 核销率较低的卡券类型可考虑调整面值或使用门槛
   - 高峰时段可投放专属优惠券，提升订单量

2. **司机运营**
   - 对TOP司机给予奖励激励，保持活跃度
   - 关注低活跃司机，分析原因并制定唤醒策略

3. **时段运营**
   - 早高峰（6-9点）和晚高峰（17-20点）是订单高峰期
   - 可在低峰时段推出限时优惠，平滑需求

4. **风险提示**
   - 关注订单异常波动，及时排查问题
   - 监控卡券使用情况，防止刷券行为

---

**报告说明**：本报告由系统自动生成，数据来源为网约车数据分析平台。
"""
        
        return report


# 便捷函数
def get_top_drivers(limit: int = 10) -> List[Dict]:
    """获取TOP司机"""
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                d.name as driver_name,
                COUNT(o.id) as order_count,
                SUM(o.order_amount) as total_amount,
                AVG(o.order_amount) as avg_amount
            FROM drivers d
            JOIN orders o ON o.driver_id = d.id
            WHERE o.status = 'completed'
            GROUP BY d.id, d.name
            ORDER BY total_amount DESC
            LIMIT ?
        """, (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_hourly_distribution() -> List[Dict]:
    """获取时段分布"""
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                CAST(strftime('%H', order_time) AS INTEGER) as hour,
                COUNT(*) as order_count,
                SUM(amount) as total_amount
            FROM orders
            WHERE status = 'completed'
            GROUP BY hour
            ORDER BY hour
        """)
        
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# 全局报告生成器实例
report_generator = ReportGenerator()