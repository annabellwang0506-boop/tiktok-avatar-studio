# -*- coding: utf-8 -*-
"""LivePortrait 本地推理 worker（部署在 GPU 机器上）。
与本项目 engine/providers.py 的 liveportrait 适配器配套:
  GET  /health           健康检查
  POST /audio            上传 TTS 音频 -> 返回可访问 URL
  POST /generate         照片+文本/音频 -> 排队
  GET  /status/{task}    轮询结果
安装: git clone https://github.com/KlingAIResearch/LivePortrait
      cd LivePortrait && pip install -r requirements.txt && 下载权重
替换下方 generate_with_liveportrait() 为官方推理调用即可。
运行: python3 liveportrait_worker.py --port 8765
"""
import os, uuid, shutil, subprocess, threading, time
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from typing import Optional

BASE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(BASE, "worker_media")
os.makedirs(MEDIA, exist_ok=True)
MASTER_DIR = "LivePortrait"   # 官方仓库目录（如与 worker 同级）

app = FastAPI(title="LivePortrait Worker")
TASKS = {}   # task_id -> {"status","video_url","error"}


class GenReq(BaseModel):
    photo_url: str
    text: Optional[str] = None
    audio_url: Optional[str] = None
    voice_id: Optional[str] = None
    job_id: Optional[str] = None


def generate_with_liveportrait(photo_path, audio_path, out_path):
    """TODO: 接入官方推理
    参考 KlingAIResearch/LivePortrait: 初始化 Inference 后
    inference.run(...) 生成口型同步视频。
    """
    raise NotImplementedError("请按 LivePortrait 官方推理替换此函数。示例: "
                              "{MASTER_DIR}/inference.py" .format(MASTER_DIR=MASTER_DIR))


def _fetch(url, dest):
    import requests
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            f.write(chunk)


@app.get("/health")
def health():
    return {"ok": True, "service": "liveportrait-worker"}


@app.post("/audio")
async def upload_audio(file: UploadFile = File(...)):
    name = f"voice_{uuid.uuid4().hex[:8]}.wav"
    dest = os.path.join(MEDIA, name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/media/{name}"}


@app.post("/generate")
def generate(req: GenReq):
    if not req.photo_url:
        return {"error": "photo_url 必填"}
    task = uuid.uuid4().hex[:10]
    TASKS[task] = {"status": "queued"}
    threading.Thread(target=_run, args=(task, req), daemon=True).start()
    return {"status": "queued", "task_id": task}


def _run(task, req):
    TASKS[task] = {"status": "processing"}
    try:
        photo = os.path.join(MEDIA, f"src_{task}.jpg")
        _fetch(req.photo_url, photo)
        audio = None
        if req.audio_url:
            audio = os.path.join(MEDIA, f"aud_{task}.wav")
            _fetch(req.audio_url, audio)
        out = os.path.join(MEDIA, f"out_{task}.mp4")
        generate_with_liveportrait(photo, audio, out)
        TASKS[task] = {"status": "done", "video_url": f"/media/out_{task}.mp4"}
    except Exception as e:
        TASKS[task] = {"status": "error", "error": str(e)[:300]}


@app.get("/status/{task}")
def status(task: str):
    return TASKS.get(task, {"status": "unknown"})


if __name__ == "__main__":
    import argparse, uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=a.port)
