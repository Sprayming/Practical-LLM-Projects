"""
集成测试：聊天接口（完整链路 + 边界路径）。

真实走通的层：FastAPI 路由 → JWT 鉴权依赖 → 请求模型校验 →
  检索/重排/引用/记忆 的编排 → 响应序列化。
外部依赖（LLM、embedding、向量库、reranker）用 mock 替代，
保证测试离线可跑、可重复，同时验证「内部接线」正确。
"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


def _make_fake_doc():
    """构造一个伪造的检索文档对象，供 mock 向量库/引用追踪返回，模拟真实召回结果。"""
    doc = MagicMock(name="retrieved_doc")
    doc.page_content = "《劳动合同法》第十条规定：建立劳动关系，应当订立书面劳动合同。"
    doc.source = "test.pdf"
    doc.filename = "test.pdf"
    doc.content = "《劳动合同法》第十条规定：建立劳动关系，应当订立书面劳动合同。"
    doc.metadata = {"source": "test.pdf"}
    return doc


@pytest.mark.integration
def test_chat_full_pipeline_with_mocked_llm(client, auth_headers):
    """在 mock 外部依赖前提下，验证聊天接口完整链路（检索→重排→引用→记忆→响应）接线正确。

    验证点：登录后携带 token 调用 /api/chat，编排层依次调用 query_rewriter、
            HybridRetriever、reranker、citation_tracker、memory 与 LLM，最终返回
            与 mock LLM 一致的 answer、citations 字段及 token_usage。
    边界/异常：外部 LLM/向量库/reranker 全部 mock，保证离线可跑且可重复。
    """
    doc = _make_fake_doc()

    fake_embedder = MagicMock(name="embedder")
    fake_vs = MagicMock(name="vector_store")
    fake_vs._collection.get.return_value = {"documents": ["doc text"]}
    fake_qr = MagicMock(name="query_rewriter")
    fake_qr.rewrite.return_value = ["重写后的查询"]
    fake_cache = MagicMock(name="cache")
    fake_cache.get.return_value = None
    fake_ct = MagicMock(name="citation_tracker")
    fake_ct.format_context.return_value = "参考文本: ..."
    fake_ct.get_sources.return_value = [doc]

    fake_mem = MagicMock(name="memory")
    fake_mem.get_context.return_value = ""

    # 模拟 LLM 返回的 JSON
    llm_json = {
        "choices": [{"message": {"content": "应当订立书面劳动合同。"}}],
        "usage": {"total_tokens": 50},
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = llm_json

    mock_client = MagicMock(name="httpx_client")
    mock_client.post = AsyncMock(return_value=mock_resp)

    mock_ac = MagicMock(name="async_client_ctx")
    mock_ac.__aenter__.return_value = mock_client
    mock_ac.__aexit__.return_value = False

    # 当前 _build_pipeline 返回 SimpleNamespace，测试需对齐该契约
    fake_pipeline = SimpleNamespace(
        embedder=fake_embedder,
        vector_store=fake_vs,
        qr=fake_qr,
        cache=fake_cache,
        ct=fake_ct,
        mem=fake_mem,
    )
    with patch(
        "app.api.chat._build_pipeline",
        return_value=fake_pipeline,
    ), patch("app.api.chat._get_memory", return_value=fake_mem), patch(
        "app.api.chat.HybridRetriever"
    ) as MockHR, patch("app.api.chat._get_reranker") as MockRR, patch(
        "app.api.chat.httpx.AsyncClient", return_value=mock_ac
    ):
        MockHR.return_value.retrieve.return_value = [doc]
        MockRR.return_value.rerank.return_value = [doc]

        r = client.post(
            "/api/chat",
            json={"message": "建立劳动关系需要签订什么合同？", "stream": False},
            headers=auth_headers,
        )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["answer"] == "应当订立书面劳动合同。"
    assert "citations" in data
    assert data["token_usage"] == 50


@pytest.mark.integration
def test_chat_without_uploaded_document(client, auth_headers):
    """向量库不存在时，接口应优雅返回「请先上传文档」，而非 500。"""
    # CHROMA_PERSIST_DIR 是临时目录，该 tenant 子目录尚未创建 → _build_pipeline 返回 None
    r = client.post(
        "/api/chat",
        json={"message": "你好", "stream": False},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert "请先上传文档" in r.json().get("answer", "")


@pytest.mark.integration
def test_chat_invalid_body(client, auth_headers):
    """缺少 message 字段 → 422。"""
    r = client.post("/api/chat", json={}, headers=auth_headers)
    assert r.status_code == 422
