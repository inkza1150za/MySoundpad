"""MySoundpad - เล่นเสียงเข้าไมค์ (ผ่าน VB-CABLE) พร้อมปุ่มลัดแบบ global

ต้องการ: pip install sounddevice soundfile numpy pynput
ดึงเสียงจาก YouTube (ไม่บังคับ): pip install yt-dlp imageio-ffmpeg
ใช้กับ Discord/เกม: ติดตั้ง VB-CABLE แล้วตั้งไมค์ในแอปนั้นเป็น "CABLE Output"
"""
import os

# numpy (OpenBLAS) จองหน่วยความจำล่วงหน้าให้ทุก CPU thread (~500 MB บนเครื่อง 16 thread)
# ทั้งที่แอปไม่ได้คำนวณเมทริกซ์เลย -> จำกัดเหลือ 1 thread (ต้องตั้งก่อน import numpy)
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import json
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
APP_VERSION = "1.4.0"
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
UPDATE_REPO = "inkza1150za/MySoundpad"
# ตั้ง MYSOUNDPAD_UPDATE_API ได้ (ใช้ทดสอบกับเซิร์ฟเวอร์จำลอง)
UPDATE_API = os.environ.get("MYSOUNDPAD_UPDATE_API") or f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_CHECK_HOURS = 24
UPDATE_ASSET_RE = re.compile(r"^MySoundpad-Setup-[\d.]+\.exe$", re.I)
YT_URL_RE = re.compile(r"^https?://((www|m|music)\.)?(youtube\.com|youtu\.be)/\S+$", re.I)
YT_MAX_MINUTES = 10
STREAM_PREBUFFER = 0.5  # วินาทีที่ต้องมีใน buffer ก่อนเริ่มเล่นสตรีม
STREAM_TIMEOUT = 15
STREAM_AHEAD = 30  # ถอดรหัสล่วงหน้าไม่เกินกี่วินาที (คุม RAM)
STREAM_KEEP = 5    # เก็บส่วนที่เล่นผ่านไปแล้วไว้กี่วินาทีก่อนทิ้ง

# ---------------------------------------------------------------- theme
# ธีมแบบแอปวิดีโอสมัยใหม่ เน้นสีชมพู-ม่วง มีทั้งแบบมืดและสว่าง
THEMES = {
    "dark": {
        "dark": True,
        "bg": "#0f0f12", "surface": "#1b1b21", "surface2": "#26262e", "hover": "#33333d", "border": "#3a3a46",
        "text": "#f4f4f5", "muted": "#a1a1aa", "faint": "#6b6b75",
        "pink": "#ec4899", "pink_hi": "#f472b6", "pink_lo": "#be185d",
        "purple": "#8b5cf6", "purple_hi": "#a78bfa", "purple_lo": "#6d28d9",
        "sel": "#6d28d9", "playing": "#3b1d4f", "playing_fg": "#f472b6", "paused": "#4a3712", "warn": "#fbbf24",
        "ok": "#4ade80", "ok_bg": "#14532d", "ok_fg": "#86efac",
        "err": "#f87171", "err_bg": "#7f1d1d", "err_fg": "#fecaca",
        "warn_bg": "#78350f", "warn_fg": "#fde68a", "playhead": "#ffffff",
    },
    "light": {
        "dark": False,
        "bg": "#f9f9fb", "surface": "#ffffff", "surface2": "#efeff4", "hover": "#e4e4ec", "border": "#d4d4dc",
        "text": "#18181b", "muted": "#5f5f6b", "faint": "#a1a1aa",
        "pink": "#db2777", "pink_hi": "#ec4899", "pink_lo": "#9d174d",
        "purple": "#7c3aed", "purple_hi": "#8b5cf6", "purple_lo": "#5b21b6",
        "sel": "#7c3aed", "playing": "#fce7f3", "playing_fg": "#be185d", "paused": "#fef3c7", "warn": "#b45309",
        "ok": "#15803d", "ok_bg": "#dcfce7", "ok_fg": "#166534",
        "err": "#dc2626", "err_bg": "#fee2e2", "err_fg": "#991b1b",
        "warn_bg": "#fef3c7", "warn_fg": "#92400e", "playhead": "#18181b",
    },
}
T = dict(THEMES["dark"])  # สีที่ใช้อยู่ตอนนี้ (เปลี่ยนด้วย use_theme)
FONT = "Segoe UI"


def use_theme(name):
    T.clear()
    T.update(THEMES.get(name, THEMES["dark"]))


# แถบสถานะด้านล่าง: ชนิด -> ข้อความบนป้าย
STATUS_LABELS = {"ready": "พร้อม", "playing": "กำลังเล่น", "paused": "พักอยู่", "busy": "กำลังทำงาน",
                 "update": "มีอัปเดต",
                 "success": "สำเร็จ", "error": "ผิดพลาด", "warn": "แจ้งเตือน", "stopped": "หยุดแล้ว"}


def status_colors():
    """ชนิดสถานะ -> (สีพื้นป้าย, สีตัวอักษรป้าย, สีข้อความ, สีเส้นด้านบน) ตามธีมปัจจุบัน"""
    return {
        "ready":   (T["ok_bg"], T["ok_fg"], T["muted"], T["border"]),
        "playing": (T["pink"], "#ffffff", T["playing_fg"], T["pink"]),
        "paused":  (T["warn_bg"], T["warn_fg"], T["warn"], T["warn"]),
        "busy":    (T["purple"], "#ffffff", T["purple_hi"], T["purple"]),
        "success": (T["ok_bg"], T["ok_fg"], T["ok"], T["ok"]),
        "error":   (T["err_bg"], T["err_fg"], T["err"], T["err"]),
        "warn":    (T["warn_bg"], T["warn_fg"], T["warn"], T["warn"]),
        "stopped": (T["surface2"], T["muted"], T["muted"], T["border"]),
        "update":  (T["purple"], "#ffffff", T["purple_hi"], T["purple"]),
    }


def status_kind(text):
    """แยกชนิดสถานะจากข้อความ (ข้อความสถานะในแอปขึ้นต้นด้วยสัญลักษณ์บอกชนิดอยู่แล้ว)"""
    for prefixes, kind in ((("▶",), "playing"), (("⏸",), "paused"), (("⚠",), "error"),
                           (("✅", "เพิ่ม "), "success"), (("■", "ยกเลิก"), "stopped"),
                           (("⏳", "🔎", "⬇", "⚙", "⬆"), "busy"), (("ยังไม่ได้เลือก",), "warn"),
                           (("🆕",), "update")):
        if text.startswith(prefixes):
            return kind
    return "ready"


