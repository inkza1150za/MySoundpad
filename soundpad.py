"""MySoundpad - เล่นเสียงเข้าไมค์ (ผ่าน VB-CABLE) พร้อมปุ่มลัดแบบ global

ต้องการ: pip install sounddevice soundfile numpy pynput
ดึงเสียงจาก YouTube (ไม่บังคับ): pip install yt-dlp imageio-ffmpeg
ใช้กับ Discord/เกม: ติดตั้ง VB-CABLE แล้วตั้งไมค์ในแอปนั้นเป็น "CABLE Output"
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import OrderedDict
from tkinter import ttk, filedialog, messagebox

import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard

APP_NAME = "MySoundpad"
APP_VERSION = "1.0.0"
FROZEN = getattr(sys, "frozen", False)  # True เมื่อรันจาก .exe (PyInstaller)
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)  # ไฟล์ที่แพ็กมากับ exe เช่น icon
# exe ที่ติดตั้งแล้ว: เก็บข้อมูลผู้ใช้ใน %APPDATA% (อัปเดต/ถอนโปรแกรมแล้วข้อมูลไม่หาย)
DATA_DIR = os.path.join(os.environ.get("APPDATA") or APP_DIR, APP_NAME) if FROZEN else APP_DIR
DATA_FILE = os.path.join(DATA_DIR, "soundpad_data.json")
AUDIO_EXT = (".wav", ".mp3", ".ogg", ".flac", ".aiff", ".aif")
BLOCK = 512
YT_DIR = os.path.join(DATA_DIR, "sounds", "youtube")
YTDLP_ZIP = os.path.join(DATA_DIR, "yt-dlp.zip")  # ตัวโหลดที่อัปเดตแล้ว ใช้แทนตัวที่แพ็กมา
YTDLP_RELEASE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
YT_URL_RE = re.compile(r"^https?://((www|m|music)\.)?(youtube\.com|youtu\.be)/\S+$", re.I)
YT_MAX_MINUTES = 10
STREAM_PREBUFFER = 0.5  # วินาทีที่ต้องมีใน buffer ก่อนเริ่มเล่นสตรีม
STREAM_TIMEOUT = 15
STREAM_AHEAD = 30  # ถอดรหัสล่วงหน้าไม่เกินกี่วินาที (คุม RAM)
STREAM_KEEP = 5    # เก็บส่วนที่เล่นผ่านไปแล้วไว้กี่วินาทีก่อนทิ้ง

# ---------------------------------------------------------------- audio utils

CACHE_LIMIT = 256 * 2**20  # bytes
_cache = OrderedDict()  # LRU: ตัวที่เพิ่งใช้อยู่ท้ายสุด


def load_audio(path, target_sr):
    """อ่านไฟล์เป็น stereo float32 ที่ sample rate ของอุปกรณ์ (มี cache จำกัดขนาด)"""
    key = (path, target_sr)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != target_sr and len(data) > 1:
        n = int(round(len(data) * target_sr / sr))
        x_old = np.arange(len(data))
        x_new = np.linspace(0, len(data) - 1, n)
        data = np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(2)], axis=1)
    data = np.ascontiguousarray(data, dtype=np.float32)
    _cache[key] = data
    total = sum(d.nbytes for d in _cache.values())
    while total > CACHE_LIMIT and len(_cache) > 1:
        _, old = _cache.popitem(last=False)  # เสียงที่กำลังเล่นยังอยู่ใน voices ไม่หาย
        total -= old.nbytes
    return data


LIMIT_KNEE = 0.8


def soft_limit(x):
    """กดเสียงที่ดังเกิน knee ให้โค้งเข้าหา 1.0 แทนการตัดแข็ง (ลดเสียงแตก)"""
    over = np.abs(x) > LIMIT_KNEE
    if over.any():
        v = x[over]
        room = 1.0 - LIMIT_KNEE
        x[over] = np.sign(v) * (LIMIT_KNEE + room * np.tanh((np.abs(v) - LIMIT_KNEE) / room))
    return x


class MicPassthrough:
    """อ่านไมค์จริงเก็บลง buffer เพื่อผสมเข้ากับไมค์เสมือน"""

    def __init__(self, device, sr, get_volume):
        self.sr = sr
        self.get_volume = get_volume
        self.buf = np.zeros((0, 2), np.float32)
        self.lock = threading.Lock()
        ch = min(2, sd.query_devices(device)["max_input_channels"])
        self.stream = sd.InputStream(device=device, samplerate=sr, channels=ch,
                                     dtype="float32", blocksize=BLOCK, callback=self._cb)
        self.stream.start()

    def _cb(self, indata, frames, t, status):
        mono = indata.mean(axis=1, keepdims=True)
        stereo = np.repeat(mono, 2, axis=1)
        with self.lock:
            self.buf = np.concatenate([self.buf, stereo])
            limit = int(self.sr * 0.15)  # กัน latency สะสม
            if len(self.buf) > limit:
                self.buf = self.buf[-limit:]

    def read(self, frames):
        with self.lock:
            chunk = self.buf[:frames]
            self.buf = self.buf[frames:]
        if len(chunk) < frames:
            chunk = np.concatenate([chunk, np.zeros((frames - len(chunk), 2), np.float32)])
        return chunk * self.get_volume()

    def close(self):
        self.stream.stop()
        self.stream.close()


class StreamSource:
    """ถอดรหัสเสียงจาก URL ด้วย ffmpeg แบบสด

    ตำแหน่ง (pos, n) นับจากต้นเสียงเสมอ แต่ buffer เก็บแค่ช่วงรอบตำแหน่งที่กำลังเล่น:
    ถอดรหัสล่วงหน้าไม่เกิน STREAM_AHEAD วินาที และทิ้งส่วนที่เล่นผ่านไปแล้ว RAM จึงคงที่แม้คลิปยาวเป็นชั่วโมง
    """

    def __init__(self, url, headers, sr, start=None, end=None):
        import imageio_ffmpeg
        self.sr = sr
        self.data = np.zeros((sr * (STREAM_AHEAD + STREAM_KEEP * 2), 2), np.float32)
        self.base = 0      # ตำแหน่งของ data[0]
        self.n = 0         # ถอดรหัสมาแล้วถึงตำแหน่งนี้
        self.read_pos = 0  # ตำแหน่งที่เล่นไปไกลสุด
        self.stopped = False
        self.done = False
        self.error = None
        self.lock = threading.Lock()
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
               "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        if headers:
            cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
        if start is not None:
            cmd += ["-ss", str(start)]
        if end is not None:
            cmd += ["-to", str(end)]
        cmd += ["-i", url, "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        rest = b""
        try:
            while not self.stopped:
                if self.n - self.read_pos > self.sr * STREAM_AHEAD:  # ล่วงหน้าพอแล้ว รอให้เล่นตามทัน
                    time.sleep(0.05)
                    continue
                raw = self.proc.stdout.read1(65536)
                if not raw:
                    break
                raw = rest + raw
                usable = len(raw) - len(raw) % 8  # 1 frame = 2ch x float32
                rest = raw[usable:]
                frames = np.frombuffer(raw[:usable], np.float32).reshape(-1, 2)
                with self.lock:
                    drop = self.read_pos - self.base - self.sr * STREAM_KEEP
                    if drop > 0:  # ทิ้งส่วนที่เล่นผ่านไปแล้ว
                        used = self.n - self.base
                        self.data[:used - drop] = self.data[drop:used]
                        self.base += drop
                    end = self.n - self.base + len(frames)
                    if end > len(self.data):
                        grown = np.zeros((end * 2, 2), np.float32)
                        grown[:self.n - self.base] = self.data[:self.n - self.base]
                        self.data = grown
                    self.data[self.n - self.base:end] = frames
                    self.n += len(frames)
            self.proc.wait()
            if self.proc.returncode not in (0, None) and self.n == 0:
                err = self.proc.stderr.read().decode("utf-8", "replace").strip()
                self.error = err[-200:] or f"ffmpeg exit {self.proc.returncode}"
        except Exception as e:
            self.error = str(e)
        finally:
            self.done = True

    def read(self, pos, frames):
        with self.lock:
            i = max(pos - self.base, 0)
            chunk = self.data[i:min(i + frames, self.n - self.base)].copy()
            self.read_pos = max(self.read_pos, pos + len(chunk))
            return chunk

    def finished_at(self, pos):
        return self.done and pos >= self.n

    def stop(self):
        self.stopped = True
        if self.proc.poll() is None:
            self.proc.kill()


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


class OutputMixer:
    """ผสมเสียงหลายเสียงพร้อมกันส่งออกอุปกรณ์หนึ่งตัว"""

    def __init__(self, device, get_volume, mic=None):
        info = sd.query_devices(device)
        self.sr = int(info["default_samplerate"])
        self.channels = min(2, info["max_output_channels"])
        self.get_volume = get_volume
        self.mic = mic
        self.voices = []  # [data (ndarray หรือ StreamSource), pos, sound_id]
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(device=device, samplerate=self.sr, channels=self.channels,
                                      dtype="float32", blocksize=BLOCK, callback=self._cb)
        self.stream.start()

    def play(self, data, sound_id):
        with self.lock:
            self.voices.append([data, 0, sound_id])

    def stop_all(self):
        with self.lock:
            self.voices = []

    def playing_ids(self):
        with self.lock:
            return [v[2] for v in self.voices]

    def _cb(self, outdata, frames, t, status):
        out = np.zeros((frames, 2), np.float32)
        with self.lock:
            alive = []
            for v in self.voices:
                data, pos = v[0], v[1]
                if isinstance(data, StreamSource):
                    chunk = data.read(pos, frames)  # ข้อมูลมาไม่ทัน = เงียบชั่วครู่ ไม่ข้ามเสียง
                    v[1] = pos + len(chunk)
                    finished = data.finished_at(v[1])
                else:
                    chunk = data[pos:pos + frames]
                    v[1] = pos + frames
                    finished = v[1] >= len(data)
                out[:len(chunk)] += chunk
                if not finished:
                    alive.append(v)
            self.voices = alive
        out *= self.get_volume()
        if self.mic is not None:
            out += self.mic.read(frames)
        soft_limit(out)
        if self.channels == 1:
            outdata[:, 0] = out.mean(axis=1)
        else:
            outdata[:] = out

    def close(self):
        self.stream.stop()
        self.stream.close()


# ---------------------------------------------------------------- hotkeys

MOD_VKS = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}
MOD_ORDER = ["ctrl", "alt", "shift", "win"]
VK_NAMES = {
    0x20: "Space", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
    0x21: "PageUp", 0x22: "PageDown", 0x13: "Pause", 0x91: "ScrollLock",
    0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0xC0: "`", 0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\",
    0xBA: ";", 0xDE: "'", 0xBC: ",", 0xBE: ".", 0xBF: "/",
}


def vk_name(vk):
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num{vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return VK_NAMES.get(vk, f"VK{vk}")


def hotkey_text(hk):
    if not hk:
        return ""
    parts = [m.capitalize() for m in MOD_ORDER if m in hk["mods"]]
    return "+".join(parts + [vk_name(hk["vk"])])


def hotkey_key(hk):
    return (tuple(m for m in MOD_ORDER if m in hk["mods"]), hk["vk"])


class HotkeyManager:
    """ฟังคีย์บอร์ดทั้งระบบ แล้วเรียก callback เมื่อกดคีย์ผสมที่ลงทะเบียนไว้"""

    def __init__(self):
        self.bindings = {}
        self.mods = set()
        self.down = set()
        self.enabled = True
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.daemon = True
        self.listener.start()

    @staticmethod
    def _vk(key):
        if isinstance(key, keyboard.KeyCode):
            return key.vk
        return getattr(key.value, "vk", None)

    def _press(self, key):
        vk = self._vk(key)
        if vk is None:
            return
        if vk in MOD_VKS:
            self.mods.add(MOD_VKS[vk])
            return
        if vk in self.down:  # กดค้าง ไม่ยิงซ้ำ
            return
        self.down.add(vk)
        if not self.enabled:
            return
        cb = self.bindings.get((tuple(m for m in MOD_ORDER if m in self.mods), vk))
        if cb:
            cb()

    def _release(self, key):
        vk = self._vk(key)
        if vk is None:
            return
        if vk in MOD_VKS:
            self.mods.discard(MOD_VKS[vk])
        self.down.discard(vk)

    def stop(self):
        self.listener.stop()


class HotkeyDialog(tk.Toplevel):
    """หน้าต่างรับการกดคีย์เพื่อตั้งปุ่มลัด"""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.result = None  # None = ยกเลิก, {} = ล้าง
        self.var = tk.StringVar(value="กดปุ่มที่ต้องการ...")
        ttk.Label(self, textvariable=self.var, font=("Segoe UI", 14), padding=20).pack()
        bar = ttk.Frame(self, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text="ล้างปุ่มลัด", command=self._clear).pack(side="left")
        ttk.Button(bar, text="ยกเลิก", command=self.destroy).pack(side="right")
        self.bind("<KeyPress>", self._key)
        self.grab_set()
        self.focus_force()
        self.geometry(f"+{parent.winfo_rootx() + 120}+{parent.winfo_rooty() + 120}")

    def _key(self, e):
        vk = e.keycode
        if vk in MOD_VKS:
            return "break"
        if vk == 0x1B:  # Esc = ยกเลิก
            self.destroy()
            return "break"
        mods = []
        if e.state & 0x4:
            mods.append("ctrl")
        if e.state & 0x20000:
            mods.append("alt")
        if e.state & 0x1:
            mods.append("shift")
        self.result = {"mods": mods, "vk": vk}
        self.destroy()
        return "break"

    def _clear(self):
        self.result = {}
        self.destroy()


# ---------------------------------------------------------------- youtube


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

    tmp_dir = os.path.join(YT_DIR, ".tmp")
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

    base = os.path.join(YT_DIR, safe_filename(name))
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


class YouTubeDialog(tk.Toplevel):
    """หน้าต่างใส่ลิงก์ YouTube; ผลลัพธ์เก็บใน self.result = (url, name, start, end, mode)"""

    def __init__(self, parent, on_update):
        super().__init__(parent)
        self.title("ดึงเสียงจาก YouTube")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        self.v_url, self.v_name = tk.StringVar(), tk.StringVar()
        self.v_start, self.v_end = tk.StringVar(), tk.StringVar()
        self.v_mode = tk.StringVar(value="download")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both")
        ttk.Label(f, text="ลิงก์ YouTube").grid(row=0, column=0, sticky="w", pady=3)
        url = ttk.Entry(f, textvariable=self.v_url, width=52)
        url.grid(row=0, column=1, columnspan=3, sticky="ew", pady=3)
        ttk.Label(f, text="ชื่อเสียง").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.v_name, width=52).grid(row=1, column=1, columnspan=3, sticky="ew", pady=3)
        ttk.Label(f, text="(เว้นว่าง = ใช้ชื่อคลิป)", foreground="gray").grid(row=2, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="ตัดช่วง").grid(row=3, column=0, sticky="w", pady=(8, 3))
        ttk.Entry(f, textvariable=self.v_start, width=10).grid(row=3, column=1, sticky="w", pady=(8, 3))
        ttk.Label(f, text="ถึง").grid(row=3, column=2, pady=(8, 3))
        ttk.Entry(f, textvariable=self.v_end, width=10).grid(row=3, column=3, sticky="w", pady=(8, 3))
        ttk.Label(f, text="เช่น 1:23 ถึง 1:30 (เว้นว่าง = ทั้งคลิป)", foreground="gray").grid(
            row=4, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="วิธีเล่น").grid(row=5, column=0, sticky="nw", pady=(8, 0))
        modes = ttk.Frame(f)
        modes.grid(row=5, column=1, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Radiobutton(modes, text="ดาวน์โหลดเก็บไว้ — กดแล้วออกทันที", value="download",
                        variable=self.v_mode, command=self._mode_changed).pack(anchor="w")
        ttk.Radiobutton(modes, text="🌐 สตรีม (ไม่เก็บไฟล์) — ต้องมีเน็ต รอ 1-3 วิก่อนเสียงออก", value="stream",
                        variable=self.v_mode, command=self._mode_changed).pack(anchor="w")

        bar = ttk.Frame(self, padding=(12, 0, 12, 12))
        bar.pack(fill="x")
        self.btn_ok = ttk.Button(bar, text="⬇ ดาวน์โหลด", command=self._ok)
        self.btn_ok.pack(side="right")
        ttk.Button(bar, text="ยกเลิก", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(bar, text="⬆ อัปเดตตัวโหลด", command=lambda: (on_update(), self.destroy())).pack(side="left")

        try:  # วางลิงก์จาก clipboard ให้อัตโนมัติ
            clip = self.clipboard_get().strip()
            if YT_URL_RE.match(clip):
                self.v_url.set(clip)
        except tk.TclError:
            pass
        url.focus_set()
        url.select_range(0, "end")
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.geometry(f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 80}")

    def _ok(self):
        url = self.v_url.get().strip()
        if not YT_URL_RE.match(url):
            messagebox.showwarning("ลิงก์ไม่ถูกต้อง", "ใส่ลิงก์ youtube.com หรือ youtu.be", parent=self)
            return
        try:
            start, end = parse_time(self.v_start.get()), parse_time(self.v_end.get())
        except ValueError as e:
            messagebox.showwarning("เวลาไม่ถูกต้อง", f"รูปแบบเวลาไม่ถูกต้อง: {e}\nใช้แบบ 83 หรือ 1:23", parent=self)
            return
        if start is not None and end is not None and end <= start:
            messagebox.showwarning("เวลาไม่ถูกต้อง", "เวลาจบต้องมากกว่าเวลาเริ่ม", parent=self)
            return
        self.result = (url, self.v_name.get().strip(), start, end, self.v_mode.get())
        self.destroy()

    def _mode_changed(self):
        self.btn_ok.config(text="🌐 เพิ่มแบบสตรีม" if self.v_mode.get() == "stream" else "⬇ ดาวน์โหลด")


# ---------------------------------------------------------------- app


def list_devices(kind):
    """คืน [(label, index)] ของอุปกรณ์ input/output"""
    apis = sd.query_hostapis()
    out = []
    for i, d in enumerate(sd.query_devices()):
        n = d["max_input_channels"] if kind == "in" else d["max_output_channels"]
        if n > 0:
            out.append((f"{d['name']} [{apis[d['hostapi']]['name']}]", i))
    return out


class SoundpadApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION}")
        try:
            root.iconbitmap(os.path.join(RES_DIR, "icon.ico"))
        except tk.TclError:
            pass
        root.geometry("820x620")
        root.minsize(700, 500)

        self.sounds = []  # {"id","path","name","hotkey"}
        self.next_id = 1
        self.monitor = None
        self.cable = None
        self.mic = None
        self.streams = []  # StreamSource ที่ ffmpeg ยังทำงานอยู่
        self.stream_lock = threading.Lock()
        self.stream_gen = 0  # เพิ่มทุกครั้งที่กดหยุด เพื่อยกเลิกสตรีมที่ยังเชื่อมต่อไม่เสร็จ

        self.v_monitor_vol = tk.DoubleVar(value=70)
        self.v_cable_vol = tk.DoubleVar(value=70)
        self.v_mic_vol = tk.DoubleVar(value=100)
        self.v_to_me = tk.BooleanVar(value=True)
        self.v_to_mic = tk.BooleanVar(value=True)
        self.v_passthrough = tk.BooleanVar(value=True)
        self.v_stop_prev = tk.BooleanVar(value=True)
        self.v_hotkeys_on = tk.BooleanVar(value=True)
        self.v_search = tk.StringVar()
        self.v_status = tk.StringVar(value="พร้อม")
        self.stop_hotkey = {"mods": [], "vk": 0x13}  # Pause
        self.saved_devices = {}

        self.out_devs = list_devices("out")
        self.in_devs = list_devices("in")

        self.hotkeys = HotkeyManager()
        self._load()
        # audio callback อ่านค่าจาก dict นี้แทน tk.Variable (tk ไม่ thread-safe)
        self.vol = {}
        for key, var in (("monitor", self.v_monitor_vol), ("cable", self.v_cable_vol), ("mic", self.v_mic_vol)):
            self.vol[key] = var.get() / 100
            var.trace_add("write", lambda *_, k=key, v=var: self.vol.__setitem__(k, v.get() / 100))
        self._build_ui()
        self._refresh_list()
        self._apply_devices()
        self._rebind_hotkeys()
        self._tick()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI
    def _build_ui(self):
        style = ttk.Style()
        style.configure(".", font=("Segoe UI", 10))
        style.configure("Treeview", rowheight=26)
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"))

        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Button(top, text="➕ เพิ่มไฟล์", command=self.add_files).pack(side="left")
        ttk.Button(top, text="📁 เพิ่มโฟลเดอร์", command=self.add_folder).pack(side="left", padx=4)
        self.btn_yt = ttk.Button(top, text="🎬 จาก YouTube", command=self.add_youtube)
        self.btn_yt.pack(side="left", padx=(0, 4))
        ttk.Button(top, text="⌨ ตั้งปุ่มลัด", command=self.set_hotkey).pack(side="left")
        ttk.Button(top, text="✏ เปลี่ยนชื่อ", command=self.rename).pack(side="left", padx=4)
        ttk.Button(top, text="🗑 ลบ", command=self.remove).pack(side="left")
        ttk.Button(top, text="▶ เล่น", style="Big.TButton", command=self.play_selected).pack(side="left", padx=(16, 4))
        ttk.Button(top, text="■ หยุด", style="Big.TButton", command=self.stop_all).pack(side="left")
        ttk.Label(top, text="ค้นหา").pack(side="right", padx=(4, 0))
        search = ttk.Entry(top, textvariable=self.v_search, width=20)
        search.pack(side="right")
        self.v_search.trace_add("write", lambda *_: self._refresh_list())

        mid = ttk.Frame(self.root, padding=(8, 0))
        mid.pack(fill="both", expand=True)
        cols = ("no", "name", "hotkey", "length")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        for c, text, w, anchor in [("no", "#", 40, "center"), ("name", "ชื่อเสียง", 420, "w"),
                                   ("hotkey", "ปุ่มลัด", 150, "center"), ("length", "ความยาว", 80, "center")]:
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "name"))
        self.tree.tag_configure("playing", background="#d6f5d6")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.play_selected())
        self.tree.bind("<Return>", lambda e: self.play_selected())
        self.tree.bind("<Delete>", lambda e: self.remove())

        # ---- settings
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")

        dev = ttk.LabelFrame(bottom, text="อุปกรณ์เสียง", padding=8)
        dev.pack(side="left", fill="both", expand=True)
        self.cb_monitor = self._device_combo(dev, 0, "🎧 ลำโพง/หูฟัง (ตัวเองได้ยิน)", self.out_devs, "monitor",
                                             sd.default.device[1])
        self.cb_cable = self._device_combo(dev, 1, "🎙 ไมค์เสมือน (CABLE Input)", self.out_devs, "cable",
                                           self._find_cable())
        self.cb_mic = self._device_combo(dev, 2, "🎤 ไมโครโฟนจริง", self.in_devs, "mic", sd.default.device[0])
        dev.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(bottom, text="การเล่น", padding=8)
        opt.pack(side="left", fill="y", padx=(8, 0))
        self._slider(opt, 0, "เสียงที่หูฉัน", self.v_monitor_vol)
        self._slider(opt, 1, "เสียงเข้าไมค์", self.v_cable_vol)
        self._slider(opt, 2, "ไมค์จริง", self.v_mic_vol)
        ttk.Checkbutton(opt, text="ให้ตัวเองได้ยิน", variable=self.v_to_me).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(opt, text="ส่งเข้าไมค์", variable=self.v_to_mic).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(opt, text="ส่งเสียงไมค์จริงผ่านด้วย", variable=self.v_passthrough,
                        command=self._apply_devices).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="หยุดเสียงเก่าเมื่อเล่นเสียงใหม่", variable=self.v_stop_prev).grid(
            row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="เปิดใช้ปุ่มลัด", variable=self.v_hotkeys_on,
                        command=lambda: setattr(self.hotkeys, "enabled", self.v_hotkeys_on.get())).grid(
            row=6, column=0, sticky="w")
        self.btn_stop_hk = ttk.Button(opt, command=self.set_stop_hotkey)
        self.btn_stop_hk.grid(row=6, column=1, sticky="e")
        self._update_stop_btn()

        ttk.Label(self.root, textvariable=self.v_status, relief="sunken", anchor="w",
                  padding=(6, 2)).pack(fill="x", side="bottom")

    def _device_combo(self, parent, row, label, devs, key, default_idx):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        labels = ["(ไม่ใช้)"] + [d[0] for d in devs]
        cb = ttk.Combobox(parent, values=labels, state="readonly", width=48)
        cb.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=3)
        saved = self.saved_devices.get(key)
        # "(ไม่ใช้)" ที่บันทึกไว้ไม่ทับการค้นหาอัตโนมัติ (เช่น เพิ่งติดตั้ง VB-CABLE ทีหลัง)
        if saved in labels[1:]:
            cb.set(saved)
        else:
            match = [d[0] for d in devs if d[1] == default_idx]
            cb.set(match[0] if match else "(ไม่ใช้)")
        cb.bind("<<ComboboxSelected>>", lambda e: self._apply_devices())
        return cb

    def _slider(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        ttk.Scale(parent, from_=0, to=150, variable=var, length=150).grid(row=row, column=1, padx=4)

    def _find_cable(self):
        # หา VB-CABLE โดยเลือก MME ก่อน (เข้ากันได้ดีที่สุด)
        for name, idx in self.out_devs:
            if "CABLE Input" in name and "[MME]" in name:
                return idx
        for name, idx in self.out_devs:
            if "CABLE" in name.upper():
                return idx
        return None

    def _dev_index(self, cb, devs):
        for name, idx in devs:
            if name == cb.get():
                return idx
        return None

    # ---------- engine
    def _apply_devices(self):
        for obj in (self.monitor, self.cable, self.mic):
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        self.monitor = self.cable = self.mic = None
        errors = []

        mon_idx = self._dev_index(self.cb_monitor, self.out_devs)
        cab_idx = self._dev_index(self.cb_cable, self.out_devs)
        mic_idx = self._dev_index(self.cb_mic, self.in_devs)

        if mon_idx is not None:
            try:
                self.monitor = OutputMixer(mon_idx, lambda: self.vol["monitor"])
            except Exception as e:
                errors.append(f"ลำโพง: {e}")
        if cab_idx is not None:
            sr = int(sd.query_devices(cab_idx)["default_samplerate"])
            if self.v_passthrough.get() and mic_idx is not None:
                try:
                    self.mic = MicPassthrough(mic_idx, sr, lambda: self.vol["mic"])
                except Exception as e:
                    errors.append(f"ไมค์จริง: {e} (ลองเลือกไมค์แบบ [MME])")
            try:
                self.cable = OutputMixer(cab_idx, lambda: self.vol["cable"], self.mic)
            except Exception as e:
                errors.append(f"ไมค์เสมือน: {e}")

        if errors:
            self.v_status.set("⚠ " + " | ".join(errors))
        elif cab_idx is None:
            self.v_status.set("ยังไม่ได้เลือกไมค์เสมือน — เสียงจะออกแค่ลำโพง (ติดตั้ง VB-CABLE เพื่อส่งเข้าไมค์)")
        else:
            self.v_status.set("พร้อม")
        self._save()

    # ---------- actions
    def _add_paths(self, paths):
        known = {s["path"] for s in self.sounds}
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if p in known or not p.lower().endswith(AUDIO_EXT):
                continue
            self.sounds.append({"id": self.next_id, "path": p,
                                "name": os.path.splitext(os.path.basename(p))[0], "hotkey": None})
            self.next_id += 1
            known.add(p)
            added += 1
        self._refresh_list()
        self._save()
        self.v_status.set(f"เพิ่ม {added} เสียง")

    def add_files(self):
        paths = filedialog.askopenfilenames(title="เลือกไฟล์เสียง", filetypes=[
            ("ไฟล์เสียง", " ".join("*" + e for e in AUDIO_EXT)), ("ทั้งหมด", "*.*")])
        if paths:
            self._add_paths(paths)

    def add_youtube(self):
        try:
            import_ytdlp()
            import imageio_ffmpeg  # noqa: F401
        except ImportError:
            messagebox.showerror("ยังไม่ได้ติดตั้ง", "ต้องติดตั้งก่อน: pip install yt-dlp imageio-ffmpeg\n"
                                                     "(หรือเปิดโปรแกรมผ่าน run_soundpad.bat / ตัวติดตั้ง)")
            return
        dlg = YouTubeDialog(self.root, self.update_ytdlp)
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        self.btn_yt.config(state="disabled")
        self.v_status.set("🔎 กำลังดึงข้อมูลคลิป...")
        threading.Thread(target=self._yt_info_worker, args=dlg.result, daemon=True).start()

    def _yt_status(self, text):
        self.root.after(0, self.v_status.set, text)

    def _yt_fail(self, e):
        self.root.after(0, lambda: (self.btn_yt.config(state="normal"),
                                    self.v_status.set("⚠ YouTube: " + friendly_yt_error(e))))

    def _yt_info_worker(self, url, name, start, end, mode="download"):
        try:
            info = youtube_info(url)
        except Exception as e:
            self._yt_fail(e)
            return
        self.root.after(0, self._yt_confirm, info, url, name, start, end, mode)

    def _yt_confirm(self, info, url, name, start, end, mode="download"):
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            self._yt_fail(Exception("ไลฟ์สดโหลดไม่ได้"))
            return
        dur = info.get("duration") or 0
        if dur and start is not None and start >= dur:
            self._yt_fail(Exception(f"เวลาเริ่มเกินความยาวคลิป ({int(dur // 60)}:{int(dur % 60):02d})"))
            return
        clip_len = (min(end, dur) if end is not None and dur else end or dur) - (start or 0)
        if mode == "stream":
            self._add_stream(url, name or info.get("title") or "youtube", start, end, clip_len or None)
            return
        if clip_len > YT_MAX_MINUTES * 60 and not messagebox.askyesno(
                "คลิปยาว", f"ช่วงที่จะโหลดยาว {int(clip_len // 60)} นาที ต้องการโหลดต่อไหม?"):
            self.btn_yt.config(state="normal")
            self.v_status.set("ยกเลิกการโหลด")
            return
        name = name or info.get("title") or "youtube"
        threading.Thread(target=self._yt_download_worker, args=(url, name, start, end), daemon=True).start()

    def _add_stream(self, url, name, start, end, length):
        self.btn_yt.config(state="normal")
        s = {"id": self.next_id, "path": None, "url": url, "start": start, "end": end,
             "name": name, "hotkey": None, "length": length}
        self.next_id += 1
        self.sounds.append(s)
        self._refresh_list()
        self._save()
        self.tree.selection_set(str(s["id"]))
        self.tree.see(str(s["id"]))
        self.v_status.set(f"✅ เพิ่มแบบสตรีม: {name}")

    def _yt_download_worker(self, url, name, start, end):
        try:
            path = youtube_download(url, name, start, end, self._yt_status)
        except Exception as e:
            self._yt_fail(e)
            return
        self.root.after(0, self._yt_done, path, name)

    def _yt_done(self, path, name):
        self.btn_yt.config(state="normal")
        self._add_paths([path])
        s = next((x for x in self.sounds if x["path"] == os.path.abspath(path)), None)
        if s:
            s["name"] = name
            self._refresh_list()
            self._save()
            self.tree.selection_set(str(s["id"]))
            self.tree.see(str(s["id"]))
        self.v_status.set(f"✅ เพิ่มจาก YouTube: {name}")

    def update_ytdlp(self):
        self.v_status.set("⬆ กำลังอัปเดตตัวโหลด YouTube...")

        def work():
            try:
                download_latest_ytdlp()
                self._yt_status("✅ อัปเดตแล้ว — ปิดแล้วเปิดโปรแกรมใหม่เพื่อใช้เวอร์ชันใหม่")
            except Exception as e:
                self._yt_status(f"⚠ อัปเดตไม่สำเร็จ: {str(e)[:150]}")
        threading.Thread(target=work, daemon=True).start()

    def add_folder(self):
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์เสียง")
        if not folder:
            return
        paths = []
        for dirpath, _, files in os.walk(folder):
            paths += [os.path.join(dirpath, f) for f in sorted(files)]
        self._add_paths(paths)

    def _selected(self):
        ids = {int(i) for i in self.tree.selection()}
        return [s for s in self.sounds if s["id"] in ids]

    def remove(self):
        sel = self._selected()
        if not sel or not messagebox.askyesno("ลบ", f"ลบ {len(sel)} เสียงออกจากรายการ?\n(ไฟล์จริงไม่ถูกลบ)"):
            return
        ids = {s["id"] for s in sel}
        self.sounds = [s for s in self.sounds if s["id"] not in ids]
        self._refresh_list()
        self._rebind_hotkeys()
        self._save()

    def rename(self):
        sel = self._selected()
        if len(sel) != 1:
            return
        s = sel[0]
        win = tk.Toplevel(self.root)
        win.title("เปลี่ยนชื่อ")
        win.transient(self.root)
        var = tk.StringVar(value=s["name"])
        ent = ttk.Entry(win, textvariable=var, width=40)
        ent.pack(padx=12, pady=12)
        ent.select_range(0, "end")
        ent.focus_set()

        def ok(_=None):
            if var.get().strip():
                s["name"] = var.get().strip()
                self._refresh_list()
                self._save()
            win.destroy()
        ent.bind("<Return>", ok)
        ent.bind("<Escape>", lambda e: win.destroy())
        ttk.Button(win, text="ตกลง", command=ok).pack(pady=(0, 12))

    def _ask_hotkey(self, title):
        self.hotkeys.enabled = False
        dlg = HotkeyDialog(self.root, title)
        self.root.wait_window(dlg)
        self.hotkeys.enabled = self.v_hotkeys_on.get()
        return dlg.result

    def set_hotkey(self):
        sel = self._selected()
        if len(sel) != 1:
            messagebox.showinfo("ตั้งปุ่มลัด", "เลือกเสียง 1 รายการก่อน")
            return
        hk = self._ask_hotkey(f"ปุ่มลัดของ: {sel[0]['name']}")
        if hk is None:
            return
        if hk:
            # ปุ่มลัดซ้ำ -> เอาออกจากเสียงเดิม
            for s in self.sounds:
                if s["hotkey"] and hotkey_key(s["hotkey"]) == hotkey_key(hk):
                    s["hotkey"] = None
        sel[0]["hotkey"] = hk or None
        self._refresh_list()
        self._rebind_hotkeys()
        self._save()

    def set_stop_hotkey(self):
        hk = self._ask_hotkey("ปุ่มลัด: หยุดทุกเสียง")
        if hk is None:
            return
        self.stop_hotkey = hk or None
        self._update_stop_btn()
        self._rebind_hotkeys()
        self._save()

    def _update_stop_btn(self):
        self.btn_stop_hk.config(text=f"หยุด: {hotkey_text(self.stop_hotkey) or '-'}")

    def _rebind_hotkeys(self):
        b = {}
        for s in self.sounds:
            if s["hotkey"]:
                sid = s["id"]
                b[hotkey_key(s["hotkey"])] = lambda sid=sid: self.root.after(0, self.play_id, sid)
        if self.stop_hotkey:
            b[hotkey_key(self.stop_hotkey)] = lambda: self.root.after(0, self.stop_all)
        self.hotkeys.bindings = b

    def play_selected(self):
        for s in self._selected()[:1]:
            self.play_id(s["id"])

    def _targets(self):
        targets = []
        if self.v_to_me.get() and self.monitor:
            targets.append(self.monitor)
        if self.v_to_mic.get() and self.cable:
            targets.append(self.cable)
        return targets

    def play_id(self, sid):
        s = next((x for x in self.sounds if x["id"] == sid), None)
        if not s:
            return
        if s.get("url"):
            self._play_stream(s)
            return
        if not os.path.exists(s["path"]):
            self.v_status.set(f"⚠ ไม่พบไฟล์: {s['path']}")
            return
        if self.v_stop_prev.get():
            self.stop_all()
        try:
            for m in self._targets():
                m.play(load_audio(s["path"], m.sr), sid)
        except Exception as e:
            self.v_status.set(f"⚠ เปิดไฟล์ไม่ได้: {e}")
            return
        self.v_status.set(f"▶ กำลังเล่น: {s['name']}")

    def _play_stream(self, s):
        if self.v_stop_prev.get():
            self.stop_all()
        targets = self._targets()
        if not targets:
            return
        self.v_status.set(f"⏳ กำลังเชื่อมต่อ: {s['name']}")
        threading.Thread(target=self._stream_worker, args=(s, targets, self.stream_gen), daemon=True).start()

    def _stream_worker(self, s, targets, gen):
        """หา URL -> เปิด ffmpeg ต่อ sample rate -> รอ buffer ขั้นต่ำ แล้วส่งให้ main thread เริ่มเล่น"""
        sources = {}
        try:
            url, headers = youtube_stream_url(s["url"])
            for m in targets:
                if m.sr not in sources:
                    sources[m.sr] = StreamSource(url, headers, m.sr, s.get("start"), s.get("end"))
            with self.stream_lock:
                self.streams.extend(sources.values())
            deadline = time.time() + STREAM_TIMEOUT
            while time.time() < deadline and gen == self.stream_gen:
                if all(src.done or src.n >= src.sr * STREAM_PREBUFFER for src in sources.values()):
                    break
                time.sleep(0.02)
            err = next((src.error for src in sources.values() if src.error), None)
            if err:
                raise RuntimeError(err)
            if gen == self.stream_gen and all(src.n == 0 for src in sources.values()):
                raise RuntimeError("เชื่อมต่อนานเกินไป ลองใหม่อีกครั้ง")
        except Exception as e:
            for src in sources.values():
                src.stop()
            _stream_url_cache.pop(s["url"], None)  # URL อาจเสีย ครั้งหน้าให้หาใหม่
            if gen == self.stream_gen:
                self._yt_status("⚠ สตรีมไม่ได้: " + friendly_yt_error(e))
            return
        self.root.after(0, self._stream_ready, s, targets, sources, gen)

    def _stream_ready(self, s, targets, sources, gen):
        if gen != self.stream_gen:  # กดหยุดระหว่างรอเชื่อมต่อ
            for src in sources.values():
                src.stop()
            return
        for m in targets:
            m.play(sources[m.sr], s["id"])
        self.v_status.set(f"▶ กำลังเล่น: {s['name']}")

    def stop_all(self):
        self.stream_gen += 1  # ยกเลิกสตรีมที่กำลังเชื่อมต่อ
        with self.stream_lock:
            for src in self.streams:
                src.stop()
            self.streams = []
        for m in (self.monitor, self.cable):
            if m:
                m.stop_all()
        if self.v_status.get().startswith("⏳"):
            self.v_status.set("■ ยกเลิกการเชื่อมต่อ")

    # ---------- list
    def _refresh_list(self):
        q = self.v_search.get().lower().strip()
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, s in enumerate(self.sounds, 1):
            if q and q not in s["name"].lower():
                continue
            if "length" not in s:
                try:
                    s["length"] = sf.info(s["path"]).duration
                except Exception:
                    s["length"] = None
            ln = s["length"]
            length = f"{int(ln // 60)}:{int(ln % 60):02d}" if ln is not None else "?"
            name = ("🌐 " if s.get("url") else "") + s["name"]
            self.tree.insert("", "end", iid=str(s["id"]),
                             values=(i, name, hotkey_text(s["hotkey"]), length))
        keep = [i for i in sel if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)

    def _tick(self):
        playing = set()
        for m in (self.monitor, self.cable):
            if m:
                playing.update(m.playing_ids())
        for iid in self.tree.get_children():
            self.tree.item(iid, tags=("playing",) if int(iid) in playing else ())
        if not playing and self.v_status.get().startswith("▶"):
            self.v_status.set("พร้อม")
        with self.stream_lock:  # สตรีมที่ ffmpeg จบแล้ว ไม่ต้องติดตามต่อ
            self.streams = [src for src in self.streams if not src.done]
        self.root.after(150, self._tick)

    # ---------- persistence
    def _load(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        for s in d.get("sounds", []):
            item = {"id": self.next_id, "path": s.get("path"), "name": s["name"], "hotkey": s.get("hotkey")}
            if s.get("url"):
                item.update(url=s["url"], start=s.get("start"), end=s.get("end"), length=s.get("length"))
            self.sounds.append(item)
            self.next_id += 1
        st = d.get("settings", {})
        for key, var in self._setting_vars().items():
            if key in st:
                var.set(st[key])
        self.stop_hotkey = d.get("stop_hotkey", self.stop_hotkey)
        self.saved_devices = d.get("devices", {})

    def _setting_vars(self):
        return {"monitor_vol": self.v_monitor_vol, "cable_vol": self.v_cable_vol, "mic_vol": self.v_mic_vol,
                "to_me": self.v_to_me, "to_mic": self.v_to_mic, "passthrough": self.v_passthrough,
                "stop_prev": self.v_stop_prev}

    @staticmethod
    def _sound_record(s):
        rec = {"path": s["path"], "name": s["name"], "hotkey": s["hotkey"]}
        if s.get("url"):
            rec.update(url=s["url"], start=s.get("start"), end=s.get("end"), length=s.get("length"))
        return rec

    def _save(self):
        if not hasattr(self, "cb_mic"):
            return
        d = {
            "sounds": [self._sound_record(s) for s in self.sounds],
            "settings": {k: v.get() for k, v in self._setting_vars().items()},
            "stop_hotkey": self.stop_hotkey,
            "devices": {"monitor": self.cb_monitor.get(), "cable": self.cb_cable.get(), "mic": self.cb_mic.get()},
        }
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.v_status.set(f"⚠ บันทึกไม่ได้: {e}")

    def _on_close(self):
        self._save()
        self.hotkeys.stop()
        self.stop_all()  # ปิด ffmpeg ของสตรีมด้วย
        for obj in (self.monitor, self.cable, self.mic):
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        self.root.destroy()


SINGLE_INSTANCE_MUTEX = "MySoundpad_SingleInstance"  # ตัวติดตั้งใช้ชื่อเดียวกันเช็กว่าโปรแกรมเปิดอยู่


def already_running():
    """เปิดซ้อน 2 ตัวจะทำให้ปุ่มลัดทำงาน 2 รอบ จึงอนุญาตแค่ตัวเดียว"""
    try:
        from ctypes import windll
        windll.kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
        return windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def selftest(out_path):
    """MySoundpad.exe --selftest <ไฟล์ผล> : ตรวจทุกส่วนแล้วเขียนผลลงไฟล์ (exe ไม่มีคอนโซลให้ดู)"""
    import tempfile
    lines = []

    def check(label, fn):
        t0 = time.perf_counter()
        try:
            lines.append(f"OK   {label}: {fn()} ({time.perf_counter() - t0:.2f}s)")
        except Exception as e:
            lines.append(f"FAIL {label}: {type(e).__name__}: {str(e)[:200]}")

    zoo = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    check("app", lambda: f"v{APP_VERSION} frozen={FROZEN} data={DATA_DIR}")
    check("cable device", lambda: [d["name"] for d in sd.query_devices() if "CABLE Input" in d["name"]][:1] or 1 / 0)

    def ffmpeg():
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([exe, "-version"], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return r.stdout.split("\n")[0][:40]
    check("ffmpeg", ffmpeg)

    def ytdlp():
        m = import_ytdlp()
        return f"{m.version.__version__} from {'updated zip' if '.zip' in m.__file__ else 'bundled'}"
    check("yt-dlp", ytdlp)
    check("youtube info", lambda: youtube_info(zoo)["title"])

    def stream():
        url, headers = youtube_stream_url(zoo)
        src = StreamSource(url, headers, 44100, 2, 4)
        while not src.done:
            time.sleep(0.05)
        src.stop()
        return f"{src.n / 44100:.2f}s decoded error={src.error}"
    check("stream", stream)

    def download():
        global YT_DIR
        old, YT_DIR = YT_DIR, tempfile.mkdtemp()
        try:
            p = youtube_download(zoo, "selftest", 2, 4, lambda m: None)
            return f"{sf.info(p).duration:.2f}s mp3 readable"
        finally:
            YT_DIR = old
    check("download", download)

    def hotkeys():
        h = HotkeyManager()
        time.sleep(0.2)
        alive = h.listener.is_alive()
        h.stop()
        return f"listener alive={alive}"
    check("hotkey listener", hotkeys)

    def cable_loop():
        devs = sd.query_devices()
        out = next(i for i, d in enumerate(devs) if "CABLE Input" in d["name"] and d["hostapi"] == 0)
        rec_dev = next(i for i, d in enumerate(devs) if "CABLE Output" in d["name"] and d["hostapi"] == 0)
        m = OutputMixer(out, lambda: 1.0)
        tone = np.repeat((0.3 * np.sin(np.arange(m.sr) * 2 * np.pi * 440 / m.sr)).astype(np.float32)[:, None], 2, 1)
        rec = sd.rec(int(m.sr * 1.4), samplerate=m.sr, channels=1, device=rec_dev, dtype="float32")
        time.sleep(0.2)
        m.play(tone, 0)
        sd.wait()
        m.close()
        peak = float(np.abs(rec).max())
        return f"recorded peak {peak:.3f}" if peak > 0.2 else 1 / 0
    check("play into CABLE", cable_loop)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
        sys.exit(0)
    if already_running():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NAME, f"{APP_NAME} เปิดอยู่แล้ว\nดูที่แถบงาน (taskbar)")
        sys.exit(0)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    os.makedirs(DATA_DIR, exist_ok=True)
    root = tk.Tk()
    SoundpadApp(root)
    root.mainloop()
