# -*- coding: utf-8 -*-
"""TikTok 数字人虚拟 IP 批量生产工作室 - FastAPI 服务端
运行: uvicorn server:app --host 0.0.0.0 --port 8000   (或 python server.py)
"""
import csv, io, json, os, sqlite3, datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional, List

from engine import generator, providers
from engine.queue import process_job, _get_setting

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE)
DB = os.path.join(DATA_DIR, "data", "studio.db")
GENERATED = os.path.join(DATA_DIR, "generated")
FRONT = os.path.join(BASE, "frontend")

os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
os.makedirs(GENERATED, exist_ok=True)

app = FastAPI(title="TikTok 数字人虚拟IP批量生产工作室")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
from fastapi.staticfiles import StaticFiles
_uploads_dir = os.path.join(DATA_DIR, "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


def conn():
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


# ---------------- 模型 ----------------
class AvipIn(BaseModel):
    name: str
    niche: str = "default"
    tone: str = "Energetic, direct, trustworthy"
    avatar_kind: str = "photo_avatar"     # photo_avatar / digital_twin / studio_avatar
    avatar_id: str = "M#mock"             # 提供商头像 ID
    avatar_url: str = ""                  # D-ID 用
    voice_id: str = ""
    tiktok_handle: str = "yourhandle"
    language: str = "en-US"
    background: dict = {"type": "color", "value": "#101223"}


class ScriptReq(BaseModel):
    avip_id: int
    topic: str
    format: str = "listicle"
    hook_style: str = "all"
    use_llm: bool = False


class BatchReq(BaseModel):
    avip_id: int
    items: List[dict]          # [{script_id} | {topic, format, hook_style}]


class PublishReq(BaseModel):
    job_ids: List[int]


class SettingPatch(BaseModel):
    provider: Optional[str] = None
    local_open_url: Optional[str] = None
    fal_key: Optional[str] = None
    heygen_key: Optional[str] = None
    did_key: Optional[str] = None
    synthesia_key: Optional[str] = None
    tts_provider: Optional[str] = None
    heygen_voice_id: Optional[str] = None
    elevenlabs_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None


# ---------------- 初始化 ----------------
def init_db():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS avips(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT, niche TEXT, tone TEXT, avatar_kind TEXT, avatar_id TEXT,
      avatar_url TEXT, voice_id TEXT, tiktok_handle TEXT, language TEXT,
      background TEXT, created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS scripts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      avip_id INTEGER, topic TEXT, format TEXT, hook_style TEXT, hook TEXT,
      hook_variants TEXT, script_text TEXT, caption TEXT, hashtags TEXT,
      word_count INTEGER, duration_seconds INTEGER, created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS jobs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      avip_id INTEGER, script_id INTEGER, provider TEXT, status TEXT DEFAULT 'queued',
      progress INTEGER DEFAULT 0, status_msg TEXT, video_path TEXT, error TEXT,
      cost_est REAL DEFAULT 0, duration_s INTEGER DEFAULT 0,
      hook TEXT, topic TEXT, scheduled_date TEXT, scheduled_time_et TEXT,
      published INTEGER DEFAULT 0, post_text TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    n = c.execute("SELECT COUNT(*) c FROM avips").fetchone()["c"]
    if n == 0:
        seed(c)
    default_settings(c)
    c.commit()
    c.close()


def seed(c):
    import copy
    avips = [
        dict(name="Alex Carter", niche="fitness", tone="Energetic, direct, no-fluff",
             avatar_kind="studio_avatar", avatar_id="Adopt-an-Avatar", voice_id="V7qG2k3p1s5x9jU0zM6e",
             tiktok_handle="alexcarter.fit", language="en-US"),
        dict(name="Jake Sterling", niche="finance", tone="Calm, confident, trustworthy",
             avatar_kind="photo_avatar", avatar_id="photo_avatar_x1", voice_id="joU06zGCanée"[:11],
             tiktok_handle="jakesterling.money", language="en-US"),
        dict(name="Meadow", niche="pet", tone="Playful, warm, funny",
             avatar_kind="digital_twin", avatar_id="digital_twin_x1", voice_id="V7qG2k3p1s5x9jU0zM6e",
             tiktok_handle="meadow.the.golden", language="en-US"),
    ]
    for a in avips:
        a["avatar_url"] = ""
        a["language"] = "en-US"
        a["background"] = json.dumps({"type": "color", "value": "#101223"})
        c.execute("""INSERT INTO avips(name,niche,tone,avatar_kind,avatar_id,avatar_url,voice_id,
                     tiktok_handle,language,background) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (a["name"], a["niche"], a["tone"], a["avatar_kind"], a["avatar_id"],
                   a["avatar_url"], a["voice_id"], a["tiktok_handle"], a["language"], a["background"]))
    avip_id = 1
    for topic, fmt in [("fast home workouts with no equipment", "how_to"),
                       ("money habits that keep you broke", "myth_bust")]:
        av = dict(c.execute("SELECT * FROM avips WHERE id=?", (avip_id,)).fetchone())
        av["background"] = json.loads(av["background"])
        s = generator.build_script(av, topic, fmt, "all")
        insert_script(c, s)


def insert_script(c, s):
    c.execute("""INSERT INTO scripts(avip_id,topic,format,hook_style,hook,hook_variants,
                 script_text,caption,hashtags,word_count,duration_seconds)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (s["avip_id"], s["topic"], s["format"], s.get("hook_style", "all"), s.get("hook", ""),
               json.dumps(s.get("hook_variants", [])), s["script_text"], s.get("caption", ""),
               json.dumps(s.get("hashtags", [])), s.get("word_count", 0), s.get("duration_seconds", 30)))
    return c.execute("SELECT last_insert_rowid() id").fetchone()["id"]


def default_settings(c):
    env = os.environ
    defaults = {
        "provider": env.get("PROVIDER", "mock"),
        "local_open_url": env.get("LIVEPORTRAIT_URL", ""),
        "fal_key": env.get("FAL_API_KEY", ""),
        "heygen_key": env.get("HEYGEN_API_KEY", ""),
        "did_key": env.get("DID_API_KEY", ""),
        "synthesia_key": env.get("SYNTHESIA_API_KEY", ""),
        "tts_provider": env.get("TTS_PROVIDER", "heygen"),
        "heygen_voice_id": env.get("HEYGEN_VOICE_ID", "V7qG2k3p1s5x9jU0zM6e"),
        "elevenlabs_key": env.get("ELEVENLABS_API_KEY", ""),
        "elevenlabs_voice_id": env.get("ELEVENLABS_VOICE_ID", "XB0fDUnXU5powFXDhCwa"),
        "llm_base_url": env.get("LLM_BASE_URL", ""),
        "llm_api_key": env.get("LLM_API_KEY", ""),
        "llm_model": env.get("LLM_MODEL", "gpt-4o-mini"),
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, json.dumps(v)))


# ---------------- 页面 ----------------
@app.get("/")
def root():
    return FileResponse(os.path.join(FRONT, "index.html"))


# ---------------- 虚拟 IP ----------------
@app.get("/api/avips")
def list_avips():
    c = conn()
    rows = [dict(r) for r in c.execute("SELECT * FROM avips ORDER BY id")]
    for r in rows:
        r["background"] = json.loads(r["background"])
    c.close()
    return rows


@app.post("/api/avips")
def create_avip(a: AvipIn):
    c = conn()
    cur = c.execute("""INSERT INTO avips(name,niche,tone,avatar_kind,avatar_id,avatar_url,voice_id,
                       tiktok_handle,language,background) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (a.name, a.niche, a.tone, a.avatar_kind, a.avatar_id, a.avatar_url,
                     a.voice_id, a.tiktok_handle, a.language, json.dumps(a.background)))
    c.commit()
    rid = cur.lastrowid
    c.close()
    return {"id": rid}


# ---------------- 脚本工坊 ----------------
@app.post("/api/scripts/generate")
def generate_script(req: ScriptReq):
    c = conn()
    av = c.execute("SELECT * FROM avips WHERE id=?", (req.avip_id,)).fetchone()
    if not av:
        c.close()
        raise HTTPException(404, "虚拟 IP 不存在")
    av = dict(av)
    av["background"] = json.loads(av["background"])
    c.close()

    s = None
    if req.use_llm:
        base = _get_setting(conn(), "llm_base_url")
        key = _get_setting(conn(), "llm_api_key")
        model = _get_setting(conn(), "llm_model")
        s = generator.llm_script(av, req.topic, req.format, req.hook_style, base or "", key or "", model or "")
    if not s:
        s = generator.build_script(av, req.topic, req.format, req.hook_style)
    s["new"] = True
    return s


@app.get("/api/scripts")
def list_scripts(avip_id: Optional[int] = None):
    c = conn()
    q = "SELECT * FROM scripts"
    args = ()
    if avip_id:
        q += " WHERE avip_id=?"
        args = (avip_id,)
    rows = [dict(r) for r in c.execute(q + " ORDER BY id DESC LIMIT 100", args)]
    for r in rows:
        r["hook_variants"] = json.loads(r["hook_variants"] or "[]")
        r["hashtags"] = json.loads(r["hashtags"] or "[]")
    c.close()
    return rows


@app.post("/api/scripts")
def create_script(s: dict):
    """把工坊生成结果存入素材库。s 含 script_text/hook/caption 等。"""
    avip_id = s.get("avip_id")
    if not avip_id or not s.get("script_text"):
        raise HTTPException(400, "缺少 avip_id 或脚本内容")
    c = conn()
    row = {"avip_id": avip_id, "topic": s.get("topic", ""), "format": s.get("format", ""),
           "hook_style": s.get("hook_style", "all"), "hook": s.get("hook", ""),
           "hook_variants": s.get("hook_variants", []), "script_text": s["script_text"],
           "caption": s.get("caption", ""), "hashtags": s.get("hashtags", []),
           "word_count": s.get("word_count", 0), "duration_seconds": s.get("duration_seconds", 30)}
    rid = insert_script(c, row)
    c.commit()
    c.close()
    return {"id": rid}


@app.post("/api/scripts/{sid}")
def save_script(sid: int, s: dict):
    c = conn()
    c.execute("""UPDATE scripts SET hook=?, hook_variants=?, script_text=?, caption=?,
                 hashtags=?, word_count=?, duration_seconds=?, format=? WHERE id=?""",
              (s.get("hook", ""), json.dumps(s.get("hook_variants", [])), s["script_text"],
               s.get("caption", ""), json.dumps(s.get("hashtags", [])),
               s.get("word_count", 0), s.get("duration_seconds", 30), s.get("format", ""), sid))
    c.commit()
    c.close()
    return {"ok": True}


@app.delete("/api/scripts/{sid}")
def delete_script(sid: int):
    c = conn()
    c.execute("DELETE FROM scripts WHERE id=?", (sid,))
    c.commit()
    c.close()
    return {"ok": True}


# ---------------- 批量生产 ----------------
@app.post("/api/batch")
def create_batch(req: BatchReq):
    c = conn()
    av = c.execute("SELECT * FROM avips WHERE id=?", (req.avip_id,)).fetchone()
    if not av:
        c.close()
        raise HTTPException(404, "虚拟 IP 不存在")
    av = dict(av)
    av["background"] = json.loads(av["background"])
    provider = _get_setting(c, "provider") or "mock"
    created = []
    for item in req.items:
        if item.get("script_id"):
            sc = c.execute("SELECT * FROM scripts WHERE id=?", (item["script_id"],)).fetchone()
            if not sc:
                continue
            sc = dict(sc)
        else:
            sc = generator.build_script(av, item.get("topic", ""), item.get("format", "listicle"),
                                        item.get("hook_style", "all"))
            sid = insert_script(c, sc)
            sc["id"] = sid
        cur = c.execute("""INSERT INTO jobs(avip_id,script_id,provider,status,progress,status_msg,
                           hook,topic) VALUES(?,?,?,?,?,?,?,?)""",
                        (req.avip_id, sc["id"], provider, "queued", 0, "排队中",
                         sc.get("hook", ""), sc.get("topic", "")))
        created.append(cur.lastrowid)
    # 自动分配发布时段（美东）
    used = [r["scheduled_date"] + " " + r["scheduled_time_et"] for r in
            c.execute("SELECT scheduled_date, scheduled_time_et FROM jobs WHERE scheduled_date IS NOT NULL")]
    for jid in created:
        slot = generator.schedule_slot(used)
        if slot["key"]:
            used.append(slot["key"])
            c.execute("UPDATE jobs SET scheduled_date=?, scheduled_time_et=? WHERE id=?",
                      (slot["date"], slot["time_et"], jid))
    c.commit()
    c.close()
    return {"job_ids": created, "provider": provider, "count": len(created),
            "published_note": "批量入队完成，后台流水线自动开始生产。"}


@app.get("/api/jobs")
def list_jobs(status: Optional[str] = None, limit: int = 200):
    c = conn()
    q = "SELECT j.*, a.name avip_name, a.tiktok_handle FROM jobs j LEFT JOIN avips a ON a.id=j.avip_id"
    args = ()
    if status:
        q += " WHERE j.status=?"
        args = (status,)
    rows = [dict(r) for r in c.execute(q + " ORDER BY j.id DESC LIMIT ?", args + (limit,))]
    c.close()
    return rows


@app.post("/api/jobs/{jid}/retry")
def retry_job(jid: int):
    c = conn()
    c.execute("UPDATE jobs SET status='queued', progress=0, status_msg='排队中', error=NULL WHERE id=?",
              (jid,))
    c.commit()
    c.close()
    return {"ok": True}


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: int):
    c = conn()
    c.execute("UPDATE jobs SET status='cancelled', status_msg='已取消' WHERE id=? AND status='queued'",
              (jid,))
    c.commit()
    c.close()
    return {"ok": True}


@app.get("/api/jobs/{jid}/file")
def job_file(jid: int):
    c = conn()
    r = c.execute("SELECT video_path FROM jobs WHERE id=?", (jid,)).fetchone()
    c.close()
    if not r or not r["video_path"]:
        raise HTTPException(404, "视频尚未生成")
    p = os.path.join(GENERATED, os.path.basename(r["video_path"]))
    if not os.path.exists(p):
        raise HTTPException(404, "视频文件不存在")
    return FileResponse(p, media_type="video/mp4")


# ---------------- 发布中心 ----------------
@app.get("/api/calendar")
def calendar(days: int = 10):
    c = conn()
    rows = [dict(r) for r in c.execute(
        """SELECT j.id, j.topic, j.hook, j.status, j.published, j.video_path,
                  j.scheduled_date, j.scheduled_time_et, a.tiktok_handle, a.name avip_name
           FROM jobs j LEFT JOIN avips a ON a.id=j.avip_id
           WHERE j.scheduled_date IS NOT NULL
           ORDER BY j.scheduled_date, j.scheduled_time_et""")]
    c.close()
    return rows


@app.post("/api/publish")
def publish(p: PublishReq):
    """将任务标记为已发布；真实发布需 TikTok Content Posting API（见 README 合规说明）。"""
    c = conn()
    notes = []
    for jid in p.job_ids:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            continue
        if r["status"] != "done":
            notes.append(f"#{jid} 未完成生产，跳过")
            continue
        post_text = (r["topic"] or r["hook"]) + " 视频已提示进行发布。"
        c.execute("UPDATE jobs SET published=1, post_text=? WHERE id=?",
                  (post_text, jid))
        notes.append(f"#{jid} 已标记发布")
    c.commit()
    c.close()
    return {"ok": True, "notes": notes,
            "note": "批量发布 → 需要 TikTok Content Posting API(官方需审核) 或接入已过审的第三方(如 Blotato)。详见 README 合规章节。"}




@app.post("/api/upload/photo")
async def upload_photo(file: UploadFile = File(...)):
    """上传一张照片作为虚拟 IP 形象（≥512px 正脸/半侧脸）。
    保存到 uploads/，返回可引用 URL；随后把它设置为某 IP 的 avatar_url。"""
    import uuid
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(400, "仅支持 png/jpg/jpeg/webp/gif")
    up_dir = os.path.join(BASE, "uploads")
    os.makedirs(up_dir, exist_ok=True)
    fname = f"ip_{uuid.uuid4().hex[:10]}{ext}"
    dest = os.path.join(up_dir, fname)
    data = await file.read()
    with open(dest, "wb") as f:
        f.write(data)
    return {"url": f"/uploads/{fname}", "filename": fname, "size": len(data)}

@app.get("/api/export.csv")
def export_csv():
    c = conn()
    rows = [dict(r) for r in c.execute(
        """SELECT j.id job_id, j.scheduled_date, j.scheduled_time_et, j.topic, j.hook,
                  s.caption, s.hashtags, j.video_path, j.post_text, j.published
           FROM jobs j LEFT JOIN scripts s ON s.id=j.script_id
           JOIN avips a ON a.id=j.avip_id
           WHERE j.video_path IS NOT NULL OR j.published=1
           ORDER BY j.scheduled_date, j.scheduled_time_et""")]
    c.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["job_id", "date_ET", "time_ET", "topic", "hook", "caption", "hashtags",
                "video_file", "post_text", "published"])
    for r in rows:
        tags = " ".join(json.loads(r["hashtags"] or "[]"))
        w.writerow([r["job_id"], r["scheduled_date"], r["scheduled_time_et"], r["topic"],
                    r["hook"], r["caption"], tags, r["video_path"], r["post_text"], r["published"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tiktok_content_manifest.csv"})


# ---------------- 设置与统计 ----------------
@app.get("/api/settings")
def get_settings():
    c = conn()
    s = {r["key"]: _get_setting(c, r["key"]) for r in c.execute("SELECT key FROM settings")}
    s["api_keys_hidden"] = {k: bool(v) for k, v in s.items() if k.endswith("_key")}
    for k in list(s):
        if k.endswith("_key") and s[k]:
            s[k] = "********"
    c.close()
    return s


@app.post("/api/settings")
def patch_settings(p: SettingPatch):
    c = conn()
    for k, v in p.dict().items():
        if v is not None:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?",
                      (k, json.dumps(v), json.dumps(v)))
    c.commit()
    c.close()
    return {"ok": True}


@app.post("/api/settings/test")
def test_provider(provider: str = "heygen"):
    c = conn()
    key = _get_setting(c, provider + "_key") or ""
    c.close()
    if not key:
        return {"ok": False, "msg": "未配置 API KEY"}
    try:
        import requests
        if provider == "heygen":
            r = requests.get("https://api.heygen.com/v2/avatars",
                             headers={"X-Api-Key": key}, timeout=30)
            r.raise_for_status()
            n = len(r.json().get("data", {}).get("avatars", []))
            return {"ok": True, "msg": f"HeyGen 连接成功，可用形象 {n} 个"}
        if provider == "did":
            r = requests.get("https://api.d-id.com/credits", headers={"Authorization": f"Bearer {key}"}, timeout=30)
            r.raise_for_status()
            return {"ok": True, "msg": "D-ID 连接成功"}
        if provider == "synthesia":
            r = requests.get("https://api.synthesia.io/v2/avatars", headers={"Authorization": key}, timeout=30)
            r.raise_for_status()
            return {"ok": True, "msg": "Synthesia 连接成功"}
        if provider == "local_open":
            from engine.providers import _is_local_running
            url = _get_setting(c, "local_open_url") or ""
            if _is_local_running(url):
                return {"ok": True, "msg": "LivePortrait 引擎已运行"}
            return {"ok": False, "msg": "引擎未运行，请先启动本地 worker（README 有步骤）"}
        if provider == "fal":
            c2 = conn()
            fk = _get_setting(c2, "fal_key") or ""
            c2.close()
            if not fk:
                return {"ok": False, "msg": "未配置 FAL_API_KEY"}
            if ":" not in fk:
                return {"ok": False, "msg": "FAL_API_KEY 格式应为 key:secret"}
            return {"ok": True, "msg": "fal.ai Key 格式正确（提交任务时可进一步验证）"}
    except Exception as e:
        return {"ok": False, "msg": f"连接失败: {str(e)[:160]}"}
    return {"ok": False, "msg": "未知提供商"}


@app.get("/api/stats")
def stats():
    c = conn()
    s = {r["key"]: _get_setting(c, r["key"]) for r in c.execute("SELECT key FROM settings")}
    provider = s.get("provider") or "mock"
    q = {
        "total": c.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"],
        "done": c.execute("SELECT COUNT(*) c FROM jobs WHERE status='done'").fetchone()["c"],
        "queued": c.execute("SELECT COUNT(*) c FROM jobs WHERE status='queued'").fetchone()["c"],
        "running": c.execute("SELECT COUNT(*) c FROM jobs WHERE status='processing'").fetchone()["c"],
        "failed": c.execute("SELECT COUNT(*) c FROM jobs WHERE status='failed'").fetchone()["c"],
        "published": c.execute("SELECT COUNT(*) c FROM jobs WHERE published=1").fetchone()["c"],
        "avips": c.execute("SELECT COUNT(*) c FROM avips").fetchone()["c"],
        "scripts": c.execute("SELECT COUNT(*) c FROM scripts").fetchone()["c"],
        "cost": c.execute("SELECT COALESCE(SUM(cost_est),0) x FROM jobs WHERE status='done'").fetchone()["x"],
        "provider": provider,
    }
    last = c.execute("SELECT video_path, topic FROM jobs WHERE video_path IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    q["last_video"] = dict(last) if last else None
    c.close()
    return q


@app.get("/api/rates")
def rates():
    return {"heygen": providers.HEYGEN_RATES, "heygen_tts": providers.HEYGEN_TTS_RATE,
            "concurrency": providers.HEYGEN_CONCURRENCY,
            "did": providers.DID_RATES, "synthesia": providers.SYNTHESIA_RATES}


# ---------------- 启动 ----------------
init_db()

from engine.queue import WorkerThread
_worker = WorkerThread(DB)
_worker.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
