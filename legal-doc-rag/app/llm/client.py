"""
client.py —— 集中式 LLM 客户端(支持主/备用供应商故障转移)

【作用与功能】
把 chat.py 里散落的 LLM 调用收敛到一个客户端,统一处理「主供应商 -> 备用供应商」
的故障转移:当主供应商返回限流(429)或服务端抖动(5xx)时,自动按
LLM_FALLBACK_PROVIDERS 配置的顺序尝试下一个可用供应商;鉴权等硬错误(401/403)
不再重试,直接抛出由上层转成友好提示。

解决的问题:
- 高并发下 DeepSeek 等单一供应商被限流(429)会导致整条问答链路雪崩;
  故障转移让系统在某个供应商不可用时仍能对外服务(保命/弹性)。
- 调用点收敛后,所有 LLM 调用(流式生成、非流式生成、记忆总结)共享同一套
  容错逻辑,不再各写一遍重试。

容错边界:
- 仅对「可重试」错误(429/5xx/连接失败)切换供应商;4xx 鉴权错误视为硬错误。
- 所有供应商都失败则抛出 LLMAllFailed,由上层转成「服务繁忙」提示而非卡死。

【主要组成】
- `LLMHardError` / `LLMAllFailed`:故障转移过程中的异常类型
- `stream_chat`:打开流式连接(逐供应商尝试,首个 200 即返回)
- `complete_chat`:非流式一次性返回全文(逐供应商尝试)

【依赖关系】
- 上游调用方:app.api.chat(流式生成、非流式生成、记忆总结)
- 下游依赖:app.core.config(多供应商解析)、httpx、loguru
"""

import httpx
from loguru import logger

from app.core import config as cfg


class LLMHardError(Exception):
    """供应商返回鉴权等硬错误(4xx,非限流),不再重试。"""

    def __init__(self, provider: str, status: int, body: str):
        self.provider = provider
        self.status = status
        self.body = body
        super().__init__(f"LLM 供应商 {provider} 硬错误 HTTP {status}")


class LLMAllFailed(Exception):
    """所有供应商均不可用。"""


def _provider_chain() -> list:
    """返回本次请求要尝试的供应商顺序:主供应商 + 去重的备用供应商。"""
    chain = [cfg.LLM_PROVIDER]
    for p in cfg.LLM_FALLBACK_PROVIDERS:
        if p != cfg.LLM_PROVIDER:
            chain.append(p)
    return chain


def _headers(prov: dict) -> dict:
    return {
        "Authorization": f"Bearer {prov['api_key']}",
        "Content-Type": "application/json",
    }


# 视为「可重试、应切换供应商」的状态码
_RETRYABLE = (429, 500, 502, 503, 504)


async def stream_chat(messages: list, temperature: float = 0.1, max_tokens: int = 1024):
    """
    打开流式 chat/completions 连接,逐供应商尝试,返回首个成功的 (client, resp, provider)。

    调用方负责在流读取结束后 `await client.aclose()`。任一供应商返回非 200 时:
    - 429/5xx -> 关闭连接,尝试下一个供应商;
    - 401/403 等硬错误 -> 抛出 LLMHardError(不再重试)。
    所有供应商都失败 -> 抛出 LLMAllFailed。

    返回:
        tuple: (httpx.AsyncClient, httpx.Response[status=200], provider_name)
    """
    for name in _provider_chain():
        prov = cfg.resolve_provider(name)
        if not prov["api_key"]:
            logger.warning("LLM 供应商 {} 未配置 API Key,跳过", name)
            continue
        client = httpx.AsyncClient(timeout=60, verify=True)
        try:
            resp = await client.post(
                f"{prov['base_url']}/chat/completions",
                headers=_headers(prov),
                json={
                    "model": prov["model"],
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
        except httpx.RequestError as e:
            await client.aclose()
            logger.warning("LLM 供应商 {} 连接失败,故障转移: {}", name, e)
            continue

        if resp.status_code == 200:
            return client, resp, name

        # 非 200:读取错误体后关闭,按状态码决定是否重试
        raw = (await resp.aread()).decode("utf-8", "replace")
        await client.aclose()
        if resp.status_code in _RETRYABLE:
            logger.warning("LLM 供应商 {} 返回 {},故障转移", name, resp.status_code)
            continue
        raise LLMHardError(name, resp.status_code, raw)

    raise LLMAllFailed()


async def complete_chat(messages: list, temperature: float = 0.1, max_tokens: int = 512) -> str:
    """
    非流式 chat/completions,逐供应商尝试,返回首个成功的完整文本。

    返回:
        str: 模型生成的文本;所有供应商失败则抛出 LLMHardError / LLMAllFailed。
    """
    for name in _provider_chain():
        prov = cfg.resolve_provider(name)
        if not prov["api_key"]:
            logger.warning("LLM 供应商 {} 未配置 API Key,跳过", name)
            continue
        try:
            async with httpx.AsyncClient(timeout=30, verify=True) as client:
                r = await client.post(
                    f"{prov['base_url']}/chat/completions",
                    headers=_headers(prov),
                    json={
                        "model": prov["model"],
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
        except httpx.RequestError as e:
            logger.warning("LLM 供应商 {} 连接失败,故障转移: {}", name, e)
            continue

        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]

        if r.status_code in _RETRYABLE:
            logger.warning("LLM 供应商 {} 返回 {},故障转移", name, r.status_code)
            continue
        raise LLMHardError(name, r.status_code, r.text)

    raise LLMAllFailed()
