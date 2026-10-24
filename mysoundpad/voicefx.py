"""เปลี่ยนเสียงพูด (voice changer) สำหรับเสียงไมค์จริง: ประมวลผลทีละ block แบบ numpy ไม่มี loop ราย sample

ทุกเอฟเฟกต์รับ/คืน mono float32 ความยาวเท่าเดิม และเก็บสถานะข้าม block เอง (เสียงต่อกันไม่มีรอยสะดุด)
"""
import numpy as np

# ชื่อที่บันทึกในไฟล์ตั้งค่า -> ชื่อบนปุ่ม (เรียงตามที่แสดง)
EFFECTS = {"off": "ปิด", "pitch_up": "🐿 เสียงสูง", "pitch_down": "👹 เสียงต่ำ", "robot": "🤖 หุ่นยนต์",
           "radio": "📻 วิทยุ", "echo": "🏛 ก้อง"}


class _PitchShifter:
    """เปลี่ยนระดับเสียงโดยไม่เปลี่ยนความเร็วพูด (delay-line 2 หัวอ่าน + crossfade แบบ sin²)

    หัวอ่านเลื่อนเร็วกว่า/ช้ากว่าหัวเขียนตามอัตรา ratio ภายในหน้าต่าง window วินาที
    ความหน่วงเฉลี่ย ~window/2
    """

    def __init__(self, sr, ratio, window=0.04):
        self.W = int(sr * window)
        self.step = (1.0 - ratio) / self.W  # delay เปลี่ยนต่อ sample (หน่วย = 1 หน้าต่าง)
        self.N = 1 << 16
        self.buf = np.zeros(self.N, np.float32)
        self.w = 0          # จำนวน sample ที่เขียนไปแล้วทั้งหมด
        self.phase = 0.0

    def process(self, x):
        n, N = len(x), self.N
        t = self.w + np.arange(n)
        self.buf[t % N] = x
        ph = (self.phase + self.step * np.arange(1, n + 1)) % 1.0
        self.phase = float(ph[-1])
        out = np.zeros(n, np.float32)
        for off in (0.0, 0.5):  # หัวอ่าน 2 หัวห่างกันครึ่งหน้าต่าง น้ำหนักรวมกัน = 1 เสมอ
            p = (ph + off) % 1.0
            r = t - p * self.W
            i0 = np.floor(r).astype(np.int64)
            frac = (r - i0).astype(np.float32)
            a, b = self.buf[i0 % N], self.buf[(i0 + 1) % N]
            out += np.sin(np.pi * p).astype(np.float32) ** 2 * (a + (b - a) * frac)
        self.w += n
        return out * 1.35  # หัวอ่าน 2 หัวหักล้างกันบางส่วน (~-2.6 dB) ชดเชยให้ดังเท่าเดิม


class _RingMod:
    """หุ่นยนต์: คูณเสียงด้วยคลื่น sine ความถี่ต่ำ"""

    def __init__(self, sr, freq):
        self.k = 2 * np.pi * freq / sr
        self.phase = 0.0

    def process(self, x):
        ph = self.phase + self.k * np.arange(1, len(x) + 1)
        self.phase = float(ph[-1] % (2 * np.pi))
        return (x * np.sin(ph)).astype(np.float32) * 1.4


class _Radio:
    """วิทยุ/โทรศัพท์: กรองให้เหลือช่วงความถี่ 300-3000 Hz (FIR) แล้วทำให้แตกเล็กน้อย"""

    def __init__(self, sr, drive):
        taps = 401  # ยาวพอให้ตัดเสียงทุ้มที่ 300 Hz ได้คม (หน่วงเพิ่ม ~4.5 ms)
        k = np.arange(taps) - (taps - 1) / 2

        def lowpass(fc):
            h = np.sinc(2 * fc / sr * k) * (2 * fc / sr)
            return h * np.hamming(taps)
        self.h = (lowpass(3000) - lowpass(300)).astype(np.float32)
        self.tail = np.zeros(taps - 1, np.float32)  # ท้าย block ก่อนหน้า ให้ filter ต่อเนื่อง
        self.drive = drive

    def process(self, x):
        z = np.concatenate([self.tail, x])
        self.tail = z[-len(self.tail):]
        y = np.convolve(z, self.h, mode="valid")
        return (np.tanh(y * self.drive) / np.tanh(self.drive) * 0.9).astype(np.float32)


class _Echo:
    """ก้อง: feedback delay 2 ระยะ (ยาวกว่า 1 block จึงคำนวณทั้ง block ได้ในครั้งเดียว)"""

    def __init__(self, sr, amount):
        self.d = (int(sr * 0.11), int(sr * 0.17))
        self.g = (0.35 * amount, 0.25 * amount)
        self.hist = np.zeros(max(self.d) + 4096, np.float32)  # เสียงขาออกย้อนหลัง

    def process(self, x):
        n, H = len(x), len(self.hist)
        if n > min(self.d):  # block ยาวผิดปกติ: แบ่งย่อยให้ยาวไม่เกินระยะ delay
            half = n // 2
            return np.concatenate([self.process(x[:half]), self.process(x[half:])])
        y = x.astype(np.float32).copy()
        for d, g in zip(self.d, self.g):
            y += g * self.hist[H - d:H - d + n]
        self.hist = np.concatenate([self.hist[n:], y])
        return y


class VoiceFX:
    """เลือกเอฟเฟกต์ 1 อย่างตามชื่อ ความแรง 0..1 (สร้างใหม่ทุกครั้งที่เปลี่ยนการตั้งค่า)"""

    def __init__(self, sr, name, strength=0.6):
        s = max(0.0, min(1.0, strength))
        self.name = name
        if name == "pitch_up":
            self.fx = _PitchShifter(sr, 1.0 + 0.8 * s)
        elif name == "pitch_down":
            self.fx = _PitchShifter(sr, 1.0 / (1.0 + 0.8 * s))
        elif name == "robot":
            self.fx = _RingMod(sr, 40 + 60 * s)
        elif name == "radio":
            self.fx = _Radio(sr, 1.5 + 6 * s)
        elif name == "echo":
            self.fx = _Echo(sr, 0.4 + 0.6 * s)
        else:
            raise ValueError(name)

    def process(self, mono):
        return self.fx.process(mono.astype(np.float32, copy=False))
