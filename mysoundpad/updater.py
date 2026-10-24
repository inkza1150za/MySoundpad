"""อัปเดตแอป: เช็ก GitHub Releases, ดาวน์โหลดพร้อมตรวจ SHA-256, รันตัวติดตั้งแบบเงียบ"""


import os
import json
import re
import subprocess

from . import config
from .config import APP_NAME, APP_VERSION, UPDATE_ASSET_RE, UPDATE_REPO
from .instance import release_instance_lock


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
    req = urllib.request.Request(config.UPDATE_API, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}",
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
    release_instance_lock()
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