def apply_theme(root):
    """ตั้งสี ttk ทั้งแอป (ใช้ธีม clam เพราะปรับสีได้ครบ)"""
    s = ttk.Style(root)
    s.theme_use("clam")
    bg, sf, sf2, hv, bd = T["bg"], T["surface"], T["surface2"], T["hover"], T["border"]
    tx, mu, pink, purple = T["text"], T["muted"], T["pink"], T["purple"]

    s.configure(".", background=bg, foreground=tx, fieldbackground=sf2, bordercolor=bd, lightcolor=sf2,
                darkcolor=sf2, troughcolor=sf2, focuscolor=purple, selectbackground=T["sel"],
                selectforeground="#ffffff", insertcolor=tx, arrowcolor=mu, font=(FONT, 10))
    s.configure("TFrame", background=bg)
    s.configure("TLabel", background=bg, foreground=tx)
    s.configure("Muted.TLabel", foreground=mu)
    s.configure("Accent.TLabel", foreground=T["playing_fg"])
    s.configure("Brand.TLabel", foreground=pink, font=(FONT, 16, "bold"))
    s.configure("StatusBar.TFrame", background=sf)
    for kind, (badge_bg, badge_fg, text_fg, line) in status_colors().items():
        s.configure(f"Badge.{kind}.TLabel", background=badge_bg, foreground=badge_fg, font=(FONT, 9, "bold"),
                    padding=(10, 2), anchor="center")
        s.configure(f"StatusText.{kind}.TLabel", background=sf, foreground=text_fg)
        s.configure(f"Line.{kind}.TFrame", background=line)

    # ปุ่ม: ปกติสีเทาเข้ม, Pink/Purple = ปุ่มหลัก
    s.configure("TButton", background=sf2, foreground=tx, bordercolor=bd, lightcolor=sf2, darkcolor=sf2,
                padding=(10, 5), focusthickness=0)
    s.map("TButton", background=[("pressed", bd), ("active", hv), ("disabled", sf)],
          foreground=[("disabled", T["faint"])], bordercolor=[("active", purple)],
          lightcolor=[("active", hv)], darkcolor=[("active", hv)])
    s.configure("Big.TButton", font=(FONT, 10, "bold"))
    for name, base, hi, lo in (("Pink", pink, T["pink_hi"], T["pink_lo"]),
                               ("Purple", purple, T["purple_hi"], T["purple_lo"])):
        s.configure(f"{name}.TButton", background=base, foreground="#ffffff", bordercolor=base, lightcolor=base,
                    darkcolor=base, font=(FONT, 10, "bold"), padding=(14, 5))
        s.map(f"{name}.TButton", background=[("pressed", lo), ("active", hi)],
              bordercolor=[("pressed", lo), ("active", hi)], lightcolor=[("pressed", lo), ("active", hi)],
              darkcolor=[("pressed", lo), ("active", hi)])

    # ช่องกรอก
    for w in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(w, fieldbackground=sf2, foreground=tx, background=sf2, bordercolor=bd, lightcolor=sf2,
                    darkcolor=sf2, insertcolor=tx, arrowcolor=mu)
        s.map(w, bordercolor=[("focus", pink), ("hover", purple)], lightcolor=[("focus", pink)])
    s.configure("TEntry", padding=4)
    s.map("TCombobox", fieldbackground=[("readonly", sf2)], foreground=[("readonly", tx)],
          selectbackground=[("readonly", sf2)], selectforeground=[("readonly", tx)], background=[("active", hv)],
          bordercolor=[("focus", pink), ("hover", purple)])
    root.option_add("*TCombobox*Listbox.background", sf2)
    root.option_add("*TCombobox*Listbox.foreground", tx)
    root.option_add("*TCombobox*Listbox.selectBackground", T["sel"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=bg, foreground=tx, indicatorbackground=sf2, indicatorforeground="#ffffff",
                    upperbordercolor=bd, lowerbordercolor=bd)
        s.map(w, background=[("active", bg)], foreground=[("active", T["pink_hi"])],
              indicatorbackground=[("selected", pink), ("active", hv)])

    s.configure("Horizontal.TProgressbar", background=pink, troughcolor=sf2, bordercolor=bd, lightcolor=pink,
                darkcolor=pink)
    s.configure("Horizontal.TScale", background=pink, troughcolor=sf2, bordercolor=bd, lightcolor=pink,
                darkcolor=pink)
    s.map("Horizontal.TScale", background=[("active", T["pink_hi"])])
    s.configure("TLabelframe", background=bg, bordercolor=bd, lightcolor=bg, darkcolor=bg)
    s.configure("TLabelframe.Label", background=bg, foreground=T["purple_hi"], font=(FONT, 10, "bold"))

    s.configure("Treeview", background=sf, fieldbackground=sf, foreground=tx, bordercolor=bd, lightcolor=sf,
                darkcolor=sf, rowheight=30)
    s.map("Treeview", background=[("selected", T["sel"])], foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=bg, foreground=mu, bordercolor=bd, lightcolor=bg, darkcolor=bg,
                font=(FONT, 9, "bold"), padding=(6, 6))
    s.map("Treeview.Heading", background=[("active", sf2)], foreground=[("active", tx)])
    s.configure("Vertical.TScrollbar", background=sf2, troughcolor=bg, bordercolor=bg, arrowcolor=mu,
                lightcolor=sf2, darkcolor=sf2, gripcount=0)
    s.map("Vertical.TScrollbar", background=[("active", hv)])


def style_window(win):
    """พื้นหลังตามธีม + แถบชื่อหน้าต่างมืด/สว่างตามธีม และขอบสีชมพู (สีแถบและขอบใช้ได้บน Windows 11)"""
    win.configure(bg=T["bg"])
    try:
        from ctypes import byref, c_int, sizeof, windll
        win.update_idletasks()
        hwnd = windll.user32.GetParent(win.winfo_id())

        def dwm(attr, value):
            v = c_int(value)
            return windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, byref(v), sizeof(v))

        dark = 1 if T["dark"] else 0
        if dwm(20, dark) != 0:  # DWMWA_USE_IMMERSIVE_DARK_MODE
            dwm(19, dark)       # ค่าเดิมของ Windows 10 รุ่นเก่า
        rgb = lambda h: int(h[5:7] + h[3:5] + h[1:3], 16)  # '#RRGGBB' -> COLORREF 0x00BBGGRR
        dwm(35, rgb(T["bg"]))    # DWMWA_CAPTION_COLOR
        dwm(36, rgb(T["text"]))  # DWMWA_TEXT_COLOR
        dwm(34, rgb(T["pink"]))  # DWMWA_BORDER_COLOR
    except Exception:
        pass


def set_app_icon(root):
    """ไอคอนโปรแกรมบนทุกหน้าต่าง (รวมหน้าต่างย่อยที่เปิดทีหลัง) และบน taskbar"""
    try:
        # ให้ Windows แยกโปรแกรมนี้ออกจาก python.exe บน taskbar จึงใช้ไอคอนของเราเอง
        from ctypes import windll
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.App")
    except Exception:
        pass
    ico, png = find_resource("icon.ico"), find_resource("icon.png")
    try:
        if ico:
            root.iconbitmap(default=ico)  # default = ใช้กับ Toplevel ทุกตัวที่สร้างภายหลังด้วย
        if png:
            root._app_icon = tk.PhotoImage(file=png)  # เก็บ ref กันโดนเก็บขยะ
            root.iconphoto(True, root._app_icon)      # True = ใช้กับหน้าต่างย่อยด้วย / ไอคอนใหญ่บน taskbar
    except tk.TclError:
        pass


def find_resource(name):
    """ไฟล์ที่แพ็กมากับ exe (RES_DIR) หรือใน build_assets ตอนรันจากซอร์สโค้ด"""
    for d in (RES_DIR, os.path.join(APP_DIR, "build_assets")):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------- audio utils

CACHE_LIMIT = 128 * 2**20  # bytes (เก็บเฉพาะเสียงสั้น แบบ 16-bit)
_cache = OrderedDict()  # LRU: ตัวที่เพิ่งใช้อยู่ท้ายสุด
LONG_SOUND_SECONDS = 30  # ไฟล์ยาวกว่านี้อ่านจากดิสก์ทีละช่วง (FileSource) แทนการโหลดทั้งไฟล์เข้า RAM
HEAD_SECONDS = 2         # เก็บต้นเพลงยาวไว้ใน RAM ให้กดซ้ำแล้วออกทันที
HEAD_CACHE_LIMIT = 32 * 2**20
_head_cache = OrderedDict()


def _cache_put(cache, key, data, limit):
    cache[key] = data
    total = sum(d.nbytes for d in cache.values())
    while total > limit and len(cache) > 1:
        _, old = cache.popitem(last=False)  # เสียงที่กำลังเล่นยังอยู่ใน voices ไม่หาย
        total -= old.nbytes


def to_int16(x):
    """float32 [-1,1] -> int16 (ใช้ RAM ครึ่งเดียว; แปลงกลับตอนผสมเสียงทีละช่วงเล็กๆ)"""
    return np.round(np.clip(x, -1.0, 1.0) * 32767).astype(np.int16)


def load_audio(path, target_sr):
    """อ่านไฟล์เป็น stereo int16 ที่ sample rate ของอุปกรณ์ (มี cache จำกัดขนาด)"""
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
    data = np.ascontiguousarray(to_int16(data))
    _cache_put(_cache, key, data, CACHE_LIMIT)
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

    def __init__(self, url, headers, sr, start=None, end=None, network=True):
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
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
        if network:  # ตัวเลือก reconnect ใช้ได้เฉพาะ http (ไฟล์ในเครื่องไม่ต้องใช้)
            cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
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


