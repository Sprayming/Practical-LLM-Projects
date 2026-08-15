# 压测脚本说明（locust）

用 [Locust](https://locust.io/) 模拟多用户登录后连续向 `/api/chat` 提问，量化高并发升级前后的
延迟与吞吐差异。

## 安装

```bash
pip install -r requirements-dev.txt
```

## 准备

1. 确保被测服务已起（本地或服务器，记下地址，如 `http://127.0.0.1:8000`）。
2. 准备一个测试账号（默认 `admin` + 你设置的密码）。

## 运行

```bash
locust -f tests/load/locustfile.py \
    -H http://127.0.0.1:8000 \
    --users 50 --spawn-rate 5 --run-time 5m \
    --username admin --password 'yourpass'
```

- `--users`：并发虚拟用户数
- `--spawn-rate`：每秒拉起多少用户
- `--run-time`：压测时长（也可去掉，在 Web UI `http://localhost:8089` 手动启停）
- `--headless`：无 UI 模式，直接跑完 `--run-time` 退出

## 看指标

Locust Web UI（默认 `http://localhost:8089`）的 Statistics 页：

| 指标名 | 含义 |
|--------|------|
| `chat_stream` | SSE 流式问答的**完整回答延迟**（发请求 → 流结束） |
| `chat_stream_ttfb` | SSE **首 token 延迟**（前端体验最关键） |
| `chat_nonstream` | 非流式问答的**完整回答延迟**（检索+RAG+LLM 全流程） |

重点看 **P95 / P99** 与 **RPS（吞吐）**。

## 升级前后对比方法

1. 在**升级前**版本（`git stash` 或直接 checkout 到升级前 commit）跑一次，记录 P95/P99/RPS。
2. 在**升级后**版本（当前 `main`）跑一次，同样记录。
3. 对比：延迟应明显下降（解阻塞 + 语义缓存命中）、RPS 上升（多 worker + 缓存兜底）。

> 提示：语义缓存命中依赖「近似问题」，压测问题库固定 8 条会很快被缓存命中、拉低延迟——
> 若要测「冷缓存」真实性能，可在每次跑前清空 Redis 的语义缓存键（`legal_doc_rag:semcache:*`）。
