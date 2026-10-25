"""ธีมมืด/สว่างโทนชมพู-ม่วง: สี ttk, แถบชื่อหน้าต่าง, ไอคอน และสีแถบสถานะ"""


import os
import tkinter as tk
from tkinter import ttk

from . import rounded
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
                               ("Purple", purple, T["purple_hi"], T["purple_lo"]),
                               ("Danger", "#dc2626", "#ef4444", "#b91c1c")):  # ปุ่มยืนยันการลบ
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
    s.configure("TCombobox", padding=(6, 4), arrowsize=15)  # ช่องเลือกสูงขึ้น ลูกศรใหญ่ขึ้น กดง่าย
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
    s.configure("Horizontal.TScale", background=bg, troughcolor=sf2)  # รางและหัวจับเป็นรูปมุมมน (_rounded_styles)
    s.map("Horizontal.TScale", background=[])
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
    _rounded_styles(root, s)


# ---------- มุมมน: แทนพื้นหลังสี่เหลี่ยมของ ttk ด้วยรูปมุมโค้ง (ดู rounded.py)
def _element(root, s, name, default, states=(), border=0, padding=None, sticky="nsew", stretch=True):
    """สร้าง element รูปภาพครั้งแรก ครั้งต่อไป (สลับธีม) แค่เปลี่ยนภาพในรูปเดิม
    states = [(สถานะ..., rgba)] เรียงตามลำดับความสำคัญ (ตัวแรกที่ตรงชนะ)"""
    key = name.replace(".", "_")
    img = rounded.photo(root, f"rr_{key}", default)
    specs = [(*st[:-1], rounded.photo(root, f"rr_{key}_{i}", st[-1])) for i, st in enumerate(states)]
    if name not in s.element_names():
        opts = {"border": border, "sticky": sticky}
        # ยืดได้: ขนาดขั้นต่ำมาจากเนื้อหา ไม่ใช่ขนาดรูป ("x"/"y" = ยืดแค่ด้านเดียว อีกด้านใช้ขนาดรูป)
        if stretch in (True, "x"):
            opts["width"] = 0
        if stretch in (True, "y"):
            opts["height"] = 0
        if padding is not None:
            opts["padding"] = padding
        s.element_create(name, "image", img, *specs, **opts)


def _swap(layout, mapping, drop=()):
    """เปลี่ยนชื่อ element ใน layout (mapping) และเอา element ใน drop ออกโดยเก็บลูกไว้ (เช่น เส้นไข่ปลาตอนโฟกัส)"""
    out = []
    for name, opts in layout:
        opts = dict(opts)
        kids = opts.get("children")
        if name in drop:
            out.extend(_swap(kids, mapping, drop) if kids else [])
            continue
        if kids:
            opts["children"] = _swap(kids, mapping, drop)
        if name in mapping:
            opts.pop("border", None)  # ขนาดขอบมาจากรูปแทน
        out.append((mapping.get(name, name), opts))
    return out


