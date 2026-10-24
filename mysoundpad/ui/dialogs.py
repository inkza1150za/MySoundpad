"""หน้าต่างย่อย: ตั้งปุ่มลัด และอัปเดตเวอร์ชัน"""


import threading
import tkinter as tk
from tkinter import ttk

from ..config import APP_VERSION, FROZEN
from ..theme import FONT, T, style_window
from ..updater import download_update, plain_notes


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
