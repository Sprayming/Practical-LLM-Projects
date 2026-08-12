"""
app/processing —— 法律文档多模态处理子包

【作用与功能】
本子包负责将原始法律文档(PDF 或纯文本)转换为可供向量检索的结构化
“多模态文本块”。它串联了 PDF 提取、OCR 文字识别、Vision 图片描述与文本
分块等步骤，是 legal-doc-rag 系统“入库”链路的核心环节之一。

【主要组成】
- `pdf_extractor`:基于 PyMuPDF 提取 PDF 每页文本与图片。
- `ocr_engine`:多后端 OCR 引擎，识别图片中的文字。
- `multimodal_pipeline`:编排上述组件，输出 `MultimodalChunk` 列表。

【适用场景】
- 场景1:文档入库(ingestion)前，将 PDF/文本预处理为带图片引用与
  OCR 文字的语义片段。
- 场景2:被 `app/ingestion` 与上层编排逻辑调用，作为检索前的数据准备。

【依赖关系】
- 上游调用方:文档入库流程、检索编排层。
- 下游依赖:`app.ingestion.vision_caption`(图片语义描述)、
  `app.core.config`(API 配置)、`langchain_text_splitters`(分块)。
"""
