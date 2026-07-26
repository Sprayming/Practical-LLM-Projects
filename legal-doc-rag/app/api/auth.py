import sys, secrets
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.tenant.auth import login as _login, register as _register, has_users as _has_users
import app.core.config as cfg

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Simple in-memory token store: token -> user_info
_tokens: dict = {}

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("/register")
def register(req: RegisterRequest):
    ok, msg = _register(req.username, req.password)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}

@router.post("/login")
def login(req: LoginRequest):
    ok, result = _login(req.username, req.password)
    if not ok:
        raise HTTPException(401, result.get("error", "Login failed"))
    token = secrets.token_urlsafe(32)
    _tokens[token] = result
    return {
        "success": True,
        "token": token,
        "user": {
            "username": result["username"],
            "tenant_id": result["tenant_id"],
            "role": result["role"],
        },
    }

def get_user_from_token(token: str) -> dict:
    user = _tokens.get(token)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user
