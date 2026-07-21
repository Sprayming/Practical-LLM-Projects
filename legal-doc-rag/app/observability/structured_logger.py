import json, os, logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

class StructuredLogger:
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
