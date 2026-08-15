FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

# 先拷贝 Docker 专用依赖清单并安装，利用分层缓存加速构建
COPY requirements-docker.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p memory_db model_cache data tenant_data uploads chroma_db

EXPOSE 8000

# 健康检查端点为 /health（非 /api/health）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health'); exit(0)"

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000