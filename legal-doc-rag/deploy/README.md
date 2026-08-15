# 生产部署清单：Nginx + HTTPS + systemd 守护 + 多副本负载

## 本文档解决什么

项目此前已能在本地跑通，但「上线」还差四件事：对外暴露 **HTTPS**、进程崩溃**自动拉起**、并发**水平扩展**、证书**自动续期**。
本文档给出一套可直接落地的裸机部署方案；也兼容沿用已有的 `docker-compose.yml`。

> 配合上一轮「高并发升级」（解阻塞事件循环 + 语义缓存 + 多供应商 fallback）使用，方能真正把延迟降下来。

## 架构

```
                           ┌──────────────┐
   浏览器 / 客户端 ─HTTPS──▶ │    Nginx     │  TLS 终止 + SSE 流式反代 + 负载均衡
                           │   (:443)     │
                           └──────┬───────┘
                                  │ 反向代理 127.0.0.1:8000（或 upstream 多实例）
                                  ▼
                           ┌──────────────┐
                           │  uvicorn     │  app.main:app --workers 4
                           │ (多进程副本)  │  阻塞调用已丢线程池（事件循环解阻塞）
                           └──────┬───────┘
                  ┌──────────────┴───────────────┐
                  ▼                              ▼
           ┌────────────┐               ┌────────────────┐
           │   Redis    │◀─ 语义缓存/记忆/限流计数     │  Chroma 向量库 │
           └────────────┘               └────────────────┘
```

## 前置条件

- 一台 ≥ 4C8G 的 Linux 服务器（**推荐 8G 起**，每个 uvicorn worker 约占 2.4GB 内存加载 BGE-M3 + reranker）。
- 域名已解析到服务器公网 IP，并开放 80/443 入站。
- Redis 与 Chroma 就绪：本仓库 `docker-compose.yml` 已内含 Redis；Chroma 走本地持久化目录。

## 方案 A：裸机 systemd 守护（本文档主线）

```bash
# 1. 拉代码 + 建虚拟环境
git clone <repo> /opt/legal-doc-rag && cd /opt/legal-doc-rag
python3 -m venv .ocr_venv
.ocr_venv/bin/pip install -r requirements-docker.txt

# 2. 配置环境变量（含 LLM_PROVIDER / 各供应商 Key / REDIS_URL 等）
cp .env.example .env && vi .env

# 3. 建专用运行用户并授权
sudo useradd -r -m -s /bin/bash appuser
sudo chown -R appuser:appuser /opt/legal-doc-rag

# 4. 安装 systemd unit 并启动
sudo cp deploy/systemd/legal-doc-rag.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now legal-doc-rag
sudo systemctl status legal-doc-rag   # 确认 active(running)
```

## 方案 B：沿用 docker-compose（更省事）

```bash
cp .env.example .env && vi .env        # 填密钥
docker compose up -d --build            # app 已带 --workers，healthcheck 探 /health
```

随后在宿主机 Nginx 反代 `127.0.0.1:8000` 并套 HTTPS 即可（见下）。

## Nginx + HTTPS（两方案通用）

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 放入站点配置并软链
sudo cp deploy/nginx/legal-doc-rag.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/legal-doc-rag /etc/nginx/sites-enabled/

sudo nginx -t && sudo systemctl reload nginx

# 一键申请 Let's Encrypt 证书（certbot 会自动改写 Nginx 启用 443）
chmod +x deploy/setup-ssl.sh
sudo ./deploy/setup-ssl.sh rag.yourdomain.com you@example.com
```

> Nginx 配置已针对 **SSE 流式** 关闭 `proxy_buffering`、拉长 `proxy_read_timeout`，保证 token 实时推到前端不被缓冲截断。

## 多副本负载（水平扩展）

- **单实例多 worker**（`--workers 4`）已具备并发能力，是首选。
- 要进一步水平扩展，启动多个 uvicorn 实例（端口 8001/8002/8003），在
  `deploy/nginx/legal-doc-rag.conf` 的 `upstream legal_doc_rag` 里追加
  `server 127.0.0.1:8001;` 等行，`nginx -s reload` 即生效（默认轮询负载均衡）。
- 或 docker 多副本：`docker compose up -d --scale app=3`（需改 compose 去掉固定端口映射并加外部 LB）。

## 监控

| 项目 | 方式 |
|------|------|
| 存活 | `GET /health`（Nginx 已暴露 `/health` 免鉴权） |
| 指标 | `GET /metrics`（可接 Prometheus + Grafana） |
| 日志 | `journalctl -u legal-doc-rag -f` |

## 回滚

```bash
cd /opt/legal-doc-rag
git checkout <上一稳定 commit>
sudo systemctl restart legal-doc-rag
```

## 备份

- 数据目录：`chroma_db/`、`memory_db/`、`uploads/`、`tenant_data/` 定期打包。
- Redis：`redis-cli SAVE` 后备份 `dump.rdb`。

## 常见问题

- **502 Bad Gateway**：uvicorn 未起或端口不对 → `systemctl status legal-doc-rag` 看日志。
- **流式问答卡住/不实时**：Nginx 必须 `proxy_buffering off`（本配置已含）。
- **内存爆 / OOM**：降低 `--workers` 数量，或开启 swap。
- **首次启动慢**：BGE-M3 模型首次加载需联网下载（Docker 内 `TRANSFORMERS_OFFLINE=0` 已放开）。
