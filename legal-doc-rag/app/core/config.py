"""
config —— legal-doc-rag 全局配置集中管理模块

【作用与功能】
该模块负责从环境变量中读取并集中定义 legal-doc-rag RAG 系统运行所需的全部
配置项，包括大语言模型(LLM)、文本嵌入模型(Embedding)、向量数据库存储、
Redis 缓存、JWT 安全、管理员以及路径相关的参数。通过统一的配置入口，各业务
模块无需各自读取环境变量，便于部署、测试与多环境切换。

【主要组成】
- `BASE_DIR`:项目根目录的绝对路径，用于拼接其他相对目录。
- LLM 配置:`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`。
- 嵌入配置:`EMBEDDER_TYPE`、`EMBEDDING_*`、`HF_MODEL_NAME` / `HF_CACHE_DIR`。
- 存储与缓存:`CHROMA_PERSIST_DIR`、`UPLOAD_DIR`、`REDIS_URL`。
- 安全与管理:`JWT_SECRET`、`ADMIN_RESET_KEY`、`MAX_SUPER_ADMINS`。
- 路径:`TENANT_DB`(租户 SQLite 数据库路径)。

【适用场景】
- 场景1:应用启动及运行时，各模块通过 `from app.core import config` 获取参数。
- 场景2:通过 .env 或系统环境变量覆盖默认值，实现不同环境的配置切换。

【依赖关系】
- 上游调用方:app.main、app.api 各路由、app.retrieval 等。
- 下游依赖:仅依赖标准库 `os` 与 `pathlib`，无业务耦合。
"""

import os
from pathlib import Path

# 获取项目根目录的绝对路径，用于后续构建其他目录的相对路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ========================================
# 大语言模型 (LLM) 配置 —— 支持多供应商切换
# ========================================
# 通过 LLM_PROVIDER 选择当前激活的模型供应商，可选值：
#   deepseek | openai | qwen | moonshot | custom
# 每个供应商使用独立的「{供应商大写}_API_KEY / _BASE_URL 风格变量」配置，
# 解析后统一写入下方的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，
# 下游业务模块（chat / admin / vision / evaluator 等）无需任何改动即可切换模型。
#
# 解析优先级（以 DEEPSEEK 为例）：
#   1) DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL（供应商专属变量）
#   2) LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（通用兜底变量）
#   3) 各供应商内建的预设默认值
# 因此：老 .env 仅含 LLM_* 时也能正常工作（自动回退）。
LLM_PROVIDER_PRESETS = {
    # DeepSeek 官方 OpenAI 兼容接口，默认 deepseek-chat
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    # OpenAI 官方接口，可换 gpt-4o / gpt-4o-mini 等
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    # 阿里云百炼（通义千问）OpenAI 兼容接口
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    # 月之暗面 Kimi（Moonshot）OpenAI 兼容接口
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    # 自定义：完全使用下方 LLM_* 通用变量，不套用任何预设
    "custom": {"base_url": "", "model": ""},
}

# 当前激活的供应商，缺省为 deepseek
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
_PROVIDER_PRESET = LLM_PROVIDER_PRESETS.get(LLM_PROVIDER, LLM_PROVIDER_PRESETS["custom"])
_PROVIDER_PREFIX = LLM_PROVIDER.upper()

# API 密钥:用于鉴权访问第三方大模型服务（优先级：供应商专属 > 通用兜底）
LLM_API_KEY = os.getenv(f"{_PROVIDER_PREFIX}_API_KEY") or os.getenv("LLM_API_KEY", "")
# API 基础 URL:大模型服务的接入点（优先级同上；custom 下无预设则用通用变量）
LLM_BASE_URL = (
    os.getenv(f"{_PROVIDER_PREFIX}_BASE_URL")
    or os.getenv("LLM_BASE_URL")
    or _PROVIDER_PRESET["base_url"]
).rstrip("/")
# 模型名称:指定使用的大模型版本（优先级同上）
LLM_MODEL = (
    os.getenv(f"{_PROVIDER_PREFIX}_MODEL")
    or os.getenv("LLM_MODEL")
    or _PROVIDER_PRESET["model"]
)

