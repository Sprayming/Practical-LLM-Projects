"""
limiter.py —— 集中管理的全局请求限流器，供各 API 路由共享(配合 slowapi)

【作用与功能】
该模块在 legal-doc-rag 系统中充当统一的速率控制层:创建全局 Limiter 实例，
基于客户端 IP 地址作为限流键值(key_func)对请求计数，防止恶意请求、
暴力破解与 DoS 攻击。它依赖于 slowapi，并在超出额度时返回 429 响应。

【主要组成】
- `limiter`:基于远程 IP 的全局 Limiter 单例，供各路由装饰器引用

【适用场景】
- 场景1:在 main.py 中注册该 limiter 实例到 FastAPI 应用
- 场景2:API 路由通过 @limiter.limit("N/时间单位") 施加具体限流规则(如 "100/minute")

【依赖关系】
- 上游调用方:FastAPI 应用入口(main.py)及各 API 路由装饰器
- 下游依赖:slowapi.Limiter、slowapi.util.get_remote_address
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# 创建全局限流器实例，使用客户端的远程 IP 地址作为限流键值
# 这样可以确保每个 IP 地址的请求都受到独立的速率限制
limiter = Limiter(key_func=get_remote_address)
