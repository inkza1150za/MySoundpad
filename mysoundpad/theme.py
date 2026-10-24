"""ธีมมืด/สว่างโทนชมพู-ม่วง: สี ttk, แถบชื่อหน้าต่าง, ไอคอน และสีแถบสถานะ"""


import os
import tkinter as tk
from tkinter import ttk

from .config import APP_DIR, APP_NAME, RES_DIR


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
                           (("⏳", "🔎", "⬇", "⚙", "⬆"), "busy"), (("ยังไม่ได้เลือก", "ยังไม่ได้เปิด"), "warn"),
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
    # ปุ่มเมนูเลือก (ชุดเสียง): หน้าตาเหมือนปุ่มปกติ + ลูกศร
    s.configure("TMenubutton", background=sf2, foreground=tx, bordercolor=bd, lightcolor=sf2, darkcolor=sf2,
                arrowcolor=mu, padding=(10, 5))
    s.map("TMenubutton", background=[("pressed", bd), ("active", hv)], bordercolor=[("active", purple)],
          lightcolor=[("active", hv)], darkcolor=[("active", hv)], arrowcolor=[("active", T["pink_hi"])])
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

    # ปุ่มแบบชิป (แท็บหมวดหมู่ / ปุ่มเลือกเอฟเฟกต์เสียง): เลือกอยู่ = ชมพู
    s.configure("Chip.Toolbutton", background=sf2, foreground=tx, bordercolor=bd, lightcolor=sf2, darkcolor=sf2,
                padding=(12, 4), anchor="center")
    s.map("Chip.Toolbutton", background=[("selected", pink), ("active", hv)],
          foreground=[("selected", "#ffffff")], bordercolor=[("selected", pink), ("active", purple)],
          lightcolor=[("selected", pink), ("active", hv)], darkcolor=[("selected", pink), ("active", hv)])
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
    ico = find_resource("icon.ico")
    try:
        if ico:
            # ใช้ .ico ที่มีครบทุกขนาด Windows เลือกขนาดที่ตรงพอดี (taskbar / แถบชื่อ / Alt+Tab) ไม่ต้องย่อเอง
            # ไม่ใช้ iconphoto กับ PNG 256 px เพราะ Windows ต้องย่อรูปใหญ่รูปเดียวลง ทำให้ไอคอนบน taskbar เบลอ
            # default = ใช้กับ Toplevel ทุกตัวที่สร้างภายหลังด้วย
            root.iconbitmap(default=ico)
    except tk.TclError:
        pass


def find_resource(name):
    """ไฟล์ที่แพ็กมากับ exe (RES_DIR) หรือใน build_assets ตอนรันจากซอร์สโค้ด"""
    for d in (RES_DIR, os.path.join(APP_DIR, "build_assets")):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None
