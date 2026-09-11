# -*- coding: utf-8 -*-
"""后期合成：片头钩子卡 + 成片 + 片尾关注卡拼接，可选字幕烧录。"""
import os, subprocess, json

GENERATED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def probe_duration(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        return float(json.loads(p.stdout)["format"]["duration"])
    except Exception:
        return 30.0


def make_intro(path, hook_text, niche="", duration=2.0, bg="0x101223"):
    """生成 2 秒钩子标题卡（进片前抓注意力）。"""
    lines = "\\n".join(hook_text.upper().split(" ")[:9]).replace("'", "\u2019")
    vf = (f"drawtext=fontfile={FONT}:text='{lines}':x=(w-text_w)/2:y=(h-text_h)/2:"
          f"fontsize=76:fontcolor=white:box=1:boxcolor=0x000000@0.5:boxborderw=30")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"gradients=s=1080x1920:d={duration}:c0=0x0F0F1E:c1=0x201B3D:c2=0x0A3A56:x0=200:y0=0:x1=880:y1=1920",
           "-vf", vf, "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-r", "30", "-an", path]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"intro 生成失败: {p.stderr[-300:]}")
    return path


def make_outro(path, handle, duration=2.5):
    """片尾关注卡。"""
    txt = f"FOLLOW @{handle}".replace("'", "")
    vf = (f"drawtext=fontfile={FONT}:text='{txt}':x=(w-text_w)/2:y=(h-text_h)/2-40:"
          f"fontsize=88:fontcolor=0x00FFB2,"
          f"drawtext=fontfile={FONT_REG}:text='MORE EVERY WEEK':x=(w-text_w)/2:y=(h-200)/2+120:"
          f"fontsize=44:fontcolor=white@0.9")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           "gradients=s=1080x1920:d=2.5:c0=0x001B14:c1=0x0F0F1E:c2=0x003F2E:x0=540:y0=0:x1=540:y1=1920",
           "-vf", vf, "-t", "2.5", "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-r", "30", "-an", path]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"outro 生成失败: {p.stderr[-300:]}")
    return path


def concat(clips, out):
    """拼接多个 mp4（相同编码参数）。"""
    lst = os.path.join(GENERATED_DIR, "_concat.txt")
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
           "-c", "copy", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        # 复制流失败时重编码兜底
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-c:a", "aac", out]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(f"拼接失败: {p.stderr[-300:]}")
    return out


def burn_captions(video, caption_path):
    """烧录副标题文件（FFmpeg subtitles 滤镜）。"""
    # 将文本转成 srt 最简单形式：整段垂直居中偏下的烧录
    out = video.replace(".mp4", "_cap.mp4")
    cmd = ["ffmpeg", "-y", "-i", video, "-vf", f"subtitles={caption_path}:force_style='FontSize=22'",
           "-c:v", "libx264", "-preset", "veryfast", "-c:a", "copy", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return video
    return out


def polish(raw_video, hook, handle, job_id, with_intro_outro=True):
    """对真实提供商成片做后期：片头钩子卡 + 正文 + 片尾关注卡。"""
    if not with_intro_outro or not raw_video:
        return raw_video
    intro = os.path.join(GENERATED_DIR, f"job_{job_id}_intro.mp4")
    outro = os.path.join(GENERATED_DIR, f"job_{job_id}_outro.mp4")
    try:
        make_intro(intro, hook[:80])
        make_outro(outro, handle)
        final = os.path.join(GENERATED_DIR, f"job_{job_id}.mp4")
        concat([intro, raw_video, outro], final)
        for tmp in (intro, outro):
            if os.path.exists(tmp):
                os.remove(tmp)
        return final
    except Exception:
        return raw_video
