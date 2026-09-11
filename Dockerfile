FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/app PORT=8000 PROVIDER=fal   # 默认写到应用目录(/app可写)，付费档可在环境变量改 /data

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 显式拷贝核心代码目录，避免漏传子目录导致启动失败
COPY server.py ./
COPY engine/ ./engine/
COPY frontend/ ./frontend/
COPY liveportrait_worker.py ./ 2>/dev/null || true

EXPOSE 8000
CMD ["python", "server.py"]
