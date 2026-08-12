"""
healthcheck.py —— Streamlit 应用健康探针脚本

【作用与功能】
通过 HTTP 请求探测本地 Streamlit 服务(默认端口 8501)的健康检查端点，
将服务存活状态映射为当前进程的退出码，供容器编排或监控组件判断服务是否就绪。

【主要组成】
- 顶层逻辑:向 `http://localhost:8501/_stcore/health` 发起 GET 请求，
  返回状态码 200 视为健康(退出码 0)，其余或异常视为不健康(退出码 1)。

【适用场景】
- 场景1:作为 Docker HEALTHCHECK 命令，例如 `python healthcheck.py`
- 场景2:编排系统(k8s / docker-compose)周期性探测服务可用性

【依赖关系】
- 依赖本地已启动的 Streamlit 服务(默认 8501 端口)
- 仅使用标准库 urllib / sys，无第三方依赖
"""
import urllib.request
import sys

try:
    # 请求 Streamlit 内置健康检查端点，超时设为 5 秒避免探测挂死
    r = urllib.request.urlopen("http://localhost:8501/_stcore/health", timeout=5)
    # 健康检查端点返回 200 表示服务就绪，退出码 0；否则视为异常，退出码 1
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    # 任何连接/超时/非 200 异常都统一判定为不健康，退出码 1
    sys.exit(1)