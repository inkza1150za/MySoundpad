"""กล่องข้อความ/ถามยืนยันตามธีมของแอป (แทน tkinter.messagebox ที่เป็นหน้าต่างสีขาวของ Windows)

ใช้แบบเดียวกับ messagebox: askyesno / showinfo / showwarning / showerror
Enter = ปุ่มหลัก, Esc หรือปิดหน้าต่าง = ยกเลิก
"""
import tkinter as tk
from tkinter import ttk

from ..theme import FONT, T, style_window

ICONS = {"question": "❓", "info": "ℹ️", "warning": "⚠️", "error": "⛔"}


class _Box(tk.Toplevel):
    def __init__(self, parent, title, message, kind, buttons, danger=False):
        super().__init__(parent)
        self.withdraw()
        style_window(self)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.result = False

        frm = ttk.Frame(self, padding=(20, 18, 20, 14))
        frm.pack(fill="both", expand=True)
        body = ttk.Frame(frm)
        body.pack(fill="x")
        ttk.Label(body, text=ICONS[kind], font=(FONT, 22)).pack(side="left", anchor="n", padx=(0, 14))
        ttk.Label(body, text=message, font=(FONT, 11), wraplength=380, justify="left").pack(side="left", anchor="w")

        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(18, 0))
        primary = None
        for i, (text, value) in enumerate(buttons):  # ปุ่มแรก = ปุ่มหลัก อยู่ขวาสุด
            main = i == 0
            style = ("Danger.TButton" if danger else "Pink.TButton") if main else "TButton"
            b = ttk.Button(row, text=text, style=style, command=lambda v=value: self._close(v))
            b.pack(side="right", padx=(8, 0))
            if main:
                primary = b
        self.bind("<Return>", lambda e: self._close(buttons[0][1]))
        self.bind("<Escape>", lambda e: self._close(False))
        self.protocol("WM_DELETE_WINDOW", lambda: self._close(False))

        # กลางหน้าต่างแม่
        self.update_idletasks()
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.deiconify()
        self.grab_set()
        primary.focus_set()

    def _close(self, value):
        self.result = value
        self.grab_release()
        self.destroy()


def _show(title, message, kind, buttons, parent=None, danger=False):
    parent = parent or tk._default_root
    box = _Box(parent, title, message, kind, buttons, danger)
    parent.wait_window(box)
    return box.result


def askyesno(title, message, parent=None, yes="ตกลง", no="ยกเลิก", danger=False):
    """danger=True: ปุ่มยืนยันเป็นสีแดง (ลบ / ทับของเดิม)"""
    return _show(title, message, "warning" if danger else "question", [(yes, True), (no, False)], parent, danger)


def showinfo(title, message, parent=None):
    _show(title, message, "info", [("ตกลง", True)], parent)


def showwarning(title, message, parent=None):
    _show(title, message, "warning", [("ตกลง", True)], parent)


def showerror(title, message, parent=None):
    _show(title, message, "error", [("ตกลง", True)], parent)
