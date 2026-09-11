FROM python:3.12-slim

# 默认写 /app（可写）；付费档可在环境变量改为 DATA_DIR=/data 持久化
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app PORT=8000 PROVIDER=fal

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./
COPY engine/ ./engine/
COPY frontend/ ./frontend/
COPY liveportrait_worker.py ./ 2>/dev/null || true

EXPOSE 8000
CMD ["python", "server.py"]
