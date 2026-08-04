from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    """用户创建模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")


class UserLogin(BaseModel):
    """用户登录模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户响应模型"""
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime]


class Token(BaseModel):
    """JWT Token模型"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # 1小时


class TokenData(BaseModel):
    """Token数据模型"""
    user_id: Optional[int] = None
    username: Optional[str] = None


class PasswordChange(BaseModel):
    """密码修改模型"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")