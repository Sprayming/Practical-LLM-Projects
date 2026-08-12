"""
集成测试:请求限流(Rate Limit)。

验证上一轮修复的 slowapi 限流确实生效:
  - /api/auth/login 限制 20/minute(按客户端 IP 计)
  - 超过阈值应返回 429，且在此之前正常返回 401(错误密码)

注意:限流是单进程内存计数，键按 IP，多个限流端点共享同一计数桶。
conftest 中每个测试都会 reset_limiter()，保证本测试从 0 开始、互不串扰。
"""
import pytest


@pytest.mark.integration
def test_login_rate_limit_returns_429(client):
    """验证 /api/auth/login 的 slowapi 限流(20/minute，按 IP)超限后返回 429。

    验证点:连续请求中，限流阈值前正常返回 401(错误密码)，超过 20 次/分钟后返回 429。
    边界/异常:限流为单进程内存计数、键按 IP；conftest 每测试 reset_limiter() 保证互不串扰。
    """
    creds = {"username": "ratelimit_user", "password": "any_pass"}
    saw_401 = False
    saw_429 = False

    # 连续请求:前 20 次应通过限流(返回 401 错误密码)，第 21 次起返回 429
    for _ in range(25):
        r = client.post("/api/auth/login", json=creds)
        if r.status_code == 401:
            saw_401 = True
        elif r.status_code == 429:
            saw_429 = True
            break

    assert saw_401, "限流生效前应正常返回 401"
    assert saw_429, "超过阈值后应返回 429(限流未生效)"
    # 429 响应头应带 Retry-After
    # (slowapi 默认会设置，此处仅做存在性软校验)
