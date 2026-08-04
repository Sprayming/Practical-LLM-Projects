from fastapi import APIRouter, HTTPException, Depends, status
from loguru import logger

from app.auth.models import UserCreate, UserLogin, UserResponse, Token, PasswordChange
from app.auth.database import create_user, get_user_by_username, authenticate_user, create_api_key
from app.auth.jwt_handler import create_access_token
from app.auth.dependencies import get_current_user, get_current_active_user
from app.security.validators import validate_api_key

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate):
    """用户注册"""
    try:
        # 创建用户
        new_user = create_user(
            username=user.username,
            email=user.email,
            password=user.password,
            full_name=user.full_name
        )
        
        if new_user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名或邮箱已存在"
            )
        
        return new_user
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("用户注册失败: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败，请稍后重试"
        )


@router.post("/login", response_model=Token)
async def login_user(user: UserLogin):
    """用户登录"""
    try:
        # 验证用户
        authenticated_user = authenticate_user(user.username, user.password)
        
        if authenticated_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 创建访问令牌
        access_token = create_access_token(
            data={
                "sub": str(authenticated_user["id"]),
                "username": authenticated_user["username"]
            }
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("用户登录失败: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败，请稍后重试"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return current_user


@router.post("/api-key", response_model=dict)
async def create_new_api_key(
    name: str = None,
    current_user: dict = Depends(get_current_active_user)
):
    """创建API密钥"""
    try:
        api_key = create_api_key(current_user["id"], name)
        
        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建API密钥失败"
            )
        
        return {
            "api_key": api_key,
            "name": name,
            "message": "API密钥创建成功，请妥善保管"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建API密钥失败: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建API密钥失败"
        )


@router.post("/change-password")
async def change_password(
    password_change: PasswordChange,
    current_user: dict = Depends(get_current_active_user)
):
    """修改密码"""
    from app.auth.database import verify_password, hash_password
    import sqlite3
    from pathlib import Path
    
    try:
        # 验证旧密码
        conn = sqlite3.connect(str(Path(__file__).resolve().parent.parent.parent / "data" / "users.db"))
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT hashed_password FROM users WHERE id = ?",
            (current_user["id"],)
        )
        row = cursor.fetchone()
        
        if not row or not verify_password(password_change.old_password, row[0]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码错误"
            )
        
        # 更新密码
        new_hashed_password = hash_password(password_change.new_password)
        cursor.execute(
            "UPDATE users SET hashed_password = ? WHERE id = ?",
            (new_hashed_password, current_user["id"])
        )
        conn.commit()
        conn.close()
        
        return {"message": "密码修改成功"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("修改密码失败: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="修改密码失败"
        )