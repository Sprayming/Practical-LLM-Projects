
"""
app/processing/ocr_engine —— 多后端 OCR 引擎

【作用与功能】
本模块提供统一的 OCR 文字识别接口 `OCREngine`，对图片(PDF 中提取的图
片、扫描页等)执行文字识别。它按优先级自动探测可用后端(PaddleOCR /
pytesseract)，并兼容不同版本的 API 差异，使上层管线无需关心具体引擎。

【主要组成】
- `OCREngine`:OCR 引擎类，`recognize()` 为对外识别入口，
  `_init_backend()/_init_paddleocr()/_init_pytesseract()` 负责后端初始化，
  `_ensure_init()` 实现惰性、幂等的后端加载。

【适用场景】
- 场景1:处理管线对 PDF 每页图片调用 `recognize()` 提取图片文字。
- 场景2:仅有扫描层、无文本层的法律文档，通过 OCR 获取可检索文字。

【依赖关系】
- 上游调用方:`app.processing.multimodal_pipeline`。
- 下游依赖:可选 `paddleocr`、可选 `pytesseract` + `pillow`。
"""
import os, base64
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class OCREngine:
    """OCR 引擎 - 自动检测可用后端。

    构造时不立即加载任何后端(惰性初始化)，首次 `recognize()` 时按
    优先级探测并锁定一个可用后端；若无任何引擎可用则标记 "none" 并返回
    空串。后端名称与 OCR 句柄分别缓存在 `_backend` 与 `_ocr`。
    """

    def __init__(self, lang: str = "ch"):
        """初始化 OCR 引擎(仅记录配置，不加载后端)。

        参数:
            lang (str): 识别语言代码，默认 "ch"(中文)。注意 PaddleOCR
                初始化时内部硬编码中文模型，此处主要供 pytesseract 分支使用。
        """
        self.lang = lang
        # 懒加载:默认不初始化任何后端，首次 recognize() 时才按需加载，
        # 避免纯文字 PDF(无需 OCR)也白白占用 PaddleOCR 数百 MB 显存/内存。
        self._backend = None  # None=尚未初始化；"none"=无可用引擎
        self._ocr = None

    def _ensure_init(self):
        """首次需要时初始化 OCR 后端(幂等)。

        若 `_backend` 仍为 None(尚未尝试初始化)，则调用 `_init_backend()`；
        否则直接返回，保证后端只加载一次。这样可避免纯文字 PDF 也白白占用
        PaddleOCR 数百 MB 显存/内存。
        """
        if self._backend is not None:
            return
        self._init_backend()

    def _init_backend(self):
        """按优先级尝试初始化 OCR 后端。

        依次尝试 `paddleocr` → `pytesseract`；首个成功初始化的后端即被
        采用并置 `_backend`，随后返回。若全部失败，则置 `_backend="none"`，
        后续 `recognize()` 直接返回空串而不再重试。
        """
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
        """初始化 PaddleOCR 后端(兼容 3.x 与 2.x API)。

        优先使用 PaddleOCR 3.x 的新参数(文档方向/扭转/文本行方向开关)；
        若构造时抛出 TypeError，则回退到 2.x 旧参数
        (use_angle_cls / use_gpu)。成功后置 `_backend="paddleocr"`。
        """
        from paddleocr import PaddleOCR
        try:
            # PaddleOCR 3.x API(2024+):用文档方向/扭转/文本行方向开关替代旧的
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
        """初始化 pytesseract 后端。

        仅做模块级导入并把 pytesseract 对象作为 OCR 句柄保存；成功后置
        `_backend="pytesseract"`。运行时以 `chi_sim+eng` 语言包识别。
        """
        import pytesseract
        self._ocr = pytesseract
        self._backend = "pytesseract"

    def recognize(self, image_bytes: bytes) -> str:
        """识别图片中的文字(对外主入口)。

        先确保后端已初始化；若无可用引擎则返回空串。随后按后端类型执行:
        PaddleOCR 需先落临时文件再调用 `predict()/ocr()`，并兼容 3.x 的
        `rec_texts` 与 2.x 的列表两种返回格式；pytesseract 则直接在内存中
        解码图片并识别。最终将各文本行用换行符拼接返回。

        参数:
            image_bytes (bytes): 图片的二进制内容。

        返回:
            str: 识别出的文字(多行以 "\\n" 连接)；无文字或无引擎时返回空串。

        异常:
            无:后端初始化与识别过程中的异常均被 `_init_backend` 内部吞掉；
            PaddleOCR 临时文件无论成败都会在 `finally` 中清理。
        """
        self._ensure_init()
        if self._backend == "none":
            return ""
        if self._backend == "paddleocr":
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            try:
                # 兼容 PaddleOCR 3.x(推荐 predict())与 2.x(ocr())
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