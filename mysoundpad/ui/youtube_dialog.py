"""หน้าต่าง YouTube: ใส่ลิงก์, หลอดเลือกช่วง 2 หมุด, ฟังตัวอย่างผ่านหูฟัง"""


import threading
import time
import tkinter as tk
from tkinter import ttk

from ..audio import OutputMixer
from ..config import STREAM_TIMEOUT, YT_URL_RE
from ..streaming import StreamSource
from ..theme import T, style_window
from ..youtube import _stream_url_cache, friendly_yt_error, parse_time, youtube_info, youtube_stream_url
from . import msgbox


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

    def __init__(self, parent, on_update, preview_device, url=None):
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
        if url:  # ลากลิงก์มาวางบนหน้าต่างหลัก
            self.v_url.set(url)
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
            msgbox.showwarning("ลิงก์ไม่ถูกต้อง", "ใส่ลิงก์ youtube.com หรือ youtu.be", parent=self)
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
