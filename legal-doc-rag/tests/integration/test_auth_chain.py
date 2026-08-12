"""
集成测试:认证链路(JWT 真实签发/校验)。

覆盖:注册 → 重复注册拒绝 → 错误密码拒绝 → 登录拿 token →
      /me(无 token / 错误 token / 正确 token)的鉴权行为。
"""
import pytest


@pytest.mark.integration
def test_register_and_login_flow(client):
    """验证「注册→重复注册拒绝→错误密码拒绝→登录拿 token」的完整认证链路。

    验证点:注册成功返回 success；重复用户名返回 400；错误密码返回 401；
            正确登录返回 200 且携带 token，首个用户角色为 super_admin。
    边界/异常:重复注册、错误密码等失败路径的 HTTP 状态码。
    """
    # 1) 注册成功
    r = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "alice_pass_123"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("success") is True

    # 2) 重复注册被拒
    r2 = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "alice_pass_123"},
    )
    assert r2.status_code == 400

    # 3) 错误密码登录被拒
    r3 = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert r3.status_code == 401

    # 4) 正确登录拿到 token
    r4 = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "alice_pass_123"},
    )
    assert r4.status_code == 200
    body = r4.json()
    assert body["success"] is True
    assert body["token"]
    assert body["user"]["username"] == "alice"
    # 默认首个用户应为超级管理员(项目逻辑)
    assert body["user"]["role"] == "super_admin"


@pytest.mark.integration
def test_me_endpoint_auth(client):
    """验证 /api/auth/me 接口对鉴权头的处理(无 token / 错误 token / 正确 token)。

    验证点:无 Authorization 头 → 422(Header 必填)；错误 JWT → 401；
            正确 token → 200 且返回当前登录用户名。
    边界/异常:非法/缺失凭证时的拒绝行为。
    """
    # 先登录拿 token
    client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "bob_pass_123"},
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": "bob_pass_123"},
    )
    token = login.json()["token"]

    # 无 Authorization 头 → 422(Header 必填)
    r_no_header = client.get("/api/auth/me")
    assert r_no_header.status_code == 422

    # 错误 token → 401
    r_bad = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.real.jwt"}
    )
    assert r_bad.status_code == 401

    # 正确 token → 200 且返回当前用户
    r_ok = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["username"] == "bob"


@pytest.mark.integration
def test_protected_endpoint_requires_valid_jwt(client):
    """验证受保护接口(聊天)在无有效 JWT 时拒绝访问。

    验证点:未带 token 访问 /api/chat，因 require_user 依赖 Header 必填，
            返回 401 或 422，绝不会是 200。
    边界/异常:缺少鉴权凭证的拒绝路径。
    """
    # 未带 token 访问受保护接口(聊天)
    r = client.post("/api/chat", json={"message": "hi", "stream": False})
    # require_user 依赖 Header，缺失 → 422；非 200
    assert r.status_code in (401, 422)
    assert r.status_code != 200
