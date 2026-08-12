"""
app/observability/structured_logger.py —— JSON 结构化日志封装

【作用与功能】
提供轻量的结构化日志能力:把每条日志统一封装为 JSON 对象(含 timestamp、level、
message 及任意附加字段)，写入按大小滚动的日志文件，便于后续被 ELK / Loki 等日志
系统采集与检索。相比纯文本日志，结构化字段更利于机器解析与按需过滤。

【主要组成】
- `StructuredLogger`:结构化日志封装类，提供 info / warn / error / query 等方法

【适用场景】
- 场景1:在查询路径中调用 query 记录问题、回答长度、Token、延迟与缓存命中
- 场景2:业务代码调用 info/warn/error 输出带自定义字段的结构化日志

【依赖关系】
- 上游调用方:app 主流程、查询管线
- 下游依赖:仅依赖标准库(json / os / logging / pathlib)
"""

import json, os, logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

class StructuredLogger:
    """JSON 结构化日志封装。

    每条日志被序列化为单行 JSON 写入滚动文件(单文件上限 10MB，保留 5 个备份)。
    通过 _log 统一拼装记录体，对外暴露 info/warn/error 通用级别与 query 专用方法。
    """

    def __init__(self, name, log_dir="logs", level="INFO"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        handler = RotatingFileHandler(
            self.log_dir / f"{name}.log",
            maxBytes=10485760,
            backupCount=5
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.handlers.clear()
        self.logger.addHandler(handler)
        self._log("info", "Logger initialized", module=name)

    def _log(self, level, message, **kwargs):
        record = {"timestamp": datetime.now().isoformat(), "level": level.upper(), "message": message, **kwargs}
        self.logger.log(getattr(logging, level.upper()), json.dumps(record, ensure_ascii=False))

    def info(self, msg, **kw): self._log("info", msg, **kw)
    def warn(self, msg, **kw): self._log("warning", msg, **kw)
    def error(self, msg, **kw): self._log("error", msg, **kw)
    def query(self, question, answer_len, tokens, latency_ms, cache_hit=False):
        self._log("info", "query", question=question[:100], answer_len=answer_len, tokens=tokens, latency_ms=latency_ms, cache_hit=cache_hit)
