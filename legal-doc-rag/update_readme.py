path = "D:/git/legal-doc-rag/README.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 新章节：变更记录与面试角度
changes_section = """
## 变更记录与面试角度

### 1. HybridRetriever (retrieval/hybrid_retriever.py)
改动: BM25 + Dense 双路检索 + RRF 融合 + Cross-Encoder 重排序
原因: 纯稠密对同义词/专有名词召回不够, BM25 做关键词补充; RRF 解决两路分数尺度不一致
面试可能问:
- RRF k 值为什么选 60? 答: k 控制排名敏感度, 60 是论文推荐默认值
- Cross-Encoder vs Bi-Encoder? 答: Bi-Encoder 分别编码(快), Cross-Encoder 拼一起输入(准), 实践中 Bi-Encoder 做召回, Cross-Encoder 做精排

### 2. QueryRewriter (retrieval/query_rewriter.py)
改动: LLM 查询改写, 同义词扩展 + 复合问题分解 + 规则兜底
原因: 用户问得模糊时检索效果差
面试可能问: 改写失败怎么办? 答: LLM 失败时返回原查询, 规则级扩展兜底

### 3. CitationTracker (retrieval/citation.py)
改动: 检索来源追踪 + 自动生成引用列表
原因: 回答需要可追溯, 建立用户信任
面试可能问: 引用怎么实现的? 答: 检索时记录每个 chunk 的源信息, 拼接上下文时附带 [来源: filename] 标记

### 4. MemorySystem + RedisClient (memory/)
改动: 重构三层记忆(短/中/长), 集成 Redis TTL 过期 + 内存回退
原因: 单一存储不够; Redis 快速读写 + 自动过期适合短/中期记忆
面试可能问:
- Redis 不可用时? 答: 自动回退内存存储, 不阻塞对话
- TTL 怎么设? 答: 短期 2h, 中期 24h, 环境变量配置
- 为什么用 Redis? 答: 支持 TTL、List/String 结构适合记忆场景、低延迟

### 5. ForgettingMechanism (memory/forgetting.py)
改动: 艾宾浩斯遗忘曲线记忆衰减 + 自动清理
原因: 记忆无限堆积影响检索质量
面试可能问: 算法公式? 答: 分数=0.5x近因性+0.3x频率+0.2x重要性, 近因性=exp(-小时数/168)

### 6. MultimodalPipeline + OCREngine (processing/)
改动: PyMuPDF 图文提取 + OCR(PaddleOCR/Tesseract) + 合并分块
原因: PDF 含图片和表格, 纯文本提取会丢失信息
面试可能问: PPT/PDF 图怎么处理? 答: 遍历页面提取图片, OCR 识别后缝合进文本 Chunk

### 7. VisionCaptioner (ingestion/vision_caption.py)
改动: Vision LLM 图片标注, 生成 Caption 缝合进 Chunk
原因: 图片无法直接被检索, Caption 实现"搜文字出图"
面试可能问: 延迟怎么处理? 答: 异步调用不阻塞; 失败时回退 OCR 文字

### 8. RAGASEvaluator + RegressionRunner (evaluation/)
改动: RAGAS 三维度(Faithfulness/Relevancy/Recall) + 31 道 Golden Test Set + 回归历史追踪
原因: 量化评估检索和生成质量, 确保优化不退化
面试可能问:
- 三维度怎么算? 答: Faithfulness 拆 claim 判断是否被支持; Relevancy 反向生成问题算相似度; Recall 判断 ground truth 是否出现在检索结果中
- 测试集怎么设计的? 答: 31 道题覆盖 10 类法律场景, 每道含 question/ground_truth/difficulty

### 9. ShadowWorker (worker/shadow_worker.py)
改动: 异步影子 Worker, 优先级队列 + 多线程 + 自动重试
原因: 记忆整理等耗时操作不阻塞主流程
面试可能问: Worker 挂了? 答: 任务标记 failed, 可配置重试; 主进程管理 Worker 自动恢复

### 10. TenantManager (tenant/tenant_manager.py)
改动: 多租户隔离, 独立 namespace + ChromaDB Collection + Redis Key 前缀
原因: 多用户数据需隔离
面试可能问: 怎么隔离? 答: collection_name = tenant:{id}:knowledge, redis_prefix = tenant:{id}:memory

### 11. TraceContext (observability/tracker.py)
改动: 全链路追踪, TraceSpan 记录每阶段耗时/Token/异常
原因: 出问题需要定位环节
面试可能问: 影响性能? 答: 不限, 只是计时计数, 内存保留最近 1000 条

### 12. Docker 容器化 (Dockerfile + docker-compose.yml)
改动: Docker 部署, 编排 app(8501) + redis(6379) 两个服务
原因: 生产环境部署需要容器化, 确保环境一致性
面试可能问:
- 镜像多大? 答: 约 2-3GB, 含 Python 依赖和模型文件
- Redis 挂了? 答: 无法使用记忆功能, 基础检索问答仍可用(回退内存)
"""

# 插入到面试常见问题之前
c = c.replace("## 面试常见问题", changes_section + "\n## 面试常见问题")

# Docker 部署章节
docker_section = """
## Docker 部署

### 文件说明
- Dockerfile: python:3.12-slim, 预装依赖 + 可选预下载嵌入模型
- docker-compose.yml: 编排 app + redis 两个服务
- .dockerignore: 排除缓存、本地数据

### 使用
```bash
cp .env.example .env   # 填入 LLM_API_KEY
docker compose up -d   # 启动
docker compose logs -f # 日志
docker compose down    # 停止
```

### 服务架构
```
浏览器 :8501 → App(Streamlit) → redis://redis:6379
```

### 数据卷
- model_cache: 嵌入模型缓存(避免每次启动下载)
- memory_db: ChromaDB 持久化
- redis_data: Redis AOF 持久化
"""

c += docker_section

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("README.md updated")
print(f"Total: {len(c)} chars")
