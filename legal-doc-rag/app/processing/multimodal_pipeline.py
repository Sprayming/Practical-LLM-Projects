
"""
app/processing/multimodal_pipeline —— 多模态文档处理管线

【作用与功能】
本模块是文档入库链路的编排核心：接收 PDF 或纯文本路径，依次完成
“图文提取 → OCR 文字识别 → Vision 图片描述 → 文本合并 → 分块”，
最终产出可向量化的 `MultimodalChunk` 列表。它把 `pdf_extractor`、
`ocr_engine` 与 `app.ingestion.vision_caption` 串成一条完整管线。

【主要组成】
- `MultimodalChunk`：多模态文本块数据类（文本 + 页码 + 关联图片引用）。
- `MultimodalPipeline`：管线主类，`process()` 对外入口，
  `_process_pdf()` 负责 PDF 的完整处理流程。

【适用场景】
- 场景1：将法律 PDF 转换为带图片引用与 OCR 文字的语义片段，供向量化入库。
- 场景2：非 PDF 文本文件直接读取为单块，走简化分支。

【依赖关系】
- 上游调用方：文档入库流程、检索编排层。
- 下游依赖：`app.processing.pdf_extractor.extract_pdf_pages`、
  `app.processing.ocr_engine.OCREngine`、`app.ingestion.vision_caption.VisionCaptioner`、
  `langchain_text_splitters.RecursiveCharacterTextSplitter`。
"""
from pathlib import Path
from app.processing.pdf_extractor import extract_pdf_pages
from app.processing.ocr_engine import OCREngine
from langchain_text_splitters import RecursiveCharacterTextSplitter


class MultimodalChunk:
    """多模态文本块 - 包含文本 + 关联图片。

    表示文档分块后的一个语义单元，除纯文本外还携带其来源页码与
    关联图片的索引/格式引用，便于后续“以文搜图”与上下文回溯。

    属性:
        text (str): 该文本块的正文内容（含 OCR 文字与图片描述）。
        page_number (int): 文本块所属的原文档页码（从 1 开始）。
        images (list): 关联图片引用列表，元素形如
            {"index": 页内图片序号, "ext": 图片扩展名}。
    """
    def __init__(self, text: str, page_number: int, images: list = None):
        """初始化多模态文本块。

        参数:
            text (str): 文本块正文。
            page_number (int): 来源页码（从 1 开始）。
            images (list, optional): 关联图片引用列表，为 None 时置为空列表。
        """
        self.text = text
        self.page_number = page_number
        self.images = images or []


class MultimodalPipeline:
    """多模态文档处理管线: PDF → 图文提取 → OCR → 分块 → 向量化。

    管线对外仅暴露 `process()` 方法：根据文件扩展名分发到 PDF 处理或
    纯文本处理分支。内部惰性创建 OCR 引擎与文本分块器，并在 PDF 分支中
    调用 VisionCaptioner 为图片生成语义描述。
    """

    def __init__(self):
        """初始化多模态处理管线。

        构造时即创建 OCR 引擎（内部为惰性后端加载，不会立刻占用资源）
        与递归字符分块器（针对中文优化的分隔符与 500 字符块大小）。
        """
        self._ocr = OCREngine()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", "，", " "],
        )

    def process(self, file_path: str) -> list[MultimodalChunk]:
        """处理文档: 提取图文 + OCR + 组装文本块。

        根据文件后缀分发处理分支：PDF 走完整的 `_process_pdf()` 流程；
        其余文本文件直接读取为单个多模态块（页码记为 1，无图片）。

        参数:
            file_path (str): 待处理文档的本地路径。

        返回:
            list[MultimodalChunk]: 分块后的多模态文本块列表。

        异常:
            无：非 PDF 文本读取失败时会以 Python 内置异常向上抛出；
            PDF 处理中各页 OCR/Vision 失败均被静默忽略，仅跳过空页。
        """
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            return self._process_pdf(file_path)
        else:
            # 非 PDF 文件: 直接读取文本
            text = Path(file_path).read_text(encoding="utf-8")
            return [MultimodalChunk(text=text, page_number=1)]

    def _process_pdf(self, pdf_path: str) -> list[MultimodalChunk]:
        """处理 PDF 文件（内部方法）。

        逐页执行：抽取页面文本与图片 → 对每张图片做 OCR 与 Vision 描述
        → 将页面文本、图片描述、OCR 文字合并为一个字符串 → 按块大小切分
        → 为每块附带整页图片引用，生成 `MultimodalChunk` 列表。

        参数:
            pdf_path (str): PDF 文件路径。

        返回:
            list[MultimodalChunk]: 该 PDF 分块后的多模态文本块列表。

        适用场景:
            - 由 `process()` 在检测到 `.pdf` 后缀时调用，通常不对外直接调用。
        """
        pages = extract_pdf_pages(pdf_path)
        chunks = []

        for page in pages:
            page_text = page["text"]
            page_images = page["images"]
            ocr_texts = []

            # OCR 识别图片中的文字
            for img in page_images:
                ocr_result = self._ocr.recognize(img["bytes"])
                if ocr_result:
                    ocr_texts.append(ocr_result)

            # AI 图片描述 (VisionCaption)
            caption_texts = []
            try:
                from app.ingestion.vision_caption import VisionCaptioner
                import app.core.config as cfg
                captioner = VisionCaptioner(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
                for img in page_images:
                    try:
                        caption = captioner.caption(img["bytes"], img.get("ext", "png"))
                        if caption:
                            caption_texts.append("[图片描述] " + caption)
                    except Exception:
                        pass
            except Exception:
                pass

            # 页面文本 + OCR 文字合并
            combined = page_text
            if caption_texts:
                combined += "\n" + "\n".join(caption_texts)
            if ocr_texts:
                combined += "\n[图片文字]\n" + "\n".join(ocr_texts)

            if not combined.strip():
                continue

            # 分块
            split_texts = self._splitter.split_text(combined)
            for st in split_texts:
                # 仅为本块保留整页图片引用（不重复内嵌二进制），供以文搜图回溯
                img_refs = [{"index": img["index"], "ext": img["ext"]} for img in page_images]
                chunks.append(MultimodalChunk(text=st, page_number=page["page_number"], images=img_refs))

        return chunks
