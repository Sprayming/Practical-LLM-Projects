
"""
OCR 引擎 - 支持多种后端引擎的 OCR 接口
"""
import os, base64
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OCREngine:
    """OCR 引擎 - 自动检测可用后端"""

    def __init__(self, lang: str = "ch"):
        self.lang = lang
        self._backend = None
        self._init_backend()

    def _init_backend(self):
        """按优先级尝试初始化 OCR 后端"""
        backends = [
            ("paddleocr", self._init_paddleocr),
            ("pytesseract", self._init_pytesseract),
        ]
        for name, init_fn in backends:
            try:
                init_fn()
                logger.info(f"OCR 后端: {name}")
                return
            except Exception:
                continue
        logger.warning("OCR 后端: 无可用引擎，返回空文本")
        self._backend = "none"

    def _init_paddleocr(self):
        from paddleocr import PaddleOCR
        try:
            # PaddleOCR 3.x API（2024+）：用文档方向/扭转/文本行方向开关替代旧的
            # use_angle_cls / use_gpu；lang 仍用于选择中英文模型。
            self._ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                lang="ch",
            )
        except TypeError:
            # 兼容旧版 2.x API
            self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False, use_gpu=False)
        self._backend = "paddleocr"

    def _init_pytesseract(self):
        import pytesseract
        self._ocr = pytesseract
        self._backend = "pytesseract"

    def recognize(self, image_bytes: bytes) -> str:
        """识别图片中的文字"""
        if self._backend == "none":
            return ""
        if self._backend == "paddleocr":
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            try:
                # 兼容 PaddleOCR 3.x（推荐 predict()）与 2.x（ocr()）
                if hasattr(self._ocr, "predict"):
                    result = self._ocr.predict(tmp_path)
                else:
                    result = self._ocr.ocr(tmp_path)
                if not result:
                    return ""
                ocr_result = result[0]
                # PaddleOCR 3.x: OCRResult 是类字典对象，识别文本在 'rec_texts' 中
                if hasattr(ocr_result, "keys") and "rec_texts" in ocr_result:
                    texts = ocr_result.get("rec_texts") or []
                    return "\n".join(str(t) for t in texts)
                # PaddleOCR 2.x: 列表格式 [ [bbox, (text, score)], ... ]
                texts = []
                for line in ocr_result:
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        texts.append(line[1][0])
                return "\n".join(str(t) for t in texts)
            finally:
                os.unlink(tmp_path)
        elif self._backend == "pytesseract":
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            return self._ocr.image_to_string(img, lang="chi_sim+eng")
        return ""