# -*- coding: utf-8 -*-
"""数字人视频提供商适配层 + TTS + 模拟模式。

真实模式支持:
  - HeyGen（推荐，北美英语效果最好；官方 2026 按量计费）
  - D-ID
  - Synthesia
TTS:
  - HeyGen TTS (v2 API)
  - ElevenLabs
模拟模式 (mock): 本机 ffmpeg 生成 1080x1920 竖版标题卡视频, 无 API 成本,
用于跑通全流程演示。
"""
import json, os, subprocess, time, requests

GENERATED_DIR = os.path.join(os.environ.get("DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "generated")

# ---- 提供商价目（美元/分钟, 来源见 README）-----------------------
# HeyGen 官方 2026 价目（help.heygen.com API pricing）：
HEYGEN_RATES = {
    "photo_avatar":       {"v_iii": 1.00, "v_iv": 3.00},
    "digital_twin":       {"v_iii": 1.00, "v_iv": 4.00},
    "studio_avatar":      {"v_iii": 1.00, "v_iv": 4.00},
}
HEYGEN_TTS_RATE = 0.04          # $0.04 / 分钟 (Speech Starfish)
HEYGEN_CONCURRENCY = 10         # API 允许 10 个并发任务（官方）

# 以下为参考价（以官方价格页为准）
DID_RATES = {"per_minute": 0.99}
SYNTHESIA_RATES = {"per_minute": 0.30}


class ProviderError(Exception):
    pass


def estimate_cost(provider, avatar_kind, seconds, engine="v_iii"):
    """按分钟折算估算成本（美元）。"""
    minutes = max(seconds, 60) / 60.0
    if provider == "heygen":
        rate = HEYGEN_RATES.get(avatar_kind, HEYGEN_RATES["photo_avatar"]).get(engine, 1.0)
        return round(minutes * rate + minutes * HEYGEN_TTS_RATE, 3)
    if provider == "did":
        return round(minutes * DID_RATES["per_minute"] + minutes * 0.15, 3)
    if provider == "synthesia":
        return round(minutes * SYNTHESIA_RATES["per_minute"] + minutes * 0.15, 3)
    return 0.0


# ---------------- 文件工具 ----------------
def _safe_name(s, maxlen=60):
    s = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in s).strip("_")
    return (s or "vid")[:maxlen]


def download(url, dest):
    r = requests.get(url, timeout=300, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return dest


# ---------------- TTS ----------------
def tts_heygen(text, voice_id, api_key, out_path):
    r = requests.post(
        "https://api.heygen.com/v2/tts",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json={"text": text, "voice_id": voice_id},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()["data"]
    url = data.get("audio_url") or data.get("url")
    download(url, out_path)
    return out_path


def tts_elevenlabs(text, voice_id, api_key, out_path):
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=180,
    )
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path


# ---------------- 数字人视频提供商 ----------------
def heygen_generate(avip, script_text, voice_id, api_key, job_id):
    """POST /v2/video/generate -> 轮询 -> 下载成片。返回本地 mp4 路径。"""
    avatar_id = avip.get("avatar_id") or os.environ.get("HEYGEN_AVATAR_ID")
    if not avatar_id:
        raise ProviderError("未配置 HeyGen avatar_id（虚拟 IP 形象），请在设置或环境变量 HEYGEN_AVATAR_ID 配置")
    r = requests.post(
        "https://api.heygen.com/v2/video/generate",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json={
            "video_inputs": [{
                "character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
                "voice": {"type": "text", "input_text": script_text,
                          "voice_id": voice_id or avip.get("voice_id")},
                "title": avip.get("name", "tiktok") + " - " + job_id,
                "background": avip.get("background", {"type": "color", "value": "#101223"}),
            }],
        },
        timeout=120,
    )
    r.raise_for_status()
    video_id = r.json()["data"]["video_id"]
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        time.sleep(6)
        s = requests.get(f"https://api.heygen.com/v2/video/{video_id}",
                         headers={"X-Api-Key": api_key}, timeout=60)
        s.raise_for_status()
        d = s.json().get("data", {})
        status = d.get("status")
        if status in ("completed", "success"):
            break
        if status in ("failed", "error"):
            raise ProviderError(f"HeyGen 生成失败: {d.get('error') or status}")
    else:
        raise ProviderError("HeyGen 生成超时(15min)")
    url = d.get("video_url")
    out = os.path.join(GENERATED_DIR, f"job_{job_id}_raw.mp4")
    download(url, out)
    return out


def did_generate(avip, script_text, voice_id, api_key, job_id):
    """D-ID talks API（需 digital twin 图片 URL）。"""
    avatar_url = avip.get("avatar_url")
    if not avatar_url:
        raise ProviderError("D-ID 需要 avatar_url（形象图片 URL）")
    r = requests.post(
        "https://api.d-id.com/talks",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"source_url": avatar_url,
              "script": {"type": "text", "input": script_text,
                         "provider": {"type": "microsoft", "voice_id": voice_id or "en-US-JennyNeural"}},
              "config": {"fluent": True, "result_format": "mp4"}},
        timeout=120,
    )
    r.raise_for_status()
    talk_id = r.json()["id"]
    deadline = time.time() + 10 * 60
    while time.time() < deadline:
        time.sleep(5)
        s = requests.get(f"https://api.d-id.com/talks/{talk_id}",
                         headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        s.raise_for_status()
        j = s.json()
        if j.get("status") == "done":
            break
        if j.get("status") == "error":
            raise ProviderError(f"D-ID 生成失败: {j.get('result', {}).get('message')}")
    else:
        raise ProviderError("D-ID 生成超时")
    out = os.path.join(GENERATED_DIR, f"job_{job_id}_raw.mp4")
    download(j["result_url"], out)
    return out


def synthesia_generate(avip, script_text, voice_id, api_key, job_id):
    """Synthesia v2 API。"""
    avatar_id = avip.get("avatar_id") or os.environ.get("SYNTHESIA_AVATAR_ID")
    if not avatar_id:
        raise ProviderError("Synthesia 需要 avatar_id")
    r = requests.post(
        "https://api.synthesia.io/v2/videos",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json={"test": True,
              "video": {"avatar": {"avatar_id": avatar_id, "avatar_style": "round"},
                        "script": script_text,
                        "background": {"type": "solid", "colour": "#101223"},
                        "audio": {"voice_id": voice_id or "7c5f90c6-e4dc-4f39-a746-453132c78f8e"}}},
        timeout=120,
    )
    r.raise_for_status()
    video_id = r.json()["id"]
    deadline = time.time() + 10 * 60
    while time.time() < deadline:
        time.sleep(5)
        s = requests.get(f"https://api.synthesia.io/v2/videos/{video_id}",
                         headers={"Authorization": api_key}, timeout=60)
        s.raise_for_status()
        j = s.json()
        if j.get("status") == "complete":
            break
        if j.get("status") == "error":
            raise ProviderError(f"Synthesia 生成失败")
    else:
        raise ProviderError("Synthesia 生成超时")
    out = os.path.join(GENERATED_DIR, f"job_{job_id}_raw.mp4")
    download(j["download_url"], out)
    return out


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _wrap(text, width_chars=26):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def mock_generate(avip, script_text, voice_id, job_id, audio_path=None, hook=None, topic=None):
    """模拟模式：ffmpeg 输出 1080x1920 竖版短视频（标题卡 + 逐行字幕 + 进度条）。
    无外部 API 成本，演示全流程。若提供 audio_path 则合成真人配音。
    """
    import math
    os.makedirs(GENERATED_DIR, exist_ok=True)
    duration = max(16, min(26, math.ceil(len(script_text.split()) / 2.4)))
    out = os.path.join(GENERATED_DIR, f"job_{job_id}.mp4")
    hook_lines = _wrap((hook or "Stop scrolling.").upper(), 14)[:3]
    sub_lines = _wrap(script_text, 24)[:6]
    niche = avip.get("niche", "content")

    hook_txt = "\\n".join(hook_lines).replace("'", "\u2019")
    subs = "\\n".join(sub_lines).replace("'", "\u2019")

    vf = (
        f"drawtext=fontfile={FONT}:text='{hook_txt}':x=(w-text_w)/2:y=h*0.16:fontsize=84:fontcolor=white:"
        f"box=1:boxcolor=0x000000@0.55:boxborderw=36,"
        f"drawtext=fontfile={FONT_REG}:text='{subs}':x=(w-text_w)/2:y=h*0.66:fontsize=52:fontcolor=white:"
        f"line_spacing=14:box=1:boxcolor=0x000000@0.45:boxborderw=22,"
        f"drawtext=fontfile={FONT}:text='@{avip.get('tiktok_handle', 'yourhandle')}':"
        f"x=(w-text_w)/2:y=h*0.90:fontsize=56:fontcolor=0x00FFB2,"
        f"drawtext=fontfile={FONT_REG}:text='{niche.upper()}  •  follow for more':"
        f"x=(w-text_w)/2:y=h*0.955:fontsize=32:fontcolor=white@0.85"
    )

    cmd = ["ffmpeg", "-y",
           "-f", "lavfi", "-i",
           f"gradients=s=1080x1920:d={duration}:c0=0x0F0F1E:c1=0x201B3D:c2=0x0A3A56:x0=200:y0=0:x1=880:y1=1920",
           "-vf", vf,
           "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-r", "30", out]
    if audio_path and os.path.exists(audio_path):
        cmd += ["-i", audio_path, "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-an"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise ProviderError(f"模拟模式 ffmpeg 失败: {p.stderr[-400:]}")
    return out


def generate_real(provider, avip, script_text, voice_id, api_key, job_id):
    if provider == "heygen":
        return heygen_generate(avip, script_text, voice_id, api_key, job_id)
    if provider == "did":
        return did_generate(avip, script_text, voice_id, api_key, job_id)
    if provider == "synthesia":
        return synthesia_generate(avip, script_text, voice_id, api_key, job_id)
    raise ProviderError(f"不支持的提供商: {provider}")


# ================= LivePortrait 本地开源引擎适配器 =================
# 照片 → 数字人口播：LivePortrait V2 (KlingAIResearch) + 本地 TTS/音频文件
# 推理在 GPU 机器上跑 (整个仓库 clone + weights ~2-6GB)，订阅 worker URL 后
# 此适配器通过 HTTP 把照片+音频送到推理服务，拿回成片。

LOCAL_PORT = int(os.environ.get("LIVEPORTRAIT_PORT", "8765"))


def _is_local_running(url=None, timeout=4):
    """快速健康检查：worker 是否已启动。"""
    base = (url or os.environ.get("LIVEPORTRAIT_URL", "")).rstrip("/")
    if not base or "://" not in base:
        base = f"http://127.0.0.1:{LOCAL_PORT}"
    try:
        r = requests.get(base + "/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _verify_photo(photo_url):
    """校验照片 URL 可访问且为图片。"""
    if not photo_url:
        raise ProviderError("本地引擎需要虚拟 IP 的照片 URL（avatar_url），请上传照片")
    try:
        r = requests.get(photo_url, timeout=25, stream=True)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "")
        if not ct.startswith("image/"):
            raise ProviderError(f"照片 URL 不是图片: {ct}")
        return photo_url
    except Exception as e:
        raise ProviderError(f"照片无法访问: {str(e)[:120]}")


def _post_audio(audio_text_or_path, worker_base):
    """POST /audio 上传 TTS 音频文件，返回带鉴权的音频 URL（引擎自动签名）。"""
    if _is_remote(worker_base) or True:
        # 支持两种：本地 worker 直接读文件；远程 worker 用签名 URL
        if os.path.exists(audio_text_or_path):
            with open(audio_text_or_path, "rb") as f:
                r = requests.post(worker_base.rstrip("/") + "/audio",
                                  files={"file": ("voice.wav", f, "audio/wav")},
                                  timeout=120)
            r.raise_for_status()
            return r.json().get("url") or r.json().get("audio_url")
    raise ProviderError("音频上传失败")


def _is_remote(u):
    return u.startswith("http://") or u.startswith("https://")


def liveportrait_generate(avip, script_text, voice_id, job_id, audio_path=None):
    """照片 + 音频 → LivePortrait 数字人口播视频（or 引擎在本地/远程 worker）。

    优先级:
      audio_path 已生成(真实 TTS) → 上传给引擎
      否则引擎侧自己 TTS（需要引擎支持 text 输入）
    """
    worker = os.environ.get("LIVEPORTRAIT_URL", f"http://127.0.0.1:{LOCAL_PORT}")
    worker = worker.rstrip("/")
    if not _is_local_running(worker):
        raise ProviderError(
            "LivePortrait 引擎未运行。启动方式见 README「本地开源引擎」；或在 settings/环境变量配置 LIVEPORTRAIT_URL")

    photo = _verify_photo(avip.get("avatar_url") or "")
    payload = {"photo_url": photo, "job_id": job_id,
               "voice_id": voice_id or "", "script": script_text}
    if audio_path and os.path.exists(audio_path):
        payload["audio_url"] = _post_audio(audio_path, worker)
    else:
        payload["text"] = script_text  # 引擎侧 TTS 兜底

    try:
        r = requests.post(worker.rstrip("/") + "/generate", json=payload, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise ProviderError(f"LivePortrait worker 调用失败: {str(e)[:150]}")

    out = os.path.join(GENERATED_DIR, f"job_{job_id}_lp.mp4")
    # 引擎可能返回"已提交任务"，此处等待完成（demo worker 返回文件）
    data = r.json()
    if data.get("video_url"):
        download(data["video_url"], out)
    elif data.get("status") == "queued":
        vid = data.get("task_id")
        for _ in range(60):
            time.sleep(3)
            try:
                s = requests.get(worker.rstrip("/") + f"/status/{vid}", timeout=30)
                d = s.json()
                if d.get("status") == "done" and d.get("video_url"):
                    download(d["video_url"], out)
                    break
                if d.get("status") == "error":
                    raise ProviderError(f"LivePortrait 生成失败: {d.get('error')}")
            except ProviderError:
                raise
            except Exception:
                pass
        else:
            raise ProviderError("LivePortrait 生成超时(3min)")
    else:
        raise ProviderError("LivePortrait worker 返回异常")
    return out


def local_open_generate(avip, script_text, voice_id, job_id, audio_path=None):
    """统一入口（provider='local_open'）。"""
    return liveportrait_generate(avip, script_text, voice_id, job_id, audio_path)

# ================= fal.ai 托管系列（不碰部署，官方 serverless 推理）=================
# 推荐端点（官方文档已知）:
#   fal-ai/sadtalker      照片+音频 -> 口播视频 (输入 source_image_url / driven_audio_url)
#   fal-ai/live-portrait  LivePortrait 托管变体（参数同）
# 鉴权: Authorization: Key <FAL_API_KEY> （形如 "key:secret"）
# 计费: 按模型输出计费，具体以 fal 控制台为准（见 README），无订阅、随用随付。

STUDIO_ROOT = os.path.dirname(GENERATED_DIR)
DEFAULT_FAL_MODEL = os.environ.get("FAL_MODEL", "fal-ai/sadtalker")


def _to_fal_url(value):
    """fal 输入 url 字段兼容：公网 URL 直接用；本地文件/相对路径转 base64 data URI。"""
    import base64, mimetypes
    value = (value or "").strip()
    if not value:
        raise ProviderError("fal.ai 需要照片 URL 或本地文件路径")
    if value.startswith("data:") or value.startswith("http://") or value.startswith("https://"):
        return value
    if os.path.isabs(value):
        p = value
    else:
        p = os.path.join(STUDIO_ROOT, value.lstrip("/")) if value.startswith("/") else value
    if not os.path.exists(p):
        raise ProviderError(f"fal.ai 找不到本地文件: {p}")
    mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
    b64 = base64.b64encode(open(p, "rb").read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _fal_queue_submit(model, inputs, fal_key, timeout=60):
    r = requests.post(f"https://queue.fal.run/{model}",
                      headers={"Authorization": f"Key {fal_key}",
                               "Content-Type": "application/json"},
                      json=inputs, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _fal_poll_response(fal_key, status_url, timeout_s=900):
    import time as _t
    start = _t.time()
    while _t.time() - start < timeout_s:
        _t.sleep(4)
        s = requests.get(status_url, headers={"Authorization": f"Key {fal_key}"}, timeout=60)
        s.raise_for_status()
        st = s.json()
        status = (st.get("status") or "").upper()
        if status in ("COMPLETED", "OK"):
            resp = requests.get(st.get("response_url") or st.get("responsePayloadUrl"),
                                headers={"Authorization": f"Key {fal_key}"}, timeout=60)
            resp.raise_for_status()
            return resp.json()
        if status in ("FAILED", "ERROR"):
            raise ProviderError(f"fal.ai 生成失败: {str(st)[:260]}")
    raise ProviderError("fal.ai 生成超时")


def _extract_video_url(result):
    d = result if isinstance(result, dict) else {}
    for k in ("video",):
        if isinstance(d.get(k), dict) and d[k].get("url"):
            return d[k]["url"]
    for k in ("data", "output", "result"):
        v = d.get(k)
        if isinstance(v, dict):
            u = v.get("video") or {}
            if isinstance(u, dict) and u.get("url"):
                return u["url"]
            if v.get("video_url"):
                return v["video_url"]
            if v.get("url") and "video" not in v.get("content_type", ""):
                return v["url"]
    if d.get("video_url"):
        return d["video_url"]
    return None


def verticalize(raw_video, target_w=1080, target_h=1920):
    """fal 输出多为 256/512px 方/横图：等比放大并上下补黑边到 1080x1920 竖版。"""
    out = raw_video.replace(".mp4", "_v1080.mp4")
    cmd = ["ffmpeg", "-y", "-i", raw_video,
           "-vf", f"scale={target_w}:-2,pad={target_w}:{target_h}:0:(oh-{target_h})/2:color=black,fps=30",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return raw_video
    return out


def fal_open_generate(avip, script_text, voice_id, job_id, audio_path=None, api_key=None):
    """fal.ai 托管：照片 + TTS 音频 -> queue 提交 -> 轮询 -> 竖版成片。零自建部署。"""
    fal_key = api_key or os.environ.get("FAL_API_KEY", "")
    if not fal_key:
        raise ProviderError("fal.ai 需要 FAL_API_KEY（设置页或环境变量 FAL_API_KEY），形如 key:secret")
    if not audio_path or not os.path.exists(audio_path):
        raise ProviderError("fal.ai 模式必须带配音音频：请在设置配置 TTS（heygen/elevenlabs）后再批量生产")
    if not (avip.get("avatar_url") or "").strip():
        raise ProviderError("fal.ai 需要虚拟 IP 的照片（avatar_url），请先上传照片")

    model = (avip.get("fal_model") or DEFAULT_FAL_MODEL).strip() or "fal-ai/sadtalker"
    inputs = {
        "source_image_url": _to_fal_url(avip.get("avatar_url")),
        "driven_audio_url": _to_fal_url(audio_path),
        "preprocess": "crop",
        "still_mode": False,
        "expression_scale": 1.0,
    }
    submitted = _fal_queue_submit(model, inputs, fal_key)
    status_url = submitted.get("status_url") or submitted.get("statusUrl")
    if not status_url:
        raise ProviderError(f"fal.ai 提交异常: {str(submitted)[:200]}")
    result = _fal_poll_response(fal_key, status_url)
    url = _extract_video_url(result)
    if not url:
        raise ProviderError(f"fal.ai 响应无视频: {str(result)[:300]}")
    raw = os.path.join(GENERATED_DIR, f"job_{job_id}_fal_raw.mp4")
    download(url, raw)
    return verticalize(raw)
