"""YouTube ผ่าน yt-dlp: ข้อมูลคลิป, ดาวน์โหลด+ตัดช่วง, หาลิงก์สตรีม, อัปเดต yt-dlp"""


import os
import re
import subprocess
import sys
import time

from . import config
from .config import APP_NAME, DATA_DIR, YTDLP_RELEASE, YTDLP_ZIP


def import_ytdlp():
    """ใช้ yt-dlp.zip ที่อัปเดตไว้ (ถ้ามี) ก่อนตัวที่แพ็กมา; zip เสียก็ถอยไปใช้ตัวที่แพ็กมา"""
    if os.path.exists(YTDLP_ZIP) and YTDLP_ZIP not in sys.path and "yt_dlp" not in sys.modules:
        sys.path.insert(0, YTDLP_ZIP)
    try:
        import yt_dlp
        return yt_dlp
    except Exception:
        if YTDLP_ZIP not in sys.path:
            raise
        sys.path.remove(YTDLP_ZIP)
        for m in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
            del sys.modules[m]
        import yt_dlp
        return yt_dlp


def download_latest_ytdlp():
    """โหลด yt-dlp (zipapp) ตัวล่าสุดจาก GitHub ทางการ ตรวจ SHA-256 แล้วบันทึกเป็น YTDLP_ZIP"""
    import hashlib
    import urllib.request

    def get(name):
        req = urllib.request.Request(YTDLP_RELEASE + name, headers={"User-Agent": APP_NAME})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()

    sums = get("SHA2-256SUMS").decode("utf-8", "replace")
    expected = next((ln.split()[0] for ln in sums.splitlines() if ln.split()[-1:] == ["yt-dlp"]), None)
    if not expected:
        raise RuntimeError("ไม่พบ hash ทางการของ yt-dlp")
    data = get("yt-dlp")
    if hashlib.sha256(data).hexdigest() != expected.lower():
        raise RuntimeError("ไฟล์ที่โหลดมาไม่ตรงกับ hash ทางการ ยกเลิกการอัปเดต")
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = YTDLP_ZIP + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, YTDLP_ZIP)


def parse_time(text):
    """'83' / '1:23' / '1:02:03' / '1:23.5' -> วินาที, ช่องว่าง -> None"""
    text = text.strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p.strip()) for p in parts):
        raise ValueError(text)
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:80] or "youtube"


class _QuietLogger:
    """กลืน log ของ yt-dlp (pythonw ไม่มี stderr ให้เขียน) ข้อผิดพลาดยังมาเป็น exception"""

    def debug(self, msg):
        pass

    info = warning = error = debug


YT_BASE_OPTS = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True,
                "logger": _QuietLogger()}


def youtube_info(url):
    yt_dlp = import_ytdlp()
    opts = dict(YT_BASE_OPTS, skip_download=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def youtube_download(url, name, start, end, progress):
    """ดาวน์โหลดเฉพาะเสียง -> ตัดช่วง -> แปลงเป็น mp3 ใน YT_DIR คืน path ของไฟล์"""
    yt_dlp = import_ytdlp()
    import imageio_ffmpeg

    tmp_dir = os.path.join(config.YT_DIR, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                progress(f"⬇ กำลังดาวน์โหลด {d['downloaded_bytes'] * 100 // total}%")

    opts = dict(YT_BASE_OPTS, format="bestaudio/best", progress_hooks=[hook],
                outtmpl=os.path.join(tmp_dir, "%(id)s.%(ext)s"))
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    src = info["requested_downloads"][0]["filepath"]

    base = os.path.join(config.YT_DIR, safe_filename(name))
    out, n = base + ".mp3", 2
    while os.path.exists(out):
        out, n = f"{base} ({n}).mp3", n + 1

    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", src, "-vn", "-ac", "2", "-ar", "44100", "-b:a", "192k", out]
    progress("⚙ กำลังแปลงไฟล์...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(r.stderr.strip()[-300:] or "ffmpeg ล้มเหลว")
    return out


def friendly_yt_error(e):
    msg = str(e)
    for key, text in [("private video", "คลิปนี้เป็นคลิปส่วนตัว"),
                      ("confirm your age", "คลิปจำกัดอายุ ต้องล็อกอิน โหลดไม่ได้"),
                      ("sign in to confirm", "YouTube ขอให้ล็อกอิน ลองใหม่ภายหลังหรืออัปเดตตัวโหลด"),
                      ("unavailable", "ไม่พบคลิป หรือคลิปถูกลบ/บล็อกในประเทศนี้"),
                      ("not a valid url", "ลิงก์ไม่ถูกต้อง"),
                      ("unable to download", "ดาวน์โหลดไม่ได้ ลองกด 'อัปเดตตัวโหลด' แล้วเปิดโปรแกรมใหม่")]:
        if key in msg.lower():
            return text
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg).replace("ERROR: ", "")
    return msg[:200]


_stream_url_cache = {}  # ลิงก์ YouTube -> (url เสียงจริง, headers, หมดอายุ unix time)


def youtube_stream_url(url):
    """หา URL ไฟล์เสียงจริงสำหรับสตรีม (จำไว้จนใกล้หมดอายุ)"""
    hit = _stream_url_cache.get(url)
    if hit and hit[2] > time.time() + 120:
        return hit[0], hit[1]
    yt_dlp = import_ytdlp()
    from urllib.parse import parse_qs, urlparse
    with yt_dlp.YoutubeDL(dict(YT_BASE_OPTS, format="bestaudio/best", skip_download=True)) as ydl:
        info = ydl.extract_info(url, download=False)
    stream = info["url"]
    headers = info.get("http_headers") or {}
    try:
        expire = float(parse_qs(urlparse(stream).query)["expire"][0])
    except (KeyError, ValueError):
        expire = time.time() + 3600
    _stream_url_cache[url] = (stream, headers, expire)
    return stream, headers
