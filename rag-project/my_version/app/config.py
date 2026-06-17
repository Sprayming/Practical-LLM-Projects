# ============================================================
# 配置中心 — 这是整个系统的"控制面板"
# 所有可调参数都集中在这里，改一处就影响全局
# 从 .env 文件或环境变量读取配置值
# ============================================================

from __future__ import annotations  # 让代码更简洁
from pathlib import Path  # 拼接存储路径
from pydantic_settings import BaseSettings, SettingsConfigDict  # 配置文件的读取器，就是给整个rag配置了一个控制面板


# 再写配置的类
class Settings(BaseSettings):
    """配置类。继承 BaseSettings 后自动从 .env 文件和环境变量读取值。"""
    # LLM 配置
    llm_api_key: str = ""  # DeepSeek API Key，从 .env 的 LLM_API_KEY 读取
    llm_base_url: str = "https://api.deepseek.com/v1"  # API 地址
    llm_model: str = "deepseek-chat"  # 模型名
    llm_temperature: float = 0.15  # 生成温度，越低越确定（0=固定，1=随机）

    # 分块参数chromeDB的配置
    chunk_size: int = 800  # 每个文本块的目标 token 数
    chunk_overlap: int = 200  # 块之间重叠的 token 数，避免切丢上下文
    # 检索返回的参数
    retrieval_top_k: int = 5  # 每次检索返回几个最相关的块
    retrieval_min_score: float = 0.20  # 最低相似度阈值，低于这个值的不要
    # 本地嵌入参数
    embedding_dimensions: int = 768  # 嵌入向量的维度
    # 存储路径
    chroma_persist_dir: str = str(Path(__file__).resolve().parent.parent / "chroma_db")
    # 上传的文件暂存目录
    upload_dir: str = str(Path(__file__).resolve().parent.parent / "uploads")

    # 读取配置文件env
    model_config = SettingsConfigDict(
        env_file=".env",  # 从 .env 文件读取配置
        env_file_encoding="utf-8",  # 文件编码
        extra="ignore",  # .env 里有其他变量也忽略，不会报错
    )


# 全局单例配置对象(实列化对象）
settings = Settings()
