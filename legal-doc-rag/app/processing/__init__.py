"""
app.processing —— 法律文档多模态处理子包（包标识文件）

【作用与功能】
将原始法律文档（PDF 或纯文本）转换为可供向量检索的结构化"多模态文本块"，
串联 PDF 提取、OCR 文字识别、Vision 图片描述与文本分块，是"入库"链路的核心环节。

【实现方式】
本文件仅作为包标识，不承载运行逻辑。具体能力由子模块提供：
- `pdf_extractor`:基于 PyMuPDF 提取 PDF 每页文本与图片
- `ocr_engine`:多后端 OCR 引擎，识别图片中的文字
- `multimodal_pipeline`:编排上述组件，输出 `MultimodalChunk` 列表

依赖 `app.ingestion.vision_caption`（图片语义描述）、`app.core.config`（API 配置）
与 `langchain_text_splitters`（分块）。

【整体作用】
作为检索前的数据准备阶段，把 PDF/文本预处理为带图片引用与 OCR 文字的语义片段，
供下游向量化与检索使用。
"""
