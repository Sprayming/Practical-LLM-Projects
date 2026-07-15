import re

path = "D:/git/rag-project/README.md"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# New architecture section
new_arch = """
## 架构总览

```
                          -------------------
                          |  浏览器 / API    |
                          -------------------
                                   | HTTP / JSON
                                   v
--------------------------------------------------------------------
|                      FastAPI Backend (:8000)                      |
|                                                                    |
|  --------- 摄取管线 (Ingestion) ----------------------------------|
|  |  Upload -> loader.py -> chunker.py -> embedder.py -> ChromaDB |
|  |             + vision_caption.py (图片标注)                     |
|  -----------------------------------------------------------------|
|                                |                                   |
|  --------- 检索问答管线 (Retrieval) --------------------------------|
|  |  Query ---> retriever.py (稠密) ----+                         |
|  |              hybrid_retriever.py    |-- RRF 融合              |
|  |               + BM25 (稀疏) --------+                          |
|  |               + Cross-Encoder 重排序                            |
|  |                    |                                            |
|  |           citation.py (来源标注)                                |
|  |                    |                                            |
|  |           generation/llm.py -> 回答                             |
|  -----------------------------------------------------------------|
|                                |                                   |
|  --------- 评估体系 (Evaluation) ----------------------------------|
|  |  scripts/run_regression.py                                    |
|  |   + evaluation/runner.py -> metrics.py -> RAGAS              |
|  |   + tests/golden_test_set.json (31道)                          |
|  -----------------------------------------------------------------|
|                                                                    |
|               ChromaDB (向量存储) <- embedder.py                  |
|               BM25 索引 (关键词)  <- hybrid_retriever.py          |
--------------------------------------------------------------------
"""

# Replace architecture section (from "## 架构总览" to next "## ")
content = re.sub(
    r"(?s)## 架构总览.*?(?=\n## )",
    new_arch,
    content,
)

# Add evaluation to file tree if not present
if "evaluation/" not in content:
    new_files = """
   |   + vision_caption.py     [NEW] Vision LLM 图片标注
   +--- evaluation/            [NEW] RAGAS 评估
   |   +--- metrics.py         Faithfulness / Relevancy / Recall
   |   +--- runner.py          回归测试 + 历史追踪
   +--- tests/                  [NEW]
   |   +--- golden_test_set.json  31 道 Golden Test Set
   +--- scripts/                [NEW]
       +--- run_regression.py  回归测试入口
"""

    content = content.replace(
        "## Environment",
        new_files + "\n## Environment",
    )

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
print("hybrid_retriever:", "hybrid_retriever" in content)
print("evaluation:", "evaluation/" in content)
print("golden_test_set:", "golden_test_set" in content)
