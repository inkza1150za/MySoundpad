"""หลอดความคืบหน้าเพลงที่กำลังเล่น: คลิกหรือลากเพื่อกระโดดไปช่วงอื่น"""
import tkinter as tk

from ..theme import T


def fmt_clock(sec):
    """วินาที -> '1:23' (หรือ '1:02:03' ถ้าเกินชั่วโมง)"""
    sec = int(max(0.0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class SeekBar(tk.Canvas):
    H, PAD, R = 22, 8, 6

    def __init__(self, parent, on_seek):
        super().__init__(parent, height=self.H, highlightthickness=0, bd=0)
        self.on_seek = on_seek  # เรียกตอนปล่อยเมาส์ด้วยสัดส่วน 0..1 (ระหว่างลากยังไม่กระโดด ffmpeg จะได้ไม่เปิดใหม่รัวๆ)
        self.frac = 0.0
        self.enabled = False
        self.drag = None  # สัดส่วนที่กำลังลากอยู่ (None = ไม่ได้ลาก)
        self._drawn = None
        self.bind("<Configure>", lambda e: self.redraw(force=True))
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, frac, enabled):
        self.frac = min(max(frac, 0.0), 1.0)
        if self.enabled != enabled:
            self.enabled = enabled
            self.config(cursor="hand2" if enabled else "")
            if not enabled:
                self.drag = None
        self.redraw()

    @property
    def shown(self):
        return self.drag if self.drag is not None else self.frac

    def redraw(self, force=False):
        w = self.winfo_width()
        x0, x1, y = self.PAD, max(self.PAD + 1, w - self.PAD), self.H // 2
        x = x0 + (x1 - x0) * self.shown
        state = (round(x), self.enabled, self.drag is not None, w, T["pink"])
        if state == self._drawn and not force:
            return  # ไม่มีอะไรเปลี่ยน ไม่ต้องวาดใหม่
        self._drawn = state
        self.delete("all")
        self.config(bg=T["bg"])
        self.create_line(x0, y, x1, y, width=6, capstyle="round", fill=T["surface2"] if T["dark"] else T["border"])
        if self.enabled:
            if x > x0:
                self.create_line(x0, y, x, y, width=6, capstyle="round", fill=T["pink"])
            r = self.R + (1 if self.drag is not None else 0)
            self.create_oval(x - r, y - r, x + r, y + r, fill="#ffffff", outline=T["pink"], width=2)

    def _frac_at(self, x):
        w = max(1, self.winfo_width() - 2 * self.PAD)
        return min(max((x - self.PAD) / w, 0.0), 1.0)

    def _press(self, e):
        if self.enabled:
            self.drag = self._frac_at(e.x)
            self.redraw()

    def _motion(self, e):
        if self.drag is not None:
            self.drag = self._frac_at(e.x)
            self.redraw()

    def _release(self, e):
        if self.drag is not None:
            self.frac, self.drag = self._frac_at(e.x), None
            self.redraw()
            self.on_seek(self.frac)