def _rounded_styles(root, s):
    f = rounded.scale(root)
    px = lambda v: max(1, round(v * f))
    bg, sf, sf2, hv, bd = T["bg"], T["surface"], T["surface2"], T["hover"], T["border"]
    pink, purple = T["pink"], T["purple"]
    ring = px(2)  # เส้นโฟกัส (แทนเส้นไข่ปลา)

    def box(r, fill, border=None, bw=1, on=bg, mid=48):
        # ส่วนกลางของรูปต้องกว้างพอ: ttk ยืดรูปด้วยการปูส่วนกลางซ้ำๆ ถ้าเล็ก (2 px) จะวาดหลายพันครั้งต่อรอบ ช้ามาก
        size = 2 * (r + 1) + mid
        return rounded.rect(size, size, r, fill, on, border, bw)

    # ---- ปุ่ม: ปกติ / ชี้ / กด / โฟกัส (เส้นทึบ) / ปิดใช้งาน
    r = px(7)
    focus_drop = ("Button.focus", "Menubutton.focus", "Toolbutton.focus", "Checkbutton.focus",
                  "Radiobutton.focus", "Horizontal.Scale.focus")

    def button_states(fill, hover, press, hover_border, focus_ring):
        return [("disabled", box(r, sf)), ("pressed", box(r, press)),
                ("focus", "active", box(r, hover, focus_ring, ring)), ("focus", box(r, fill, focus_ring, ring)),
                ("active", box(r, hover, hover_border))]
    plain = button_states(sf2, hv, bd, purple, pink)
    _element(root, s, "R.Button.border", box(r, sf2, bd), plain, border=r + 1, padding=px(2))
    s.layout("TButton", _swap(s.layout("TButton"), {"Button.border": "R.Button.border"}, focus_drop))
    for name, base, hi, lo in (("Pink", pink, T["pink_hi"], T["pink_lo"]),
                               ("Purple", purple, T["purple_hi"], T["purple_lo"]),
                               ("Danger", "#dc2626", "#ef4444", "#b91c1c")):
        _element(root, s, f"R.{name}.border", box(r, base),
                 button_states(base, hi, lo, hi, rounded.mix(base, "#ffffff", 0.75)), border=r + 1, padding=px(2))
        s.layout(f"{name}.TButton", _swap(s.layout("TButton"), {"R.Button.border": f"R.{name}.border"}))
    _element(root, s, "R.Menubutton.border", box(r, sf2, bd), plain, border=r + 1, padding=px(2))
    s.layout("TMenubutton", _swap(s.layout("TMenubutton"), {"Menubutton.border": "R.Menubutton.border"}, focus_drop))

    # ---- ชิป (แท็บหมวด / เปิดใช้): ทรงแคปซูล เลือกอยู่ = ชมพู
    rc = px(11)
    white_ring = rounded.mix(pink, "#ffffff", 0.75)
    _element(root, s, "R.Chip.border", box(rc, sf2, bd), [
        ("disabled", box(rc, sf)), ("pressed", "!selected", box(rc, bd)),
        ("selected", "focus", box(rc, pink, white_ring, ring)), ("selected", "active", box(rc, T["pink_hi"])),
        ("selected", box(rc, pink)),
        ("focus", "active", box(rc, hv, pink, ring)), ("focus", box(rc, sf2, pink, ring)),
        ("active", box(rc, hv, purple))], border=rc + 1, padding=px(2))
    s.layout("Chip.Toolbutton", _swap(s.layout("Toolbutton"), {"Toolbutton.border": "R.Chip.border"}, focus_drop))

    # ---- ช่องกรอก / ช่องเลือก / ช่องตัวเลข: ขอบม่วงตอนชี้ ชมพูตอนพิมพ์
    rf = px(7)
    field = [("disabled", box(rf, sf, bd)), ("focus", box(rf, sf2, pink, ring)), ("hover", box(rf, sf2, purple))]
    _element(root, s, "R.field", box(rf, sf2, bd), field, border=rf + 1, padding=px(3))
    s.layout("TEntry", _swap(s.layout("TEntry"), {"Entry.field": "R.field"}))
    s.layout("TSpinbox", _swap(s.layout("TSpinbox"), {"Spinbox.field": "R.field"}))
    s.layout("TCombobox", [("R.field", {"sticky": "nswe", "children": [  # ลูกศรอยู่ในกรอบโค้งด้วย
        ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"sticky": "nswe", "children": [("Combobox.textarea", {"sticky": "nswe"})]})]})])
    for w in ("TEntry", "TSpinbox", "TCombobox"):  # ลูกศรวาดบนพื้นช่องเดียวกัน ไม่มีกรอบของตัวเอง
        s.configure(w, background=sf2, bordercolor=sf2, lightcolor=sf2, darkcolor=sf2)
        s.map(w, bordercolor=[], lightcolor=[], background=[])
    s.map("TCombobox", fieldbackground=[("readonly", sf2)], foreground=[("readonly", T["text"])],
          selectbackground=[("readonly", sf2)], selectforeground=[("readonly", T["text"])],
          arrowcolor=[("hover", T["pink_hi"])])

    # ---- ช่องติ๊ก / ปุ่มเลือกวงกลม
    cs, cr, gap = px(17), px(4), px(7)
    tick = lambda fill, border=None, mark=None: rounded.check(cs, cr, fill, bg, border, px(1.5), mark, gap)
    _element(root, s, "R.check", tick(sf2, bd), [
        ("disabled", tick(sf, bd)), ("selected", "active", tick(T["pink_hi"], mark="#ffffff")),
        ("selected", tick(pink, mark="#ffffff")), ("focus", tick(sf2, pink)), ("active", tick(sf2, purple))],
        sticky="", stretch=False)
    s.layout("TCheckbutton", _swap(s.layout("TCheckbutton"), {"Checkbutton.indicator": "R.check"}, focus_drop))
    radio = lambda fill, border=None, center=None: rounded.dot(cs, fill, bg, border, px(1.5), center, gap)
    _element(root, s, "R.radio", radio(sf2, bd), [
        ("disabled", radio(sf, bd)), ("selected", radio(sf2, pink, "#ffffff" if T["dark"] else pink)),
        ("focus", radio(sf2, pink)), ("active", radio(sf2, purple))], sticky="", stretch=False)
    s.layout("TRadiobutton", _swap(s.layout("TRadiobutton"), {"Radiobutton.indicator": "R.radio"}, focus_drop))

    # ---- แถบเลื่อน: รางโค้งบาง + หัวจับวงกลม
    th = px(6)
    track = sf2 if T["dark"] else bd  # ธีมสว่าง: สีพื้นช่องจางเกินไปบนพื้นขาว
    _element(root, s, "R.scale.trough", rounded.rect(2 * th + 64, th, th / 2, track, bg), border=(th, 0, th, 0),
             sticky="ew", padding=0, stretch="x")
    ks = px(18)
    knob = lambda border: rounded.dot(ks, "#ffffff", bg, border, px(2))
    _element(root, s, "R.scale.slider", knob(pink), [("disabled", knob(bd)), ("pressed", knob(T["pink_lo"])),
                                                     ("active", knob(T["pink_hi"]))], sticky="", stretch=False)
    s.layout("Horizontal.TScale", _swap(s.layout("Horizontal.TScale"),
                                        {"Horizontal.Scale.trough": "R.scale.trough",
                                         "Horizontal.Scale.slider": "R.scale.slider"}, focus_drop))

    # ---- หลอดดาวน์โหลด
    ph = px(8)
    _element(root, s, "R.progress.trough", rounded.rect(2 * ph + 64, ph, ph / 2, track, bg), border=(ph, 0, ph, 0),
             padding=0, stretch="x")
    _element(root, s, "R.progress.pbar", rounded.rect(2 * ph + 64, ph, ph / 2, pink, track), border=(ph, 0, ph, 0),
             padding=0, stretch="x")
    s.layout("Horizontal.TProgressbar", [("R.progress.trough", {"sticky": "nswe", "children": [
        ("R.progress.pbar", {"side": "left", "sticky": "ns"})]})])

    # ---- แถบเลื่อนรายการ: ตัวจับโค้งมน ไม่มีปุ่มลูกศร
    # "Popup." = ในเมนู/รายการ dropdown ที่พื้นเป็นสี surface
    sw = px(12)
    for prefix, on in (("", bg), ("Popup.", sf)):
        thumb = lambda fill, on=on: rounded.rect(sw, 2 * sw + 48, (sw - px(4)) / 2, fill, on, inset=px(2))
        name = f"R.{prefix}v.thumb"  # ต้องลงท้าย .thumb: ttk หา element นี้จากชื่อเพื่อวางตามตำแหน่งเลื่อน
        _element(root, s, name, thumb(bd if T["dark"] else T["faint"]),
                 [("pressed", thumb(T["muted"] if T["dark"] else T["text"])), ("active", thumb(T["muted"]))],
                 border=(0, sw, 0, sw), padding=0, stretch="y")
        s.layout(f"{prefix}Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            (name, {"sticky": "nswe"})]})])
        s.configure(f"{prefix}Vertical.TScrollbar", troughcolor=on, bordercolor=on, background=on)

    # ---- กรอบ (อุปกรณ์เสียง / การเล่น) และกรอบรายการเสียง
    rb = px(10)
    _element(root, s, "R.labelframe", box(rb, bg, bd, mid=256), border=rb + 1, padding=px(2))
    s.layout("TLabelframe", [("R.labelframe", {"sticky": "nswe"})])
    # padding ต้องพอให้หัวคอลัมน์/แถวสี่เหลี่ยมไม่ทับเส้นขอบโค้ง (เส้นโค้งห่างมุมเข้ามา ~0.3 เท่าของรัศมี)
    _element(root, s, "R.tree", box(rb, sf, bd, mid=256), border=rb + 1, padding=round(rb * 0.4) + 1)
    s.layout("Treeview", _swap(s.layout("Treeview"), {"Treeview.field": "R.tree"}))
    # หัวคอลัมน์: พื้นเดียวกับตาราง ไม่มีกรอบสี่เหลี่ยม (มุมจึงกลืนกับขอบโค้ง) มีแค่เส้นล่างและเส้นคั่นสั้นๆ
    gap = px(8)
    _element(root, s, "R.heading", rounded.header_cell(48, 2 * gap + 16, sf, bd, gap), border=(0, gap, 1, gap),
             padding=0)
    s.layout("Treeview.Heading", _swap(s.layout("Treeview.Heading"), {"Treeheading.cell": "R.heading"},
                                       ("Treeheading.border",)))  # กรอบเดิมทับเส้นล่าง/เส้นคั่น
    s.configure("Treeview.Heading", background=sf, bordercolor=sf, lightcolor=sf, darkcolor=sf)
    s.map("Treeview.Heading", background=[], foreground=[("active", T["pink_hi"])])  # ชี้ = ตัวอักษรชมพู

    # ---- ป้ายสถานะด้านล่าง: ทรงแคปซูล
    rp = px(10)
    for kind, (badge_bg, _, _, _) in status_colors().items():
        _element(root, s, f"R.badge.{kind}", box(rp, badge_bg, on=sf), border=rp + 1, padding=0)
        s.layout(f"Badge.{kind}.TLabel", _swap(s.layout("TLabel"), {"Label.border": f"R.badge.{kind}"}))


def style_window(win):
    """พื้นหลังตามธีม + แถบชื่อหน้าต่างมืด/สว่างตามธีม และขอบสีชมพู (สีแถบและขอบใช้ได้บน Windows 11)"""
    win.configure(bg=T["bg"])
    # หน้าต่างที่เพิ่งสร้าง: Windows แสดงเป็นสีขาวก่อน แล้วสีธีม/แถบชื่อค่อยตามมา (เห็นแวบขาว)
    # จึงทำให้โปร่งใสไว้จนตั้งสีครบ แล้วค่อยแสดง
    fresh = not win.winfo_ismapped()
    if fresh:
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            fresh = False
    _style_titlebar(win)

    def finish(tries=0):
        if not win.winfo_exists():
            return
        if not win.winfo_ismapped() and tries < 50:  # ยังซ่อนอยู่ (เช่น กล่องข้อความที่ยังจัดตำแหน่ง) รอให้ขึ้นจอก่อน
            win.after(20, finish, tries + 1)
            return
        # ตั้งสีตอนกรอบหน้าต่างยังวาดไม่เสร็จจะไม่ติด จึงตั้งซ้ำหลังขึ้นจอ
        _style_titlebar(win)
        if fresh:
            win.after(30, lambda: win.winfo_exists() and win.attributes("-alpha", 1.0))
    win.after(60, finish)


def _style_titlebar(win):
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