class FileSource:
    """เพลงยาวจากไฟล์ในเครื่อง: อ่านจากดิสก์ทีละช่วงด้วย ffmpeg (RAM คงที่ ~14 MB ไม่ว่าเพลงยาวแค่ไหน)

    ต้นเพลง HEAD_SECONDS วินาทีแรกเก็บไว้ใน RAM ตั้งแต่เล่นครั้งแรก ครั้งต่อไปจึงเริ่มเล่นทันที
    ระหว่างที่ ffmpeg เริ่มถอดรหัสจากต้นเพลงอยู่เบื้องหลัง ต้นเพลงกับส่วนที่เหลือมาจาก ffmpeg ตัวเดียวกัน
    รอยต่อจึงตรงกันทุก sample
    """

    def __init__(self, path, sr):
        self.key = (path, sr)
        self.sr = sr
        self.head = _head_cache.get(self.key)  # int16 หรือ None (ยังไม่เคยเล่น)
        if self.head is not None:
            _head_cache.move_to_end(self.key)
        self.head_frames = sr * HEAD_SECONDS
        self.stream = StreamSource(path, None, sr, network=False)

    @property
    def done(self):
        return self.stream.done

    @property
    def error(self):
        return self.stream.error

    def read(self, pos, frames):
        if self.head is None:
            self._save_head()
        elif pos < len(self.head):
            chunk = self.head[pos:pos + frames].astype(np.float32) * (1 / 32768)
            if len(chunk) < frames:  # คร่อมรอยต่อ: ต่อด้วยข้อมูลจาก ffmpeg
                rest = self.stream.read(pos + len(chunk), frames - len(chunk))
                chunk = np.concatenate([chunk, rest])
            return chunk
        return self.stream.read(pos, frames)

    def _save_head(self):
        s = self.stream
        with s.lock:
            if s.base == 0 and s.n >= self.head_frames:
                self.head = to_int16(s.data[:self.head_frames])
                _cache_put(_head_cache, self.key, self.head, HEAD_CACHE_LIMIT)

    def finished_at(self, pos):
        return self.stream.finished_at(pos)

    def stop(self):
        self.stream.stop()


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
        self.voices = []  # [data (ndarray int16/float32 หรือ StreamSource/FileSource), pos, sound_id]
        self.paused = False  # พัก: เก็บตำแหน่งเสียงไว้ ไม่เดินหน้า (เสียงไมค์จริงยังผ่านตามปกติ)
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
            if not self.paused:  # พักอยู่ = ไม่แตะ voices เลย ตำแหน่งจึงค้างไว้ที่เดิม
                alive = []
                for v in self.voices:
                    data, pos = v[0], v[1]
                    if not isinstance(data, np.ndarray):  # StreamSource / FileSource
                        chunk = data.read(pos, frames)  # ข้อมูลมาไม่ทัน = เงียบชั่วครู่ ไม่ข้ามเสียง
                        v[1] = pos + len(chunk)
                        finished = data.finished_at(v[1])
                    else:
                        chunk = data[pos:pos + frames]
                        if chunk.dtype == np.int16:
                            chunk = chunk.astype(np.float32) * (1 / 32768)
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
        # ถ้าตั้งไว้ คีย์ถัดไปจะส่งให้ฟังก์ชันนี้แทนการยิงปุ่มลัด (ใช้ตอนตั้งปุ่มลัด เพื่อให้เห็นคีย์แบบเดียวกับตอนใช้จริง)
        self.capture = None
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
        mods = tuple(m for m in MOD_ORDER if m in self.mods)
        if self.capture:
            self.capture(mods, vk)
            return
        if not self.enabled:
            return
        cb = self.bindings.get((mods, vk))
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
    """หน้าต่างรับการกดคีย์เพื่อตั้งปุ่มลัด

    รับคีย์ผ่าน HotkeyManager (ตัวเดียวกับที่ยิงปุ่มลัด) ไม่ใช้ event ของ Tk
    คีย์ผสมที่ตั้งได้จึงตรงกับที่กดใช้จริงเสมอ เช่น Alt+1, Ctrl+Shift+F, Ctrl+Num5
    """

    def __init__(self, parent, title, hotkeys):
        super().__init__(parent)
        style_window(self)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.hotkeys = hotkeys
        self.result = None  # None = ยกเลิก, {} = ล้าง
        self.var = tk.StringVar(value="กดปุ่มที่ต้องการ...")
        ttk.Label(self, textvariable=self.var, font=("Segoe UI", 14), padding=(20, 20, 20, 4)).pack()
        self.hint = tk.StringVar(value="กดคีย์เดียว หรือกดค้าง Ctrl / Alt / Shift แล้วกดอีกปุ่ม\n"
                                       "เช่น Alt+1, Ctrl+2, Ctrl+Shift+F, Num5   (Esc = ยกเลิก)")
        ttk.Label(self, textvariable=self.hint, style="Muted.TLabel", justify="center",
                  padding=(20, 0, 20, 12)).pack()
        bar = ttk.Frame(self, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text="ล้างปุ่มลัด", command=self._clear).pack(side="left")
        ttk.Button(bar, text="ยกเลิก", command=self.destroy).pack(side="right")
        self.bind("<KeyPress>", lambda e: "break")  # กันไม่ให้คีย์ไปกดปุ่มในหน้าต่าง
        hotkeys.capture = lambda mods, vk: self.after(0, self._captured, mods, vk)
        self.grab_set()
        self.focus_force()
        self.geometry(f"+{parent.winfo_rootx() + 120}+{parent.winfo_rooty() + 120}")

    def _captured(self, mods, vk):
        if not self.winfo_exists():
            return
        if vk == 0x1B:  # Esc = ยกเลิก
            self.destroy()
            return
        if "win" in mods:
            self.var.set("⚠ ใช้ปุ่ม Win ไม่ได้")
            self.hint.set("Windows ใช้ Win+ปุ่มอยู่แล้ว (เช่น Win+1 เปิดแอปบน taskbar)\nลองใช้ Ctrl หรือ Alt แทน")
            return
        self.result = {"mods": list(mods), "vk": vk}
        self.destroy()

    def destroy(self):
        if self.hotkeys.capture:
            self.hotkeys.capture = None
        super().destroy()

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


def fmt_time(sec):
    """วินาที -> '1:23.4' (หรือ '1:02:03.4' ถ้าเกินชั่วโมง)"""
    sec = round(max(0.0, sec), 1)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:04.1f}" if h >= 1 else f"{int(m)}:{s:04.1f}"


class PreviewPlayer:
    """เล่นเสียงตัวอย่างจาก YouTube ออกหูฟังอย่างเดียว (ไม่เข้าไมค์) ใช้ตอนเลือกช่วงตัด"""

    PREBUFFER = 0.25  # วินาที

    def __init__(self, device, get_volume):
        self.mixer = OutputMixer(device, get_volume)
        self.src = None
        self.offset = 0.0  # เวลาในคลิปที่ตรงกับต้นของ src
        self.gen = 0       # เพิ่มทุกครั้งที่หยุด เพื่อยกเลิกงานเชื่อมต่อที่ค้างอยู่
        self.loading = False
        self.lock = threading.Lock()

    def play(self, page_url, start, end, on_error):
        """เล่นช่วง start..end ของคลิป (end=None = ไปจนจบคลิป); เชื่อมต่อใน thread แยก"""
        self.stop()
        self.loading = True
        gen = self.gen

        def work():
            src = None
            try:
                url, headers = youtube_stream_url(page_url)
                if gen != self.gen:
                    return
                src = StreamSource(url, headers, self.mixer.sr, start or None, end)
                deadline = time.time() + STREAM_TIMEOUT
                while (gen == self.gen and time.time() < deadline and not src.done
                       and src.n < src.sr * self.PREBUFFER):
                    time.sleep(0.02)
                if src.error:
                    raise RuntimeError(src.error)
                if src.n == 0 and not src.done and gen == self.gen:
                    raise RuntimeError("เชื่อมต่อนานเกินไป ลองใหม่อีกครั้ง")
                with self.lock:
                    if gen != self.gen:
                        src.stop()
                        return
                    self.mixer.stop_all()
                    self.src, self.offset = src, start or 0.0
                    self.mixer.play(src, 0)
            except Exception as e:
                if src:
                    src.stop()
                _stream_url_cache.pop(page_url, None)
                if gen == self.gen:
                    on_error(e)
            finally:
                if gen == self.gen:
                    self.loading = False
        threading.Thread(target=work, daemon=True).start()

    def position(self):
        """เวลาในคลิปที่ได้ยินอยู่ตอนนี้ (หักความหน่วงของลำโพงแล้ว) หรือ None ถ้าไม่ได้เล่น"""
        with self.mixer.lock:
            if not self.mixer.voices:
                return None
            pos = self.mixer.voices[0][1]
        heard = pos / self.mixer.sr - (self.mixer.stream.latency or 0)
        return self.offset + max(0.0, heard)

    def playing(self):
        return self.loading or self.position() is not None

    def stop(self):
        with self.lock:
            self.gen += 1
            self.mixer.stop_all()
            if self.src:
                self.src.stop()
                self.src = None
        self.loading = False

    def close(self):
        self.stop()
        self.mixer.close()


