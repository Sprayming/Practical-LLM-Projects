import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent))
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Header, Request, Depends
from pydantic import BaseModel
from app.tenant.auth import login as _login, register as _register, has_users as _has_users, change_password as _change_password
import app.core.config as cfg
from app.core.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/register")
@limiter.limit("20/minute")
def register(request: Request, req: RegisterRequest):
    ok, msg = _register(req.username, req.password)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.post("/login")
@limiter.limit("20/minute")
def login(request: Request, req: LoginRequest):
    ok, result = _login(req.username, req.password)
    if not ok:
        raise HTTPException(401, result.get("error", "Login failed"))
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
    """签发带签名、有过期时间的 JWT。"""
    payload = {
        "sub": user_info.get("username", ""),
        "tenant_id": user_info.get("tenant_id", ""),
        "role": user_info.get("role", "user"),
        "exp": datetime.now(timezone.utc) + timedelta(days=expires_days),
    }
    return jwt.encode(payload, cfg.JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_from_token(token: str) -> dict:
    """解码 JWT 并返回用户信息；无效或过期则抛出 401。"""
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
    """FastAPI 依赖：从 Authorization 头解析并校验 JWT。"""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)


@router.get("/me")
def get_current_user(authorization: str = Header(...)):
    """Get current user info from token."""
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
    """修改当前登录用户的密码（需校验原密码）。"""
    ok, msg = _change_password(user["username"], req.old_password, req.new_password)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}
