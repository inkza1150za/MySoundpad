"""กันเปิดโปรแกรมซ้อน (named mutex ที่ตัวติดตั้งใช้เช็กด้วย)"""



SINGLE_INSTANCE_MUTEX = "MySoundpad_SingleInstance"  # ตัวติดตั้งใช้ชื่อเดียวกันเช็กว่าโปรแกรมเปิดอยู่


_instance_mutex = None  # เก็บ handle ไว้ ตัวอัปเดตจะปล่อยก่อนเปิดตัวติดตั้ง


def already_running():
    """เปิดซ้อน 2 ตัวจะทำให้ปุ่มลัดทำงาน 2 รอบ จึงอนุญาตแค่ตัวเดียว"""
    global _instance_mutex
    try:
        from ctypes import windll, wintypes
        windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
        _instance_mutex = windll.kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
        return windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def release_instance_lock():
    """ปล่อย mutex ก่อนเปิดตัวติดตั้ง (ตัวติดตั้งเช็ก mutex นี้ว่าแอปยังเปิดอยู่ไหม)"""
    global _instance_mutex
    if _instance_mutex:
        from ctypes import windll
        windll.kernel32.CloseHandle(_instance_mutex)
        _instance_mutex = None
