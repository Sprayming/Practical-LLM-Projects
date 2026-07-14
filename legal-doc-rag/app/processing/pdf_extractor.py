"""
PDF 提取器 - 使用 PyMuPDF 提取文本和图片
"""
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional


def extract_pdf_pages(pdf_path: str) -> list[dict]:
    """提取 PDF 文档的每页内容，返回结构化页面列表"""
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
    """提取指定页面的渲染预览（返回 base64 PNG）"""
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