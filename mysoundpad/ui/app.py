"""หน้าจอหลัก: รายการเสียง, เล่น/พัก/หยุด, อุปกรณ์เสียง, ตั้งค่า และบันทึกข้อมูล"""


import os
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import sounddevice as sd
import soundfile as sf

from .. import config
from ..audio import LONG_SOUND_SECONDS, MicPassthrough, OutputMixer, list_devices, load_audio
from ..config import APP_NAME, APP_VERSION, AUDIO_EXT, STREAM_PREBUFFER, STREAM_TIMEOUT, UPDATE_CHECK_HOURS, YT_MAX_MINUTES
from ..hotkeys import HotkeyManager, hotkey_key, hotkey_text
from ..streaming import FileSource, StreamSource
from ..theme import FONT, STATUS_LABELS, T, apply_theme, find_resource, set_app_icon, status_kind, style_window, use_theme
from .dialogs import HotkeyDialog, UpdateDialog
from .youtube_dialog import YouTubeDialog
from ..updater import check_for_update, run_installer
from ..youtube import _stream_url_cache, download_latest_ytdlp, friendly_yt_error, import_ytdlp, youtube_download, youtube_info, youtube_stream_url


class SoundpadApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION}")
        set_app_icon(root)
        root.geometry("980x720")  # ปรับอีกครั้งหลังสร้างหน้าจอ ให้พอดีกับเนื้อหาจริง

        self.sounds = []  # {"id","path","name","hotkey"}
        self.next_id = 1
        self.monitor = None
        self.cable = None
        self.mic = None
        self.streams = []  # StreamSource ที่ ffmpeg ยังทำงานอยู่
        self.stream_lock = threading.Lock()
        self.stream_gen = 0  # เพิ่มทุกครั้งที่กดหยุด เพื่อยกเลิกสตรีมที่ยังเชื่อมต่อไม่เสร็จ
        self.paused = False
        self._row_state = None  # (เสียงที่เล่นอยู่, พักอยู่ไหม) ที่ระบายสีแถวไว้ล่าสุด

        self.v_monitor_vol = tk.DoubleVar(value=70)
        self.v_cable_vol = tk.DoubleVar(value=70)
        self.v_mic_vol = tk.DoubleVar(value=100)
        self.v_to_me = tk.BooleanVar(value=True)
        self.v_to_mic = tk.BooleanVar(value=True)
        self.v_passthrough = tk.BooleanVar(value=True)
        self.v_stop_prev = tk.BooleanVar(value=True)
        self.v_hotkeys_on = tk.BooleanVar(value=True)
        self.v_theme = tk.StringVar(value="dark")
        self.v_auto_update = tk.BooleanVar(value=True)
        self.update_state = {"last_check": 0, "skip": ""}  # บันทึกลงไฟล์ตั้งค่า
        self.update_info = None  # เวอร์ชันใหม่ที่เจอ (dict จาก check_for_update)
        self._checking_update = False
        self.v_search = tk.StringVar()
        self.v_status = tk.StringVar(value="พร้อม")
        self.stop_hotkey = {"mods": [], "vk": 0x13}  # Pause
        self.saved_devices = {}

        self.out_devs = list_devices("out")
        self.in_devs = list_devices("in")

        self.hotkeys = HotkeyManager()
        self._load()
        use_theme(self.v_theme.get())  # ธีมที่บันทึกไว้ (ค่าเริ่มต้น = มืด)
        apply_theme(root)
        style_window(root)
        # audio callback อ่านค่าจาก dict นี้แทน tk.Variable (tk ไม่ thread-safe)
        self.vol = {}
        for key, var in (("monitor", self.v_monitor_vol), ("cable", self.v_cable_vol), ("mic", self.v_mic_vol)):
            self.vol[key] = var.get() / 100
            var.trace_add("write", lambda *_, k=key, v=var: self.vol.__setitem__(k, v.get() / 100))
        self._build_ui()
        root.update_idletasks()
        need_w, need_h = root.winfo_reqwidth(), root.winfo_reqheight()
        root.minsize(need_w, min(need_h, 640))
        root.geometry(f"{max(980, need_w)}x{max(720, need_h)}")
        self._refresh_list()
        self._apply_devices()
        self._rebind_hotkeys()
        self._tick()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(3000, self._auto_check_update)  # รอให้หน้าต่างขึ้นก่อน ไม่ทำให้เปิดช้า

    # ---------- UI
    def _build_ui(self):
        # ---- หัวแอป: โลโก้ + ชื่อ
        head = ttk.Frame(self.root, padding=(12, 10, 12, 2))
        head.pack(fill="x")
        logo = find_resource("icon.png")
        if logo:
            self._logo = tk.PhotoImage(file=logo).subsample(8)  # 256 -> 32 px (เก็บ ref กันโดนเก็บขยะ)
            ttk.Label(head, image=self._logo).pack(side="left", padx=(0, 8))
        ttk.Label(head, text=APP_NAME, style="Brand.TLabel").pack(side="left")
        self.btn_theme = ttk.Button(head, command=self.toggle_theme)
        self.btn_theme.pack(side="right")
        self.btn_update = ttk.Button(head, text="🔄 ตรวจสอบอัปเดต", command=self.on_update_button)
        self.btn_update.pack(side="right", padx=(0, 6))
        self._update_theme_button()
        ttk.Label(head, text=f"v{APP_VERSION}", style="Muted.TLabel").pack(side="left", padx=(6, 0), pady=(6, 0))

        top = ttk.Frame(self.root, padding=(12, 8, 12, 4))
        top.pack(fill="x")
        ttk.Button(top, text="➕ เพิ่มไฟล์", command=self.add_files).pack(side="left")
        ttk.Button(top, text="📁 เพิ่มโฟลเดอร์", command=self.add_folder).pack(side="left", padx=4)
        self.btn_yt = ttk.Button(top, text="🎬 จาก YouTube", command=self.add_youtube)
        self.btn_yt.pack(side="left", padx=(0, 4))
        ttk.Button(top, text="⌨ ตั้งปุ่มลัด", command=self.set_hotkey).pack(side="left")
        ttk.Button(top, text="✏ เปลี่ยนชื่อ", command=self.rename).pack(side="left", padx=4)
        ttk.Button(top, text="🗑 ลบ", command=self.remove).pack(side="left")
        ttk.Button(top, text="▶ เล่น", style="Pink.TButton", command=self.play_selected).pack(side="left", padx=(16, 4))
        self.btn_pause = ttk.Button(top, text="⏸ พัก", style="Purple.TButton", width=9, command=self.toggle_pause)
        self.btn_pause.pack(side="left")
        ttk.Button(top, text="■ หยุด", style="Big.TButton", command=self.stop_all).pack(side="left", padx=(4, 0))

        # ---- ค้นหา: แถวของตัวเอง กว้างเต็มหน้าต่าง
        bar = ttk.Frame(self.root, padding=(12, 4, 12, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="🔍", font=(FONT, 13)).pack(side="left")
        self.search_entry = ttk.Entry(bar, textvariable=self.v_search, font=(FONT, 12))
        self.search_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=4)
        ttk.Button(bar, text="✕ ล้าง", command=self._clear_search).pack(side="left")
        self.v_count = tk.StringVar()
        ttk.Label(bar, textvariable=self.v_count, style="Muted.TLabel", width=14, anchor="e").pack(side="left")
        self.v_search.trace_add("write", lambda *_: self._refresh_list())
        self.search_entry.bind("<Escape>", lambda e: self._clear_search())
        self.search_entry.bind("<Return>", lambda e: self._focus_first_result())
        self.search_entry.bind("<Down>", lambda e: self._focus_first_result())
        self.root.bind("<Control-f>", lambda e: (self.search_entry.focus_set(),
                                                 self.search_entry.select_range(0, "end")))

        mid = ttk.Frame(self.root, padding=(12, 0))
        mid.pack(fill="both", expand=True)
        cols = ("no", "name", "hotkey", "length")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        for c, text, w, anchor in [("no", "#", 40, "center"), ("name", "ชื่อเสียง", 420, "w"),
                                   ("hotkey", "ปุ่มลัด", 150, "center"), ("length", "ความยาว", 80, "center")]:
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "name"))
        self._style_tree_tags()
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.play_selected())
        self.tree.bind("<Return>", lambda e: self.play_selected())
        self.tree.bind("<Delete>", lambda e: self.remove())
        self.tree.bind("<space>", lambda e: (self.toggle_pause(), "break")[1])

        # ---- settings
        bottom = ttk.Frame(self.root, padding=(12, 10, 12, 10))
        bottom.pack(fill="x")

        dev = ttk.LabelFrame(bottom, text="อุปกรณ์เสียง", padding=8)
        dev.pack(side="left", fill="both", expand=True)
        self.cb_monitor = self._device_combo(dev, 0, "🎧 ลำโพง/หูฟัง (ตัวเองได้ยิน)", self.out_devs, "monitor",
                                             sd.default.device[1])
        self.cb_cable = self._device_combo(dev, 1, "🎙 ไมค์เสมือน (CABLE Input)", self.out_devs, "cable",
                                           self._find_cable())
        self.cb_mic = self._device_combo(dev, 2, "🎤 ไมโครโฟนจริง", self.in_devs, "mic", sd.default.device[0])
        dev.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(bottom, text="การเล่น", padding=8)
        opt.pack(side="left", fill="y", padx=(8, 0))
        self._slider(opt, 0, "เสียงที่หูฉัน", self.v_monitor_vol)
        self._slider(opt, 1, "เสียงเข้าไมค์", self.v_cable_vol)
        self._slider(opt, 2, "ไมค์จริง", self.v_mic_vol)
        ttk.Checkbutton(opt, text="ให้ตัวเองได้ยิน", variable=self.v_to_me).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(opt, text="ส่งเข้าไมค์", variable=self.v_to_mic).grid(row=3, column=1, sticky="w")
        ttk.Checkbutton(opt, text="ส่งเสียงไมค์จริงผ่านด้วย", variable=self.v_passthrough,
                        command=self._apply_devices).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="หยุดเสียงเก่าเมื่อเล่นเสียงใหม่", variable=self.v_stop_prev).grid(
            row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="เปิดใช้ปุ่มลัด", variable=self.v_hotkeys_on,
                        command=lambda: setattr(self.hotkeys, "enabled", self.v_hotkeys_on.get())).grid(
            row=6, column=0, sticky="w")
        self.btn_stop_hk = ttk.Button(opt, command=self.set_stop_hotkey)
        self.btn_stop_hk.grid(row=6, column=1, sticky="e")
        self._update_stop_btn()
        ttk.Checkbutton(opt, text="ตรวจสอบเวอร์ชันใหม่อัตโนมัติ", variable=self.v_auto_update,
                        command=self._save).grid(row=7, column=0, columnspan=2, sticky="w")

        # ---- แถบสถานะ: ป้ายสี + ข้อความสี + เส้นสีด้านบน เปลี่ยนตามสถานะ
        sbar = ttk.Frame(self.root, style="StatusBar.TFrame")
        sbar.pack(fill="x", side="bottom")
        self.status_line = ttk.Frame(self.root, height=2)
        self.status_line.pack(fill="x", side="bottom")
        self.status_badge = ttk.Label(sbar, width=11)
        self.status_badge.pack(side="left", padx=(10, 8), pady=6)
        self.status_text = ttk.Label(sbar, textvariable=self.v_status, anchor="w")
        self.status_text.pack(side="left", fill="x", expand=True)
        self.v_status.trace_add("write", lambda *_: self._update_status_style())
        self._update_status_style()

    def _device_combo(self, parent, row, label, devs, key, default_idx):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        labels = ["(ไม่ใช้)"] + [d[0] for d in devs]
        cb = ttk.Combobox(parent, values=labels, state="readonly", width=48)
        cb.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=3)
        saved = self.saved_devices.get(key)
        # "(ไม่ใช้)" ที่บันทึกไว้ไม่ทับการค้นหาอัตโนมัติ (เช่น เพิ่งติดตั้ง VB-CABLE ทีหลัง)
        if saved in labels[1:]:
            cb.set(saved)
        else:
            match = [d[0] for d in devs if d[1] == default_idx]
            cb.set(match[0] if match else "(ไม่ใช้)")
        cb.bind("<<ComboboxSelected>>", lambda e: self._apply_devices())
        return cb

    def _slider(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        ttk.Scale(parent, from_=0, to=150, variable=var, length=150).grid(row=row, column=1, padx=4)
        # ช่องตัวเลข %: ขยับตามแถบเลื่อน และพิมพ์ค่า/กดลูกศรเองได้ (Enter หรือคลิกออกเพื่อใช้ค่า)
        text = tk.StringVar(value=str(round(var.get())))
        box = ttk.Spinbox(parent, from_=0, to=150, increment=5, width=4, textvariable=text, justify="right")
        box.grid(row=row, column=2)
        ttk.Label(parent, text="%").grid(row=row, column=3, sticky="w", padx=(1, 0))
        var.trace_add("write", lambda *_: text.set(str(round(var.get()))))

        def commit(_=None):
            try:
                v = float(text.get().strip().rstrip("%"))
            except ValueError:
                v = var.get()
            v = max(0.0, min(150.0, v))
            var.set(v)
            text.set(str(round(v)))
        box.configure(command=commit)
        box.bind("<Return>", commit)
        box.bind("<FocusOut>", commit)

    def _find_cable(self):
        # หา VB-CABLE โดยเลือก MME ก่อน (เข้ากันได้ดีที่สุด)
        for name, idx in self.out_devs:
            if "CABLE Input" in name and "[MME]" in name:
                return idx
        for name, idx in self.out_devs:
            if "CABLE" in name.upper():
                return idx
        return None

    def _dev_index(self, cb, devs):
        for name, idx in devs:
            if name == cb.get():
                return idx
        return None

    # ---------- engine
    def _apply_devices(self):
        if hasattr(self, "btn_pause"):
            self.stop_all()  # ปิด ffmpeg ของเพลงยาว/สตรีมที่เล่นค้างอยู่ด้วย ไม่งั้นจะค้างอยู่จนกดหยุด
        for obj in (self.monitor, self.cable, self.mic):
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        self.monitor = self.cable = self.mic = None
        errors = []

        mon_idx = self._dev_index(self.cb_monitor, self.out_devs)
        cab_idx = self._dev_index(self.cb_cable, self.out_devs)
        mic_idx = self._dev_index(self.cb_mic, self.in_devs)

        if mon_idx is not None:
            try:
                self.monitor = OutputMixer(mon_idx, lambda: self.vol["monitor"])
            except Exception as e:
                errors.append(f"ลำโพง: {e}")
        if cab_idx is not None:
            sr = int(sd.query_devices(cab_idx)["default_samplerate"])
            if self.v_passthrough.get() and mic_idx is not None:
                try:
                    self.mic = MicPassthrough(mic_idx, sr, lambda: self.vol["mic"])
                except Exception as e:
                    errors.append(f"ไมค์จริง: {e} (ลองเลือกไมค์แบบ [MME])")
            try:
                self.cable = OutputMixer(cab_idx, lambda: self.vol["cable"], self.mic)
            except Exception as e:
                errors.append(f"ไมค์เสมือน: {e}")
        self._set_paused(False, quiet=True)  # mixer ใหม่ยังไม่มีเสียงค้าง

        if errors:
            self.v_status.set("⚠ " + " | ".join(errors))
        elif cab_idx is None:
            self.v_status.set("ยังไม่ได้เลือกไมค์เสมือน — เสียงจะออกแค่ลำโพง (ติดตั้ง VB-CABLE เพื่อส่งเข้าไมค์)")
        else:
            self.v_status.set("พร้อม")
        self._save()

    # ---------- actions
    def _add_paths(self, paths):
        known = {s["path"] for s in self.sounds}
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if p in known or not p.lower().endswith(AUDIO_EXT):
                continue
            self.sounds.append({"id": self.next_id, "path": p,
                                "name": os.path.splitext(os.path.basename(p))[0], "hotkey": None})
            self.next_id += 1
            known.add(p)
            added += 1
        self._refresh_list()
        self._save()
        self.v_status.set(f"เพิ่ม {added} เสียง")

    def add_files(self):
        paths = filedialog.askopenfilenames(title="เลือกไฟล์เสียง", filetypes=[
            ("ไฟล์เสียง", " ".join("*" + e for e in AUDIO_EXT)), ("ทั้งหมด", "*.*")])
        if paths:
            self._add_paths(paths)

    def add_youtube(self):
        try:
            import_ytdlp()
            import imageio_ffmpeg  # noqa: F401
        except ImportError:
            messagebox.showerror("ยังไม่ได้ติดตั้ง", "ต้องติดตั้งก่อน: pip install yt-dlp imageio-ffmpeg\n"
                                                     "(หรือเปิดโปรแกรมผ่าน run_soundpad.bat / ตัวติดตั้ง)")
            return
        # เสียงตัวอย่างออกหูฟังที่เลือกไว้ (ไม่ใช่ไมค์เสมือน) เพื่อนจึงไม่ได้ยินตอนตัดเพลง
        preview_dev = self._dev_index(self.cb_monitor, self.out_devs)
        if preview_dev is None:
            preview_dev = sd.default.device[1]
        dlg = YouTubeDialog(self.root, self.update_ytdlp, preview_dev)
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        self.btn_yt.config(state="disabled")
        self.v_status.set("🔎 กำลังดึงข้อมูลคลิป...")
        threading.Thread(target=self._yt_info_worker, args=dlg.result, daemon=True).start()

    def _yt_status(self, text):
        self.root.after(0, self.v_status.set, text)

    def _yt_fail(self, e):
        self.root.after(0, lambda: (self.btn_yt.config(state="normal"),
                                    self.v_status.set("⚠ YouTube: " + friendly_yt_error(e))))

    def _yt_info_worker(self, url, name, start, end, mode="download"):
        try:
            info = youtube_info(url)
        except Exception as e:
            self._yt_fail(e)
            return
        self.root.after(0, self._yt_confirm, info, url, name, start, end, mode)

    def _yt_confirm(self, info, url, name, start, end, mode="download"):
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            self._yt_fail(Exception("ไลฟ์สดโหลดไม่ได้"))
            return
        dur = info.get("duration") or 0
        if dur and start is not None and start >= dur:
            self._yt_fail(Exception(f"เวลาเริ่มเกินความยาวคลิป ({int(dur // 60)}:{int(dur % 60):02d})"))
            return
        clip_len = (min(end, dur) if end is not None and dur else end or dur) - (start or 0)
        if mode == "stream":
            self._add_stream(url, name or info.get("title") or "youtube", start, end, clip_len or None)
            return
        if clip_len > YT_MAX_MINUTES * 60 and not messagebox.askyesno(
                "คลิปยาว", f"ช่วงที่จะโหลดยาว {int(clip_len // 60)} นาที ต้องการโหลดต่อไหม?"):
            self.btn_yt.config(state="normal")
            self.v_status.set("ยกเลิกการโหลด")
            return
        name = name or info.get("title") or "youtube"
        threading.Thread(target=self._yt_download_worker, args=(url, name, start, end), daemon=True).start()

    def _add_stream(self, url, name, start, end, length):
        self.btn_yt.config(state="normal")
        s = {"id": self.next_id, "path": None, "url": url, "start": start, "end": end,
             "name": name, "hotkey": None, "length": length}
        self.next_id += 1
        self.sounds.append(s)
        self._refresh_list()
        self._save()
        self.tree.selection_set(str(s["id"]))
        self.tree.see(str(s["id"]))
        self.v_status.set(f"✅ เพิ่มแบบสตรีม: {name}")

    def _yt_download_worker(self, url, name, start, end):
        try:
            path = youtube_download(url, name, start, end, self._yt_status)
        except Exception as e:
            self._yt_fail(e)
            return
        self.root.after(0, self._yt_done, path, name)

    def _yt_done(self, path, name):
        self.btn_yt.config(state="normal")
        self._add_paths([path])
        s = next((x for x in self.sounds if x["path"] == os.path.abspath(path)), None)
        if s:
            s["name"] = name
            self._refresh_list()
            self._save()
            self.tree.selection_set(str(s["id"]))
            self.tree.see(str(s["id"]))
        self.v_status.set(f"✅ เพิ่มจาก YouTube: {name}")

    def update_ytdlp(self):
        self.v_status.set("⬆ กำลังอัปเดตตัวโหลด YouTube...")

        def work():
            try:
                download_latest_ytdlp()
                self._yt_status("✅ อัปเดตแล้ว — ปิดแล้วเปิดโปรแกรมใหม่เพื่อใช้เวอร์ชันใหม่")
            except Exception as e:
                self._yt_status(f"⚠ อัปเดตไม่สำเร็จ: {str(e)[:150]}")
        threading.Thread(target=work, daemon=True).start()

    def add_folder(self):
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์เสียง")
        if not folder:
            return
        paths = []
        for dirpath, _, files in os.walk(folder):
            paths += [os.path.join(dirpath, f) for f in sorted(files)]
        self._add_paths(paths)

    def _selected(self):
        ids = {int(i) for i in self.tree.selection()}
        return [s for s in self.sounds if s["id"] in ids]

    def remove(self):
        sel = self._selected()
        if not sel or not messagebox.askyesno("ลบ", f"ลบ {len(sel)} เสียงออกจากรายการ?\n(ไฟล์จริงไม่ถูกลบ)"):
            return
        ids = {s["id"] for s in sel}
        self.sounds = [s for s in self.sounds if s["id"] not in ids]
        self._refresh_list()
        self._rebind_hotkeys()
        self._save()

    def rename(self):
        sel = self._selected()
        if len(sel) != 1:
            return
        s = sel[0]
        win = tk.Toplevel(self.root)
        style_window(win)
        win.title("เปลี่ยนชื่อ")
        win.transient(self.root)
        var = tk.StringVar(value=s["name"])
        ent = ttk.Entry(win, textvariable=var, width=40)
        ent.pack(padx=12, pady=12)
        ent.select_range(0, "end")
        ent.focus_set()

        def ok(_=None):
            if var.get().strip():
                s["name"] = var.get().strip()
                self._refresh_list()
                self._save()
            win.destroy()
        ent.bind("<Return>", ok)
        ent.bind("<Escape>", lambda e: win.destroy())
        ttk.Button(win, text="ตกลง", command=ok).pack(pady=(0, 12))

    def _ask_hotkey(self, title):
        self.hotkeys.enabled = False
        dlg = HotkeyDialog(self.root, title, self.hotkeys)
        self.root.wait_window(dlg)
        self.hotkeys.enabled = self.v_hotkeys_on.get()
        return dlg.result

    def set_hotkey(self):
        sel = self._selected()
        if len(sel) != 1:
            messagebox.showinfo("ตั้งปุ่มลัด", "เลือกเสียง 1 รายการก่อน")
            return
        hk = self._ask_hotkey(f"ปุ่มลัดของ: {sel[0]['name']}")
        if hk is None:
            return
        if hk:
            # ปุ่มลัดซ้ำ -> เอาออกจากเสียงเดิม
            for s in self.sounds:
                if s["hotkey"] and hotkey_key(s["hotkey"]) == hotkey_key(hk):
                    s["hotkey"] = None
        sel[0]["hotkey"] = hk or None
        self._refresh_list()
        self._rebind_hotkeys()
        self._save()

    def set_stop_hotkey(self):
        hk = self._ask_hotkey("ปุ่มลัด: หยุดทุกเสียง")
        if hk is None:
            return
        self.stop_hotkey = hk or None
        self._update_stop_btn()
        self._rebind_hotkeys()
        self._save()

    def _update_stop_btn(self):
        self.btn_stop_hk.config(text=f"หยุด: {hotkey_text(self.stop_hotkey) or '-'}")

    def _rebind_hotkeys(self):
        b = {}
        for s in self.sounds:
            if s["hotkey"]:
                sid = s["id"]
                b[hotkey_key(s["hotkey"])] = lambda sid=sid: self.root.after(0, self.play_id, sid)
        if self.stop_hotkey:
            b[hotkey_key(self.stop_hotkey)] = lambda: self.root.after(0, self.stop_all)
        self.hotkeys.bindings = b

    def play_selected(self):
        for s in self._selected()[:1]:
            self.play_id(s["id"])

    def _targets(self):
        targets = []
        if self.v_to_me.get() and self.monitor:
            targets.append(self.monitor)
        if self.v_to_mic.get() and self.cable:
            targets.append(self.cable)
        return targets

    def play_id(self, sid):
        s = next((x for x in self.sounds if x["id"] == sid), None)
        if not s:
            return
        if s.get("url"):
            self._play_stream(s)
            return
        if not os.path.exists(s["path"]):
            self.v_status.set(f"⚠ ไม่พบไฟล์: {s['path']}")
            return
        if self.v_stop_prev.get():
            self.stop_all()
        self._set_paused(False, quiet=True)  # กดเล่นเสียงใหม่ระหว่างพัก = เลิกพัก
        try:
            if (s.get("length") or 0) > LONG_SOUND_SECONDS:
                # เพลงยาว: อ่านจากดิสก์ทีละช่วง ถอดรหัสครั้งเดียวต่อ sample rate แล้วแจกให้ทุกอุปกรณ์
                sources = {}
                for m in self._targets():
                    if m.sr not in sources:
                        sources[m.sr] = FileSource(s["path"], m.sr)
                    m.play(sources[m.sr], sid)
                with self.stream_lock:
                    self.streams.extend(sources.values())
            else:
                for m in self._targets():
                    m.play(load_audio(s["path"], m.sr), sid)
        except Exception as e:
            self.v_status.set(f"⚠ เปิดไฟล์ไม่ได้: {e}")
            return
        self.v_status.set(f"▶ กำลังเล่น: {s['name']}")

    def _play_stream(self, s):
        if self.v_stop_prev.get():
            self.stop_all()
        targets = self._targets()
        if not targets:
            return
        self.v_status.set(f"⏳ กำลังเชื่อมต่อ: {s['name']}")
        threading.Thread(target=self._stream_worker, args=(s, targets, self.stream_gen), daemon=True).start()

    def _stream_worker(self, s, targets, gen):
        """หา URL -> เปิด ffmpeg ต่อ sample rate -> รอ buffer ขั้นต่ำ แล้วส่งให้ main thread เริ่มเล่น"""
        sources = {}
        try:
            url, headers = youtube_stream_url(s["url"])
            for m in targets:
                if m.sr not in sources:
                    sources[m.sr] = StreamSource(url, headers, m.sr, s.get("start"), s.get("end"))
            with self.stream_lock:
                self.streams.extend(sources.values())
            deadline = time.time() + STREAM_TIMEOUT
            while time.time() < deadline and gen == self.stream_gen:
                if all(src.done or src.n >= src.sr * STREAM_PREBUFFER for src in sources.values()):
                    break
                time.sleep(0.02)
            err = next((src.error for src in sources.values() if src.error), None)
            if err:
                raise RuntimeError(err)
            if gen == self.stream_gen and all(src.n == 0 for src in sources.values()):
                raise RuntimeError("เชื่อมต่อนานเกินไป ลองใหม่อีกครั้ง")
        except Exception as e:
            for src in sources.values():
                src.stop()
            _stream_url_cache.pop(s["url"], None)  # URL อาจเสีย ครั้งหน้าให้หาใหม่
            if gen == self.stream_gen:
                self._yt_status("⚠ สตรีมไม่ได้: " + friendly_yt_error(e))
            return
        self.root.after(0, self._stream_ready, s, targets, sources, gen)

    def _stream_ready(self, s, targets, sources, gen):
        if gen != self.stream_gen:  # กดหยุดระหว่างรอเชื่อมต่อ
            for src in sources.values():
                src.stop()
            return
        self._set_paused(False, quiet=True)
        for m in targets:
            m.play(sources[m.sr], s["id"])
        self.v_status.set(f"▶ กำลังเล่น: {s['name']}")

    def toggle_pause(self):
        playing = any(m.playing_ids() for m in (self.monitor, self.cable) if m)
        if playing or self.paused:
            self._set_paused(not self.paused)

    def _set_paused(self, paused, quiet=False):
        self.paused = paused
        for m in (self.monitor, self.cable):
            if m:
                m.paused = paused
        self.btn_pause.config(text="▶ เล่นต่อ" if paused else "⏸ พัก")
        if not quiet:
            self.v_status.set("⏸ พักไว้ — กด ▶ เล่นต่อ หรือ Space" if paused else "▶ เล่นต่อ")

    def stop_all(self):
        self.stream_gen += 1  # ยกเลิกสตรีมที่กำลังเชื่อมต่อ
        with self.stream_lock:
            for src in self.streams:
                src.stop()
            self.streams = []
        for m in (self.monitor, self.cable):
            if m:
                m.stop_all()
        self._set_paused(False, quiet=True)
        if self.v_status.get().startswith(("⏳", "⏸")):
            self.v_status.set("■ หยุดแล้ว")

    # ---------- list
    def _refresh_list(self):
        q = self.v_search.get().lower().strip()
        sel = self.tree.selection()
        self._row_state = None  # แถวถูกสร้างใหม่ ให้ _tick ระบายสีอีกรอบ
        self.tree.delete(*self.tree.get_children())
        for i, s in enumerate(self.sounds, 1):
            if q and q not in s["name"].lower():
                continue
            if "length" not in s:
                try:
                    s["length"] = sf.info(s["path"]).duration
                except Exception:
                    s["length"] = None
            ln = s["length"]
            length = f"{int(ln // 60)}:{int(ln % 60):02d}" if ln is not None else "?"
            name = ("🌐 " if s.get("url") else "") + s["name"]
            self.tree.insert("", "end", iid=str(s["id"]),
                             values=(i, name, hotkey_text(s["hotkey"]), length))
        keep = [i for i in sel if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)
        shown, total = len(self.tree.get_children()), len(self.sounds)
        self.v_count.set(f"{shown}/{total} เสียง" if q else f"{total} เสียง")

    # ---------- update
    def _auto_check_update(self):
        due = time.time() - float(self.update_state.get("last_check") or 0) > UPDATE_CHECK_HOURS * 3600
        if self.v_auto_update.get() and due:
            self._start_update_check(manual=False)

    def on_update_button(self):
        if self.update_info:
            self.open_update_dialog()
        else:
            self._start_update_check(manual=True)

    def _start_update_check(self, manual):
        if self._checking_update:
            return
        self._checking_update = True
        if manual:
            self.v_status.set("🔎 กำลังตรวจสอบเวอร์ชันใหม่...")

        def work():
            try:
                info, err = check_for_update(), None
            except Exception as e:
                info, err = None, e
            self.root.after(0, self._update_checked, info, err, manual)
        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, info, err, manual):
        self._checking_update = False
        if err:  # เช็กอัตโนมัติแล้วไม่มีเน็ต = เงียบไว้
            if manual:
                self.v_status.set(f"⚠ ตรวจสอบอัปเดตไม่ได้: {str(err)[:120]}")
            return
        self.update_state["last_check"] = time.time()
        self._save()
        if not info:
            if manual:
                self.v_status.set(f"✅ ใช้เวอร์ชันล่าสุดอยู่แล้ว ({APP_VERSION})")
            return
        if not manual and info["version"] == self.update_state.get("skip"):
            return  # ผู้ใช้กดข้ามเวอร์ชันนี้ไว้
        self.update_info = info
        self.btn_update.config(text=f"⬆ อัปเดต {info['version']}", style="Pink.TButton")
        self.v_status.set(f"🆕 มีเวอร์ชันใหม่ {info['version']} — กดปุ่ม ⬆ อัปเดต ที่มุมขวาบน")
        if manual:
            self.open_update_dialog()

    def open_update_dialog(self):
        dlg = UpdateDialog(self.root, self.update_info)
        self.root.wait_window(dlg)
        if dlg.result == "skip":
            self.update_state["skip"] = self.update_info["version"]
            self.update_info = None
            self.btn_update.config(text="🔄 ตรวจสอบอัปเดต", style="TButton")
            self.v_status.set("พร้อม")
            self._save()
        elif dlg.result:
            self.install_update(dlg.result)

    def install_update(self, path):
        self._on_close()  # บันทึก + หยุดเสียง/ffmpeg + ปิดหน้าต่าง ก่อนให้ตัวติดตั้งทับไฟล์
        run_installer(path)

    def toggle_theme(self):
        self.v_theme.set("light" if self.v_theme.get() == "dark" else "dark")
        use_theme(self.v_theme.get())
        apply_theme(self.root)
        style_window(self.root)
        self._style_tree_tags()
        self._update_status_style()
        self._update_theme_button()
        for cb in (self.cb_monitor, self.cb_cable, self.cb_mic):  # รายการ dropdown ที่สร้างไปแล้ว
            try:
                lb = f"{self.root.tk.call('ttk::combobox::PopdownWindow', cb)}.f.l"
                self.root.tk.call(lb, "configure", "-background", T["surface2"], "-foreground", T["text"],
                                  "-selectbackground", T["sel"], "-selectforeground", "#ffffff")
            except tk.TclError:
                pass
        self._save()

    def _update_theme_button(self):
        dark = self.v_theme.get() == "dark"
        self.btn_theme.config(text="☀ ธีมสว่าง" if dark else "🌙 ธีมมืด")

    def _style_tree_tags(self):
        self.tree.tag_configure("playing", background=T["playing"], foreground=T["playing_fg"])
        self.tree.tag_configure("paused", background=T["paused"], foreground=T["warn"])

    def _update_status_style(self):
        kind = status_kind(self.v_status.get())
        self.status_badge.config(text=STATUS_LABELS[kind], style=f"Badge.{kind}.TLabel")
        self.status_text.config(style=f"StatusText.{kind}.TLabel")
        self.status_line.config(style=f"Line.{kind}.TFrame")

    def _clear_search(self):
        self.v_search.set("")
        self.search_entry.focus_set()

    def _focus_first_result(self):
        items = self.tree.get_children()
        if items:
            self.tree.focus_set()
            self.tree.selection_set(items[0])
            self.tree.focus(items[0])
            self.tree.see(items[0])
        return "break"

    def _tick(self):
        playing = set()
        for m in (self.monitor, self.cable):
            if m:
                playing.update(m.playing_ids())
        state = (frozenset(playing), self.paused)
        if state != self._row_state:  # ระบายสีแถวใหม่เฉพาะตอนมีอะไรเปลี่ยน (ประหยัด CPU ตอนเปิดทิ้งไว้)
            self._row_state = state
            tag = ("paused",) if self.paused else ("playing",)
            for iid in self.tree.get_children():
                self.tree.item(iid, tags=tag if int(iid) in playing else ())
        if not playing and self.v_status.get().startswith("▶"):
            self.v_status.set("พร้อม")
        with self.stream_lock:  # สตรีมที่ ffmpeg จบแล้ว ไม่ต้องติดตามต่อ
            self.streams = [src for src in self.streams if not src.done]
        self.root.after(150, self._tick)

    # ---------- persistence
    def _load(self):
        if not os.path.exists(config.DATA_FILE):
            return
        try:
            with open(config.DATA_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return
        for s in d.get("sounds", []):
            item = {"id": self.next_id, "path": s.get("path"), "name": s["name"], "hotkey": s.get("hotkey")}
            if s.get("url"):
                item.update(url=s["url"], start=s.get("start"), end=s.get("end"), length=s.get("length"))
            self.sounds.append(item)
            self.next_id += 1
        st = d.get("settings", {})
        for key, var in self._setting_vars().items():
            if key in st:
                var.set(st[key])
        self.stop_hotkey = d.get("stop_hotkey", self.stop_hotkey)
        self.update_state.update(d.get("update") or {})
        self.saved_devices = d.get("devices", {})

    def _setting_vars(self):
        return {"monitor_vol": self.v_monitor_vol, "cable_vol": self.v_cable_vol, "mic_vol": self.v_mic_vol,
                "to_me": self.v_to_me, "to_mic": self.v_to_mic, "passthrough": self.v_passthrough,
                "stop_prev": self.v_stop_prev, "theme": self.v_theme, "auto_update": self.v_auto_update}

    @staticmethod
    def _sound_record(s):
        rec = {"path": s["path"], "name": s["name"], "hotkey": s["hotkey"]}
        if s.get("url"):
            rec.update(url=s["url"], start=s.get("start"), end=s.get("end"), length=s.get("length"))
        return rec

    def _save(self):
        if not hasattr(self, "cb_mic"):
            return
        d = {
            "sounds": [self._sound_record(s) for s in self.sounds],
            "settings": {k: v.get() for k, v in self._setting_vars().items()},
            "stop_hotkey": self.stop_hotkey,
            "update": self.update_state,
            "devices": {"monitor": self.cb_monitor.get(), "cable": self.cb_cable.get(), "mic": self.cb_mic.get()},
        }
        try:
            with open(config.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.v_status.set(f"⚠ บันทึกไม่ได้: {e}")

    def _on_close(self):
        self._save()
        self.hotkeys.stop()
        self.stop_all()  # ปิด ffmpeg ของสตรีมด้วย
        for obj in (self.monitor, self.cable, self.mic):
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        self.root.destroy()
