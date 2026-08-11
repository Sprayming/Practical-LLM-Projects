"""
集中管理的请求限流器，供各 API 路由共享（配合 slowapi）。

该模块创建了一个全局的 Limiter 实例，使用客户端的 IP 地址作为限流键值（key_func），
对来自同一 IP 的请求进行统一的速率限制。主要用于防止恶意请求、暴力破解和 DoS 攻击。

使用方法：
1. 在 FastAPI 应用中注册此 limiter 实例（见 main.py）
2. 在 API 路由装饰器中使用 @limiter.limit("N/时间单位") 指定具体的限流规则
   例如：@limiter.limit("100/minute") 表示每分钟最多允许 100 次请求

限流策略：
- 基于 IP 地址进行识别和计数
- 支持灵活的时间窗口（如 "100/minute"、"10/second"、"5/hour"）
- 超出限制时自动返回 429 Too Many Requests 响应
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# 创建全局限流器实例，使用客户端的远程 IP 地址作为限流键值
# 这样可以确保每个 IP 地址的请求都受到独立的速率限制
limiter = Limiter(key_func=get_remote_address)
