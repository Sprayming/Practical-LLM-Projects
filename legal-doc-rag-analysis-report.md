# Legal-DOC-RAG 项目评估报告（P0/P1/P2 完成后）

**评估日期：** 2026年8月5日
**项目路径：** `D:\git\legal-doc-rag`
**评估范围：** 完成 P0（上线必备）+ P1（产品化）+ P2（高级功能）之后的真实状态

---

## 1. 项目规模（当前）

- **文件总数：** 138 个（83 个 `.py`）
- **app 子模块：** `api` / `core` / `evaluation` / `frontend` / `ingestion` / `memory` / `observability` / `processing` / `retrieval` / `security` / `tenant` / `worker` —— 共 14 个
- **测试：** `tests/unit`（4 个）、`tests/integration`（4 个）、`tests/evaluation`（1 个）三层
- **部署：** `Dockerfile` + `docker-compose.yml` + `healthcheck.py` + 多个启动脚本
- **文档：** `README.md` 约 38KB，含架构图、踩坑记录、更新日志

---

## 2. 功能完成度矩阵

| 层级 | 功能 | 状态 | 说明 |
|------|------|------|------|
| 核心 | 混合检索（BM25+Dense+RRF+重排序） | ✅ | 检索主链路完整 |
| 核心 | 多租户隔离 + 角色权限 | ✅ | 独立向量库 + 上传目录 |
| 核心 | 三层记忆系统（短/中/长 + 遗忘曲线） | ✅ | |
| 核心 | 流式输出（SSE） | ✅ | |
| 核心 | 多模态 PDF 解析（PyMuPDF + PaddleOCR） | ✅ | |
| **P0** | 测试套件 | ⚠️ | 框架在，但**未全绿**（见第 4 节） |
| **P0** | 安全加固 | ✅ | 路径穿越修复、安全头、CORS 收紧、上传校验 |
| **P0** | 数据备份/恢复 | ✅ | `scripts/backup.py` 完整 CLI |
| **P0** | 监控告警 | ✅ | `/metrics` `/health` `/stats` |
| **P1** | 管理后台 Web | ✅ | 用户/文档/系统统计 |
| **P1** | 文档预览 | ✅ | PDF.js 在线预览 |
| **P1** | 使用统计 | ✅ | 接入指标记录 |
| **P1** | 错误处理 | ✅ | 统一错误码 + 中文提示 |
| **P1** | 性能优化 | ✅ | LRU 缓存 + 分词优化 |
| **P2** | 知识库分组 | ✅ | 文档分类 + 按类检索 |
| **P2** | 多轮对话管理 | ✅ | 对话历史持久化 |
| **P2** | Elasticsearch 全文检索 | ✅ | 可选兜底检索 |
| **P2** | A/B 测试框架 | ✅ | 实验/变体/流量分配 |
| **P2** | Webhook 通知 | ✅ | 8 种事件 + 重试 |

**结论：** 功能广度覆盖非常完整，从核心 RAG 到产品化到工程化，是能体现全栈工程能力的项目。

---

## 3. 工程质量评估

### 优点
- **模块化清晰：** 14 个职责分明的子模块，符合分层架构。
- **文档详尽：** README 含架构图、请求流程、踩坑记录、更新日志（P0/P1/P2 齐全）。
- **部署完备：** Docker 一键起，健康检查、CI 基础检查都有。
- **安全意识：** 修复了路径穿越、收紧了 CORS、加了安全响应头。

### 待改进
- **测试未全绿（最大短板）：** 见第 4 节。
- **代码重复：** `_require_user` 在 `chat.py` / `documents.py` / `feedback.py` 重复定义，应抽成公共依赖。
- **配置硬编码：** 分块大小、RRF 参数等部分仍未外部化。
- **根目录散落临时脚本：** `_fix_login.py`、`_fix_upload.py`、`test_hybrid.py`、`test_retrieval.py` 等应清理或归入 `tests/`。
- **注释遗留：** 早期部分注释为乱码（编码问题），P0 时已修一部分。

---

## 4. 测试真实状态（实测）

运行 `pytest tests/unit/`：

```
18 passed, 14 failed
```

失败 **不是业务逻辑坏**，而是测试的 mock/import 没对准真实代码结构：

| 失败测试 | 根因 |
|---------|------|
| `test_memory_manager_fixed.py`（7 个） | `app.memory` 包未将 `memory_manager` 暴露为属性，测试用 `app.memory.memory_manager` 访问失败 |
| `test_hybrid_retriever_v3.py`（4 个 Reranker） | `Reranker` 类定义在 `hybrid_retriever.py` 内，测试 mock 目标路径不对 |
| `test_api_chat_simple.py`（3 个） | chat 端点测试的 fixture/mock 未对齐 |

**影响：** clone 下来 `pytest` 一片红，会把"我写了测试"的价值抵消掉。这是面试项目当前最该补的一刀——修正 mock 路径即可，**不涉及业务代码改动**。

---

## 5. 面试可用性结论

**能用，而且项目本身的深度足够讲：**
- 混合检索的取舍（为什么 BM25+Dense+RRF）
- 三层记忆 + 遗忘曲线设计
- 多租户隔离方案
- 安全加固的具体漏洞与修复

**上线前最值得做的 3 件事（按性价比排序）：**
1. **修绿测试**（修正 mock 路径，低风险，立即提升"代码可信度"）
2. **清理根目录临时脚本**（移入 tests/ 或删除 `_fix_*.py`）
3. **抽公共 `_require_user` 依赖**（消除重复，体现代码洁癖）

> 注：之前评估说"测试框架就位、19 passed"是乐观估计，实测为 18 passed / 14 failed，特此更正。
