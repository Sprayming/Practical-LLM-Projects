import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# ============================================================
# 嵌入服务 - 使用 sentence-transformers 语义嵌入
# ============================================================

from typing import Optional

from loguru import logger
from sentence_transformers import SentenceTransformer

from app.config import settings


class Embedder:
    def __init__(self) -> None:
        self.dim = settings.embedding_dimensions
        cache_dir = getattr(settings, "model_cache", str(settings.chroma_persist_dir))
        self._model = SentenceTransformer(
            "shibing624/text2vec-base-chinese",
            cache_folder=cache_dir,
        )
        logger.info("Embedder ready: text2vec-base-chinese, dim={}", self.dim)

    def embed_document(self, texts: list[str]) -> list[list[float]]:
        embs = self._model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embs]

    def embed_query(self, text: str) -> list[float]:
        emb = self._model.encode([text], show_progress_bar=False)
        return emb[0].tolist()


_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
