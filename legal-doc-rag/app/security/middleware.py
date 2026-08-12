"""
middleware.py —— Legal-DOC-RAG 安全中间件与输入防护

【作用与功能】
本模块提供一组基于 Starlette `BaseHTTPMiddleware` 的安全中间件与工具函数，
在不侵入业务逻辑的前提下增强 API 安全:注入响应安全头、限制请求体大小
以抵御 DoS、净化文件名与校验路径防止路径穿越、清洗用户查询输入以消除
XSS/注入风险。

【主要组成】
- `SecurityHeadersMiddleware`:为所有响应注入安全相关的 HTTP 头
- `RequestSizeLimitMiddleware`:限制请求体大小，超出即拒绝(413)
- `sanitize_filename` / `is_safe_path` / `get_safe_upload_path`:文件名与
  上传路径的安全处理
- `sanitize_query_input` / `is_query_safe`:用户查询输入的清洗与危险检测

【适用场景】
- 场景1:应用启动时将两类中间件加入 ASGI 中间件栈
- 场景2:文件上传前调用安全函数生成可信路径，聊天前清洗用户输入

【依赖关系】
- 上游调用方:app 启动装配、上传接口、聊天接口
- 下游依赖:Starlette middleware、loguru
"""
import re
import os
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from loguru import logger


# ============================================================
# 1. Security Headers Middleware
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """为所有响应注入安全相关的 HTTP 头。

    通过继承 `BaseHTTPMiddleware`，在响应返回前统一追加一系列防御性响应头，
    降低 MIME 嗅探、点击劫持、XSS、敏感数据缓存等风险。
    """

    async def dispatch(self, request: Request, call_next):
        """拦截请求并在响应上补充安全头后返回。

        先放行后续处理链(`call_next`)，再对产生的响应逐一设置安全头。

        参数:
            request (Request): 当前请求对象
            call_next (Callable): 调用后续中间件的回调

        返回:
            Response: 已附加安全头的响应对象
        """
        response = await call_next(request)

        # 禁止浏览器对响应做 MIME 类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Prevent caching of sensitive data
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        # Content Security Policy (basic)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"

        return response


# ============================================================
# 2. Request Size Limit Middleware
# ============================================================

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """限制请求体大小以抵御 DoS / 大文件耗尽资源。

    在请求进入业务处理前检查 `Content-Length`，超出上限直接返回 413，
    避免超大请求占用后续处理资源。
    """

    def __init__(self, app, max_size_mb: int = 100):
        """构造中间件并记录允许的最大字节数。

        参数:
            app: ASGI 应用(由 Starlette 中间件机制传入)
            max_size_mb (int): 允许的最大请求体大小(MB)，默认 100
        """
        super().__init__(app)
        # 将 MB 换算为字节并缓存，避免每次请求重复计算
        self.max_size_bytes = max_size_mb * 1024 * 1024

    async def dispatch(self, request: Request, call_next):
        """检查请求体大小，超限直接拒绝。

        读取请求头中的 `content-length`，若超过 `max_size_bytes` 则立即
        返回 413 响应，否则放行。注意:此处仅基于声明的长度做前置拦截。

        参数:
            request (Request): 当前请求对象
            call_next (Callable): 调用后续中间件的回调

        返回:
            Response: 413 拒绝响应或正常响应
        """
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request too large. Maximum size is {self.max_size_bytes // (1024*1024)}MB"}
            )
        return await call_next(request)


# ============================================================
# 3. Path Traversal Protection
# ============================================================

