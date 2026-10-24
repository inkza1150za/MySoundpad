"""เมนูคลิกขวาแบบตัวใหญ่ตามธีม (แทน tk.Menu ที่ตัวเล็ก สีไม่ตรงธีม และเมนูย่อยต้องเลื่อนเมาส์ค้างไว้)

ตัวเลือกย่อย (โหมดเล่น / หมวด) แสดงเป็นชิปในเมนูเลย คลิกเดียวจบ
ปิดเมื่อคลิกนอกเมนู, กด Esc หรือสลับไปโปรแกรมอื่น เลื่อนด้วยลูกศรขึ้นลงแล้วกด Enter ได้
"""
import tkinter as tk

from ..theme import FONT, T


class PopupMenu(tk.Toplevel):
    MAX_W = 330  # ความกว้างสูงสุดของแถวชิปก่อนขึ้นบรรทัดใหม่

    def __init__(self, parent, min_width=0, max_height=None):
        """max_height: สูงเกินนี้ให้เลื่อนดูได้ (รายการยาว เช่น อุปกรณ์เสียง) ไม่กำหนด = สูงได้ถึงขอบจอ"""
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg=T["border"])
        self.max_height = max_height
        # เนื้อหาอยู่ใน canvas เพื่อให้เลื่อนได้เมื่อรายการยาวกว่าที่แสดง
        self.canvas = tk.Canvas(self, bg=T["surface"], highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        self.body = tk.Frame(self.canvas, bg=T["surface"], padx=6, pady=6)
        self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.scroll = None
        self.bind("<MouseWheel>", lambda e: self.scroll and self.canvas.yview_scroll(-e.delta // 40, "units"))
        if min_width:  # dropdown: กว้างอย่างน้อยเท่าช่องที่กด
            tk.Frame(self.body, width=min_width - 14, height=0, bg=T["surface"]).pack()
        self.items = []  # [(แถว, คำสั่ง)] สำหรับเลื่อนด้วยลูกศร
        self.active = None
        self.selected = None  # แถวของค่าปัจจุบัน (dropdown) เปิดมาแล้วไฮไลต์ไว้ก่อน
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Up>", lambda e: self._step(-1))
        self.bind("<Down>", lambda e: self._step(1))
        self.bind("<Return>", lambda e: self.active is not None and self._run(self.items[self.active][1]))
        self.bind("<FocusOut>", lambda e: e.widget is self and self.close())
        self.bind("<ButtonPress>", self._click_outside)

    # ---- ส่วนประกอบ
    def header(self, text):
        tk.Label(self.body, text=text, font=(FONT, 11, "bold"), bg=T["surface"], fg=T["playing_fg"],
                 anchor="w", padx=10).pack(fill="x", pady=(2, 4))

    def label(self, text):
        tk.Label(self.body, text=text, font=(FONT, 9), bg=T["surface"], fg=T["muted"],
                 anchor="w", padx=10).pack(fill="x", pady=(4, 0))

    def separator(self):
        tk.Frame(self.body, height=1, bg=T["border"]).pack(fill="x", padx=4, pady=5)

    def item(self, icon, text, command, hint="", danger=False, selected=False):
        """selected: ค่าที่เลือกอยู่ (dropdown) ตัวอักษรสีชมพูตัวหนา + ✓ ด้านขวา"""
        row = tk.Frame(self.body, bg=T["surface"], cursor="hand2")
        row.pack(fill="x")
        fg = T["err"] if danger else T["playing_fg"] if selected else T["text"]
        parts = [tk.Label(row, text=icon, width=2, font=(FONT, 12), bg=T["surface"], fg=fg)]
        parts[0].pack(side="left", padx=(8, 6), pady=5)
        if hint or selected:
            parts.append(tk.Label(row, text=hint or "✓", font=(FONT, 11 if selected else 9), bg=T["surface"],
                                  fg=fg if selected else T["muted"]))
            parts[-1].pack(side="right", padx=(16, 12))
        parts.append(tk.Label(row, text=text, font=(FONT, 11, "bold") if selected else (FONT, 11),
                              bg=T["surface"], fg=fg, anchor="w"))
        parts[-1].pack(side="left", fill="x", expand=True, padx=(0, 8))
        index = len(self.items)
        if selected:
            self.selected = index
        self.items.append((row, command))
        for w in (row, *parts):
            w.bind("<Enter>", lambda e, i=index: self._highlight(i))
            w.bind("<ButtonRelease-1>", lambda e, c=command: self._run(c))

    def chips(self, options, current, command):
        """ตัวเลือกแบบชิปในแถวเดียว (ขึ้นบรรทัดใหม่เมื่อยาวเกิน) options = [(ค่า, ชื่อ)]"""
        wrap = tk.Frame(self.body, bg=T["surface"])
        wrap.pack(fill="x", padx=8, pady=(2, 4))
        font = (FONT, 10)
        line, width = None, 0
        for value, text in options:
            w = int(self.tk.call("font", "measure", font, text)) + 30
            if line is None or width + w > self.MAX_W:
                line, width = tk.Frame(wrap, bg=T["surface"]), 0
                line.pack(anchor="w")
            on = value == current
            base, fg = (T["pink"], "#ffffff") if on else (T["surface2"], T["text"])
            chip = tk.Label(line, text=text, font=font, bg=base, fg=fg, padx=12, pady=4, cursor="hand2")
            chip.pack(side="left", padx=(0, 6), pady=3)
            if not on:
                chip.bind("<Enter>", lambda e, c=chip: c.config(bg=T["hover"]))
                chip.bind("<Leave>", lambda e, c=chip: c.config(bg=T["surface2"]))
            chip.bind("<ButtonRelease-1>", lambda e, v=value: self._run(lambda: command(v)))
            width += w + 6

    # ---- แสดง / ปิด
    def show(self, x, y, flip_y=None):
        """flip_y: ถ้าล้นจอด้านล่าง ให้เปิดขึ้นด้านบนของจุดนี้แทน (dropdown = ขอบบนของช่องที่กด)"""
        left, top, right, bottom = _work_area(x, y, self)
        self.body.update_idletasks()
        bw, bh = self.body.winfo_reqwidth(), self.body.winfo_reqheight()
        limit = min(self.max_height or bh, bottom - top - 16)
        self.canvas.config(width=bw, height=min(bh, limit), scrollregion=(0, 0, bw, bh), yscrollincrement=12)
        if bh > limit:  # ยาวเกิน: มีแถบเลื่อน + เลื่อนด้วยลูกกลิ้งเมาส์ / ลูกศรได้
            from tkinter import ttk
            self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
            self.scroll.pack(side="right", fill="y", pady=1, padx=(0, 1))
            self.canvas.config(yscrollcommand=self.scroll.set)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = x if x + w <= right else max(left, (x - w) if flip_y is None else right - w)  # ล้นขวา
        y = y if y + h <= bottom else max(top, (y if flip_y is None else flip_y) - h)    # ล้นล่าง -> เปิดขึ้น
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        _round_corners(self)
        self.lift()
        self.focus_force()
        if self.selected is not None:
            self._highlight(self.selected)
        try:
            self.grab_set()  # คลิกที่อื่นในแอป = ปิดเมนู
        except tk.TclError:
            pass

    def close(self):
        if self.winfo_exists():
            try:
                self.grab_release()
            except tk.TclError:
                pass
            self.destroy()

    def _run(self, command):
        master = self.master
        self.close()
        master.after(1, command)  # ปิดเมนูก่อน คำสั่งที่เปิดหน้าต่างใหม่ (เปลี่ยนชื่อ ฯลฯ) จะได้ไม่ติด grab

    def _click_outside(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        if w is None or w.winfo_toplevel() is not self:
            self.close()

    def _highlight(self, index):
        if self.active is not None and self.active < len(self.items):
            _paint(self.items[self.active][0], T["surface"])
        self.active = index
        row = self.items[index][0]
        _paint(row, T["hover"])
        if self.scroll:  # เลื่อนให้แถวที่เลือกอยู่ในส่วนที่มองเห็น
            total = max(1, self.body.winfo_reqheight())
            view_top, view_h = self.canvas.canvasy(0), self.canvas.winfo_height()
            y, h = row.winfo_y(), row.winfo_height()
            step = 12  # yscrollincrement: ตำแหน่งเลื่อนปัดเป็นทีละ 12 px จึงปัดให้แถวพ้นขอบเต็มแถว
            if y < view_top:
                self.canvas.yview_moveto((y // step) * step / total)
            elif y + h > view_top + view_h:
                self.canvas.yview_moveto(-(-(y + h - view_h) // step) * step / total)

    def _step(self, d):
        if self.items:
            self._highlight(((self.active if self.active is not None else -d) + d) % len(self.items))


def attach_dropdown(cb):
    """ให้ ttk.Combobox แบบ readonly เปิดรายการเป็นเมนูตัวใหญ่ของแอป แทนรายการตัวเล็กของ Tk
    (ค่ายังอ่านด้วย cb.get() และยิง <<ComboboxSelected>> เหมือนเดิม โค้ดเดิมจึงไม่ต้องแก้)"""
    def open_list(e=None):
        if cb.instate(["disabled"]):
            return "break"
        cur = cb.get()
        m = PopupMenu(cb, min_width=cb.winfo_width(), max_height=420)
        for value in cb.tk.splitlist(cb.cget("values")):
            m.item("", value, lambda v=value: (cb.set(v), cb.event_generate("<<ComboboxSelected>>")),
                   selected=value == cur)
        m.show(cb.winfo_rootx(), cb.winfo_rooty() + cb.winfo_height() + 2, flip_y=cb.winfo_rooty() - 2)
        return "break"
    for seq in ("<Button-1>", "<Alt-Down>", "<Down>", "<space>", "<Return>"):
        cb.bind(seq, open_list)


def _paint(row, color):
    row.config(bg=color)
    for w in row.winfo_children():
        w.config(bg=color)


def _work_area(x, y, widget):
    """พื้นที่ใช้งานของจอที่จุด (x, y) อยู่ (ไม่รวม taskbar) รองรับหลายจอ"""
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        u32 = ctypes.windll.user32
        u32.MonitorFromPoint.restype = ctypes.c_void_p
        u32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
        mon = u32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            r = mi.rcWork
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def _round_corners(win):
    """มุมโค้งแบบเมนูของ Windows 11 (Windows 10 ไม่มีผล)"""
    try:
        from ctypes import byref, c_int, sizeof, windll
        hwnd = windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        pref = c_int(3)  # DWMWCP_ROUNDSMALL
        windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(pref), sizeof(pref))
    except Exception:
        pass
