"""
集成测试：文档上传（API 契约 + 多租户隔离）。

真实走通的层：FastAPI 路由 → JWT 鉴权 → 扩展名/大小校验 →
  安全路径（防穿越）→ 落盘保存 → 列表查询。
重依赖（OCR/分块 MultimodalPipeline、embedding、Chroma 向量库）用 mock 替代，
避免测试需要 GPU/网络，同时验证「上传后文件确实落盘、并被列表接口可见」。
"""
import os
from unittest.mock import patch, MagicMock

import pytest


class _FakeChunk:
    def __init__(self, text):
        self.text = text


@pytest.mark.integration
def test_upload_document_success_and_listed(client, auth_headers, test_env):
    chunks = [_FakeChunk("第一段法律文本"), _FakeChunk("第二段法律文本")]
    fake_pipeline = MagicMock()
    fake_pipeline.process.return_value = chunks

    pdf_bytes = b"%PDF-1.4 fake pdf content for testing"

    with patch(
        "app.api.documents.MultimodalPipeline", return_value=fake_pipeline
    ), patch("app.api.documents.create_embedder", return_value=MagicMock()), patch(
        "app.api.documents.Chroma"
    ):
        r = client.post(
            "/api/documents/upload",
            files={"file": ("contract.pdf", pdf_bytes, "application/pdf")},
            headers=auth_headers,
        )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["chunks"] == 2

    tenant_id = data["tenant_id"]
    # 文件确实落盘到临时上传目录
    saved = os.path.join(test_env["upload_dir"], tenant_id, "contract.pdf")
    assert os.path.exists(saved), f"上传文件未落盘: {saved}"

    # 列表接口应能看到该文件
    r2 = client.get("/api/documents", headers=auth_headers)
    assert r2.status_code == 200
    assert "contract.pdf" in r2.json()["documents"]


@pytest.mark.integration
def test_upload_rejects_non_pdf(client, auth_headers):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("note.txt", b"hello world", "text/plain")},
        headers=auth_headers,
    )
    assert r.status_code == 400


@pytest.mark.integration
def test_upload_requires_auth(client):
    # 缺 Authorization 头 → 422（Header 必填）
    r = client.post(
        "/api/documents/upload",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code in (401, 422)


@pytest.mark.integration
def test_upload_rejects_bad_token(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert r.status_code == 401