# 故障转移供应商列表(逗号分隔),主供应商限流/5xx 时按此顺序依次尝试。
# 例如: "qwen,openai"。留空则不做故障转移,仅使用主供应商。
LLM_FALLBACK_PROVIDERS = [
    p.strip().lower()
    for p in os.getenv("LLM_FALLBACK_PROVIDERS", "").split(",")
    if p.strip()
]


def resolve_provider(name: str) -> dict:
    """
    按供应商名解析其 API 配置,返回 {api_key, base_url, model}。

    解析规则与模块级 LLM_* 保持一致(供应商专属变量 > 通用 LLM_* > 预设默认值),
    供 LLM 客户端在「主供应商 -> 备用供应商」故障转移时复用,避免重复解析逻辑。

    参数:
        name (str): 供应商名(deepseek/openai/qwen/moonshot/custom)
    返回:
        dict: 含 api_key / base_url(已去尾部斜杠) / model 的配置字典
    """
    name = (name or "custom").strip().lower()
    preset = LLM_PROVIDER_PRESETS.get(name, LLM_PROVIDER_PRESETS["custom"])
    prefix = name.upper()
    api_key = os.getenv(f"{prefix}_API_KEY") or os.getenv("LLM_API_KEY", "")
    base_url = (
        os.getenv(f"{prefix}_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or preset["base_url"]
    ).rstrip("/")
    model = os.getenv(f"{prefix}_MODEL") or os.getenv("LLM_MODEL") or preset["model"]
    return {"api_key": api_key, "base_url": base_url, "model": model}

# ========================================
# 文本嵌入模型 (Embedding) 配置
# ========================================
# 嵌入模型类型:支持 "huggingface"(本地部署)或 "openai"(在线调用)
EMBEDDER_TYPE = os.getenv("EMBEDDER_TYPE", "huggingface")
# 在线嵌入 API 密钥:当 EMBEDDER_TYPE=openai 时使用
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
# 在线嵌入 API 基础 URL:当 EMBEDDER_TYPE=openai 时使用
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
# 在线嵌入模型名称:当 EMBEDDER_TYPE=openai 时使用
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "ep-m-20251117205847-trwgz")

# 本地 HuggingFace embedding 配置(仅在 EMBEDDER_TYPE=huggingface 时生效)
# 模型名称:指定使用的本地嵌入模型，默认为 BGE-M3
HF_MODEL_NAME = os.getenv("HF_MODEL_NAME", "BAAI/bge-m3")
# 模型缓存目录:用于存放下载的 HuggingFace 模型文件
HF_CACHE_DIR = os.getenv("HF_CACHE_DIR", "./model_cache")

# ========================================
# 数据存储配置
# ========================================
# 向量数据库持久化目录:存放 ChromaDB 的索引数据
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
# 文件上传目录:存放用户上传的文档
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

# ========================================
# Redis 缓存配置
# ========================================
# Redis 连接 URL:用于缓存、会话存储等场景
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ========================================
# JWT 安全配置
# ========================================
# JWT 签名密钥:用于生成和验证用户登录 Token
JWT_SECRET = os.getenv("JWT_SECRET", "legal-rag-secret-key-change-in-production")

# ========================================
# 管理员配置
# ========================================
# 管理员重置密钥:用于用户忘记密码时的安全重置，必须配置且保密，切勿提交到仓库
ADMIN_RESET_KEY = os.getenv("ADMIN_RESET_KEY", "")
# 超级管理员名额上限:管理后台手动设置角色时进行校验，防止超级管理员过多
MAX_SUPER_ADMINS = int(os.getenv("MAX_SUPER_ADMINS", "3"))

# ========================================
# 路径配置
# ========================================
# 租户数据库路径:SQLite 数据库文件，用于存储租户和用户信息
TENANT_DB = str(BASE_DIR / "tenant_data" / "users.db")
