\"\"\"
可插拔 Embedder 工厂。
通过 .env 中 EMBEDDER_TYPE 控制使用哪个 Embedder 实现。
支持策略模式：生产切 API（零 GPU）、本地开发切 HuggingFace（零成本）。
\"\"\"
import os


def create_embedder():
    \"\"\"根据 EMBEDDER_TYPE 配置创建对应的 embedder 实例\"\"\"
    embedder_type = os.getenv("EMBEDDER_TYPE", "openai")

    if embedder_type == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=os.getenv("EMBEDDING_MODEL", "ep-m-20251117205847-trwgz"),
            openai_api_key=os.getenv("EMBEDDING_API_KEY", "df9c9b2d-35d9-4df6-b49d-f489708e1eab"),
            openai_api_base=os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        )

    elif embedder_type == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name=os.getenv("HF_MODEL_NAME", "shibing624/text2vec-base-chinese"),
            cache_folder=os.getenv("HF_CACHE_DIR", "./model_cache"),
        )

    else:
        raise ValueError(
            f"Unknown embedder_type: {embedder_type}. "
            f"Supported: openai, huggingface"
        )