# Forgetting mechanism - Ebbinghaus forgetting curve

import math, time
from datetime import datetime
from typing import Optional
from loguru import logger


class ForgettingMechanism:
    def __init__(self, threshold: float = 0.15, decay_hours: float = 168.0):
        self.threshold = threshold
        self.decay_hours = decay_hours

    def score(self, content: str, timestamp: datetime, access_count: int = 0, importance: Optional[float] = None) -> float:
        hours_elapsed = (datetime.now() - timestamp).total_seconds() / 3600.0
        recency = math.exp(-hours_elapsed / self.decay_hours)
        frequency = math.log(access_count + 1) / 10.0
        imp = max(0.0, min(1.0, importance)) if importance is not None else min(len(content) / 500.0, 1.0)
        final = 0.5 * recency + 0.3 * frequency + 0.2 * imp
        return round(max(0.0, min(1.0, final)), 4)

    def should_forget(self, score: float) -> bool:
        return score < self.threshold

    def filter_memories(self, memories, timestamps, access_counts=None):
        if access_counts is None:
            access_counts = [0] * len(memories)
        scored, forgotten = [], 0
        for i, mem in enumerate(memories):
            s = self.score(mem, timestamps[i] if i < len(timestamps) else datetime.now(), access_counts[i] if i < len(access_counts) else 0)
            if not self.should_forget(s):
                scored.append((mem, s))
            else:
                forgotten += 1
        scored.sort(key=lambda x: x[1], reverse=True)
        if forgotten:
            logger.info("Forgot {} memories (threshold={})", forgotten, self.threshold)
        return scored

    def estimate_forgetting_curve(self, hours):
        return [round(math.exp(-h / self.decay_hours), 4) for h in hours]
