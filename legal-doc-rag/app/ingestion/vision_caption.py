"""
app/ingestion/vision_caption —— Vision LLM 图片标注

【作用与功能】
调用 Vision LLM（如 DeepSeek）为图片生成一句话语义描述，与 OCR 提取的
图片文字配合，实现“以文搜图”的检索能力：图片的描述文本会与页面文本一起
被向量化，从而让用户用自然语言检索到相关图片/页面。

【主要组成】
- `VisionCaptioner`：图片标注器类，`caption()` 标注单张图片，
  `batch_caption()` 标注批量图片。

【适用场景】
- 场景1：处理管线对每页图片调用 `caption()` 生成“[图片描述]”并入块。
- 场景2：扫描件、图表类法律文档补充可被检索的图片语义信息。

【依赖关系】
- 上游调用方：`app.processing.multimodal_pipeline`。
- 下游依赖：Vision LLM API（`LLM_API_KEY` / `LLM_BASE_URL` 来自
  `app.core.config` 或 .env），以及 `requests` 与 `loguru`。

与 processing/ocr_engine.py 配合使用：
- OCR 引擎提取图片中的文字
- Vision LLM 生成图片的语义描述
- 两者结合实现基于文字的图片搜索功能

主要特点：
1. 支持 base64 编码的图片输入
2. 自动处理不同图片格式（jpg/png）
3. 批量处理能力
4. 完善的错误处理和日志记录
"""

import base64, os
from pathlib import Path
from typing import Optional
from loguru import logger


class VisionCaptioner:
    """
    图片标注器类，用于调用 Vision LLM API 生成图片描述。

    支持单张图片和批量图片的标注，自动处理图片格式转换和 API 调用。
    构造时从环境变量（或显式参数）加载 API 密钥与基础地址，供后续
    `caption()` / `batch_caption()` 复用。
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        初始化图片标注器。

        从环境变量加载 API 配置，支持手动传入参数覆盖环境变量。

        Args:
            api_key (Optional[str]): Vision API 密钥，如果未提供则从环境变量 LLM_API_KEY 读取。
            base_url (Optional[str]): Vision API 基础 URL，如果未提供则从环境变量 LLM_BASE_URL 读取。

        适用场景:
            - 处理管线在 `_process_pdf()` 中按页实例化本类，传入 cfg.LLM_API_KEY
              与 cfg.LLM_BASE_URL 以复用全局配置。
        """
        # 加载环境变量配置
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists(): 
            load_dotenv(str(env_path))
        
        # 使用传入的参数或环境变量中的配置
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")

    def caption(self, image_bytes: bytes, image_ext: str = "png") -> str:
        """
        为单张图片生成描述文字。

        将图片转换为 base64 编码，构造 API 请求，调用 Vision LLM 生成描述。

        Args:
            image_bytes (bytes): 图片的二进制数据。
            image_ext (str): 图片扩展名（png/jpg），默认为 png。

        Returns:
            str: 生成的图片描述文字。如果 API 调用失败或未配置，返回空字符串。
                 注意：失败时返回空串而非错误信息，避免无意义的占位文本污染向量库。

        异常:
            无：API 未配置时返回提示串，请求异常时记录 warning 并返回空串，
            不会中断上层处理流程。
        适用场景:
            - 处理管线对每页图片逐一调用，生成“[图片描述]”文本并入块。
        """
        # 检查 API 是否已配置
        if not self.api_key: 
            return "[Vision LLM not configured]"
            
        # 将图片转换为 base64 编码
        b64 = base64.b64encode(image_bytes).decode()
        # 处理 MIME 类型
        mime = f"image/{image_ext}" if image_ext != "jpg" else "image/jpeg"
        data_url = f"data:{mime};base64,{b64}"
        
        import requests
        try:
            # 构造并发送 API 请求
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}", 
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat", 
                    "messages": [{
                        "role": "user", 
                        "content": [
                            {
                                "type": "text", 
                                "text": "请用一句话描述这张图片的核心内容，包括其中的文字信息。"
                            },
                            {
                                "type": "image_url", 
                                "image_url": {"url": data_url}
                            }
                        ]
                    }], 
                    "temperature": 0.1,  # 设置较低温度以获得更确定的输出
                    "max_tokens": 200     # 限制输出长度
                },
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"] or ""
        except Exception as e:
            # 记录警告日志，但不中断流程
            logger.warning("Vision caption failed: {}", e)
            
        # 失败时返回空字符串，避免无意义的占位文本污染向量库
        # 特别注意：对于无 OCR/无文字层的扫描页，不应写入无意义的占位 chunk
        return ""

    def batch_caption(self, images: list[tuple[bytes, str]]) -> list[str]:
        """
        批量处理多张图片的标注。

        Args:
            images (list[tuple[bytes, str]]): 图片列表，每个元素是 (图片二进制数据, 图片扩展名) 的元组。

        Returns:
            list[str]: 每张图片对应的描述文字列表，顺序与输入一致。

        适用场景:
            - 需要一次性标注多页/多张图片时调用，等价于对每张图片循环调用
              `caption()`，但语义更明确。
        """
        # 使用列表推导式对每张图片调用 caption 方法
        return [self.caption(img, ext) for img, ext in images]
