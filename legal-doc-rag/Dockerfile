FROM python:3.12-slim

WORKDIR /app

# 绯荤粺渚濊禆
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

# 瀹夎 Python 渚濊禆锛堝埄鐢?Docker 缂撳瓨灞傦級
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 棰勪笅杞藉祵鍏ユā鍨嬶紙閬垮厤棣栨鍚姩鏃朵笅杞斤級
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('shibing624/text2vec-base-chinese')" 2>/dev/null || true

# 澶嶅埗搴旂敤浠ｇ爜
COPY . .

# 鍒涘缓杩愯鏃剁洰褰?RUN mkdir -p memory_db model_cache data

# Streamlit 绔彛
EXPOSE 8501

# 鍚姩鍛戒护
CMD streamlit run app/streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.enableXsrfProtection=false
