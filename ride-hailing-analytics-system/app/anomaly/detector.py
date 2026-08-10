import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from loguru import logger
from enum import Enum


class AnomalyLevel(str, Enum):
    """异常级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    """异常类型"""
    ORDER_DROP = "order_drop"              # 订单量下降
    AMOUNT_DROP = "amount_drop"            # 金额下降
    COUPON_DROP = "coupon_drop"            # 核销率下降
    DRIVER_DROP = "driver_drop"            # 活跃司机下降
    UNUSUAL_SPIKE = "usual_spike"          # 异常激增
    LOW_REDEMPTION = "low_redemption"      # 低核销率
    SUSPICIOUS_PATTERN = "suspicious"      # 可疑模式


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self):
        self.db_path = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
        # 阈值配置
        self.thresholds = {
            "order_drop_percent": 20,       # 订单下降超过20%告警
            "amount_drop_percent": 25,      # 金额下降超过25%告警
            "coupon_drop_percent": 30,      # 核销率下降超过30%告警
            "driver_drop_percent": 15,      # 活跃司机下降超过15%告警
            "spike_percent": 50,            # 异常激增超过50%告警
            "low_redemption_percent": 10,   # 核销率低于10%告警
        }
    
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def detect_all(self) -> List[Dict]:
        """检测所有异常"""
        anomalies = []
        
        # 检测各项指标
        anomalies.extend(self._detect_order_anomaly())
        anomalies.extend(self._detect_amount_anomaly())
        anomalies.extend(self._detect_coupon_anomaly())
        anomalies.extend(self._detect_driver_anomaly())
        anomalies.extend(self._detect_low_redemption())
        
        # 按严重程度排序
        level_order = {AnomalyLevel.CRITICAL: 0, AnomalyLevel.WARNING: 1, AnomalyLevel.INFO: 2}
        anomalies.sort(key=lambda x: level_order.get(x["level"], 3))
        
        logger.info("异常检测完成，发现 {} 个异常", len(anomalies))
        return anomalies
    
    def _detect_order_anomaly(self) -> List[Dict]:
        """检测订单异常"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            anomalies = []
            
            # 获取今日和昨日订单数
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE DATE(order_date) = ? AND status = 'completed'", (today,))
            today_orders = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM orders WHERE DATE(order_date) = ? AND status = 'completed'", (yesterday,))
            yesterday_orders = cursor.fetchone()[0]
            
            if yesterday_orders > 0:
                change_percent = (today_orders - yesterday_orders) / yesterday_orders * 100
                
                # 检测下降
                if change_percent < -self.thresholds["order_drop_percent"]:
                    level = AnomalyLevel.CRITICAL if change_percent < -40 else AnomalyLevel.WARNING
                    anomalies.append({
                        "type": AnomalyType.ORDER_DROP,
                        "level": level,
                        "message": f"订单量异常下降 {abs(change_percent):.1f}%（昨日 {yesterday_orders}，今日 {today_orders}）",
                        "metric": "orders",
                        "today_value": today_orders,
                        "yesterday_value": yesterday_orders,
                        "change_percent": round(change_percent, 1),
                        "detected_at": datetime.now().isoformat(),
                    })
                
                # 检测激增
                elif change_percent > self.thresholds["spike_percent"]:
                    anomalies.append({
                        "type": AnomalyType.UNUSUAL_SPIKE,
                        "level": AnomalyLevel.INFO,
                        "message": f"订单量异常激增 {change_percent:.1f}%（昨日 {yesterday_orders}，今日 {today_orders}）",
                        "metric": "orders",
                        "today_value": today_orders,
                        "yesterday_value": yesterday_orders,
                        "change_percent": round(change_percent, 1),
                        "detected_at": datetime.now().isoformat(),
                    })
            
            return anomalies
        finally:
            conn.close()
    
    def _detect_amount_anomaly(self) -> List[Dict]:
        """检测金额异常"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            anomalies = []
            
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            cursor.execute("SELECT SUM(amount) FROM orders WHERE DATE(order_date) = ? AND status = 'completed'", (today,))
            today_amount = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT SUM(amount) FROM orders WHERE DATE(order_date) = ? AND status = 'completed'", (yesterday,))
            yesterday_amount = cursor.fetchone()[0] or 0
            
            if yesterday_amount > 0:
                change_percent = (today_amount - yesterday_amount) / yesterday_amount * 100
                
                if change_percent < -self.thresholds["amount_drop_percent"]:
                    level = AnomalyLevel.CRITICAL if change_percent < -50 else AnomalyLevel.WARNING
                    anomalies.append({
                        "type": AnomalyType.AMOUNT_DROP,
                        "level": level,
                        "message": f"订单金额异常下降 {abs(change_percent):.1f}%（昨日 ¥{yesterday_amount:,.2f}，今日 ¥{today_amount:,.2f}）",
                        "metric": "amount",
                        "today_value": round(today_amount, 2),
                        "yesterday_value": round(yesterday_amount, 2),
                        "change_percent": round(change_percent, 1),
                        "detected_at": datetime.now().isoformat(),
                    })
            
            return anomalies
        finally:
            conn.close()
    
    def _detect_coupon_anomaly(self) -> List[Dict]:
        """检测卡券异常"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            anomalies = []
            
            # 检测各类卡券的核销率
            cursor.execute("""
                SELECT ct.name, ct.value,
                       COUNT(DISTINCT c.id) as total,
                       COUNT(DISTINCT r.id) as redeemed
                FROM coupon_types ct
                LEFT JOIN coupons c ON c.coupon_type_id = ct.id
                LEFT JOIN redemptions r ON r.coupon_id = c.id
                WHERE c.id IS NOT NULL
                GROUP BY ct.id, ct.name, ct.value
            """)
            
            for row in cursor.fetchall():
                name, value, total, redeemed = row
                if total > 0:
                    redemption_rate = redeemed / total * 100
                    
                    if redemption_rate < self.thresholds["low_redemption_percent"]:
                        anomalies.append({
                            "type": AnomalyType.LOW_REDEMPTION,
                            "level": AnomalyLevel.WARNING,
                            "message": f"{name}（¥{value}）核销率过低：{redemption_rate:.1f}%（{redeemed}/{total}）",
                            "metric": "coupon_redemption",
                            "coupon_name": name,
                            "coupon_value": value,
                            "redemption_rate": round(redemption_rate, 1),
                            "detected_at": datetime.now().isoformat(),
                        })
            
            return anomalies
        finally:
            conn.close()
    
    def _detect_driver_anomaly(self) -> List[Dict]:
        """检测司机异常"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            anomalies = []
            
            today = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            cursor.execute("SELECT COUNT(DISTINCT driver_id) FROM orders WHERE DATE(order_date) = ?", (today,))
            today_drivers = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT driver_id) FROM orders WHERE DATE(order_date) = ?", (yesterday,))
            yesterday_drivers = cursor.fetchone()[0]
            
            if yesterday_drivers > 0:
                change_percent = (today_drivers - yesterday_drivers) / yesterday_drivers * 100
                
                if change_percent < -self.thresholds["driver_drop_percent"]:
                    anomalies.append({
                        "type": AnomalyType.DRIVER_DROP,
                        "level": AnomalyLevel.WARNING,
                        "message": f"活跃司机数异常下降 {abs(change_percent):.1f}%（昨日 {yesterday_drivers}，今日 {today_drivers}）",
                        "metric": "active_drivers",
                        "today_value": today_drivers,
                        "yesterday_value": yesterday_drivers,
                        "change_percent": round(change_percent, 1),
                        "detected_at": datetime.now().isoformat(),
                    })
            
            return anomalies
        finally:
            conn.close()
    
    def _detect_low_redemption(self) -> List[Dict]:
        """检测整体低核销率"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            anomalies = []
            
            # 获取最近7天的核销率
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            
            cursor.execute("""
                SELECT COUNT(*) as total, 
                       SUM(CASE WHEN status = 'used' THEN 1 ELSE 0 END) as used
                FROM coupons
                WHERE DATE(issue_date) >= ?
            """, (week_ago,))
            
            row = cursor.fetchone()
            total = row["total"]
            used = row["used"]
            
            if total > 0:
                usage_rate = used / total * 100
                
                if usage_rate < self.thresholds["low_redemption_percent"]:
                    anomalies.append({
                        "type": AnomalyType.LOW_REDEMPTION,
                        "level": AnomalyLevel.CRITICAL,
                        "message": f"近7天卡券整体使用率过低：{usage_rate:.1f}%（{used}/{total}）",
                        "metric": "overall_coupon_usage",
                        "usage_rate": round(usage_rate, 1),
                        "total_coupons": total,
                        "used_coupons": used,
                        "detected_at": datetime.now().isoformat(),
                    })
            
            return anomalies
        finally:
            conn.close()
    
    def get_anomaly_summary(self) -> Dict:
        """获取异常摘要"""
        anomalies = self.detect_all()
        
        summary = {
            "total": len(anomalies),
            "critical": len([a for a in anomalies if a["level"] == AnomalyLevel.CRITICAL]),
            "warning": len([a for a in anomalies if a["level"] == AnomalyLevel.WARNING]),
            "info": len([a for a in anomalies if a["level"] == AnomalyLevel.INFO]),
            "by_type": {},
            "anomalies": anomalies,
        }
        
        # 按类型统计
        for anomaly in anomalies:
            anomaly_type = anomaly["type"]
            if anomaly_type not in summary["by_type"]:
                summary["by_type"][anomaly_type] = 0
            summary["by_type"][anomaly_type] += 1
        
        return summary


# 全局异常检测器实例
anomaly_detector = AnomalyDetector()