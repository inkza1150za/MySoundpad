"""MySoundpad - เล่นเสียงเข้าไมค์ (ผ่าน VB-CABLE) พร้อมปุ่มลัดแบบ global

ไฟล์นี้เป็นแค่จุดเปิดโปรแกรม (ใช้กับ run_soundpad.bat และ PyInstaller) โค้ดทั้งหมดอยู่ในแพ็กเกจ mysoundpad/

ต้องการ: pip install sounddevice soundfile numpy pynput
ดึงเสียงจาก YouTube (ไม่บังคับ): pip install yt-dlp imageio-ffmpeg
ใช้กับ Discord/เกม: ติดตั้ง VB-CABLE แล้วตั้งไมค์ในแอปนั้นเป็น "CABLE Output"
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox

from mysoundpad.config import APP_NAME, DATA_DIR
from mysoundpad.instance import already_running


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        from mysoundpad.selftest import selftest
        selftest(sys.argv[2])
        sys.exit(0)
    if already_running():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NAME, f"{APP_NAME} เปิดอยู่แล้ว\nดูที่แถบงาน (taskbar)")
        sys.exit(0)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    os.makedirs(DATA_DIR, exist_ok=True)
    from mysoundpad.ui.app import SoundpadApp
    root = tk.Tk()
    SoundpadApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