class RangeTimeline(tk.Canvas):
    """หลอดเลือกช่วง 2 หมุด

    ลากหมุดซ้าย/ขวา = เลื่อนจุดเริ่ม/จบ, ลากแถบสีระหว่างหมุด = ย้ายทั้งช่วง,
    คลิกที่อื่นบนหลอด (หรือคลิกแถบสีโดยไม่ลาก) = ฟังจากจุดนั้น
    """

    PAD, HIT, MIN_LEN, TRACK_Y = 16, 9, 0.1, 40
    # อ่านสีจากธีมตอนวาด จึงเปลี่ยนตามธีมมืด/สว่างได้
    C_TRACK = property(lambda self: T["surface2"])
    C_SEL = property(lambda self: T["purple"])
    C_HANDLE = property(lambda self: T["pink"])
    C_HEAD = property(lambda self: T["playhead"])
    C_TEXT = property(lambda self: T["text"])
    C_GRAY = property(lambda self: T["muted"])

    def __init__(self, parent, on_change, on_release, on_seek, width=620, height=76):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=T["bg"])
        self.on_change, self.on_release, self.on_seek = on_change, on_release, on_seek
        self.duration = 0.0
        self.start = self.end = 0.0
        self.view = (0.0, 0.0)
        self.playhead = None
        self.drag = None  # (ชนิด, ค่าที่จำไว้, x ตอนกด)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._hover)
        self.bind("<Configure>", lambda e: self.redraw())

    # ---- ค่า
    def set_duration(self, d):
        self.duration = max(0.0, float(d or 0))
        self.start, self.end = 0.0, self.duration
        self.view = (0.0, self.duration)
        self.playhead = None
        self.redraw()

    def set_range(self, start, end):
        if not self.duration:
            return
        start = max(0.0, min(start, self.duration - self.MIN_LEN))
        end = max(start + self.MIN_LEN, min(end, self.duration))
        self.start, self.end = start, end
        self.redraw()

    def set_playhead(self, t):
        if t != self.playhead:
            self.playhead = t
            self.redraw()

    @property
    def zoomed(self):
        return self.view != (0.0, self.duration)

    def zoom_to_selection(self):
        pad = max((self.end - self.start) * 0.5, 2.0)
        self.view = (max(0.0, self.start - pad), min(self.duration, self.end + pad))
        self.redraw()

    def reset_zoom(self):
        self.view = (0.0, self.duration)
        self.redraw()

    # ---- พิกัด
    def _x(self, t):
        v0, v1 = self.view
        w = self.winfo_width() - 2 * self.PAD
        return self.PAD + (t - v0) / max(v1 - v0, 1e-6) * w

    def _t(self, x):
        v0, v1 = self.view
        w = self.winfo_width() - 2 * self.PAD
        return max(0.0, min(self.duration, v0 + (x - self.PAD) / max(w, 1) * (v1 - v0)))

    # ---- วาด
    def redraw(self):
        self.delete("all")
        w, y = self.winfo_width(), self.TRACK_Y
        if not self.duration:
            self.create_rectangle(self.PAD, y - 3, w - self.PAD, y + 3, fill=self.C_TRACK, outline="")
            self.create_text(w / 2, y + 22, text="วางลิงก์แล้วรอโหลดข้อมูลคลิป เพื่อเลือกช่วง", fill=self.C_GRAY)
            return
        v0, v1 = self.view
        self.create_rectangle(self.PAD, y - 3, w - self.PAD, y + 3, fill=self.C_TRACK, outline="")
        xs, xe = self._x(self.start), self._x(self.end)
        lo, hi = max(xs, self.PAD), min(xe, w - self.PAD)
        if hi > lo:
            self.create_rectangle(lo, y - 7, hi, y + 7, fill=self.C_SEL, outline="")
        for t, x, anchor in ((self.start, xs, "e"), (self.end, xe, "w")):
            if v0 <= t <= v1:
                self.create_rectangle(x - 4, y - 14, x + 4, y + 14, fill=self.C_HANDLE, outline="white")
                self.create_text(x + (-7 if anchor == "e" else 7), y - 24, text=fmt_time(t),
                                 anchor=anchor, fill=self.C_TEXT, font=("Segoe UI", 9, "bold"))
        if self.playhead is not None and v0 <= self.playhead <= v1:
            xp = self._x(self.playhead)
            self.create_line(xp, y - 18, xp, y + 18, fill=self.C_HEAD, width=2)
        self.create_text(self.PAD, y + 26, text=fmt_time(v0), anchor="w", fill=self.C_GRAY, font=("Segoe UI", 8))
        self.create_text(w - self.PAD, y + 26, text=fmt_time(v1), anchor="e", fill=self.C_GRAY, font=("Segoe UI", 8))
        if self.zoomed:
            self.create_text(w / 2, y + 26, text="🔍 ซูมอยู่", fill=self.C_GRAY, font=("Segoe UI", 8))

    # ---- เมาส์
    def _hit(self, x, y):
        xs, xe = self._x(self.start), self._x(self.end)
        ds, de = abs(x - xs), abs(x - xe)
        if min(ds, de) <= self.HIT:
            return "start" if ds <= de else "end"
        if xs < x < xe and abs(y - self.TRACK_Y) <= 12:
            return "move"
        return None

    def _hover(self, e):
        kind = self._hit(e.x, e.y) if self.duration else None
        self.config(cursor={"start": "sb_h_double_arrow", "end": "sb_h_double_arrow",
                            "move": "fleur"}.get(kind, "hand2" if self.duration else ""))

    def _press(self, e):
        self.focus_set()
        if not self.duration:
            return
        kind = self._hit(e.x, e.y)
        if kind == "move":
            self.drag = ("move", self._t(e.x) - self.start, e.x)
        elif kind:
            self.drag = (kind, None, e.x)
        else:
            self.drag = None
            self.on_seek(self._t(e.x))

    def _motion(self, e):
        if not self.drag:
            return
        kind, grab, _ = self.drag
        t = self._t(e.x)
        if kind == "start":
            self.start = max(0.0, min(t, self.end - self.MIN_LEN))
        elif kind == "end":
            self.end = min(self.duration, max(t, self.start + self.MIN_LEN))
        else:
            length = self.end - self.start
            self.start = max(0.0, min(t - grab, self.duration - length))
            self.end = self.start + length
        self.redraw()
        self.on_change(self.start, self.end)

    def _release(self, e):
        if not self.drag:
            return
        kind, _, x0 = self.drag
        self.drag = None
        if kind == "move" and abs(e.x - x0) < 3:  # คลิกแถบสีเฉยๆ = ฟังจากจุดนั้น
            self.on_seek(self._t(e.x))
        else:
            self.on_release(kind)


