"""หน้าต่างปรับเสียงเอง: แถบเลื่อนทุกเอฟเฟกต์ (หุ่นยนต์, เอเลี่ยน, ปีศาจ ...) ได้ยินผลทันทีขณะลาก

ไม่บล็อกหน้าจอหลัก (เปิดค้างไว้แล้วใช้แอปต่อได้) ค่าในแถบส่งไปที่ SoundpadApp ซึ่งเป็นเจ้าของสถานะเสียงทั้งหมด
"""
import tkinter as tk
from tkinter import ttk, messagebox

from ..theme import style_window
from ..voicefx import DEFAULT_PARAMS, PERCENT_KEYS, PRESETS, SLIDERS

# จัดกลุ่มแถบเป็น 2 คอลัมน์ให้สูงใกล้กัน
COLUMNS = [["ระดับเสียง", "หุ่นยนต์ / โลหะ", "โทนเสียง"], ["แปลกประหลาด", "ห้อง"]]
CUSTOM = "custom"


def to_slider(key, value):
    return value * 100 if key in PERCENT_KEYS else value


def from_slider(key, value):
    if key in PERCENT_KEYS:
        return round(value) / 100
    if key == "pitch":
        return round(value * 2) / 2  # ทีละครึ่งของครึ่งเสียง
    return float(round(value))


def value_text(key, value, unit):
    if key in PERCENT_KEYS:
        return f"{round(value * 100)}%"
    if key == "pitch":
        return "ปกติ" if value == 0 else f"{value:+g} {unit}"
    if (key == "lowcut" and value <= 0) or (key == "highcut" and value >= DEFAULT_PARAMS["highcut"]):
        return "ปิด"
    return f"{value:g} {unit}"


class VoiceWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        style_window(self)
        self.title("🎛 ปรับเสียงเอง")
        self.resizable(False, False)
        self.transient(app.root)
        self.vars, self.texts = {}, {}
        self._loading = False

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        top = ttk.Frame(frm)
        top.pack(fill="x")
        ttk.Label(top, text="ชุดเสียง").pack(side="left")
        self.cb_preset = ttk.Combobox(top, state="readonly", width=24)
        self.cb_preset.pack(side="left", padx=(8, 12))
        self.cb_preset.bind("<<ComboboxSelected>>", self._on_pick)
        ttk.Checkbutton(top, text="เปิดเปลี่ยนเสียง", variable=app.v_fx_on, style="Chip.Toolbutton",
                        command=app._apply_fx).pack(side="left")
        ttk.Checkbutton(top, text="ฟังเสียงตัวเอง", variable=app.v_fx_monitor,
                        command=app._apply_fx).pack(side="right")

        body = ttk.Frame(frm)
        body.pack(fill="x", pady=(10, 0))
        by_group = {}
        for key, label, lo, hi, unit, group in SLIDERS:
            by_group.setdefault(group, []).append((key, label, lo, hi, unit))
        for c, groups in enumerate(COLUMNS):
            col = ttk.Frame(body)
            col.grid(row=0, column=c, sticky="n", padx=(0, 10) if c == 0 else 0)
            for group in groups:
                box = ttk.LabelFrame(col, text=group, padding=(10, 4, 10, 6))
                box.pack(fill="x", pady=(0, 8))
                for r, (key, label, lo, hi, unit) in enumerate(by_group[group]):
                    ttk.Label(box, text=label, width=16).grid(row=r, column=0, sticky="w", pady=3)
                    var = tk.DoubleVar()
                    ttk.Scale(box, from_=lo, to=hi, variable=var, length=210,
                              command=lambda _v, k=key: self._on_slide(k)).grid(row=r, column=1, padx=6)
                    txt = ttk.Label(box, width=13, anchor="e")
                    txt.grid(row=r, column=2, sticky="e")
                    self.vars[key], self.texts[key] = (var, unit), txt

        ttk.Label(frm, text="ลากแถบแล้วเสียงเปลี่ยนทันที — เปิด 'ฟังเสียงตัวเอง' เพื่อลองฟังในหูฟัง",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="💾 บันทึกเป็นชุดใหม่", style="Pink.TButton", command=self.save_as).pack(side="left")
        self.btn_rename = ttk.Button(btns, text="✏ เปลี่ยนชื่อ", command=self.rename)
        self.btn_rename.pack(side="left", padx=(6, 0))
        self.btn_delete = ttk.Button(btns, text="🗑 ลบชุดนี้", command=self.delete)
        self.btn_delete.pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="↺ รีเซ็ต", command=self.reset).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="ปิด", command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda e: self.destroy())
        self.load_from_app()

    # ---- ซิงก์กับแอป
    def _choices(self):
        items = [(k, label) for k, (label, _) in PRESETS.items()]
        items += [("u:" + name, "⭐ " + name) for name in self.app.voice_presets]
        if self.app.v_fx_preset.get() == CUSTOM:
            items.append((CUSTOM, "🎛 กำหนดเอง"))
        return items

    def load_from_app(self):
        """ดึงค่าปัจจุบันของแอปมาแสดง (หลังเลือกชุดเสียงจากที่ไหนก็ตาม)"""
        self._loading = True
        try:
            items = self._choices()
            self._keys = [k for k, _ in items]
            self.cb_preset.config(values=[label for _, label in items])
            cur = self.app.v_fx_preset.get()
            if cur in self._keys:
                self.cb_preset.current(self._keys.index(cur))
            for key, (var, unit) in self.vars.items():
                v = self.app.fx_params.get(key, DEFAULT_PARAMS[key])
                var.set(to_slider(key, v))
                self.texts[key].config(text=value_text(key, v, unit))
            user = cur.startswith("u:")
            for b in (self.btn_rename, self.btn_delete):
                b.state(["!disabled"] if user else ["disabled"])
        finally:
            self._loading = False

    def _params(self):
        return {key: from_slider(key, var.get()) for key, (var, _) in self.vars.items()}

    def _on_slide(self, key):
        if self._loading:
            return
        var, unit = self.vars[key]
        self.texts[key].config(text=value_text(key, from_slider(key, var.get()), unit))
        self.app.set_fx_custom(self._params(), refresh=False)  # ไม่ดึงค่ากลับมาทับแถบที่กำลังลาก
        i = self.cb_preset.current()
        if i < 0 or self._keys[i] != CUSTOM:
            self.load_from_app()  # ชื่อชุดเปลี่ยนเป็น "กำหนดเอง"

    def _on_pick(self, _=None):
        i = self.cb_preset.current()
        if i >= 0 and self._keys[i] != CUSTOM:
            self.app.select_fx_preset(self._keys[i])

    # ---- ชุดเสียงของผู้ใช้
    def _ask_name(self, title, initial=""):
        name = self.app._ask_text(title, initial)
        if name and (name in self.app.voice_presets) and name != initial:
            if not messagebox.askyesno(title, f"มีชุดเสียง '{name}' อยู่แล้ว บันทึกทับไหม?", parent=self):
                return None
        return name

    def save_as(self):
        name = self._ask_name("ตั้งชื่อชุดเสียงใหม่")
        if name:
            self.app.voice_presets[name] = self._params()
            self.app.select_fx_preset("u:" + name)

    def rename(self):
        old = self.app.v_fx_preset.get()[2:]
        new = self._ask_name("เปลี่ยนชื่อชุดเสียง", old)
        if new and new != old:
            presets = self.app.voice_presets
            # คงลำดับเดิมในเมนู
            self.app.voice_presets = {(new if k == old else k): v for k, v in presets.items() if k != new or k == old}
            self.app.select_fx_preset("u:" + new)

    def delete(self):
        name = self.app.v_fx_preset.get()[2:]
        if messagebox.askyesno("ลบชุดเสียง", f"ลบชุดเสียง '{name}'?", parent=self):
            self.app.voice_presets.pop(name, None)
            self.app.set_fx_custom(self.app.fx_params)  # เสียงที่ได้ยินอยู่ไม่เปลี่ยน แค่ไม่มีชื่อแล้ว

    def reset(self):
        self.app.set_fx_custom(dict(DEFAULT_PARAMS))
