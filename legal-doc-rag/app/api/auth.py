"""
auth.py —— 认证与鉴权 API 模块

【作用与功能】
本模块提供 legal-doc-rag 系统的用户认证与鉴权接口，包括用户注册、登录并签发 JWT、
获取当前登录态、修改密码以及凭管理员重置密钥自助重置密码。它是所有受保护接口的身份
校验入口，并通过 FastAPI 依赖注入（require_user）把解析出的用户信息传递给下游路由。

【主要组成】
- `register`：用户注册接口，速率限制 20 次/分钟以防批量注册。
- `login`：用户登录接口，校验凭据后签发 JWT Token。
- `change_password`：修改当前登录用户密码，速率限制 10 次/分钟。
- `reset_password`：凭管理员重置密钥自助重置密码，速率限制 5 次/分钟。
- `get_current_user`：解析 Token 返回当前用户登录态与基本信息。
- `_create_token`：基于 HS256 算法生成带过期时间的 JWT。
- `get_user_from_token`：解码并校验 JWT 签名与有效期，返回用户信息。
- `require_user`：FastAPI 依赖函数，从 Authorization 头提取并校验 JWT。

【适用场景】
- 用户首次进入系统时注册账号、登录获取 Token。
- 前端在每次请求受保护接口时在 Authorization 头携带该 Token。
- 用户忘记密码时凭管理员颁发的重置密钥自助重置。

【依赖关系】
- 上游调用方：前端登录/注册页；所有受保护 API 通过 require_user 依赖本模块。
- 下游依赖：app.tenant.auth（注册/登录/改密底层实现）、app.core.config（JWT 密钥）、
  app.core.limiter（限流）、PyJWT 库。
"""

import sys

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent))
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Header, Request, Depends
from pydantic import BaseModel
# 导入租户认证底层操作函数（使用别名避免与当前路由函数名冲突）
from app.tenant.auth import (
    login as _login, 
    register as _register, 
    has_users as _has_users, 
    change_password as _change_password, 
    reset_password_with_key as _reset_password_with_key
)
import app.core.config as cfg
from app.core.limiter import limiter

# 创建 API 路由器实例，统一添加 /api/auth 前缀，并打上 "auth" 标签用于文档分类
router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT 相关常量定义
JWT_ALGORITHM = "HS256"         # JWT 签名算法
TOKEN_EXPIRE_DAYS = 30          # Token 默认过期时间（天）


class LoginRequest(BaseModel):
    """
    登录请求的数据模型。
    
    Attributes:
        username (str): 用户名。
        password (str): 密码。
    """
    username: str
    password: str


class RegisterRequest(BaseModel):
    """
    注册请求的数据模型。
    
    Attributes:
        username (str): 用户名。
        password (str): 密码。
    """
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    """
    修改密码请求的数据模型。
    
    Attributes:
        old_password (str): 原密码。
        new_password (str): 新密码。
    """
    old_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    """
    重置密码请求的数据模型。
    
    Attributes:
        username (str): 需要重置密码的用户名。
        reset_key (str): 管理员颁发的重置密钥。
    """
    username: str
    reset_key: str


@router.post("/register")
@limiter.limit("20/minute")
def register(request: Request, req: RegisterRequest):
    """
    用户注册接口。
    
    接收用户名和密码，调用底层服务创建新用户。带有速率限制（20次/分钟）以防恶意批量注册。
    
    Args:
        request (Request): FastAPI 原生 Request 对象，用于速率限制器获取客户端信息。
        req (RegisterRequest): 包含用户名和密码的请求体。
        
    Raises:
        HTTPException: 如果注册失败（如用户名已存在），抛出 400 异常。
        
    Returns:
        dict: 包含成功标志和操作消息。
    """
    ok, msg = _register(req.username, req.password)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.post("/login")
@limiter.limit("20/minute")
def login(request: Request, req: LoginRequest):
    """
    用户登录接口。
    
    校验用户名和密码，校验通过后签发 JWT Token。带有速率限制（20次/分钟）以防暴力破解。
    
    Args:
        request (Request): FastAPI 原生 Request 对象，用于速率限制。
        req (LoginRequest): 包含用户名和密码的请求体。
        
    Raises:
        HTTPException: 如果登录失败（如密码错误、用户不存在），抛出 401 异常。
        
    Returns:
        dict: 包含成功标志、JWT Token 以及当前用户的基本信息（用户名、租户ID、角色）。
    """
    ok, result = _login(req.username, req.password)
    if not ok:
        raise HTTPException(401, result.get("error", "Login failed"))
    
    # 登录成功，生成 JWT Token
    token = _create_token(result)
    return {
        "success": True,
        "token": token,
        "user": {
            "username": result["username"],
            "tenant_id": result["tenant_id"],
            "role": result["role"],
        },
    }


