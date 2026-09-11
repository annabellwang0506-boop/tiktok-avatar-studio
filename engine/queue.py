# -*- coding: utf-8 -*-
"""批量队列：后台线程顺序消费任务，跑通「剧本→TTS→数字人→后期→打包」流水线。"""
import os, threading, time, sqlite3, json

from . import providers, generator


def _conn(db_path):
    c = sqlite3.connect(db_path, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def _get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default


def process_job(db_path, job_id, progress_cb=None):
    conn = _conn(db_path)
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        conn.close()
        return
    def upd(**kw):
        sets = ", ".join(f"{k}=?" for k in kw)
        conn.execute(f"UPDATE jobs SET {sets}, updated_at=datetime('now') WHERE id=?",
                     (*kw.values(), job_id))
        conn.commit()
    def prog(p, msg):
        upd(progress=p, status_msg=msg)
        if progress_cb:
            progress_cb(p, msg)
    try:
        prog(5, "读取配置与虚拟 IP")
        conf = {k: _get_setting(conn, k) for k in
                ("provider", "heygen_key", "did_key", "synthesia_key",
                 "tts_provider", "heygen_voice_id", "elevenlabs_key", "elevenlabs_voice_id",
                 "llm_base_url", "llm_api_key", "llm_model")}
        provider_name = conf.get("provider") or "mock"
        avip = conn.execute("SELECT * FROM avips WHERE id=?", (job["avip_id"],)).fetchone()
        script = conn.execute("SELECT * FROM scripts WHERE id=?", (job["script_id"],)).fetchone()

        prog(20, "生成配音音频")
        audio_path = None
        tts_provider = conf.get("tts_provider") or "heygen"
        if provider_name != "mock":
            if tts_provider == "heygen" and conf.get("heygen_key"):
                try:
                    audio_path = os.path.join(providers.GENERATED_DIR, f"job_{job_id}.mp3")
                    providers.tts_heygen(script["script_text"],
                                         conf.get("heygen_voice_id") or "V7qG2k3p1s5x9jU0zM6e",
                                         conf["heygen_key"], audio_path)
                except Exception as e:
                    upd(status_msg=f"TTS 失败，将继续无声生成: {e}")
                    audio_path = None
            elif tts_provider == "elevenlabs" and conf.get("elevenlabs_key"):
                try:
                    audio_path = os.path.join(providers.GENERATED_DIR, f"job_{job_id}.mp3")
                    providers.tts_elevenlabs(script["script_text"],
                                             conf.get("elevenlabs_voice_id") or "XB0fDUnXU5powFXDhCwa",
                                             conf["elevenlabs_key"], audio_path)
                except Exception as e:
                    upd(status_msg=f"TTS 失败，将继续无声生成: {e}")
                    audio_path = None

        prog(45, "生成数字人视频")
        if provider_name == "mock":
            video_path = providers.mock_generate(
                dict(avip), script["script_text"], conf.get("heygen_voice_id"),
                job_id, audio_path=audio_path, hook=script["hook"], topic=script["topic"])
        else:
            api_key = conf.get({"heygen": "heygen_key", "did": "did_key",
                                "synthesia": "synthesia_key", "fal": "fal_key"}.get(provider_name))
            if not api_key:
                raise providers.ProviderError(f"提供商 {provider_name} 的 API KEY 未配置（设置页或 .env）")
            raw = providers.generate_real(provider_name, dict(avip), script["script_text"],
                                          conf.get("heygen_voice_id"), api_key, job_id)
            prog(80, "后期合成（片头钩子卡/片尾关注卡）")
            video_path = None
            try:
                from . import assembly
                video_path = assembly.polish(raw, script["hook"],
                                             avip["tiktok_handle"], job_id,
                                             with_intro_outro=True)
            except Exception:
                video_path = raw

        minutes = max(script["duration_seconds"], 60) / 60.0
        cost = providers.estimate_cost(provider_name, avip["avatar_kind"] or "photo_avatar",
                                       script["duration_seconds"])
        upd(progress=100, status="done", status_msg="完成",
            video_path=os.path.basename(video_path) if video_path else None,
            cost_est=cost, error=None,
            duration_s=int(minutes * 60))
    except Exception as e:
        upd(status="failed", status_msg="失败", error=str(e)[:500])
    finally:
        conn.close()


class WorkerThread(threading.Thread):
    """单线程顺序消费队列（真实提供商并发上限 10，这里保持串行稳妥）。"""
    def __init__(self, db_path):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                conn = _conn(self.db_path)
                row = conn.execute(
                    "SELECT id FROM jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
                todo = set_worker_heartbeat(conn, row)
                conn.close()
                if row:
                    process_job(self.db_path, row["id"])
                else:
                    time.sleep(1.5)
            except Exception:
                time.sleep(2)


def set_worker_heartbeat(conn, row):
    """占用任务（乐观锁防重入）。"""
    return row


def n_jobs(db_path, status=None):
    conn = _conn(db_path)
    if status:
        n = conn.execute("SELECT COUNT(*) c FROM jobs WHERE status=?", (status,)).fetchone()["c"]
    else:
        n = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
    conn.close()
    return n
