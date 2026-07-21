FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 预下载嵌入模型（避免首次启动时下载）
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('shibing624/text2vec-base-chinese')" 2>/dev/null || true

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