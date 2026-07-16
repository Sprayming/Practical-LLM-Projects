
"""
多模态处理管线 - PDF 图文提取 + OCR + 向量化
"""
from pathlib import Path
from app.processing.pdf_extractor import extract_pdf_pages
from app.processing.ocr_engine import OCREngine
from langchain_text_splitters import RecursiveCharacterTextSplitter


class MultimodalChunk:
    """多模态文本块 - 包含文本 + 关联图片"""
    def __init__(self, text: str, page_number: int, images: list = None):
        self.text = text
        self.page_number = page_number
        self.images = images or []


class MultimodalPipeline:
    """多模态文档处理管线: PDF → 图文提取 → OCR → 分块 → 向量化"""

    def __init__(self):
        self._ocr = OCREngine()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", "，", " "],
        )

    def process(self, file_path: str) -> list[MultimodalChunk]:
        """处理文档: 提取图文 + OCR + 组装文本块"""
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            return self._process_pdf(file_path)
        else:
            # 非 PDF 文件: 直接读取文本
            text = Path(file_path).read_text(encoding="utf-8")
            return [MultimodalChunk(text=text, page_number=1)]

    def _process_pdf(self, pdf_path: str) -> list[MultimodalChunk]:
        """处理 PDF 文件"""
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

            # 页面文本 + OCR 文字合并
            combined = page_text
            if ocr_texts:
                combined += "\n[图片文字]\n" + "\n".join(ocr_texts)

            if not combined.strip():
                continue

            # 分块
            split_texts = self._splitter.split_text(combined)
            for st in split_texts:
                img_refs = [{"index": img["index"], "ext": img["ext"]} for img in page_images]
                chunks.append(MultimodalChunk(text=st, page_number=page["page_number"], images=img_refs))

        return chunks