# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""
遗忘机制 - 基于艾宾浩斯遗忘曲线的记忆衰减与自动清理

核心算法：
  记忆分数 = 0.5 x 近因性 + 0.3 x 频率 + 0.2 x 重要性
  近因性 = exp(-小时数 / 168)        # 7天半衰期
  频率 = log(访问次数 + 1) / 10
  重要性 = min(内容长度 / 500, 1.0)

  如果分数 < 阈值 → 遗忘（清理或降权）
"""
import math, time
from datetime import datetime
from typing import Optional
from loguru import logger


class ForgettingMechanism:
    """自动遗忘机制 - 记忆评分 + 衰减 + 清理"""

    def __init__(self, threshold: float = 0.15, decay_hours: float = 168.0):
        self.threshold = threshold
        self.decay_hours = decay_hours

    def score(
        self,
        content: str,
        timestamp: datetime,
        access_count: int = 0,
        importance: Optional[float] = None,
    ) -> float:
        """计算记忆分数（0~1），越低越应该遗忘"""
        hours_elapsed = (datetime.now() - timestamp).total_seconds() / 3600.0

        # 近因性：越近访问分数越高
        recency = math.exp(-hours_elapsed / self.decay_hours)

        # 频率：访问越多分数越高
        frequency = math.log(access_count + 1) / 10.0

        # 重要性：内容越长或显式指定
        if importance is not None:
            imp = max(0.0, min(1.0, importance))
        else:
            imp = min(len(content) / 500.0, 1.0)

        final = 0.5 * recency + 0.3 * frequency + 0.2 * imp
        return round(max(0.0, min(1.0, final)), 4)

    def should_forget(self, score: float) -> bool:
        """判断是否应该遗忘"""
        return score < self.threshold

    def filter_memories(
        self,
        memories: list[tuple],
        timestamps: list[datetime],
        access_counts: Optional[list[int]] = None,
    ) -> list[tuple]:
        """过滤掉应该被遗忘的记忆，返回 (记忆, 分数) 列表"""
        if access_counts is None:
            access_counts = [0] * len(memories)

        scored = []
        forgotten = 0
        for i, mem in enumerate(memories):
            s = self.score(mem, timestamps[i] if i < len(timestamps) else datetime.now(), access_counts[i] if i < len(access_counts) else 0)
            if not self.should_forget(s):
                scored.append((mem, s))
            else:
                forgotten += 1

        scored.sort(key=lambda x: x[1], reverse=True)
        if forgotten:
            logger.info("Forgetting: {} memories forgotten (threshold={})", forgotten, self.threshold)
        return scored

    def estimate_forgetting_curve(self, hours: list[float]) -> list[float]:
        """艾宾浩斯遗忘曲线：给定小时数，返回保留率"""
        return [round(math.exp(-h / self.decay_hours), 4) for h in hours]


# 集成到 MemorySystem 的辅助函数
def apply_forgetting_to_retrieve(
    retrieve_fn,
    query: str,
    k: int = 3,
    min_score: Optional[float] = None,
    forgetting: Optional[ForgettingMechanism] = None,
):
    """为检索结果应用遗忘机制"""
    if forgetting is None:
        forgetting = ForgettingMechanism()
    results = retrieve_fn(query, k=k * 2)
    # 假设结果有 metadata 中的 timestamp
    now = datetime.now()
    filtered = []
    for doc in results:
        ts_str = doc.metadata.get("timestamp", now.isoformat())
        try:
            ts = datetime.fromisoformat(ts_str)
        except:
            ts = now
        access = doc.metadata.get("access_count", 0)
        s = forgetting.score(doc.page_content, ts, access)
        if not forgetting.should_forget(s):
            doc.metadata["forgetting_score"] = s
            filtered.append(doc)
    filtered.sort(key=lambda d: d.metadata.get("forgetting_score", 0), reverse=True)
    return filtered[:k]