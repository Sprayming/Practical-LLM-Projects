"""
Integration test fixtures for Legal-DOC-RAG.

这些用例验证「多个真实组件被接线起来跑得通」:
  - FastAPI 路由 → JWT 鉴权 → 业务层 → (外部 LLM / 向量库 用 mock 替代)
  - 只 mock 真正的外部依赖(LLM、embedding、OCR)，其余走真实代码路径。

测试环境与生产完全隔离:临时 sqlite 用户库 + 临时上传/向量目录 + 固定 JWT 密钥。
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import app.core.config as cfg
from app.core.limiter import limiter


def reset_limiter():
    """重置 slowapi 限流计数，避免跨测试 429 串扰(限流键按 IP，单进程共享)。"""
    try:
        limiter.reset()
    except Exception:
        try:
            limiter._storage.reset()
        except Exception:
            pass


@pytest.fixture(scope="session")
def test_env():
    """隔离测试环境:临时用户库 + 临时上传/向量目录 + 固定 JWT 密钥。"""
    tmp = tempfile.mkdtemp(prefix="legalrag_it_")
    db_path = os.path.join(tmp, "users.db")
    upload_dir = os.path.join(tmp, "uploads")
    chroma_dir = os.path.join(tmp, "chroma_db")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(chroma_dir, exist_ok=True)

    # 固定 JWT 密钥，保证签发/校验一致(不依赖默认占位值)
    cfg.JWT_SECRET = "test-secret-for-integration"
    # 指向临时目录，避免污染项目真实的 uploads / chroma_db
    cfg.UPLOAD_DIR = upload_dir
    cfg.CHROMA_PERSIST_DIR = chroma_dir

    with patch("app.tenant.auth._db_path", return_value=db_path):
        yield {
            "tmp": tmp,
            "db_path": db_path,
            "upload_dir": upload_dir,
            "chroma_dir": chroma_dir,
        }
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def client(test_env):
    """每个测试都重置限流并提供一个干净的 TestClient。"""
    from fastapi.testclient import TestClient
    from app.main import app

    reset_limiter()
    yield TestClient(app)


@pytest.fixture
def auth_headers(client):
    """注册并登录一个测试用户，返回带 Bearer token 的请求头。"""
    reset_limiter()
    creds = {"username": "it_user", "password": "it_password_123"}
    # 注册(若因重复而 400 可忽略，登录即可)
    client.post("/api/auth/register", json=creds)
    r = client.post("/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}
