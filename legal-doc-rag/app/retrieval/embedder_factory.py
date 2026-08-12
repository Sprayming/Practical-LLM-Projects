"""
embedder_factory —— 可插拔 Embedder 工厂。

【作用与功能】
根据配置（EMBEDDER_TYPE）创建统一的文本嵌入器实例，屏蔽「云端 API 嵌入」
与「本地模型嵌入」的差异，供索引构建与检索查询复用。

【主要组成】
- `DirectEmbed`：直接调用豆包/OpenAI 兼容 Embedding API（分批+限速+退避重试）
- `create_embedder`：按 EMBEDDER_TYPE 创建 openai / huggingface 嵌入器

【适用场景】
- 场景1：文档索引时为海量 chunk 批量生成向量
- 场景2：提问时生成查询向量以做相似度检索

【依赖关系】
- 上游调用方：索引构建脚本、HybridRetriever（稠密通道）
- 下游依赖：app.core.config、requests、FlagEmbedding/BGE-M3、langchain_huggingface
"""
import os
import time
import requests
from typing import List

import loguru


class DirectEmbed:
    """直接调用豆包 / OpenAI 兼容 Embedding API。
    不依赖 langchain-openai 的 tokenizer，确保发送原始文本。
    """
    def __init__(self, model: str, api_key: str, base_url: str):
        """初始化直接调用云端 Embedding API 的客户端。

        保存模型名、API Key 与 base_url（统一去掉尾部斜杠）。
        分批/限速/重试参数在类属性 BATCH_SIZE/BATCH_INTERVAL/MAX_RETRY 中定义。

        参数:
            model: 云端 Embedding 模型名（如 doubao-embedding / text-embedding-3）
            api_key: API 密钥
            base_url: API 基址（如 https://ark.cn-beijing.volces.com/api/v3）
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    # 云端 Embedding API 对单次请求条数有上限（火山云约 256 条），超出返回 400；
    # 且有 QPM/TPM 频率限制，连续快发会返回 429。大文档动辄切出上千 chunk，
    # 必须「分批 + 限速 + 退避重试」，否则整篇文档索引失败。
    BATCH_SIZE = 32
    BATCH_INTERVAL = 0.5      # 批次间隔（秒），主动限速
    MAX_RETRY = 6             # 429/5xx 最大重试次数

    def _post(self, texts: List[str]):
        """向 /embeddings 端点发送一次 Embedding 请求并返回响应对象。

        参数:
            texts: 本批次待嵌入文本列表
        返回:
            requests.Response: 原始 HTTP 响应（由调用方判断状态码）
        """
        return requests.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts},
            timeout=120,
        )

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """发送单批：429/5xx 指数退避重试；400 折半拆分再试。"""
        delay = 2.0
        for attempt in range(self.MAX_RETRY):
            resp = self._post(texts)

            if resp.status_code == 200:
                data = resp.json()
                return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

            # 条数/长度超限：折半拆分
            if resp.status_code == 400 and len(texts) > 1:
                mid = len(texts) // 2
                return self._embed_batch(texts[:mid]) + self._embed_batch(texts[mid:])

            # 限流或服务端抖动：退避重试
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < self.MAX_RETRY - 1:
                    loguru.logger.warning(
                        "Embedding {} (batch={}), {:.0f}s 后重试 ({}/{})",
                        resp.status_code, len(texts), delay, attempt + 1, self.MAX_RETRY,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue

            resp.raise_for_status()

        raise RuntimeError(f"Embedding 重试 {self.MAX_RETRY} 次仍失败（最后状态码 {resp.status_code}）")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档（自动分批 + 限速，保持输入顺序）"""
        vectors: List[List[float]] = []
        total = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        for idx, i in enumerate(range(0, len(texts), self.BATCH_SIZE)):
            if idx:
                time.sleep(self.BATCH_INTERVAL)
            vectors.extend(self._embed_batch(texts[i:i + self.BATCH_SIZE]))
            if total > 1:
                loguru.logger.info("Embedding 进度 {}/{} 批", idx + 1, total)
        return vectors

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        return self.embed_documents([text])[0]


def create_embedder():
    """根据 EMBEDDER_TYPE 配置创建对应的 embedder 实例。

    统一从 app.core.config 读取配置，避免与 config 中的默认值不一致
    （历史 bug：此处默认 openai、config 默认 huggingface，导致未配 key 时
    仍会去调云端 API 并 401，表现为「文档索引失败」）。
    """
    from app.core import config

    embedder_type = config.EMBEDDER_TYPE

    if embedder_type == "openai":
        if not config.EMBEDDING_API_KEY:
            raise ValueError(
                "EMBEDDER_TYPE=openai 但 EMBEDDING_API_KEY 为空。"
                "请在 .env 中配置 EMBEDDING_API_KEY，或改用 EMBEDDER_TYPE=huggingface（本地模型）。"
            )
        return DirectEmbed(
            model=config.EMBEDDING_MODEL,
            api_key=config.EMBEDDING_API_KEY,
            base_url=config.EMBEDDING_BASE_URL,
        )

    elif embedder_type == "huggingface":
        try:
            from app.retrieval.bge_m3_embedder import BGEM3Embedder

            return BGEM3Embedder()
        except Exception as e:  # noqa: BLE001
            loguru.logger.warning(
                "BGEM3Embedder 不可用，回退 HuggingFaceEmbeddings: {}", e
            )
            from langchain_huggingface import HuggingFaceEmbeddings

            return HuggingFaceEmbeddings(
                model_name=config.HF_MODEL_NAME,
                cache_folder=config.HF_CACHE_DIR,
            )

    else:
        raise ValueError(
            f"Unknown embedder_type: {embedder_type}. "
            f"Supported: openai, huggingface"
        )