class YouTubeDialog(tk.Toplevel):
    """หน้าต่างใส่ลิงก์ YouTube + เลือกช่วงตัดด้วยหลอด 2 หมุด พร้อมฟังตัวอย่าง (ออกหูฟังอย่างเดียว)

    ผลลัพธ์: self.result = (url, name, start, end, mode) โดย start/end = None คือไม่ตัดฝั่งนั้น
    """

    def __init__(self, parent, on_update, preview_device):
        super().__init__(parent)
        style_window(self)
        self.title("ดึงเสียงจาก YouTube")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        self.duration = 0.0
        self.info_url = None
        self._fetch_after = self._tick_after = None
        self.v_url, self.v_name = tk.StringVar(), tk.StringVar()
        self.v_start, self.v_end = tk.StringVar(), tk.StringVar()
        self.v_info, self.v_len, self.v_prev = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_mode = tk.StringVar(value="download")
        self.v_pvol = tk.DoubleVar(value=70)
        self.preview_vol = 0.7
        self.v_pvol.trace_add("write", lambda *_: setattr(self, "preview_vol", self.v_pvol.get() / 100))
        try:
            self.player = PreviewPlayer(preview_device, lambda: self.preview_vol)
        except Exception as e:
            self.player = None
            self.v_prev.set(f"⚠ เปิดหูฟังสำหรับฟังตัวอย่างไม่ได้: {e}")

        f = ttk.Frame(self, padding=12)
        f.pack(fill="both")
        ttk.Label(f, text="ลิงก์ YouTube").grid(row=0, column=0, sticky="w", pady=3)
        self.url_entry = ttk.Entry(f, textvariable=self.v_url, width=70)
        self.url_entry.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(f, textvariable=self.v_info, style="Accent.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Label(f, text="ชื่อเสียง").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.v_name, width=70).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(f, text="(เว้นว่าง = ใช้ชื่อคลิป)", style="Muted.TLabel").grid(row=3, column=1, sticky="w")

        # ---- หลอดเลือกช่วง
        ttk.Label(f, text="ช่วงที่ตัด").grid(row=4, column=0, sticky="nw", pady=(12, 0))
        self.timeline = RangeTimeline(f, self._on_drag, self._on_drag_release, self._seek)
        self.timeline.grid(row=4, column=1, sticky="ew", pady=(8, 0))
        info_row = ttk.Frame(f)
        info_row.grid(row=5, column=1, sticky="ew")
        ttk.Label(info_row, textvariable=self.v_len, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.btn_zoom = ttk.Button(info_row, text="🔍 ซูมเข้าช่วงที่เลือก", command=self._toggle_zoom)
        self.btn_zoom.pack(side="right")

        for row, label, which in ((6, "เริ่ม", "start"), (7, "จบ", "end")):
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=2)
            r = ttk.Frame(f)
            r.grid(row=row, column=1, sticky="w", pady=2)
            var = self.v_start if which == "start" else self.v_end
            ent = ttk.Entry(r, textvariable=var, width=10, justify="center")
            ent.pack(side="left")
            ent.bind("<Return>", lambda e: (self._commit_entries(), "break")[1])
            ent.bind("<FocusOut>", lambda e: self._commit_entries())
            for d in (-1, -0.1, 0.1, 1):
                ttk.Button(r, text=f"{d:+g}s", width=5,
                           command=lambda w=which, d=d: self._nudge(w, d)).pack(side="left", padx=(4 if d == -1 else 1, 0))
            key = "[" if which == "start" else "]"
            ttk.Button(r, text=f"ตั้งจากเสียงที่ได้ยินอยู่  ( {key} )",
                       command=lambda w=which: self._mark(w)).pack(side="left", padx=(10, 0))

        # ---- ฟังตัวอย่าง
        ttk.Label(f, text="ฟังตัวอย่าง").grid(row=8, column=0, sticky="w", pady=(10, 2))
        p = ttk.Frame(f)
        p.grid(row=8, column=1, sticky="w", pady=(10, 2))
        ttk.Button(p, text="▶ ฟังช่วงที่เลือก", style="Purple.TButton", command=self._play_range).pack(side="left")
        ttk.Button(p, text="⏮ 3 วิแรก", command=self._play_head).pack(side="left", padx=(4, 0))
        ttk.Button(p, text="⏭ 3 วิสุดท้าย", command=self._play_tail).pack(side="left", padx=(4, 0))
        ttk.Button(p, text="■ หยุดฟัง", command=self._stop_preview).pack(side="left", padx=(4, 0))
        ttk.Label(p, text="🔊").pack(side="left", padx=(12, 2))
        ttk.Scale(p, from_=0, to=150, variable=self.v_pvol, length=90).pack(side="left")
        self.v_pvol_txt = tk.StringVar(value="70%")
        self.v_pvol.trace_add("write", lambda *_: self.v_pvol_txt.set(f"{round(self.v_pvol.get())}%"))
        ttk.Label(p, textvariable=self.v_pvol_txt, width=5).pack(side="left", padx=(2, 0))
        ttk.Label(f, textvariable=self.v_prev, style="Accent.TLabel").grid(row=9, column=1, sticky="w")
        ttk.Label(f, text="คลิกบนหลอด = ฟังจากจุดนั้น • Space = ฟัง/หยุด • [ ] = ตั้งจุดเริ่ม/จบตอนที่ได้ยิน"
                          "\nเสียงตัวอย่างออกหูฟังคุณอย่างเดียว เพื่อนไม่ได้ยิน",
                  style="Muted.TLabel").grid(row=10, column=1, sticky="w")

        ttk.Label(f, text="วิธีเล่น").grid(row=11, column=0, sticky="nw", pady=(10, 0))
        modes = ttk.Frame(f)
        modes.grid(row=11, column=1, sticky="w", pady=(10, 0))
        ttk.Radiobutton(modes, text="ดาวน์โหลดเก็บไว้ — กดแล้วออกทันที", value="download",
                        variable=self.v_mode, command=self._mode_changed).pack(anchor="w")
        ttk.Radiobutton(modes, text="🌐 สตรีม (ไม่เก็บไฟล์) — ต้องมีเน็ต รอ 1-2 วิก่อนเสียงออก", value="stream",
                        variable=self.v_mode, command=self._mode_changed).pack(anchor="w")

        bar = ttk.Frame(self, padding=(12, 0, 12, 12))
        bar.pack(fill="x")
        self.btn_ok = ttk.Button(bar, text="⬇ ดาวน์โหลด", style="Pink.TButton", command=self._ok)
        self.btn_ok.pack(side="right")
        ttk.Button(bar, text="ยกเลิก", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(bar, text="⬆ อัปเดตตัวโหลด", command=lambda: (on_update(), self.destroy())).pack(side="left")

        self.v_url.trace_add("write", lambda *_: self._schedule_fetch())
        try:  # วางลิงก์จาก clipboard ให้อัตโนมัติ
            clip = self.clipboard_get().strip()
            if YT_URL_RE.match(clip):
                self.v_url.set(clip)
        except tk.TclError:
            pass
        self.url_entry.focus_set()
        self.url_entry.select_range(0, "end")
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<space>", lambda e: self._key(self._toggle_preview))
        self.bind("<bracketleft>", lambda e: self._key(lambda: self._mark("start")))
        self.bind("<bracketright>", lambda e: self._key(lambda: self._mark("end")))
        self._update_len()
        self.grab_set()
        self.geometry(f"+{parent.winfo_rootx() + 60}+{parent.winfo_rooty() + 40}")
        self._tick()

    # ---- โหลดข้อมูลคลิป
    def _schedule_fetch(self):
        if self._fetch_after:
            self.after_cancel(self._fetch_after)
        self._fetch_after = self.after(400, self._fetch_info)

    def _fetch_info(self):
        self._fetch_after = None
        url = self.v_url.get().strip()
        if url == self.info_url:
            return
        if self.player:
            self.player.stop()
        self.info_url, self.duration = None, 0.0
        self.timeline.set_duration(0)
        self.v_start.set(""), self.v_end.set("")
        self._update_len()
        if not YT_URL_RE.match(url):
            self.v_info.set("")
            return
        self.v_info.set("🔎 กำลังโหลดข้อมูลคลิป...")

        def work():
            try:
                info = youtube_info(url)
                self.after(0, self._info_loaded, url, info, None)
            except Exception as e:
                self.after(0, self._info_loaded, url, None, e)
        threading.Thread(target=work, daemon=True).start()

    def _info_loaded(self, url, info, err):
        if not self.winfo_exists() or url != self.v_url.get().strip():
            return  # ลิงก์เปลี่ยนไปแล้ว
        if err:
            self.v_info.set("⚠ " + friendly_yt_error(err))
            return
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            self.v_info.set("⚠ ไลฟ์สดโหลดไม่ได้")
            return
        self.info_url = url
        self.duration = float(info.get("duration") or 0)
        self.v_info.set(f"🎵 {info.get('title', '')}  —  ยาว {fmt_time(self.duration)}")
        self.timeline.set_duration(self.duration)
        self.btn_zoom.config(text="🔍 ซูมเข้าช่วงที่เลือก")
        self._sync_from_timeline()
        if self.focus_get() is self.url_entry:
            self.timeline.focus_set()  # ให้ Space / [ ] ใช้ได้ทันที

    # ---- ช่วงที่เลือก
    def _ready(self):
        return self.duration > 0

    def _sync_from_timeline(self):
        self.v_start.set(fmt_time(self.timeline.start))
        self.v_end.set(fmt_time(self.timeline.end))
        self._update_len()

    def _update_len(self):
        if self._ready():
            self.v_len.set(f"ความยาวช่วง {self.timeline.end - self.timeline.start:.1f} วินาที")
        else:
            self.v_len.set("")

    def _on_drag(self, start, end):
        self._sync_from_timeline()

    def _on_drag_release(self, kind):
        if kind == "end":
            self._play_tail()
        else:
            self._play_range()

    def _commit_entries(self):
        if not self._ready():
            return
        try:
            s, e = parse_time(self.v_start.get()), parse_time(self.v_end.get())
        except ValueError:
            s = e = None
        self.timeline.set_range(self.timeline.start if s is None else s, self.timeline.end if e is None else e)
        self._sync_from_timeline()

    def _nudge(self, which, delta):
        if not self._ready():
            return
        tl = self.timeline
        if which == "start":
            tl.set_range(tl.start + delta, tl.end)
        else:
            tl.set_range(tl.start, tl.end + delta)
        self._sync_from_timeline()

    def _mark(self, which):
        if not self._ready():
            return
        t = self.player.position() if self.player else None
        if t is None:
            self.v_prev.set("กดฟังก่อน แล้วค่อยกด [ หรือ ] ตอนที่ได้ยินท่อนที่ต้องการ")
            return
        tl = self.timeline
        if which == "start":
            tl.set_range(t, max(tl.end, t + tl.MIN_LEN))
        else:
            tl.set_range(min(tl.start, t - tl.MIN_LEN), t)
        self._sync_from_timeline()

    def _toggle_zoom(self):
        if not self._ready():
            return
        if self.timeline.zoomed:
            self.timeline.reset_zoom()
            self.btn_zoom.config(text="🔍 ซูมเข้าช่วงที่เลือก")
        else:
            self.timeline.zoom_to_selection()
            self.btn_zoom.config(text="↔ ดูทั้งคลิป")

    # ---- ฟังตัวอย่าง
    def _preview(self, start, end):
        if not self._ready() or not self.player:
            return
        self.v_prev.set("⏳ กำลังโหลดเสียงตัวอย่าง...")
        self.player.play(self.info_url, start, end,
                         lambda e: self.after(0, self.v_prev.set, "⚠ ฟังตัวอย่างไม่ได้: " + friendly_yt_error(e)))

    def _play_range(self):
        self._preview(self.timeline.start, self.timeline.end)

    def _play_head(self):
        self._preview(self.timeline.start, min(self.timeline.start + 3, self.timeline.end))

    def _play_tail(self):
        self._preview(max(self.timeline.start, self.timeline.end - 3), self.timeline.end)

    def _seek(self, t):
        self._preview(t, None)  # ฟังต่อไปเรื่อยๆ จนกดหยุด

    def _stop_preview(self):
        if self.player:
            self.player.stop()

    def _toggle_preview(self):
        if self.player and self.player.playing():
            self.player.stop()
        else:
            self._play_range()

    def _key(self, action):
        """Space / [ / ] ใช้ได้เมื่อไม่ได้พิมพ์อยู่ในช่องข้อความ"""
        if isinstance(self.focus_get(), (ttk.Entry, tk.Entry, ttk.Spinbox)):
            return None
        action()
        return "break"

    def _tick(self):
        if self.player:
            pos = self.player.position()
            self.timeline.set_playhead(pos)
            msg = self.v_prev.get()
            if pos is not None:
                self.v_prev.set(f"🔊 กำลังฟัง {fmt_time(pos)}")
            elif not self.player.loading and msg.startswith(("⏳", "🔊")):
                self.v_prev.set("")
        self._tick_after = self.after(50, self._tick)

    # ---- ปิด
    def _ok(self):
        url = self.v_url.get().strip()
        if not YT_URL_RE.match(url):
            messagebox.showwarning("ลิงก์ไม่ถูกต้อง", "ใส่ลิงก์ youtube.com หรือ youtu.be", parent=self)
            return
        if self._ready():
            self._commit_entries()
            start, end = self.timeline.start, self.timeline.end
            start = None if start < 0.05 else round(start, 2)
            end = None if end > self.duration - 0.05 else round(end, 2)
        else:
            start = end = None  # ยังโหลดข้อมูลคลิปไม่เสร็จ = เอาทั้งคลิป
        self.result = (url, self.v_name.get().strip(), start, end, self.v_mode.get())
        self.destroy()

    def _mode_changed(self):
        self.btn_ok.config(text="🌐 เพิ่มแบบสตรีม" if self.v_mode.get() == "stream" else "⬇ ดาวน์โหลด")

    def destroy(self):
        for a in (self._fetch_after, self._tick_after):
            if a:
                self.after_cancel(a)
        if self.player:
            self.player.close()
            self.player = None
        super().destroy()


# ---------------------------------------------------------------- update


def parse_version(text):
    """'v1.4.0' / '1.4' -> (1, 4, 0); อ่านไม่ได้ -> None"""
    m = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", (text or "").strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def check_for_update():
    """ถาม GitHub ว่า Release ล่าสุด (ไม่นับ draft/pre-release) ใหม่กว่าเวอร์ชันนี้ไหม

    คืน dict ของเวอร์ชันใหม่ หรือ None ถ้าใช้ล่าสุดอยู่แล้ว (เชื่อมต่อไม่ได้ = โยน exception)
    """
    import urllib.error
    import urllib.request
    req = urllib.request.Request(UPDATE_API, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}",
                                                      "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:  # repo ยังไม่มี Release (หรือมีแต่ pre-release) = ยังไม่มีอะไรให้อัปเดต
            return None
        raise
    latest = parse_version(rel.get("tag_name"))
    if not latest or rel.get("draft") or rel.get("prerelease") or latest <= parse_version(APP_VERSION):
        return None
    asset = next((a for a in rel.get("assets") or [] if UPDATE_ASSET_RE.match(a.get("name", ""))), None)
    sha = None
    if asset:
        digest = (asset.get("digest") or "").lower()
        if digest.startswith("sha256:"):
            sha = digest[7:]
        else:  # Release เก่าที่ GitHub ไม่ได้เก็บ digest: ใช้ค่า SHA-256 ที่เขียนไว้ในคำอธิบาย
            m = re.search(r"\b[0-9a-fA-F]{64}\b", rel.get("body") or "")
            sha = m.group(0).lower() if m else None
    return {"version": ".".join(map(str, latest)), "notes": rel.get("body") or "",
            "page": rel.get("html_url") or f"https://github.com/{UPDATE_REPO}/releases/latest",
            "url": asset.get("browser_download_url") if asset else None,
            "name": asset.get("name") if asset else None,
            "size": asset.get("size") if asset else None, "sha256": sha}


def download_update(info, progress, cancelled):
    """โหลดตัวติดตั้งไปที่ %TEMP% แล้วตรวจขนาด + SHA-256 คืน path; ไม่ตรง = โยน exception (ไม่ติดตั้ง)"""
    import hashlib
    import tempfile
    import urllib.request
    if not (info.get("url") and info.get("sha256")):
        raise RuntimeError("Release นี้ไม่มีค่า SHA-256 ให้ตรวจ จึงไม่ติดตั้งอัตโนมัติ")
    folder = os.path.join(tempfile.gettempdir(), f"{APP_NAME}-update")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, os.path.basename(info["name"]))
    part, h, done = path + ".part", hashlib.sha256(), 0
    req = urllib.request.Request(info["url"], headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
            total = info.get("size") or int(r.headers.get("Content-Length") or 0)
            while True:
                if cancelled():
                    raise RuntimeError("ยกเลิกการดาวน์โหลด")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                progress(done, total)
        if info.get("size") and done != info["size"]:
            raise RuntimeError(f"ขนาดไฟล์ไม่ตรง ({done} / {info['size']} bytes)")
        if h.hexdigest() != info["sha256"].lower():
            raise RuntimeError("ไฟล์ที่ดาวน์โหลดมาไม่ตรงกับ SHA-256 ของ Release จึงไม่ติดตั้ง")
    except Exception:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    os.replace(part, path)
    return path


def run_installer(path):
    """ปล่อย mutex ให้ตัวติดตั้งไม่ต้องรอแอปปิด แล้วเปิดตัวติดตั้งแบบเงียบ (ติดตั้งเสร็จจะเปิดแอปให้ใหม่)"""
    global _instance_mutex
    if _instance_mutex:
        from ctypes import windll
        windll.kernel32.CloseHandle(_instance_mutex)
        _instance_mutex = None
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/relaunch=1"],
                     close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def plain_notes(md):
    """คำอธิบาย Release (markdown) -> ข้อความอ่านง่ายในหน้าต่างเล็ก"""
    text = re.sub(r"`([^`]*)`", r"\1", md or "")
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    return text.strip() or "(ไม่มีรายละเอียด)"


class UpdateDialog(tk.Toplevel):
    """หน้าต่างอัปเดต: แสดงว่ามีอะไรใหม่ ดาวน์โหลดพร้อมแถบความคืบหน้า แล้วตรวจ SHA-256

    self.result = path ของตัวติดตั้งที่ตรวจแล้ว / "skip" = ข้ามเวอร์ชันนี้ / None = ไว้ทีหลัง
    """

    def __init__(self, parent, info):
        super().__init__(parent)
        style_window(self)
        self.title("อัปเดต MySoundpad")
        self.resizable(False, False)
        self.transient(parent)
        self.info, self.result, self.cancel = info, None, False
        can_install = FROZEN and info.get("url") and info.get("sha256")

        f = ttk.Frame(self, padding=16)
        f.pack(fill="both")
        ttk.Label(f, text=f"🆕 มีเวอร์ชันใหม่ {info['version']}", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(f, text=f"เวอร์ชันที่ใช้อยู่: {APP_VERSION}", style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        ttk.Label(f, text="มีอะไรใหม่").pack(anchor="w")
        notes = tk.Text(f, width=70, height=14, wrap="word", relief="flat", padx=10, pady=8,
                        bg=T["surface"], fg=T["text"], insertbackground=T["text"], font=(FONT, 10),
                        highlightthickness=1, highlightbackground=T["border"], highlightcolor=T["border"])
        notes.insert("1.0", plain_notes(info["notes"]))
        notes.config(state="disabled")
        notes.pack(fill="both", pady=(4, 10))
        self.bar = ttk.Progressbar(f, length=480, maximum=100)
        self.v_msg = tk.StringVar()
        if not can_install:
            why = ("กำลังรันจากซอร์สโค้ด ให้อัปเดตด้วย git pull" if not FROZEN
                   else "Release นี้ไม่มีตัวติดตั้งหรือค่า SHA-256 ให้ตรวจ จึงอัปเดตอัตโนมัติไม่ได้")
            self.v_msg.set(why)
        else:
            self.v_msg.set("ดาวน์โหลดจาก GitHub แล้วตรวจ SHA-256 ก่อนติดตั้ง • รายการเสียงและการตั้งค่าอยู่ครบ")
        ttk.Label(f, textvariable=self.v_msg, style="Muted.TLabel", wraplength=520).pack(anchor="w")

        bar = ttk.Frame(self, padding=(16, 0, 16, 16))
        bar.pack(fill="x")
        if can_install:
            self.btn_go = ttk.Button(bar, text="⬆ อัปเดตเลย", style="Pink.TButton", command=self._start)
        else:
            self.btn_go = ttk.Button(bar, text="🌐 เปิดหน้าดาวน์โหลด", style="Pink.TButton", command=self._open_page)
        self.btn_go.pack(side="right")
        self.btn_later = ttk.Button(bar, text="ไว้ทีหลัง", command=self.destroy)
        self.btn_later.pack(side="right", padx=6)
        self.btn_skip = ttk.Button(bar, text="ข้ามเวอร์ชันนี้", command=self._skip)
        self.btn_skip.pack(side="left")
        self.bind("<Escape>", lambda e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()
        self.geometry(f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 60}")

    def _open_page(self):
        import webbrowser
        webbrowser.open(self.info["page"])
        self.destroy()

    def _skip(self):
        self.result = "skip"
        self.destroy()

    def _close(self):
        self.cancel = True  # ถ้ากำลังโหลดอยู่ ให้หยุด
        self.destroy()

    def _start(self):
        for b in (self.btn_go, self.btn_skip):
            b.config(state="disabled")
        self.btn_later.config(text="ยกเลิก")
        self.bar.pack(fill="x", pady=(8, 0))  # สร้างไว้ใน frame เนื้อหาแล้ว เพิ่งแสดงตอนเริ่มโหลด
        self.v_msg.set("⬇ กำลังดาวน์โหลด...")

        def progress(done, total):
            pct = done * 100 / total if total else 0
            self.after(0, lambda: (self.winfo_exists() and (self.bar.config(value=pct), self.v_msg.set(
                f"⬇ กำลังดาวน์โหลด {done / 2**20:.1f} / {total / 2**20:.1f} MB"))))

        def work():
            try:
                path = download_update(self.info, progress, lambda: self.cancel)
                self.after(0, self._done, path, None)
            except Exception as e:
                self.after(0, self._done, None, e)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, path, err):
        if not self.winfo_exists():
            return
        if err:
            self.v_msg.set(f"⚠ อัปเดตไม่สำเร็จ: {str(err)[:160]}")
            self.btn_go.config(state="normal", text="ลองใหม่")
            self.btn_skip.config(state="normal")
            self.btn_later.config(text="ไว้ทีหลัง")
            return
        self.v_msg.set("✅ ตรวจ SHA-256 ผ่าน กำลังติดตั้ง... โปรแกรมจะปิดแล้วเปิดใหม่เอง")
        self.result = path
        self.after(600, self.destroy)


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
        set_app_icon(root)
        root.geometry("980x720")  # ปรับอีกครั้งหลังสร้างหน้าจอ ให้พอดีกับเนื้อหาจริง

        self.sounds = []  # {"id","path","name","hotkey"}
        self.next_id = 1
        self.monitor = None
        self.cable = None
        self.mic = None
        self.streams = []  # StreamSource ที่ ffmpeg ยังทำงานอยู่
        self.stream_lock = threading.Lock()
        self.stream_gen = 0  # เพิ่มทุกครั้งที่กดหยุด เพื่อยกเลิกสตรีมที่ยังเชื่อมต่อไม่เสร็จ
        self.paused = False
        self._row_state = None  # (เสียงที่เล่นอยู่, พักอยู่ไหม) ที่ระบายสีแถวไว้ล่าสุด

        self.v_monitor_vol = tk.DoubleVar(value=70)
        self.v_cable_vol = tk.DoubleVar(value=70)
        self.v_mic_vol = tk.DoubleVar(value=100)
        self.v_to_me = tk.BooleanVar(value=True)
        self.v_to_mic = tk.BooleanVar(value=True)
        self.v_passthrough = tk.BooleanVar(value=True)
        self.v_stop_prev = tk.BooleanVar(value=True)
        self.v_hotkeys_on = tk.BooleanVar(value=True)
        self.v_theme = tk.StringVar(value="dark")
        self.v_auto_update = tk.BooleanVar(value=True)
        self.update_state = {"last_check": 0, "skip": ""}  # บันทึกลงไฟล์ตั้งค่า
        self.update_info = None  # เวอร์ชันใหม่ที่เจอ (dict จาก check_for_update)
        self._checking_update = False
        self.v_search = tk.StringVar()
        self.v_status = tk.StringVar(value="พร้อม")
        self.stop_hotkey = {"mods": [], "vk": 0x13}  # Pause
        self.saved_devices = {}

        self.out_devs = list_devices("out")
        self.in_devs = list_devices("in")

        self.hotkeys = HotkeyManager()
        self._load()
        use_theme(self.v_theme.get())  # ธีมที่บันทึกไว้ (ค่าเริ่มต้น = มืด)
        apply_theme(root)
        style_window(root)
        # audio callback อ่านค่าจาก dict นี้แทน tk.Variable (tk ไม่ thread-safe)
        self.vol = {}
        for key, var in (("monitor", self.v_monitor_vol), ("cable", self.v_cable_vol), ("mic", self.v_mic_vol)):
            self.vol[key] = var.get() / 100
            var.trace_add("write", lambda *_, k=key, v=var: self.vol.__setitem__(k, v.get() / 100))
        self._build_ui()
        root.update_idletasks()
        need_w, need_h = root.winfo_reqwidth(), root.winfo_reqheight()
        root.minsize(need_w, min(need_h, 640))
        root.geometry(f"{max(980, need_w)}x{max(720, need_h)}")
        self._refresh_list()
        self._apply_devices()
        self._rebind_hotkeys()
        self._tick()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(3000, self._auto_check_update)  # รอให้หน้าต่างขึ้นก่อน ไม่ทำให้เปิดช้า

    # ---------- UI
    def _build_ui(self):
        # ---- หัวแอป: โลโก้ + ชื่อ
        head = ttk.Frame(self.root, padding=(12, 10, 12, 2))
        head.pack(fill="x")
        logo = find_resource("icon.png")
        if logo:
            self._logo = tk.PhotoImage(file=logo).subsample(8)  # 256 -> 32 px (เก็บ ref กันโดนเก็บขยะ)
            ttk.Label(head, image=self._logo).pack(side="left", padx=(0, 8))
        ttk.Label(head, text=APP_NAME, style="Brand.TLabel").pack(side="left")
        self.btn_theme = ttk.Button(head, command=self.toggle_theme)
        self.btn_theme.pack(side="right")
        self.btn_update = ttk.Button(head, text="🔄 ตรวจสอบอัปเดต", command=self.on_update_button)
        self.btn_update.pack(side="right", padx=(0, 6))
        self._update_theme_button()
        ttk.Label(head, text=f"v{APP_VERSION}", style="Muted.TLabel").pack(side="left", padx=(6, 0), pady=(6, 0))

        top = ttk.Frame(self.root, padding=(12, 8, 12, 4))
        top.pack(fill="x")
        ttk.Button(top, text="➕ เพิ่มไฟล์", command=self.add_files).pack(side="left")
        ttk.Button(top, text="📁 เพิ่มโฟลเดอร์", command=self.add_folder).pack(side="left", padx=4)
        self.btn_yt = ttk.Button(top, text="🎬 จาก YouTube", command=self.add_youtube)
        self.btn_yt.pack(side="left", padx=(0, 4))
        ttk.Button(top, text="⌨ ตั้งปุ่มลัด", command=self.set_hotkey).pack(side="left")
        ttk.Button(top, text="✏ เปลี่ยนชื่อ", command=self.rename).pack(side="left", padx=4)
        ttk.Button(top, text="🗑 ลบ", command=self.remove).pack(side="left")
        ttk.Button(top, text="▶ เล่น", style="Pink.TButton", command=self.play_selected).pack(side="left", padx=(16, 4))
        self.btn_pause = ttk.Button(top, text="⏸ พัก", style="Purple.TButton", width=9, command=self.toggle_pause)
        self.btn_pause.pack(side="left")
        ttk.Button(top, text="■ หยุด", style="Big.TButton", command=self.stop_all).pack(side="left", padx=(4, 0))

        # ---- ค้นหา: แถวของตัวเอง กว้างเต็มหน้าต่าง
        bar = ttk.Frame(self.root, padding=(12, 4, 12, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="🔍", font=(FONT, 13)).pack(side="left")
        self.search_entry = ttk.Entry(bar, textvariable=self.v_search, font=(FONT, 12))
        self.search_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=4)
        ttk.Button(bar, text="✕ ล้าง", command=self._clear_search).pack(side="left")
        self.v_count = tk.StringVar()
        ttk.Label(bar, textvariable=self.v_count, style="Muted.TLabel", width=14, anchor="e").pack(side="left")
        self.v_search.trace_add("write", lambda *_: self._refresh_list())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        self.search_entry.bind("<Return>", lambda e: self._focus_first_result())
        self.search_entry.bind("<Down>", lambda e: self._focus_first_result())
        self.root.bind("<Control-f>", lambda e: (self.search_entry.focus_set(),
                                                 self.search_entry.select_range(0, "end")))

        mid = ttk.Frame(self.root, padding=(12, 0))
        mid.pack(fill="both", expand=True)
        cols = ("no", "name", "hotkey", "length")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        for c, text, w, anchor in [("no", "#", 40, "center"), ("name", "ชื่อเสียง", 420, "w"),
                                   ("hotkey", "ปุ่มลัด", 150, "center"), ("length", "ความยาว", 80, "center")]:
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "name"))
        self._style_tree_tags()
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.play_selected())
        self.tree.bind("<Return>", lambda e: self.play_selected())
        self.tree.bind("<Delete>", lambda e: self.remove())
        self.tree.bind("<space>", lambda e: (self.toggle_pause(), "break")[1])

        # ---- settings
        bottom = ttk.Frame(self.root, padding=(12, 10, 12, 10))
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
        ttk.Checkbutton(opt, text="ตรวจสอบเวอร์ชันใหม่อัตโนมัติ", variable=self.v_auto_update,
                        command=self._save).grid(row=7, column=0, columnspan=2, sticky="w")

        # ---- แถบสถานะ: ป้ายสี + ข้อความสี + เส้นสีด้านบน เปลี่ยนตามสถานะ
        sbar = ttk.Frame(self.root, style="StatusBar.TFrame")
        sbar.pack(fill="x", side="bottom")
        self.status_line = ttk.Frame(self.root, height=2)
        self.status_line.pack(fill="x", side="bottom")
        self.status_badge = ttk.Label(sbar, width=11)
        self.status_badge.pack(side="left", padx=(10, 8), pady=6)
        self.status_text = ttk.Label(sbar, textvariable=self.v_status, anchor="w")
        self.status_text.pack(side="left", fill="x", expand=True)
        self.v_status.trace_add("write", lambda *_: self._update_status_style())
        self._update_status_style()

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
        # ช่องตัวเลข %: ขยับตามแถบเลื่อน และพิมพ์ค่า/กดลูกศรเองได้ (Enter หรือคลิกออกเพื่อใช้ค่า)
        text = tk.StringVar(value=str(round(var.get())))
        box = ttk.Spinbox(parent, from_=0, to=150, increment=5, width=4, textvariable=text, justify="right")
        box.grid(row=row, column=2)
        ttk.Label(parent, text="%").grid(row=row, column=3, sticky="w", padx=(1, 0))
        var.trace_add("write", lambda *_: text.set(str(round(var.get()))))

        def commit(_=None):
            try:
                v = float(text.get().strip().rstrip("%"))
            except ValueError:
                v = var.get()
            v = max(0.0, min(150.0, v))
            var.set(v)
            text.set(str(round(v)))
        box.configure(command=commit)
        box.bind("<Return>", commit)
        box.bind("<FocusOut>", commit)

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
        if hasattr(self, "btn_pause"):
            self.stop_all()  # ปิด ffmpeg ของเพลงยาว/สตรีมที่เล่นค้างอยู่ด้วย ไม่งั้นจะค้างอยู่จนกดหยุด
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
        self._set_paused(False, quiet=True)  # mixer ใหม่ยังไม่มีเสียงค้าง

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
        # เสียงตัวอย่างออกหูฟังที่เลือกไว้ (ไม่ใช่ไมค์เสมือน) เพื่อนจึงไม่ได้ยินตอนตัดเพลง
        preview_dev = self._dev_index(self.cb_monitor, self.out_devs)
        if preview_dev is None:
            preview_dev = sd.default.device[1]
        dlg = YouTubeDialog(self.root, self.update_ytdlp, preview_dev)
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
        style_window(win)
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
        dlg = HotkeyDialog(self.root, title, self.hotkeys)
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
        self._set_paused(False, quiet=True)  # กดเล่นเสียงใหม่ระหว่างพัก = เลิกพัก
        try:
            if (s.get("length") or 0) > LONG_SOUND_SECONDS:
                # เพลงยาว: อ่านจากดิสก์ทีละช่วง ถอดรหัสครั้งเดียวต่อ sample rate แล้วแจกให้ทุกอุปกรณ์
                sources = {}
                for m in self._targets():
                    if m.sr not in sources:
                        sources[m.sr] = FileSource(s["path"], m.sr)
                    m.play(sources[m.sr], sid)
                with self.stream_lock:
                    self.streams.extend(sources.values())
            else:
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
        self._set_paused(False, quiet=True)
        for m in targets:
            m.play(sources[m.sr], s["id"])
        self.v_status.set(f"▶ กำลังเล่น: {s['name']}")

    def toggle_pause(self):
        playing = any(m.playing_ids() for m in (self.monitor, self.cable) if m)
        if playing or self.paused:
            self._set_paused(not self.paused)

    def _set_paused(self, paused, quiet=False):
        self.paused = paused
        for m in (self.monitor, self.cable):
            if m:
                m.paused = paused
        self.btn_pause.config(text="▶ เล่นต่อ" if paused else "⏸ พัก")
        if not quiet:
            self.v_status.set("⏸ พักไว้ — กด ▶ เล่นต่อ หรือ Space" if paused else "▶ เล่นต่อ")

    def stop_all(self):
        self.stream_gen += 1  # ยกเลิกสตรีมที่กำลังเชื่อมต่อ
        with self.stream_lock:
            for src in self.streams:
                src.stop()
            self.streams = []
        for m in (self.monitor, self.cable):
            if m:
                m.stop_all()
        self._set_paused(False, quiet=True)
        if self.v_status.get().startswith(("⏳", "⏸")):
            self.v_status.set("■ หยุดแล้ว")

    # ---------- list
    def _refresh_list(self):
        q = self.v_search.get().lower().strip()
        sel = self.tree.selection()
        self._row_state = None  # แถวถูกสร้างใหม่ ให้ _tick ระบายสีอีกรอบ
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
        shown, total = len(self.tree.get_children()), len(self.sounds)
        self.v_count.set(f"{shown}/{total} เสียง" if q else f"{total} เสียง")

    # ---------- update
    def _auto_check_update(self):
        due = time.time() - float(self.update_state.get("last_check") or 0) > UPDATE_CHECK_HOURS * 3600
        if self.v_auto_update.get() and due:
            self._start_update_check(manual=False)

    def on_update_button(self):
        if self.update_info:
            self.open_update_dialog()
        else:
            self._start_update_check(manual=True)

    def _start_update_check(self, manual):
        if self._checking_update:
            return
        self._checking_update = True
        if manual:
            self.v_status.set("🔎 กำลังตรวจสอบเวอร์ชันใหม่...")

        def work():
            try:
                info, err = check_for_update(), None
            except Exception as e:
                info, err = None, e
            self.root.after(0, self._update_checked, info, err, manual)
        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, info, err, manual):
        self._checking_update = False
        if err:  # เช็กอัตโนมัติแล้วไม่มีเน็ต = เงียบไว้
            if manual:
                self.v_status.set(f"⚠ ตรวจสอบอัปเดตไม่ได้: {str(err)[:120]}")
            return
        self.update_state["last_check"] = time.time()
        self._save()
        if not info:
            if manual:
                self.v_status.set(f"✅ ใช้เวอร์ชันล่าสุดอยู่แล้ว ({APP_VERSION})")
            return
        if not manual and info["version"] == self.update_state.get("skip"):
            return  # ผู้ใช้กดข้ามเวอร์ชันนี้ไว้
        self.update_info = info
        self.btn_update.config(text=f"⬆ อัปเดต {info['version']}", style="Pink.TButton")
        self.v_status.set(f"🆕 มีเวอร์ชันใหม่ {info['version']} — กดปุ่ม ⬆ อัปเดต ที่มุมขวาบน")
        if manual:
            self.open_update_dialog()

    def open_update_dialog(self):
        dlg = UpdateDialog(self.root, self.update_info)
        self.root.wait_window(dlg)
        if dlg.result == "skip":
            self.update_state["skip"] = self.update_info["version"]
            self.update_info = None
            self.btn_update.config(text="🔄 ตรวจสอบอัปเดต", style="TButton")
            self.v_status.set("พร้อม")
            self._save()
        elif dlg.result:
            self.install_update(dlg.result)

    def install_update(self, path):
        self._on_close()  # บันทึก + หยุดเสียง/ffmpeg + ปิดหน้าต่าง ก่อนให้ตัวติดตั้งทับไฟล์
        run_installer(path)

    def toggle_theme(self):
        self.v_theme.set("light" if self.v_theme.get() == "dark" else "dark")
        use_theme(self.v_theme.get())
        apply_theme(self.root)
        style_window(self.root)
        self._style_tree_tags()
        self._update_status_style()
        self._update_theme_button()
        for cb in (self.cb_monitor, self.cb_cable, self.cb_mic):  # รายการ dropdown ที่สร้างไปแล้ว
            try:
                lb = f"{self.root.tk.call('ttk::combobox::PopdownWindow', cb)}.f.l"
                self.root.tk.call(lb, "configure", "-background", T["surface2"], "-foreground", T["text"],
                                  "-selectbackground", T["sel"], "-selectforeground", "#ffffff")
            except tk.TclError:
                pass
        self._save()

    def _update_theme_button(self):
        dark = self.v_theme.get() == "dark"
        self.btn_theme.config(text="☀ ธีมสว่าง" if dark else "🌙 ธีมมืด")

    def _style_tree_tags(self):
        self.tree.tag_configure("playing", background=T["playing"], foreground=T["playing_fg"])
        self.tree.tag_configure("paused", background=T["paused"], foreground=T["warn"])

    def _update_status_style(self):
        kind = status_kind(self.v_status.get())
        self.status_badge.config(text=STATUS_LABELS[kind], style=f"Badge.{kind}.TLabel")
        self.status_text.config(style=f"StatusText.{kind}.TLabel")
        self.status_line.config(style=f"Line.{kind}.TFrame")

    def _clear_search(self):
        self.v_search.set("")
        self.search_entry.focus_set()

    def _focus_first_result(self):
        items = self.tree.get_children()
        if items:
            self.tree.focus_set()
            self.tree.selection_set(items[0])
            self.tree.focus(items[0])
            self.tree.see(items[0])
        return "break"

    def _tick(self):
        playing = set()
        for m in (self.monitor, self.cable):
            if m:
                playing.update(m.playing_ids())
        state = (frozenset(playing), self.paused)
        if state != self._row_state:  # ระบายสีแถวใหม่เฉพาะตอนมีอะไรเปลี่ยน (ประหยัด CPU ตอนเปิดทิ้งไว้)
            self._row_state = state
            tag = ("paused",) if self.paused else ("playing",)
            for iid in self.tree.get_children():
                self.tree.item(iid, tags=tag if int(iid) in playing else ())
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
        self.update_state.update(d.get("update") or {})
        self.saved_devices = d.get("devices", {})

    def _setting_vars(self):
        return {"monitor_vol": self.v_monitor_vol, "cable_vol": self.v_cable_vol, "mic_vol": self.v_mic_vol,
                "to_me": self.v_to_me, "to_mic": self.v_to_mic, "passthrough": self.v_passthrough,
                "stop_prev": self.v_stop_prev, "theme": self.v_theme, "auto_update": self.v_auto_update}

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
            "update": self.update_state,
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


_instance_mutex = None  # เก็บ handle ไว้ ตัวอัปเดตจะปล่อยก่อนเปิดตัวติดตั้ง


def already_running():
    """เปิดซ้อน 2 ตัวจะทำให้ปุ่มลัดทำงาน 2 รอบ จึงอนุญาตแค่ตัวเดียว"""
    global _instance_mutex
    try:
        from ctypes import windll, wintypes
        windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
        _instance_mutex = windll.kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
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
