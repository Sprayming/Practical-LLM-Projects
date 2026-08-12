"""
error_handlers.py —— Legal-DOC-RAG 全局异常处理器

【作用与功能】
本模块为 FastAPI 应用提供全局异常捕获与统一的错误响应格式，将各类
异常（HTTP 异常、值错误、文件未找到、权限错误及未捕获异常）转换为
结构一致的 JSON 错误体，并借助 `ERROR_MESSAGES` 映射返回对用户友好的
中文提示，避免向客户端泄露敏感内部细节。

【主要组成】
- `error_response`：构造标准化错误 JSON 响应
- `ErrorCodes`：应用级错误码常量（鉴权/文档/对话/系统）
- `ERROR_MESSAGES`：错误码到中文提示语的映射
- `get_error_message`：按错误码取友好提示
- `setup_error_handlers`：向 FastAPI 注册各类全局异常处理器

【适用场景】
- 场景1：应用启动时调用 `setup_error_handlers(app)` 完成注册
- 场景2：业务代码主动返回 `error_response(...)` 统一错误格式

【依赖关系】
- 上游调用方：app 启动装配流程
- 下游依赖：FastAPI、loguru
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
    构造统一格式的错误响应体。

    将错误字段封装为 `{error: True, status_code, message, [error_code], [detail]}`，
    供所有异常处理器与主动出错分支复用，保证前端拿到的错误结构一致。

    参数:
        status_code (int): HTTP 状态码（如 400/401/404/500）
        message (str): 对用户友好的错误提示信息
        detail (str, 可选): 技术细节，通常仅用于非生产环境便于排查
        error_code (str, 可选): 应用级错误码（见 `ErrorCodes`），便于前端按码处理

    返回:
        JSONResponse: 携带标准化错误体的响应对象

    异常:
        无（该函数自身不抛出业务异常）
    适用场景:
        - 全局异常处理器内部统一返回
        - 业务逻辑中需要主动返回标准化错误时
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
    """应用级错误码常量集合。

    使用带前缀的字符串编码区分错误域：`AUTH_*`（鉴权）、`DOC_*`（文档）、
    `CHAT_*`（对话）、`SYS_*`（系统）。业务与异常处理器通过返回这些码，
    配合 `ERROR_MESSAGES` 向用户呈现统一的中文提示。
    """
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
    """根据错误码获取对用户友好的中文提示信息。

    在 `ERROR_MESSAGES` 映射中查找对应错误码的中文提示；若未命中，
    则回退到调用方提供的 `default`，仍未提供时返回「未知错误」。

    参数:
        error_code (str): 应用级错误码（见 `ErrorCodes`）
        default (str, 可选): 未命中映射时的兜底文案

    返回:
        str: 中文错误提示文案

    异常:
        无
    适用场景:
        - 异常处理器中将错误码转换为用户可见提示
    """
    return ERROR_MESSAGES.get(error_code, default or "未知错误")


# ============================================================
# Global Exception Handlers
# ============================================================

def setup_error_handlers(app: FastAPI):
    """向 FastAPI 应用注册全局异常处理器。

    通过 `@app.exception_handler(...)` 为 `HTTPException`、`ValueError`、
    `FileNotFoundError`、`PermissionError` 以及兜底 `Exception` 分别安装
    处理函数，使任意未捕获异常都能转换为统一格式的错误响应。

    参数:
        app (FastAPI): 待注册异常处理器的 FastAPI 应用实例

    返回:
        无

    异常:
        无（注册过程本身不抛出）
    适用场景:
        - 应用启动装配阶段调用一次，完成全局异常屏蔽
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """处理 HTTP 异常，返回统一格式错误体。

        将常见 HTTP 状态码映射到应用级错误码（如 401→AUTH_INVALID_TOKEN、
        403→权限不足、413→文件过大、429→限流），并以 `exc.detail` 作为提示；
        若状态码无对应错误码则仅返回原始信息，保证语义清晰。
        """
        # 将常见 HTTP 状态码映射到应用级错误码
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
        """处理 `ValueError`（如参数非法、类型错误）。

        记录警告日志并返回 400 错误；将异常信息作为提示返回给调用方，
        错误码归为系统内部错误 `SYS_INTERNAL_ERROR`。
        """
        logger.warning("ValueError: {} - {}", exc, request.url)
        return error_response(
            status_code=400,
            message=str(exc),
            error_code=ErrorCodes.SYS_INTERNAL_ERROR,
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(request: Request, exc: FileNotFoundError):
        """处理 `FileNotFoundError`。

        记录警告日志并返回 404，提示文案复用「文档不存在」（DOC_NOT_FOUND），
        用于统一文件缺失类错误的用户感知。
        """
        logger.warning("FileNotFoundError: {} - {}", exc, request.url)
        return error_response(
            status_code=404,
            message=get_error_message(ErrorCodes.DOC_NOT_FOUND),
            error_code=ErrorCodes.DOC_NOT_FOUND,
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        """处理 `PermissionError`。

        记录警告日志并返回 403，提示文案复用「权限不足」
        （AUTH_INSUFFICIENT_PERMISSIONS），统一权限类错误的呈现。
        """
        logger.warning("PermissionError: {} - {}", exc, request.url)
        return error_response(
            status_code=403,
            message=get_error_message(ErrorCodes.AUTH_INSUFFICIENT_PERMISSIONS),
            error_code=ErrorCodes.AUTH_INSUFFICIENT_PERMISSIONS,
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """兜底处理所有未被上述处理器捕获的异常。

        记录错误日志与完整堆栈（debug 级别），并返回 500。是否把堆栈作为
        `detail` 暴露给客户端，取决于应用是否处于 debug 模式：生产环境
        出于安全考虑不泄露内部细节。
        """
        logger.error("Unhandled exception: {} - {}", exc, request.url)
        logger.debug("Traceback: {}", traceback.format_exc())

        # 生产环境不向客户端暴露内部堆栈细节
        detail = traceback.format_exc() if app.debug else None

        return error_response(
            status_code=500,
            message=get_error_message(ErrorCodes.SYS_INTERNAL_ERROR),
            detail=detail,
            error_code=ErrorCodes.SYS_INTERNAL_ERROR,
        )

    logger.info("Global error handlers registered")