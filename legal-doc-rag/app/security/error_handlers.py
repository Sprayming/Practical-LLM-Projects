"""
Global error handlers for Legal-DOC-RAG.

Provides:
- Unified error response format
- Friendly error messages
- Global exception handlers
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import traceback
import sys


# ============================================================
# Error Response Format
# ============================================================

def error_response(status_code: int, message: str, detail: str = None, error_code: str = None) -> JSONResponse:
    """
    Create a unified error response.

    Args:
        status_code: HTTP status code
        message: User-friendly error message
        detail: Technical detail (optional, only in non-production)
        error_code: Application-specific error code (optional)

    Returns:
        JSONResponse with standardized error format
    """
    content = {
        "error": True,
        "status_code": status_code,
        "message": message,
    }

    if error_code:
        content["error_code"] = error_code

    if detail:
        content["detail"] = detail

    return JSONResponse(status_code=status_code, content=content)


# ============================================================
# Error Code Constants
# ============================================================

class ErrorCodes:
    """Application-specific error codes."""
    # Authentication
    AUTH_MISSING_TOKEN = "AUTH_001"
    AUTH_INVALID_TOKEN = "AUTH_002"
    AUTH_TOKEN_EXPIRED = "AUTH_003"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_004"
    AUTH_USER_NOT_FOUND = "AUTH_005"
    AUTH_INVALID_CREDENTIALS = "AUTH_006"

    # Documents
    DOC_NOT_FOUND = "DOC_001"
    DOC_UPLOAD_FAILED = "DOC_002"
    DOC_PROCESSING_FAILED = "DOC_003"
    DOC_INVALID_TYPE = "DOC_004"
    DOC_TOO_LARGE = "DOC_005"
    DOC_PATH_TRAVERSAL = "DOC_006"

    # Chat
    CHAT_NO_DOCUMENTS = "CHAT_001"
    CHAT_LLM_ERROR = "CHAT_002"
    CHAT_RETRIEVAL_ERROR = "CHAT_003"
    CHAT_MEMORY_ERROR = "CHAT_004"

    # System
    SYS_INTERNAL_ERROR = "SYS_001"
    SYS_SERVICE_UNAVAILABLE = "SYS_002"
    SYS_RATE_LIMIT = "SYS_003"
    SYS_STORAGE_FULL = "SYS_004"


# ============================================================
# Error Message Mapping
# ============================================================

ERROR_MESSAGES = {
    ErrorCodes.AUTH_MISSING_TOKEN: "请先登录",
    ErrorCodes.AUTH_INVALID_TOKEN: "登录已过期，请重新登录",
    ErrorCodes.AUTH_TOKEN_EXPIRED: "登录已过期，请重新登录",
    ErrorCodes.AUTH_INSUFFICIENT_PERMISSIONS: "权限不足",
    ErrorCodes.AUTH_USER_NOT_FOUND: "用户不存在",
    ErrorCodes.AUTH_INVALID_CREDENTIALS: "用户名或密码错误",

    ErrorCodes.DOC_NOT_FOUND: "文档不存在",
    ErrorCodes.DOC_UPLOAD_FAILED: "文档上传失败",
    ErrorCodes.DOC_PROCESSING_FAILED: "文档处理失败，请检查文件格式",
    ErrorCodes.DOC_INVALID_TYPE: "仅支持PDF格式文件",
    ErrorCodes.DOC_TOO_LARGE: "文件过大，最大支持100MB",
    ErrorCodes.DOC_PATH_TRAVERSAL: "文件名包含非法字符",

    ErrorCodes.CHAT_NO_DOCUMENTS: "请先上传文档",
    ErrorCodes.CHAT_LLM_ERROR: "AI服务暂时不可用，请稍后重试",
    ErrorCodes.CHAT_RETRIEVAL_ERROR: "检索服务异常，请稍后重试",
    ErrorCodes.CHAT_MEMORY_ERROR: "记忆系统异常，已降级处理",

    ErrorCodes.SYS_INTERNAL_ERROR: "系统内部错误，请稍后重试",
    ErrorCodes.SYS_SERVICE_UNAVAILABLE: "服务暂时不可用",
    ErrorCodes.SYS_RATE_LIMIT: "请求过于频繁，请稍后重试",
    ErrorCodes.SYS_STORAGE_FULL: "存储空间不足",
}


def get_error_message(error_code: str, default: str = None) -> str:
    """Get user-friendly error message for error code."""
    return ERROR_MESSAGES.get(error_code, default or "未知错误")


# ============================================================
# Global Exception Handlers
# ============================================================

def setup_error_handlers(app: FastAPI):
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with unified format."""
        # Map common HTTP status codes to error codes
        status_to_code = {
            400: ErrorCodes.SYS_INTERNAL_ERROR,
            401: ErrorCodes.AUTH_INVALID_TOKEN,
            403: ErrorCodes.AUTH_INSUFFICIENT_PERMISSIONS,
            404: ErrorCodes.DOC_NOT_FOUND,
            413: ErrorCodes.DOC_TOO_LARGE,
            429: ErrorCodes.SYS_RATE_LIMIT,
            500: ErrorCodes.SYS_INTERNAL_ERROR,
        }

        error_code = status_to_code.get(exc.status_code)
        message = str(exc.detail) if exc.detail else get_error_message(error_code)

        return error_response(
            status_code=exc.status_code,
            message=message,
            detail=str(exc.detail) if exc.detail else None,
            error_code=error_code,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle ValueError (e.g., bad input)."""
        logger.warning("ValueError: {} - {}", exc, request.url)
        return error_response(
            status_code=400,
            message=str(exc),
            error_code=ErrorCodes.SYS_INTERNAL_ERROR,
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError):
        """Handle FileNotFoundError."""
        logger.warning("FileNotFoundError: {} - {}", exc, request.url)
        return error_response(
            status_code=404,
            message=get_error_message(ErrorCodes.DOC_NOT_FOUND),
            error_code=ErrorCodes.DOC_NOT_FOUND,
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        """Handle PermissionError."""
        logger.warning("PermissionError: {} - {}", exc, request.url)
        return error_response(
            status_code=403,
            message=get_error_message(ErrorCodes.AUTH_INSUFFICIENT_PERMISSIONS),
            error_code=ErrorCodes.AUTH_INSUFFICIENT_PERMISSIONS,
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other exceptions."""
        logger.error("Unhandled exception: {} - {}", exc, request.url)
        logger.debug("Traceback: {}", traceback.format_exc())

        # Don't expose internal details in production
        detail = traceback.format_exc() if app.debug else None

        return error_response(
            status_code=500,
            message=get_error_message(ErrorCodes.SYS_INTERNAL_ERROR),
            detail=detail,
            error_code=ErrorCodes.SYS_INTERNAL_ERROR,
        )

    logger.info("Global error handlers registered")