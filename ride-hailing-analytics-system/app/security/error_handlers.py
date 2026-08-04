from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import traceback


class AppError(Exception):
    """应用错误基类"""
    
    def __init__(self, message: str, status_code: int = 400, error_code: str = None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or "UNKNOWN_ERROR"
        super().__init__(self.message)


class ValidationError(AppError):
    """验证错误"""
    
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR"):
        super().__init__(message, status_code=400, error_code=error_code)


class NotFoundError(AppError):
    """未找到错误"""
    
    def __init__(self, message: str, error_code: str = "NOT_FOUND"):
        super().__init__(message, status_code=404, error_code=error_code)


class DatabaseError(AppError):
    """数据库错误"""
    
    def __init__(self, message: str, error_code: str = "DATABASE_ERROR"):
        super().__init__(message, status_code=500, error_code=error_code)


class LLMError(AppError):
    """LLM服务错误"""
    
    def __init__(self, message: str, error_code: str = "LLM_ERROR"):
        super().__init__(message, status_code=500, error_code=error_code)


class SecurityError(AppError):
    """安全错误"""
    
    def __init__(self, message: str, error_code: str = "SECURITY_ERROR"):
        super().__init__(message, status_code=403, error_code=error_code)


# 错误码映射
ERROR_CODES = {
    "VALIDATION_ERROR": "参数验证失败",
    "NOT_FOUND": "资源未找到",
    "DATABASE_ERROR": "数据库错误",
    "LLM_ERROR": "LLM服务错误",
    "SECURITY_ERROR": "安全错误",
    "INTERNAL_ERROR": "内部服务器错误",
    "RATE_LIMIT_EXCEEDED": "请求频率超限",
    "QUERY_FAILED": "查询失败",
}


async def app_error_handler(request: Request, exc: AppError):
    """应用错误处理器"""
    logger.error("应用错误: {} - {}", exc.error_code, exc.message)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "message": exc.message,
            "error_code": exc.error_code,
            "detail": ERROR_CODES.get(exc.error_code, "未知错误")
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理器"""
    logger.warning("HTTP异常: {} - {}", exc.status_code, exc.detail)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "message": str(exc.detail),
            "error_code": "HTTP_ERROR"
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    logger.error("未处理的异常: {}", exc)
    logger.debug("异常堆栈: {}", traceback.format_exc())
    
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "message": "内部服务器错误",
            "error_code": "INTERNAL_ERROR"
        }
    )


def register_error_handlers(app):
    """注册错误处理器"""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    logger.info("错误处理器注册完成")