"""วาดรูปมุมโค้งขอบเนียน (anti-alias) เป็น PhotoImage ด้วย numpy ล้วน ไว้ทำปุ่ม/ช่องกรอก/ชิปมุมมน

ttk วาดได้แค่สี่เหลี่ยม จึงใช้รูปเป็นพื้นหลังแทน (ttk ยืดส่วนกลางของรูป มุมคงความโค้งเดิม)
ทุกรูปทาสีพื้นด้านหลัง (bg) ไว้ในตัว ขอบโค้งจึงกลืนกับพื้นหน้าต่างพอดี
"""
import base64
import struct
import tkinter as tk
import zlib

import numpy as np

_images = {}  # (interpreter, ชื่อ) -> PhotoImage (ต้องเก็บไว้ ไม่งั้นรูปหายเมื่อโดนเก็บขยะ)


def scale(widget):
    """ตัวคูณขนาดตาม DPI ของจอ (100% = 1.0, 150% = 1.5)"""
    return max(1.0, widget.winfo_fpixels("1i") / 96)


def _rgb(color):
    return np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], float)


def mix(a, b, t):
    """ผสมสี a -> b ตามสัดส่วน t (0..1) คืนเป็น '#rrggbb'"""
    c = _rgb(a) * (1 - t) + _rgb(b) * t
    return "#" + "".join(f"{int(round(v)):02x}" for v in c)


