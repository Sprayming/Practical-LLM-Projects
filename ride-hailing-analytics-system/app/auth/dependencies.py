from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.auth.jwt_handler import verify_token
from app.auth.database import get_user_by_id, validate_api_key
from app.auth.models import TokenData

# HTTP Bearer认证
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """获取当前用户"""
    token = credentials.credentials
    
    # 验证令牌
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 获取用户信息
    user = get_user_by_id(int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账户已禁用"
        )
    
    return user


async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """获取当前活跃用户"""
    if not current_user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账户已禁用"
        )
    return current_user


async def get_current_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """获取当前管理员用户"""
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user


async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[dict]:
    """获取当前用户（可选）"""
    if credentials is None:
        return None
    
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if payload is None:
            return None
        
        user_id = payload.get("sub")
        if user_id is None:
            return None
        
        user = get_user_by_id(int(user_id))
        return user
    except Exception:
        return None


def verify_api_key(api_key: str) -> Optional[int]:
    """验证API密钥"""
    return validate_api_key(api_key)


async def get_user_from_api_key(api_key: str = None) -> Optional[dict]:
    """从API密钥获取用户"""
    if api_key is None:
        return None
    
    user_id = verify_api_key(api_key)
    if user_id is None:
        return None
    
    return get_user_by_id(user_id)