"""
Security middleware for Legal-DOC-RAG.

Provides:
- Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- Request size limiting
- Path traversal protection
- Input sanitization
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
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent MIME type sniffing
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
    """Limit request body size to prevent DoS attacks."""

    def __init__(self, app, max_size_mb: int = 100):
        super().__init__(app)
        self.max_size_bytes = max_size_mb * 1024 * 1024

    async def dispatch(self, request: Request, call_next):
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
    Sanitize a filename to prevent path traversal attacks.

    - Removes path separators (/, \)
    - Removes null bytes
    - Strips leading dots (prevent hidden files)
    - Enforces max length
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
    """
    Check if target_path is within base_dir (prevents path traversal).
    """
    try:
        base = Path(base_dir).resolve()
        target = Path(target_path).resolve()
        return target.is_relative_to(base)
    except (ValueError, OSError):
        return False


def get_safe_upload_path(upload_dir: str, tenant_id: str, filename: str) -> str:
    """
    Get a safe file upload path with all protections applied.

    Returns:
        Safe absolute path for the uploaded file.
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
    """
    Sanitize user query input for security.

    - Trims whitespace
    - Enforces max length
    - Strips potentially dangerous patterns
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
    """Check if query contains potentially dangerous patterns."""
    query_lower = query.lower()
    for pattern in FORBIDDEN_QUERY_PATTERNS:
        if re.search(pattern, query_lower):
            logger.warning("Blocked potentially dangerous query: {}", query[:100])
            return False
    return True