def _sdf(w, h, r, inset=0.0):
    """ระยะจากขอบสี่เหลี่ยมมุมโค้ง (ลบ = อยู่ข้างใน) ของทุก pixel"""
    y, x = np.mgrid[0:h, 0:w] + 0.5
    hw, hh = w / 2 - inset, h / 2 - inset
    r = min(r, hw, hh)
    qx = np.abs(x - w / 2) - (hw - r)
    qy = np.abs(y - h / 2) - (hh - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def _compose(layers, bg, w, h):
    """layers = [(alpha 0..1, สี)] ทับกันตามลำดับบนพื้น bg -> RGBA uint8"""
    out = np.broadcast_to(_rgb(bg), (h, w, 3)).copy()
    for a, color in layers:
        out = out * (1 - a[..., None]) + _rgb(color) * a[..., None]
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = np.clip(np.round(out), 0, 255)
    rgba[..., 3] = 255
    return rgba


def rect(w, h, r, fill, bg, border=None, bw=1.0, inset=0.0):
    """สี่เหลี่ยมมุมโค้ง r: พื้น fill ขอบ border หนา bw วางบนพื้น bg"""
    d = _sdf(w, h, r, inset)
    outer = np.clip(0.5 - d, 0, 1)
    if not border or border == fill or bw <= 0:
        return _compose([(outer, fill)], bg, w, h)
    inner = np.clip(0.5 - (d + bw), 0, 1)
    return _compose([(outer, border), (inner, fill)], bg, w, h)


def _segments(w, h, points, width):
    """alpha ของเส้นหนา width ที่ลากผ่านจุด points (พิกัด 0..1 ของรูป) ปลายมน"""
    y, x = np.mgrid[0:h, 0:w] + 0.5
    d = np.full((h, w), np.inf)
    pts = [(px * w, py * h) for px, py in points]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        vx, vy = bx - ax, by - ay
        t = np.clip(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        d = np.minimum(d, np.hypot(x - ax - t * vx, y - ay - t * vy))
    return np.clip(width / 2 - d + 0.5, 0, 1)


def check(size, r, fill, bg, border=None, bw=1.0, mark=None, margin_right=0):
    """ช่องติ๊ก: สี่เหลี่ยมมุมโค้ง + เครื่องหมายถูกสี mark (None = ไม่ติ๊ก) เว้นที่ขวา margin_right"""
    w = size + margin_right
    d = _sdf(size, size, r)
    layers = [(np.clip(0.5 - d, 0, 1), border or fill)]
    if border and border != fill:
        layers.append((np.clip(0.5 - (d + bw), 0, 1), fill))
    if mark:
        layers.append((_segments(size, size, [(0.27, 0.53), (0.44, 0.69), (0.74, 0.35)], size * 0.13), mark))
    layers = [(np.pad(a, ((0, 0), (0, margin_right))), c) for a, c in layers]
    return _compose(layers, bg, w, size)


def dot(size, fill, bg, border=None, bw=1.0, center=None, margin_right=0):
    """วงกลม (ปุ่มเลือกแบบวงกลม / หัวจับแถบเลื่อน) + จุดตรงกลางสี center"""
    w = size + margin_right
    d = _sdf(size, size, size / 2)
    layers = [(np.clip(0.5 - d, 0, 1), border or fill)]
    if border and border != fill:
        layers.append((np.clip(0.5 - (d + bw), 0, 1), fill))
    if center:
        layers.append((np.clip(0.5 - (d + size * 0.28), 0, 1), center))
    layers = [(np.pad(a, ((0, 0), (0, margin_right))), c) for a, c in layers]
    return _compose(layers, bg, w, size)


def pause_bars(size, color):
    """ไอคอนพัก: ขีดคู่มุมโค้ง พื้นโปร่งใส (ขนาดคุมได้เอง ไม่ขึ้นกับฟอนต์ของ Windows)"""
    h = int(round(size))                 # สูงเท่า ■ / ▶ บนปุ่มข้างๆ
    w = int(round(size * 0.85))
    bw = w * 0.38                        # ความกว้างแต่ละขีด (ช่องว่างแคบ ขีดอยู่ใกล้กัน)
    gap = w - 2 * bw
    y, x = np.mgrid[0:h, 0:w] + 0.5
    a = np.zeros((h, w))
    for x0 in (0.0, bw + gap):
        cx, hw, hh, r = x0 + bw / 2, bw / 2, h / 2, bw * 0.35
        qx = np.abs(x - cx) - (hw - r)
        qy = np.abs(y - h / 2) - (hh - r)
        d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
        a = np.maximum(a, np.clip(0.5 - d, 0, 1))
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = _rgb(color).astype(np.uint8)
    rgba[..., 3] = np.round(a * 255).astype(np.uint8)
    return rgba


def play_triangle(size, color):
    """ไอคอนเล่น ▶ พื้นโปร่งใส ขนาดเดียวกับ pause_bars (ปุ่มพัก/เล่นต่อจึงกว้างเท่ากันทั้งสองสถานะ)"""
    h = int(round(size))
    w = int(round(size * 0.85))
    y, x = np.mgrid[0:h, 0:w] + 0.5
    # สามเหลี่ยมจุดยอด (0,0) (0,h) (w,h/2): ระยะถึงขอบซ้าย, ขอบเอียงบน y = kx, ขอบเอียงล่าง y = h - kx
    k = (h / 2) / w
    norm = np.hypot(1, k)
    d = np.maximum.reduce([-x, (k * x - y) / norm, (y - h + k * x) / norm])
    a = np.clip(0.5 - d, 0, 1)
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = _rgb(color).astype(np.uint8)
    rgba[..., 3] = np.round(a * 255).astype(np.uint8)
    return rgba


def header_cell(w, h, fill, line, gap):
    """หัวคอลัมน์แบบไม่มีกรอบ: พื้น fill + เส้นล่าง + เส้นคั่นสั้นด้านขวา (เว้นบนล่าง gap px)"""
    rgba = rect(w, h, 0, fill, fill)
    c = np.array([int(line[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)
    rgba[-1, :, :3] = c
    rgba[gap:h - gap, -1, :3] = c
    return rgba


def _png(rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def photo(master, name, rgba):
    """PhotoImage ชื่อคงที่: เรียกซ้ำด้วยชื่อเดิม = เปลี่ยนภาพในรูปเดิม (ตอนสลับธีม ปุ่มทุกปุ่มเปลี่ยนตามทันที)"""
    data = base64.b64encode(_png(rgba))
    key = (master.tk, name)
    img = _images.get(key)
    if img is None:
        img = tk.PhotoImage(master=master, name=name, data=data, format="png")
        _images[key] = img
    else:
        img.configure(data=data, format="png")
    return img