def sanitize_filename(filename: str) -> str:
    r"""
    安全化文件名，防止路径穿越与隐藏文件攻击。

    依次执行:去除空字节、用 `basename` 去掉路径分隔符与穿越序列、去掉
    开头的点(避免 Unix 隐藏文件)、替换非法字符为下划线、截断到 255 字符
    (文件系统常见上限)。若结果为空则回退为「unnamed」。

    参数:
        filename (str): 原始文件名(可能含路径或非法字符)

    返回:
        str: 清洗后的安全文件名

    异常:
        无(仅做字符串处理，不抛异常)
    适用场景:
        - 文件上传保存前对客户端传入的文件名做净化
    """
    if not filename:
        return "unnamed"

    # Remove null bytes
    filename = filename.replace("\x00", "")

    # Remove path separators and traversal sequences
    filename = os.path.basename(filename)

    # Remove leading dots (prevent hidden files on Unix)
    filename = filename.lstrip(".")

    # Replace problematic characters
    filename = re.sub(r'[<>:"|?*]', '_', filename)

    # Enforce max length (255 is standard filesystem limit)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext

    return filename or "unnamed"


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """判断目标路径是否落在基准目录内(防路径穿越)。

    将 `base_dir` 与 `target_path` 均解析为绝对规范化路径，再用
    `is_relative_to` 判断后者是否仍位于前者之下。一旦解析失败(非法路径)
    直接返回 False，从而拒绝可疑路径。

    参数:
        base_dir (str): 允许的根目录(基准目录)
        target_path (str): 待校验的目标路径

    返回:
        bool: 目标路径安全(在基准目录内)为 True，否则 False

    异常:
        无(内部已捕获 `ValueError`/`OSError` 并降级为 False)
    适用场景:
        - 拼接出上传路径后与基准目录做最终安全校验
    """
    try:
        base = Path(base_dir).resolve()
        target = Path(target_path).resolve()
        return target.is_relative_to(base)
    except (ValueError, OSError):
        return False


def get_safe_upload_path(upload_dir: str, tenant_id: str, filename: str) -> str:
    """生成带全量防护的安全上传路径。

    先清洗 `tenant_id`(仅保留字母数字与连字符)，再净化 `filename`，
    将二者拼接到 `upload_dir` 下并确保目标目录存在，最后用 `is_safe_path`
    做最终校验——若不合法则抛出 `ValueError`，确保绝不会写出基准目录之外。

    参数:
        upload_dir (str): 上传根目录
        tenant_id (str): 租户标识(用于目录隔离)
        filename (str): 原始文件名

    返回:
        str: 安全、绝对的上传文件路径

    异常:
        ValueError: 当最终路径校验不安全时抛出(信息中暴露原始文件名)
    适用场景:
        - 文档上传接口落盘前调用，获得可信保存路径
    """
    # Sanitize tenant_id (alphanumeric + hyphens only)
    safe_tenant = re.sub(r'[^a-zA-Z0-9_-]', '', tenant_id)

    # Sanitize filename
    safe_filename = sanitize_filename(filename)

    # Build and verify path
    upload_dir = os.path.join(upload_dir, safe_tenant)
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, safe_filename)

    # Final safety check
    if not is_safe_path(upload_dir, file_path):
        raise ValueError(f"Unsafe file path detected: {filename}")

    return file_path


# ============================================================
# 4. Input Sanitization
# ============================================================

# Characters that should not appear in user input for queries
FORBIDDEN_QUERY_PATTERNS = [
    r'<script',          # XSS
    r'javascript:',      # JS injection
    r'onerror=',         # Event handler injection
    r'onload=',          # Event handler injection
    r'eval\(',           # Code execution
    r'exec\(',           # Code execution
]


def sanitize_query_input(query: str) -> str:
    """清洗用户查询输入以提升安全性。

    对原始查询做:去除首尾空白、截断到 2000 字符、剔除空字节。注意本函数
    只做基础净化(长度与空字节)，更进一步的危险模式检测交由
    `is_query_safe` 完成。

    参数:
        query (str): 用户原始查询文本

    返回:
        str: 清洗后的查询文本(空输入返回空串)

    异常:
        无
    适用场景:
        - 聊天/检索接口拿到用户输入后先做基础净化
    """
    if not query:
        return ""

    # Trim
    query = query.strip()

    # Max length
    query = query[:2000]

    # Remove null bytes
    query = query.replace("\x00", "")

    return query


def is_query_safe(query: str) -> bool:
    """检测查询是否包含潜在危险的注入模式。

    将查询转为小写后，逐条匹配 `FORBIDDEN_QUERY_PATTERNS` 中的黑名单模式
    (如 `<script`、`javascript:`、`onerror=`、`eval(`、`exec(` 等)。
    命中即记录告警并返回 False，提示上层拒绝该请求。

    参数:
        query (str): 待检测的查询文本

    返回:
        bool: 查询安全为 True，否则 False

    异常:
        无
    适用场景:
        - 接收聊天/检索请求前做安全闸门校验
    """
    query_lower = query.lower()
    for pattern in FORBIDDEN_QUERY_PATTERNS:
        if re.search(pattern, query_lower):
            logger.warning("Blocked potentially dangerous query: {}", query[:100])
            return False
    return True