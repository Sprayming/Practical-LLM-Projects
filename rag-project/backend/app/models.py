# ============================================================
# 数据模型 — 定义 API 请求和响应的"格式说明书"
# 所有 HTTP 接口的输入输出都经过这里校验
# ============================================================

from typing import Optional          # 可选类型，表示字段可以为 None
from pydantic import BaseModel, Field  # 数据校验和序列化


class DocumentMeta(BaseModel):
    """文档的元信息（不包含全文内容，只含描述性字段）。"""
    id: str                           # 文档唯一 ID
    filename: str                     # 文件名
    file_size: int                    # 文件大小（字节）
    file_type: str                    # 文件类型（.pdf / .docx / .txt）
    page_count: Optional[int] = None  # 页数（PDF 才有）
    char_count: int                   # 字符数
    chunk_count: int                  # 被切分成几个块
    created_at: str                   # 创建时间（ISO-8601 格式）


class CitationSource(BaseModel):
    """单条引用来源 — 回答中标注的原文出处。"""
    document_id: str                  # 来源文档的 ID
    filename: str                     # 来源文档的文件名
    page_number: Optional[int] = None # 页码（如果有）
    chunk_index: int                  # 文本块的索引
    content: str = Field(..., description="匹配文本片段")  # 匹配到的原文内容
    # Field(...) 表示该字段必填
    score: float = Field(..., ge=0.0, le=1.0)  # 相似度分数（0~1 之间）


class ChatRequest(BaseModel):
    """用户发起问答时的请求体。"""
    query: str = Field(..., min_length=1, max_length=4096)  # 用户问题，1-4096 字符
    top_k: int = Field(default=5, ge=1, le=20)    # 检索几个相关块，默认5
    document_ids: Optional[list[str]] = None       # 可选：限定只在某些文档里搜


class ChatResponse(BaseModel):
    """问答的响应体。"""
    answer: str                       # DeepSeek 生成的回答文本
    sources: list[CitationSource]     # 引用的原文来源列表
    latency_ms: float                 # 总耗时（毫秒）
    tokens_used: int = 0              # 消耗的 token 总数


class UploadResponse(BaseModel):
    """上传文档的响应体。"""
    success: bool                     # 是否成功
    document_id: str                  # 生成的文档 ID
    filename: str                     # 文件名
    message: str                      # 提示消息


class DocumentListResponse(BaseModel):
    """文档列表的响应体。"""
    documents: list[DocumentMeta]     # 文档列表
    total: int                        # 总数


class DeleteResponse(BaseModel):
    """删除文档的响应体。"""
    success: bool
    message: str


class HealthResponse(BaseModel):
    """健康检查的响应体。"""
    status: str                       # 服务状态 "ok"
    version: str = "0.1.0"            # 版本号
    api_key_configured: bool          # API Key 是否已配置
    collection_stats: Optional[dict] = None  # 向量库统计信息




class DocumentDetail(DocumentMeta):
    """文档详情（包含内容预览）。"""
    content_preview: str = ""

class ErrorResponse(BaseModel):
    """错误响应体。"""
    detail: str
    code: Optional[str] = None
