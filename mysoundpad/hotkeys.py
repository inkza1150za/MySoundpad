"""ปุ่มลัดแบบ global: ฟังคีย์บอร์ดทั้งระบบแล้วเรียกเสียงตามคีย์ผสมที่ตั้งไว้"""


from pynput import keyboard


MOD_VKS = {
    0x10: "shift", 0xA0: "shift", 0xA1: "shift",
    0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
    0x12: "alt", 0xA4: "alt", 0xA5: "alt",
    0x5B: "win", 0x5C: "win",
}


MOD_ORDER = ["ctrl", "alt", "shift", "win"]


VK_NAMES = {
    0x20: "Space", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
    0x21: "PageUp", 0x22: "PageDown", 0x13: "Pause", 0x91: "ScrollLock",
    0x6A: "Num*", 0x6B: "Num+", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0xC0: "`", 0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\",
    0xBA: ";", 0xDE: "'", 0xBC: ",", 0xBE: ".", 0xBF: "/",
}


def vk_name(vk):
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num{vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return VK_NAMES.get(vk, f"VK{vk}")


def hotkey_text(hk):
    if not hk:
        return ""
    parts = [m.capitalize() for m in MOD_ORDER if m in hk["mods"]]
    return "+".join(parts + [vk_name(hk["vk"])])


def hotkey_key(hk):
    return (tuple(m for m in MOD_ORDER if m in hk["mods"]), hk["vk"])


class HotkeyManager:
    """ฟังคีย์บอร์ดทั้งระบบ แล้วเรียก callback เมื่อกดคีย์ผสมที่ลงทะเบียนไว้"""

    def __init__(self):
        self.bindings = {}
        self.mods = set()
        self.down = set()
        self.enabled = True
        # ถ้าตั้งไว้ คีย์ถัดไปจะส่งให้ฟังก์ชันนี้แทนการยิงปุ่มลัด (ใช้ตอนตั้งปุ่มลัด เพื่อให้เห็นคีย์แบบเดียวกับตอนใช้จริง)
        self.capture = None
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.daemon = True
        self.listener.start()

    @staticmethod
    def _vk(key):
        if isinstance(key, keyboard.KeyCode):
            return key.vk
        return getattr(key.value, "vk", None)

    def _press(self, key):
        vk = self._vk(key)
        if vk is None:
            return
        if vk in MOD_VKS:
            self.mods.add(MOD_VKS[vk])
            return
        if vk in self.down:  # กดค้าง ไม่ยิงซ้ำ
            return
        self.down.add(vk)
        mods = tuple(m for m in MOD_ORDER if m in self.mods)
        if self.capture:
            self.capture(mods, vk)
            return
        if not self.enabled:
            return
        cb = self.bindings.get((mods, vk))
        if cb:
            cb()

    def _release(self, key):
        vk = self._vk(key)
        if vk is None:
            return
        if vk in MOD_VKS:
            self.mods.discard(MOD_VKS[vk])
        self.down.discard(vk)

    def stop(self):
        self.listener.stop()
