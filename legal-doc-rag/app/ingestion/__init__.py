"""
app/ingestion —— 法律文档入库（图片语义标注）子包

【作用与功能】
本子包负责为文档中的图片生成语义描述（caption），配合 OCR 提取的图片
文字，实现“以文搜图”的能力。它是 legal-doc-rag 多模态入库链路的组成部分，
在图片检索与问答中提供可被向量化的图片文本表示。

【主要组成】
- `vision_caption`：调用 Vision LLM（如 DeepSeek）为单张/批量图片生成
  一句话核心描述。

【适用场景】
- 场景1：处理管线（`processing/multimodal_pipeline`）对每页图片调用本
  子包，生成“[图片描述]”文本并入块。
- 场景2：为扫描件、图表类法律文档补充可被检索的图片语义信息。

【依赖关系】
- 上游调用方：`app.processing.multimodal_pipeline`。
- 下游依赖：Vision LLM API（通过 `app.core.config` 注入密钥与地址）。
"""
