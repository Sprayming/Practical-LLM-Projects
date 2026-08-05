"""集中管理的请求限流器，供各 API 路由共享（配合 slowapi）。"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
