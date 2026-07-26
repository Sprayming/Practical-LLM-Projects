FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

COPY requirements-docker.txt requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p memory_db model_cache data tenant_data uploads chroma_db

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000