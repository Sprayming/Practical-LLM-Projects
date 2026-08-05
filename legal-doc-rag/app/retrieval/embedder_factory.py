"""
可插拔 Embedder 工厂。
"""
import os
import requests
from typing import List


class DirectEmbed:
    """直接调用豆包 / OpenAI 兼容 Embedding API。
    不依赖 langchain-openai 的 tokenizer，确保发送原始文本。
    """
    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档"""
        resp = requests.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        return self.embed_documents([text])[0]


def create_embedder():
    """根据 EMBEDDER_TYPE 配置创建对应的 embedder 实例"""
    embedder_type = os.getenv("EMBEDDER_TYPE", "openai")

    if embedder_type == "openai":
        return DirectEmbed(
            model=os.getenv("EMBEDDING_MODEL", "ep-m-20251117205847-trwgz"),
            api_key=os.getenv("EMBEDDING_API_KEY", ""),
            base_url=os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        )

    elif embedder_type == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name=os.getenv("HF_MODEL_NAME", "BAAI/bge-m3"),
            cache_folder=os.getenv("HF_CACHE_DIR", "./model_cache"),
        )

    else:
        raise ValueError(
            f"Unknown embedder_type: {embedder_type}. "
            f"Supported: openai, huggingface"
        )