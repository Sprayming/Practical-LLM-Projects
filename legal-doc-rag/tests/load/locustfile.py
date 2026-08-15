"""
locustfile.py —— legal-doc-rag 高并发压测脚本

【用途】
    模拟多用户「登录 → 连续向 /api/chat 提问」，实测高并发下的延迟与吞吐，
    用于量化验证「高并发升级」（解阻塞事件循环 + 语义缓存 + 多供应商 fallback）的收益。
    升级前（旧版本）与升级后（当前版本）用同一脚本跑一遍，对比 P95/P99/RPS 即可。

【用法】
    # 1. 安装压测依赖（见 仓库根 requirements-dev.txt）
    #    pip install -r requirements-dev.txt
    # 2. 准备一个测试账号（默认 admin / 你设置的密码）
    # 3. 启动压测：
    #    -H        被测服务地址
    #    --users   并发虚拟用户数
    #    --spawn-rate  每秒拉起多少用户
    #    --run-time    压测时长
    #    --username / --password  测试账号
    locust -f tests/load/locustfile.py \
        -H http://127.0.0.1:8000 \
        --users 50 --spawn-rate 5 --run-time 5m \
        --username admin --password 'yourpass'

【指标含义】
    - chat_stream          : SSE 流式问答的「完整回答延迟」（从发请求到流结束）
    - chat_stream_ttfb     : SSE 首个 token 延迟（首字延迟，前端体验最关键指标）
    - chat_nonstream       : 非流式问答的「完整回答延迟」（含检索+RAG+LLM 全流程）
"""
import time
import random

from locust import HttpUser, task, between, events

# 模拟真实法律问答的问题库（覆盖不同主题与长度，触发 RAG 检索 + LLM 生成）
QUESTIONS = [
    "劳动合同到期不续签，公司需要给经济补偿吗？",
    "如何解除劳动合同？需要提前多久通知？",
    "试用期最长可以约定几个月？",
    "工伤认定的条件和流程是什么？",
    "公司拖欠工资，劳动者可以怎么维权？",
    "竞业限制协议的有效期和最长期限是多少？",
    "社保断缴会有什么影响？如何补缴？",
    "加班费的计算标准是什么？",
]


class LegalRAGUser(HttpUser):
    """模拟一个已登录用户的问答行为。"""

    # 每轮提问间隔 1~3 秒，贴近真实用户节奏
    wait_time = between(1, 3)

    def on_start(self):
        """虚拟用户线程启动时先登录，拿到后续请求用的 JWT Token。"""
        username = self.environment.parsed_options.username
        password = self.environment.parsed_options.password
        with self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            name="login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200 and resp.json().get("token"):
                self.token = resp.json()["token"]
            else:
                # 登录失败则停止该虚拟用户，避免无效压测污染数据
                resp.failure(f"login failed: HTTP {resp.status_code}")
                self.token = None

    def _auth_headers(self):
        """构造带 JWT 的鉴权头。"""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(3)
    def chat_stream(self):
        """流式问答（前端默认行为）：测完整回答延迟 + 首 token 延迟。"""
        if not self.token:
            return
        q = random.choice(QUESTIONS)
        start = time.time()
        first_token_ts = None
        with self.client.post(
            "/api/chat",
            json={"message": q, "history": [], "stream": True},
            headers=self._auth_headers(),
            stream=True,
            name="chat_stream",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            # 逐行读取 SSE，记录首个有效 token 的时间（首字延迟）
            for line in resp.iter_lines():
                if not line:
                    continue
                if first_token_ts is None:
                    first_token_ts = time.time()
                    # 额外上报「首 token 延迟」这一关键体验指标（毫秒）
                    events.request.fire(
                        request_type="SSE-TTFB",
                        name="chat_stream_ttfb",
                        response_time=(first_token_ts - start) * 1000,
                        response_length=0,
                        exception=None,
                        context={},
                    )
                # 读完所有 token 即结束；总耗时由 locust 自动记录到 chat_stream
        if first_token_ts is None:
            resp.failure("stream ended without any token")

    @task(1)
    def chat_nonstream(self):
        """非流式问答：测完整回答延迟（一次性拿到全文）。"""
        if not self.token:
            return
        q = random.choice(QUESTIONS)
        with self.client.post(
            "/api/chat",
            json={"message": q, "history": [], "stream": False},
            headers=self._auth_headers(),
            name="chat_nonstream",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            try:
                body = resp.json()
                if not body.get("answer"):
                    resp.failure("empty answer")
            except ValueError:
                resp.failure("invalid json")


# 注册命令行参数：压测用的测试账号
@events.init_command_line_parser.add_listener
def _add_args(parser):
    parser.add_argument(
        "--username", type=str, default="admin",
        help="压测用的测试账号用户名（默认 admin）",
    )
    parser.add_argument(
        "--password", type=str, default="",
        help="压测用的测试账号密码",
    )
