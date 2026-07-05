# ============================================================
# 数据模型
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional


class DocumentMetaModel(BaseModel):
    id: str
    filename: str
    file_size: int
    file_type: str
    page_count: Optional[int] = None
    char_count: int
    chunk_count: int


class DocumentDetailModel(DocumentMetaModel):
    content_preview: str = ""


class UploadResponseModel(BaseModel):
    success: bool
    document_id: str
    filename: str
    message: str


class DeleteResponseModel(BaseModel):
    success: bool
    message: str


class ChatRequestModel(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: Optional[list[str]] = None


class CitationSourceModel(BaseModel):
    document_id: str
    filename: str
    page_number: Optional[int] = None
    chunk_index: int
    content: str = Field(..., description="matched text")
    score: float = Field(..., ge=0.0, le=1.0)


class ChatResponseModel(BaseModel):
    answer: str
    sources: list[CitationSourceModel]
    latency_ms: float
    tokens_used: int = 0


class DocumentListResponseModel(BaseModel):
    documents: list[DocumentMetaModel]
    total: int


class ErrorResponseModel(BaseModel):
    detail: str
    code: Optional[str] = None


class HealthResponseModel(BaseModel):
    status: str
    version: str = "0.1.0"
    api_key_configured: bool
    collection_stats: Optional[dict] = None
