"""ค่าคงที่ทั้งแอป: ชื่อ/เวอร์ชัน ที่เก็บข้อมูล และค่าตั้งต้นของเสียง สตรีม YouTube และตัวอัปเดต"""


import os
import re
import sys


APP_NAME = "MySoundpad"


APP_VERSION = "1.6.0"


FROZEN = getattr(sys, "frozen", False)  # True เมื่อรันจาก .exe (PyInstaller)


# โฟลเดอร์โปรเจกต์ (ตอนรันจากซอร์สโค้ด) หรือโฟลเดอร์ของ exe; ไฟล์นี้อยู่ใน mysoundpad/ จึงขึ้นไป 1 ชั้น
APP_DIR = os.path.dirname(sys.executable) if FROZEN else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