def _create_token(user_info: dict, expires_days: int = TOKEN_EXPIRE_DAYS) -> str:
    """
    签发带签名、有过期时间的 JWT。
    
    将用户关键信息（用户名、租户ID、角色）和过期时间打包进 Payload，使用配置的密钥进行签名。
    
    Args:
        user_info (dict): 包含用户信息的字典，需包含 username, tenant_id, role。
        expires_days (int, optional): Token 有效期天数，默认为 30 天。
        
    Returns:
        str: 编码后的 JWT 字符串。
    """
    payload = {
        "sub": user_info.get("username", ""),        # sub (subject): 通常存用户名
        "tenant_id": user_info.get("tenant_id", ""), # 自定义声明：租户ID，用于多租户数据隔离
        "role": user_info.get("role", "user"),       # 自定义声明：用户角色，用于权限校验
        "exp": datetime.now(timezone.utc) + timedelta(days=expires_days), # 过期时间
    }
    return jwt.encode(payload, cfg.JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_from_token(token: str) -> dict:
    """
    解码并验证 JWT，返回用户信息。
    
    使用密钥验证 Token 的签名和有效期。如果验证失败，抛出 401 异常。
    
    Args:
        token (str): JWT Token 字符串。
        
    Raises:
        HTTPException: 如果 Token 无效、被篡改或已过期，抛出 401 异常。
        
    Returns:
        dict: 从 Token 中解析出的用户信息字典，包含 username, tenant_id, role。
    """
    try:
        payload = jwt.decode(token, cfg.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return {
        "username": payload.get("sub", ""),
        "tenant_id": payload.get("tenant_id", ""),
        "role": payload.get("role", "user"),
    }


def require_user(authorization: str = Header(...)) -> dict:
    """
    FastAPI 依赖注入函数：从 Authorization 请求头解析并校验 JWT。
    
    用于保护需要登录才能访问的路由。自动提取 Header 中的 Token，验证通过后将用户信息注入到路由函数中。
    
    Args:
        authorization (str): 请求头中的 Authorization 字段值，预期格式为 "Bearer <token>"。
        
    Raises:
        HTTPException: 如果缺少 Token 抛出 401；如果 Token 无效抛出 401。
        
    Returns:
        dict: 当前登录用户的详细信息字典。
    """
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)


@router.get("/me")
def get_current_user(authorization: str = Header(...)):
    """
    获取当前登录用户的信息。
    
    前端在刷新页面或初始化时调用此接口，通过携带 Token 获取当前用户的登录态和基本信息。
    
    Args:
        authorization (str): 请求头中的 Authorization 字段值。
        
    Raises:
        HTTPException: 如果缺少 Token 或 Token 无效抛出 401。
        
    Returns:
        dict: 当前用户信息，包含 username, tenant_id, role。
    """
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    user = get_user_from_token(token)
    return {
        "username": user.get("username", ""),
        "tenant_id": user.get("tenant_id", ""),
        "role": user.get("role", "user"),
    }


@router.post("/change-password")
@limiter.limit("10/minute")
def change_password(
    request: Request,
    req: ChangePasswordRequest,
    user: dict = Depends(require_user),
):
    """
    修改当前登录用户的密码。
    
    需要用户已登录（依赖 require_user）。需校验原密码是否正确，正确后方可修改为新密码。
    带有速率限制（10次/分钟）。
    
    Args:
        request (Request): FastAPI 原生 Request 对象，用于速率限制。
        req (ChangePasswordRequest): 包含原密码和新密码的请求体。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    Raises:
        HTTPException: 如果原密码错误或修改失败，抛出 400 异常。
        
    Returns:
        dict: 包含成功标志和操作消息。
    """
    ok, msg = _change_password(user["username"], req.old_password, req.new_password)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, req: ResetPasswordRequest):
    """
    忘记密码自救：凭管理员重置密钥重置指定账号密码。
    
    无需登录即可访问。用户需提供用户名及管理员事先分发重置密钥，验证通过后系统将密码重置为默认密码或随机密码。
    带有严格的速率限制（5次/分钟）以防密钥爆破。
    
    Args:
        request (Request): FastAPI 原生 Request 对象，用于速率限制。
        req (ResetPasswordRequest): 包含用户名和重置密钥的请求体。
        
    Raises:
        HTTPException: 如果重置密钥错误或用户不存在，抛出 400 异常。
        
    Returns:
        dict: 包含成功标志和操作消息（可能包含新密码或提示检查邮件）。
    """
    ok, msg = _reset_password_with_key(req.username, req.reset_key)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}
