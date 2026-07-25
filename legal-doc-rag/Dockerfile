FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements-docker.txt requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建运行时目录
RUN mkdir -p memory_db model_cache data

# Streamlit 端口
EXPOSE 8501

# 启动命令
CMD streamlit run app/streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.enableXsrfProtection=false