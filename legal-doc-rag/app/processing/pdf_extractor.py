
"""
app/processing/pdf_extractor —— 基于 PyMuPDF 的 PDF 图文提取器

【作用与功能】
本模块负责将 PDF 文档逐页解析为结构化数据:每页抽取纯文本，并提取页内
嵌入的图片(二进制与格式)。提取结果为 `multimodal_pipeline` 提供原始
素材，是“PDF → 多模态文本块”链路的第一环。

【主要组成】
- `extract_pdf_pages`:逐页提取文本与图片，返回页面列表。
- `extract_page_preview`:将指定页渲染为 base64 PNG 预览图。

【适用场景】
- 场景1:处理管线在 `_process_pdf()` 中调用 `extract_pdf_pages()` 获取
  页面文本与图片。
- 场景2:前端/调试时调用 `extract_page_preview()` 生成页面缩略图。

【依赖关系】
- 上游调用方:`app.processing.multimodal_pipeline`。
- 下游依赖:`fitz`(PyMuPDF)。
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional


def extract_pdf_pages(pdf_path: str) -> list[dict]:
    """提取 PDF 文档的每页内容，返回结构化页面列表。

    打开 PDF 后逐页遍历:用 `get_text("text")` 取纯文本，用
    `get_images(full=True)` 枚举嵌入图片并通过 `extract_image` 取出二进制
    与扩展名，最后将每页汇总为字典。

    参数:
        pdf_path (str): PDF 文件路径。

    返回:
        list[dict]: 页面列表，每个元素形如
            {"page_number": int(从1开始), "text": str, "images": list}，
            其中 images 元素含 index/ext/bytes/width/height。

    异常:
        fitz.FileDataError: 当 PDF 损坏或路径不可用时由 PyMuPDF 抛出。
    适用场景:
        - 处理管线的 `_process_pdf()` 调用，作为多模态分块的数据源。
    """
    pages = []
    doc = fitz.open(pdf_path)
    for page_num in range(doc.page_count):
        page = doc[page_num]
        page_data = {
            "page_number": page_num + 1,
            "text": page.get_text("text").strip(),
            "images": [],
        }
        # 提取每页中的图片
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_data = {
                "index": img_index,
                "ext": image_ext,
                "bytes": image_bytes,
                "width": base_image.get("width", 0),
                "height": base_image.get("height", 0),
            }
            page_data["images"].append(image_data)
        pages.append(page_data)
    doc.close()
    return pages


def extract_page_preview(pdf_path: str, page_num: int = 0) -> Optional[str]:
    """提取指定页面的渲染预览(返回 base64 PNG)。

    以 150 DPI 将指定页渲染为位图，再编码为 base64 字符串，便于前端直接
    作为 `<img src>` 展示。页码越界时安全返回 None。

    参数:
        pdf_path (str): PDF 文件路径。
        page_num (int): 目标页码(0 基)，默认第 0 页。

    返回:
        Optional[str]: base64 编码的 PNG 字符串；页码越界时返回 None。

    异常:
        无:越界等错误通过提前 `return None` 处理，不会向上抛出。
    适用场景:
        - 文档预览/调试展示页面缩略图。
    """
    import base64
    doc = fitz.open(pdf_path)
    if page_num >= doc.page_count:
        doc.close()
        return None
    page = doc[page_num]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode()