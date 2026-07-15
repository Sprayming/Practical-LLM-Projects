# ============================================================
# RAG 智能知识检索系统 - 正确的框架总览与文件关系图
# 打开此文件直接阅读
# ============================================================

"""
Part 1: rag-project 架构总览

序列流程：
┌──────────────────────────────────────────────────────────────────────────────┐
│  摄取管线 (Ingestion Pipeline)                                               │
│                                                                              │
│  Upload(PDF/DOCX/TXT/图片)                                                   │
│    ↓                                                                          │
│  api/documents.py [上传接口]                                                   │
│    ↓                                                                          │
│  ingestion/pipeline.py [编排]                                                  │
│    ├── loader.py → 解析文件为纯文本                                            │
│    ├── vision_caption.py → Vision LLM 描述图片                                 │
│    ├── chunker.py → 切分为 Chunk (512/128)                                    │
│    ├── embedder.py → 转向量                                                    │
│    └── vector_store.py → 存入 ChromaDB                                        │
│                                                                              │
│  检索问答管线 (Retrieval Pipeline)                                             │
│                                                                              │
│  User Query                                                                    │
│    ↓                                                                          │
│  api/chat.py [问答接口]                                                        │
│    ├── retriever.py (基础) or hybrid_retriever.py (混合)                       │
│    │    ├── embedder.py → query 转向量                                         │
│    │    ├── vector_store.py → ChromaDB 检索                                    │
│    │    └── hybrid额外: BM25 + RRF + Cross-Encoder                             │
│    ├── citation.py → 追踪引用来源                                               │
│    └── generation/llm.py → 生成回答 (DeepSeek)                                 │
│         └── prompt_templates.py → 提示词模板                                    │
│    ↓                                                                          │
│  Answer + Citations                                                           │
│                                                                              │
│  评估体系 (Evaluation)                                                        │
│  scripts/run_regression.py                                                    │
│    └── evaluation/runner.py                                                   │
│         ├── evaluation/metrics.py (RAGAS)                                     │
│         └── tests/golden_test_set.json (31题)                                 │
└──────────────────────────────────────────────────────────────────────────────┘

Part 2: 文件关系图 (import 链)

┌──────────────────────────────────────────────────────────────────┐
│ main.py                                                          │
│  ├── api/chat.py                                                 │
│  │    ├── models.py                                              │
│  │    ├── generation/llm.py                                      │
│  │    │    ├── config.py                                         │
│  │    │    ├── models.py                                         │
│  │    │    └── prompt_templates.py                               │
│  │    ├── retrieval/retriever.py                                 │
│  │    │    ├── retrieval/embedder.py → config.py                 │
│  │    │    └── retrieval/vector_store.py → config.py + models.py │
│  │    └── retrieval/hybrid_retriever.py                          │
│  │         ├── retrieval/retriever.py + vector_store.py          │
│  │         └── models.py                                         │
│  │                                                               │
│  ├── api/documents.py                                            │
│  │    ├── config.py                                              │
│  │    ├── models.py                                              │
│  │    └── ingestion/pipeline.py                                  │
│  │         ├── ingestion/loader.py                               │
│  │         ├── ingestion/vision_caption.py                       │
│  │         ├── ingestion/chunker.py                              │
│  │         ├── retrieval/embedder.py                             │
│  │         └── retrieval/vector_store.py                         │
│  │                                                               │
│  └── evaluation/ (独立运行)                                        │
│       └── runner.py → metrics.py → RAGAS                         │
│                                                               │
│  独立文件:                                                    │
│  - tests/golden_test_set.json (31题, 被 runner 加载)              │
│  - scripts/run_regression.py (入口, 调用 runner)                   │
└──────────────────────────────────────────────────────────────────┘

Part 3: 模块详解 (11个核心模块)

1. hybrid_retriever.py  ──── 混合检索器 (BM25 + Dense + RRF + Cross-Encoder)
   为什么需要?    纯稠密向量对同义词/专有名词召回不够
   解决了什么?    BM25补充关键词匹配, RRF融合两路结果, Cross-Encoder精排
   如果删掉?     Top-10命中率下降约25%

2. chunker.py  ──── 语义分块器
   为什么需要?    长文档不能直接喂LLM, 需要切成合适大小的块
   解决了什么?    按段落→句子逐级切分, 块间重叠避免切丢上下文
   如果删掉?    LLM上下文窗口塞不下整篇文档

3. retriever.py  ──── 基础检索器
   为什么需要?    将用户问题转为向量, 搜索最相关的文本块
   解决了什么?    语义检索, 不依赖关键词精确匹配
   如果删掉?    整个RAG系统无法工作

4. evaluation/metrics.py  ──── RAGAS评估
   为什么需要?    量化评估检索和生成质量, 避免靠感觉优化
   解决了什么?    Faithfulness/AnswerRelevancy/ContextRecall三维度打分
   如果删掉?    无法衡量优化效果

5. evaluation/runner.py  ──── 回归测试
   为什么需要?    确保每次优化不会让之前的效果倒退
   解决了什么?    31道Golden Test Set自动评估 + 历史对比
   如果删掉?    优化A指标时可能导致B指标退化而不自知

6. ingestion/loader.py  ──── 文档加载器
   为什么需要?    支持多种格式(PDF/DOCX/TXT/图片等)统一解析
   解决了什么?    把非结构化文档转为结构化文本
   如果删掉?    只能处理纯文本

7. ingestion/vision_caption.py  ──── Vision LLM标注
   为什么需要?    图片无法直接被检索, 需要转为文字描述
   解决了什么?    Vision LLM生成图片Caption, 缝合进Chunk实现搜文字出图
   如果删掉?    图片内容无法被检索到

8. generation/prompt_templates.py  ──── 提示词模板
   为什么需要?    控制LLM的行为, 避免幻觉
   解决了什么?    要求只基于资料回答, 标注引用, 无法回答时明确说明
   如果删掉?    LLM自由发挥, Faithfulness大幅下降

9. retrieval/citation.py  ──── 来源标注
   为什么需要?    回答需要可追溯, 建立信任
   解决了什么?    追踪每个chunk的来源, 生成引用列表
   如果删掉?    回答不可验证, 用户不敢采信

10. ingestion/pipeline.py  ──── 摄取管线编排
    为什么需要?    串联 load → chunk → embed → store 全流程
    解决了什么?    一步完成文档入库
    如果删掉?    需要手动调用每个步骤

11. retrieval/embedder.py  ──── 嵌入器
    为什么需要?    将文本转为向量, 用于语义检索
    解决了什么?    基于jieba分词的hash嵌入, 本地运行无需API
    如果删掉?    无法进行语义检索

Part 4: 面试高频问题

Q1: BM25和稠密向量检索有什么区别? 为什么都用?
A: 稠密向量检索把文本转为语义向量, 匹配同义词效果好
   ("解除合同"和"合同终止"语义相近)。BM25是基于词频的稀疏检索,
   精确匹配关键词。两者互补: 稠密抓语义, 稀疏抓精确命中。
   我们用RRF融合两路结果, 再经过Cross-Encoder精排。

Q2: RRF的k值为什么选60?
A: k是RRF公式中的常数: score = sum(1/(k + rank))
   k=60是原始论文推荐的默认值。k越小前几名权重越大,
   k=30适合检索质量已经很高的场景, k=100时排名影响变小。

Q3: Cross-Encoder和Bi-Encoder的区别?
A: Bi-Encoder分别编码query和doc成向量后算相似度, 速度快可预计算。
   Cross-Encoder把query和doc拼一起输入模型直接输出分数, 精度高但慢。
   实践中: Bi-Encoder做第一轮召回(候选100+), Cross-Encoder对Top-30精排。

Q4: 分块大小为什么选512? Overlap为什么选128?
A: 512 token的考虑: 太短(128)语义不完整, 太长(1024+)含多主题检索不准。
   Overlap 128(25%)为防止关键句在切分边界被切断。做了A/B测试,
   对比256/512/1024, 512在ContextRecall上表现最好。

Q5: RAGAS三维度具体怎么算?
A:
   1. Faithfulness: 把回答拆成claim, 逐个判断是否被上下文支持
   2. AnswerRelevancy: 从回答反向生成问题, 看与原始问题的相似度
   3. ContextRecall: 把ground truth拆成claims, 判断是否出现在检索结果中
   评估用DeepSeek作为LLM Judge。

Q6: Faithfulness从0.62提升到0.81做了什么?
A: 三条线并行:
   1. 检索质量(贡献最大): 纯稠密→BM25+Dense双路+RRF+Cross-Encoder
   2. 提示词约束: System Prompt要求只基于资料回答, 标注引用
   3. 上下文质量控制: 加min_score=0.2过滤低质量结果, 调整Chunk参数
   每次改动后跑31道Golden Test Set做回归测试。

Q7: 多模态检索怎么实现的?
A: 1. PyMuPDF提取文档中的图片
   2. Vision LLM(通过API)对图片生成文字描述(Caption)
   3. 把Caption缝合到该页的文本Chunk中
   4. 用户检索时通过Caption匹配到图片
   兜底: 如果Vision API不可用, 用OCR提取图片中的文字

Q8: 项目遇到的最大技术难点?
A: Golden Test Set的设计。不同人写的ground truth标准不一致,
   导致RAGAS评分波动巨大。后来统一模板: 每个问题包含question,
   ground_truth, 来源文档, 难度分类。这样Faithfulness评估才稳定。

Q9: 上线后检索质量下降怎么办?
A: 通过回归测试发现:
   1. 查最近一次回归测试的结果对比
   2. 定位是检索问题还是生成问题
   3. 如果是检索, 检查BM25索引是否需要重建
   4. 如果是生成, 检查API状态和Prompt

Q10: 为什么不用现成的RAG框架?
A: LangChain/LlamaIndex提供基础组件, 我们在三层做了定制:
   1. 检索策略: 自研BM25+Dense双路 + RRF + Cross-Encoder
   2. 评估体系: 基于RAGAS搭建完整评估管线, 31题+回归测试
   3. 多模态: 自研Vision LLM Caption缝合Chunk
   用框架做基础设施, 在上面搭建业务逻辑。

Part 5: 优化路径

Phase 1: Baseline (纯稠密检索)
  → Faithfulness: 0.62 (基线)

Phase 2: 混合检索 (BM25 + Dense + RRF)
  → Faithfulness: 0.62 → 0.71

Phase 3: 重排序 (Cross-Encoder)
  → Faithfulness: 0.71 → 0.76

Phase 4: 提示词 + 上下文优化
  (Prompt约束 + Chunk调整 + 分数阈值)
  → Faithfulness: 0.76 → 0.81
"""
