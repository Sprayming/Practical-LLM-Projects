# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""
可观测性追踪 - 全链路追踪 + 指标采集

记录每次查询的：
  - 各阶段耗时（改写 → 检索 → 生成）
  - Token 消耗
  - 检索结果数量
  - 异常信息
"""
import json, uuid, time, threading
from datetime import datetime
from typing import Optional
from pathlib import Path
from loguru import logger


class TraceSpan:
    """单个操作阶段追踪"""

    def __init__(self, name: str):
        self.name = name
        self.start = time.time()
        self.end: Optional[float] = None
        self.duration_ms: float = 0.0
        self.input: str = ""
        self.output: str = ""
        self.tokens: int = 0
        self.error: Optional[str] = None

    def finish(self):
        self.end = time.time()
        self.duration_ms = round((self.end - self.start) * 1000, 1)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "tokens": self.tokens,
            "error": self.error,
            "input_preview": self.input[:100] if self.input else "",
        }


class TraceContext:
    """单次查询的全链路追踪"""

    def __init__(self):
        self.trace_id = str(uuid.uuid4())[:8]
        self.start_time = datetime.now()
        self.spans: list[TraceSpan] = []
        self._current_span: Optional[TraceSpan] = None

    def begin_span(self, name: str) -> "TraceContext":
        """开始一个新阶段"""
        if self._current_span:
            self._current_span.finish()
        self._current_span = TraceSpan(name)
        self.spans.append(self._current_span)
        return self

    def end_span(self):
        """结束当前阶段"""
        if self._current_span:
            self._current_span.finish()
            self._current_span = None

    def set_input(self, text: str):
        if self._current_span:
            self._current_span.input = text

    def set_output(self, text: str):
        if self._current_span:
            self._current_span.output = text

    def set_tokens(self, count: int):
        if self._current_span:
            self._current_span.tokens = count

    def set_error(self, error: str):
        if self._current_span:
            self._current_span.error = error

    def total_duration_ms(self) -> float:
        return sum(s.duration_ms for s in self.spans)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "start_time": self.start_time.isoformat(),
            "total_duration_ms": self.total_duration_ms(),
            "spans": [s.to_dict() for s in self.spans],
        }

    def print_summary(self):
        """打印追踪摘要"""
        print(f"\n[Tracer {self.trace_id}] 链路追踪")
        for s in self.spans:
            err = f" ❌ {s.error}" if s.error else ""
            tok = f" | {s.tokens} tokens" if s.tokens else ""
            print(f"  ├─ {s.name}: {s.duration_ms}ms{tok}{err}")
        print(f"  └─ 总计: {self.total_duration_ms()}ms")


class TraceStore:
    """追踪存储 - 线程安全地保存所有追踪记录"""

    def __init__(self, max_traces: int = 1000):
        self._traces: list[dict] = []
        self._lock = threading.Lock()
        self._max = max_traces

    def save(self, trace: TraceContext):
        with self._lock:
            self._traces.append(trace.to_dict())
            if len(self._traces) > self._max:
                self._traces = self._traces[-self._max:]

    def get_recent(self, n: int = 10) -> list[dict]:
        with self._lock:
            return self._traces[-n:]

    def export_json(self, path: Optional[str] = None):
        if path is None:
            path = str(Path(__file__).resolve().parent.parent / "traces.json")
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._traces, f, ensure_ascii=False, indent=2)
        logger.info("Traces exported: {} records -> {}", len(self._traces), path)

    def summary(self) -> dict:
        with self._lock:
            if not self._traces:
                return {}
            avg_duration = sum(t["total_duration_ms"] for t in self._traces) / len(self._traces)
            total_tokens = sum(
                s["tokens"] for t in self._traces for s in t["spans"]
            )
            return {
                "total_queries": len(self._traces),
                "avg_duration_ms": round(avg_duration, 1),
                "total_tokens": total_tokens,
            }


# 全局单例
_store: Optional[TraceStore] = None


def get_trace_store() -> TraceStore:
    global _store
    if _store is None:
        _store = TraceStore()
    return _store


def trace_pipeline(query: str, llm_func=None, retriever_func=None, rewriter_func=None) -> dict:
    """带追踪的完整管线执行"""
    ctx = TraceContext()
    store = get_trace_store()

    # 1. 查询改写
    ctx.begin_span("query_rewrite")
    ctx.set_input(query)
    queries = [query]
    if rewriter_func:
        try:
            queries = rewriter_func(query)
            ctx.set_output(str(queries))
        except Exception as e:
            ctx.set_error(str(e))
    ctx.end_span()

    # 2. 检索
    ctx.begin_span("retrieve")
    ctx.set_input(str(queries))
    docs = []
    if retriever_func:
        try:
            for q in queries:
                docs.extend(retriever_func(q))
            ctx.set_output(f"{len(docs)} chunks")
        except Exception as e:
            ctx.set_error(str(e))
    ctx.end_span()

    # 3. 生成
    ctx.begin_span("generate")
    ctx.set_input(query)
    answer = ""
    if llm_func:
        try:
            answer, tokens = llm_func(query, docs)
            ctx.set_output(answer[:200])
            ctx.set_tokens(tokens)
        except Exception as e:
            ctx.set_error(str(e))
    ctx.end_span()

    store.save(ctx)
    ctx.print_summary()
    return {"answer": answer, "trace": ctx.to_dict()}