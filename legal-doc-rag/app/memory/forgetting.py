"""
app/memory/forgetting.py —— 基于艾宾浩斯遗忘曲线的记忆评分与淘汰机制

【作用与功能】
实现一套综合评分系统，用于判断哪些长期记忆应被「遗忘」（清理/降权）。评分由三个
维度加权得到：新近度（Recency，时间越近分越高）、频率（Frequency，被访问越多分
越高）、重要性（Importance，内容越长或显式权重越高分越高）。当综合评分低于阈值
时即判定为可遗忘，从而在有限存储下保留高价值记忆。

【主要组成】
- `ForgettingMechanism`：遗忘机制核心类，提供 score / should_forget /
  filter_memories / estimate_forgetting_curve 方法

【适用场景】
- 场景1：在 MemorySystem 检索长期记忆后，用于过滤低价值记忆（反遗忘/清理）
- 场景2：用于离线模拟或可视化不同时间点的记忆保留率（遗忘曲线）

【依赖关系】
- 上游调用方：app.memory.memory_manager（MemorySystem.retrieve_long_term）
- 下游依赖：仅依赖标准库（math / time）与 loguru，无外部服务依赖
"""

# Forgetting mechanism - Ebbinghaus forgetting curve

import math, time
from datetime import datetime
from typing import Optional
from loguru import logger


class ForgettingMechanism:
    """
    基于艾宾浩斯遗忘曲线的记忆管理器。
    
    实现了一个综合评分系统，结合三个维度来评估记忆的重要性：
    1. 新近度（Recency）：距离上次访问的时间
    2. 频率（Frequency）：被访问的次数
    3. 重要性（Importance）：内容本身的权重或长度
    
    当综合评分低于阈值时，认为该记忆可以被遗忘。
    
    参数说明：
    - threshold: 遗忘阈值（0-1之间），低于此值的记忆将被遗忘
    - decay_hours: 记忆衰减常数（小时），影响新近度计算的衰减速度
    """
    
    def __init__(self, threshold: float = 0.15, decay_hours: float = 168.0):
        """
        初始化遗忘机制参数。
        
        Args:
            threshold (float): 遗忘阈值，默认为 0.15。低于此值的记忆将被遗忘。
            decay_hours (float): 记忆衰减时间常数（小时），默认为 168 小时（1周）。
                                值越小表示遗忘速度越快。
        """
        self.threshold = threshold
        self.decay_hours = decay_hours

    def score(self, content: str, timestamp: datetime, access_count: int = 0, importance: Optional[float] = None) -> float:
        """
        计算记忆的综合评分。
        
        评分公式：
        final = 0.5 * recency + 0.3 * frequency + 0.2 * importance
        
        Args:
            content (str): 记忆内容文本。
            timestamp (datetime): 记忆的创建或最后访问时间。
            access_count (int): 记忆被访问的次数，默认为 0。
            importance (Optional[float]): 记忆的重要性权重（0-1之间），
                                        如果未提供则根据内容长度自动计算。
                                        
        Returns:
            float: 记忆的综合评分（0-1之间的浮点数），保留 4 位小数。
        """
        # 1. 计算新近度得分（基于时间衰减）
        hours_elapsed = (datetime.now() - timestamp).total_seconds() / 3600.0
        recency = math.exp(-hours_elapsed / self.decay_hours)  # 指数衰减函数
        
        # 2. 计算频率得分（对数函数，避免过度放大高频访问）
        frequency = math.log(access_count + 1) / 10.0  # +1 避免 log(0)
        
        # 3. 计算重要性得分
        if importance is not None:
            # 确保重要性在 0-1 范围内
            imp = max(0.0, min(1.0, importance))
        else:
            # 如果未提供重要性，则根据内容长度估算（最长 500 字为满分）
            imp = min(len(content) / 500.0, 1.0)
        
        # 4. 计算综合评分
        final = 0.5 * recency + 0.3 * frequency + 0.2 * imp
        return round(max(0.0, min(1.0, final)), 4)  # 确保评分在 0-1 范围内

    def should_forget(self, score: float) -> bool:
        """
        判断记忆是否应该被遗忘。
        
        Args:
            score (float): 记忆的综合评分。
            
        Returns:
            bool: 如果评分低于阈值则返回 True（应该遗忘），否则返回 False。
        """
        return score < self.threshold

    def filter_memories(self, memories, timestamps, access_counts=None):
        """
        过滤记忆列表，保留重要记忆并移除被遗忘的记忆。
        
        Args:
            memories (list): 记忆内容列表。
            timestamps (list): 每个记忆对应的时间戳列表。
            access_counts (list, optional): 每个记忆的访问次数列表，默认为全 0。
            
        Returns:
            list: 保留的记忆列表，每个元素是 (记忆内容, 评分) 的元组，按评分降序排列。
        """
        # 如果未提供访问次数列表，初始化为全 0
        if access_counts is None:
            access_counts = [0] * len(memories)
            
        scored = []
        forgotten = 0
        
        # 遍历所有记忆，计算评分并过滤
        for i, mem in enumerate(memories):
            # 获取当前记忆的时间戳和访问次数
            ts = timestamps[i] if i < len(timestamps) else datetime.now()
            ac = access_counts[i] if i < len(access_counts) else 0
            
            # 计算评分
            s = self.score(mem, ts, ac)
            
            # 判断是否应该遗忘
            if not self.should_forget(s):
                scored.append((mem, s))
            else:
                forgotten += 1
                
        # 按评分降序排序
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # 如果有被遗忘的记忆，记录日志
        if forgotten:
            logger.info("Forgot {} memories (threshold={})", forgotten, self.threshold)
            
        return scored

    def estimate_forgetting_curve(self, hours):
        """
        估计遗忘曲线在不同时间点的保留率。
        
        Args:
            hours (list): 时间点列表（单位：小时）。
            
        Returns:
            list: 每个时间点的记忆保留率（0-1 之间的浮点数），保留 4 位小数。
        """
        return [round(math.exp(-h / self.decay_hours), 4) for h in hours]
