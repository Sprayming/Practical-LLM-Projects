
"""
OCR 引擎 - 支持多种后端引擎的 OCR 接口
"""
import os, base64
from pathlib import Path
from typing import Optional


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
                print(f"OCR 后端: {name}")
                return
            except Exception:
                continue
        print("OCR 后端: 无可用引擎，返回空文本")
        self._backend = "none"

    def _init_paddleocr(self):
        from paddleocr import PaddleOCR
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
                result = self._ocr.ocr(tmp_path, cls=True)
                texts = []
                if result and result[0]:
                    for line in result[0]:
                        texts.append(line[1][0])
                return " ".join(texts)
            finally:
                os.unlink(tmp_path)
        elif self._backend == "pytesseract":
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            return self._ocr.image_to_string(img, lang="chi_sim+eng")
        return ""