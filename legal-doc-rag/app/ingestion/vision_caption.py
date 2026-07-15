"""Vision LLM 图片标注 - 为图片生成描述文字，实现"搜文字出图"
与 processing/ocr_engine.py 配合使用：OCR 提取文字，Vision LLM 生成语义描述"""
import base64, os
from pathlib import Path
from typing import Optional
from loguru import logger


class VisionCaptioner:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists(): load_dotenv(str(env_path))
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")

    def caption(self, image_bytes: bytes, image_ext: str = "png") -> str:
        if not self.api_key: return "[Vision LLM not configured]"
        b64 = base64.b64encode(image_bytes).decode()
        mime = f"image/{image_ext}" if image_ext != "jpg" else "image/jpeg"
        data_url = f"data:{mime};base64,{b64}"
        import requests
        try:
            resp = requests.post(f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "请用一句话描述这张图片的核心内容，包括其中的文字信息。"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}], "temperature": 0.1, "max_tokens": 200}, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"] or ""
        except Exception as e:
            logger.warning("Vision caption failed: {}", e)
        return "[Image]"

    def batch_caption(self, images: list[tuple[bytes, str]]) -> list[str]:
        return [self.caption(img, ext) for img, ext in images]