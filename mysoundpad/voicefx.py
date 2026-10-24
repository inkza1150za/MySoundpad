"""เปลี่ยนเสียงพูด (voice changer) สำหรับเสียงไมค์จริง: ห่วงโซ่เอฟเฟกต์ที่ปรับค่าได้ทุกตัว

ประมวลผลทีละ block แบบ numpy (ไม่มี loop ราย sample) ทุกขั้นรับ/คืน mono float32 ความยาวเท่าเดิม
และเก็บสถานะข้าม block เอง เปลี่ยนค่าระหว่างทำงานได้โดยไม่เริ่มใหม่ (ลากแถบแล้วเสียงไม่สะดุด)
ขั้นที่ค่าเป็น 0 / ปิด จะถูกข้าม: ทุกค่าเป็นค่าเริ่มต้น = เสียงออกตรงกับเสียงเข้าทุก sample
"""
import numpy as np

# ค่าเริ่มต้น = ไม่เปลี่ยนเสียงเลย
DEFAULT_PARAMS = {
    "pitch": 0.0,          # ครึ่งเสียง -12..+12
    "robot": 0.0,          # 0..1 ความเป็นหุ่นยนต์/โลหะ (ring modulation)
    "robot_freq": 60.0,    # Hz 30..500
    "vibrato": 0.0,        # 0..1 เสียงสั่น
    "vibrato_rate": 6.0,   # Hz 1..12
    "chorus": 0.0,         # 0..1 เสียงซ้อน
    "distortion": 0.0,     # 0..1 เสียงแตก
    "bitcrush": 0.0,       # 0..1 เสียงเกม 8-bit
    "lowcut": 0.0,         # Hz 0 (ปิด)..1000 ตัดเสียงทุ้ม
    "highcut": 20000.0,    # Hz 2000..20000 (20000 = ปิด) ตัดเสียงแหลม
    "echo": 0.0,           # 0..1 เสียงก้อง
    "echo_ms": 150.0,      # ms 50..500 ระยะเสียงสะท้อน
}

# แถบเลื่อนในหน้าต่างปรับเสียง: (คีย์, ชื่อ, ต่ำสุด, สูงสุด, หน่วยที่แสดง, กลุ่ม)
SLIDERS = [
    ("pitch", "ระดับเสียง", -12, 12, "ครึ่งเสียง", "ระดับเสียง"),
    ("robot", "ความเป็นหุ่นยนต์", 0, 100, "%", "หุ่นยนต์ / โลหะ"),
    ("robot_freq", "ความถี่เสียงโลหะ", 30, 500, "Hz", "หุ่นยนต์ / โลหะ"),
    ("vibrato", "เสียงสั่น", 0, 100, "%", "แปลกประหลาด"),
    ("vibrato_rate", "ความเร็วเสียงสั่น", 1, 12, "Hz", "แปลกประหลาด"),
    ("chorus", "เสียงซ้อน", 0, 100, "%", "แปลกประหลาด"),
    ("distortion", "เสียงแตก", 0, 100, "%", "แปลกประหลาด"),
    ("bitcrush", "เกม 8-bit", 0, 100, "%", "แปลกประหลาด"),
    ("lowcut", "ตัดเสียงทุ้ม", 0, 1000, "Hz", "โทนเสียง"),
    ("highcut", "ตัดเสียงแหลม", 2000, 20000, "Hz", "โทนเสียง"),
    ("echo", "เสียงก้อง", 0, 100, "%", "ห้อง"),
    ("echo_ms", "ระยะเสียงสะท้อน", 50, 500, "ms", "ห้อง"),
]
PERCENT_KEYS = {k for k, _, _, _, unit, _ in SLIDERS if unit == "%"}  # เก็บเป็น 0..1 แสดงเป็น %


def _p(**kw):
    d = dict(DEFAULT_PARAMS)
    d.update(kw)
    return d


# ชุดเสียงสำเร็จรูป: คีย์ -> (ชื่อบนเมนู, ค่า) — 5 คีย์แรกคือเอฟเฟกต์เดิมของ 1.5.0 (ไฟล์ตั้งค่าเก่าใช้ต่อได้)
PRESETS = {
    "pitch_up": ("🐿 เสียงสูง", _p(pitch=7)),
    "pitch_down": ("👹 เสียงต่ำ", _p(pitch=-7)),
    "robot": ("🤖 หุ่นยนต์", _p(robot=1.0, robot_freq=76)),
    "radio": ("📻 วิทยุ", _p(lowcut=300, highcut=3000, distortion=0.45)),
    "echo": ("🏛 ก้อง", _p(echo=0.8, echo_ms=110)),
    "alien": ("👽 เอเลี่ยน", _p(pitch=3, robot=0.35, robot_freq=320, vibrato=0.6, vibrato_rate=9, chorus=0.6)),
    "demon": ("😈 ปีศาจ", _p(pitch=-10, distortion=0.25, echo=0.35, echo_ms=90, lowcut=60)),
    "chipmunk": ("🐭 ตัวจิ๋ว", _p(pitch=12, highcut=12000)),
    "retro": ("🕹 เกม 8-bit", _p(bitcrush=0.7, highcut=6000)),
    "cave": ("🕳 ถ้ำ", _p(echo=0.9, echo_ms=320, highcut=9000)),
    "ghost": ("👻 ผี", _p(pitch=-2, vibrato=0.8, vibrato_rate=2.5, echo=0.6, echo_ms=260, chorus=0.3)),
}


class _DelayLine:
    """buffer วงกลม + อ่านค่าที่ระยะ delay (ทศนิยม) ด้วย linear interpolation"""

    def __init__(self, size=1 << 16):
        self.N = size
        self.buf = np.zeros(size, np.float32)
        self.w = 0  # จำนวน sample ที่เขียนไปแล้วทั้งหมด

    def write(self, x):
        t = self.w + np.arange(len(x))
        self.buf[t % self.N] = x
        self.w += len(x)
        return t  # ตำแหน่งสัมบูรณ์ของ sample ใน block นี้

    def read(self, t, delay):
        r = t - delay
        i0 = np.floor(r).astype(np.int64)
        frac = (r - i0).astype(np.float32)
        a, b = self.buf[i0 % self.N], self.buf[(i0 + 1) % self.N]
        return a + (b - a) * frac


class _PitchShifter:
    """เปลี่ยนระดับเสียงโดยไม่เปลี่ยนความเร็วพูด (2 หัวอ่าน + crossfade แบบ sin²) หน่วงเฉลี่ย ~window/2"""

    def __init__(self, sr, window=0.04):
        self.W = int(sr * window)
        self.line = _DelayLine()
        self.phase = 0.0
        self.step = 0.0

    def set_semitones(self, st):
        self.step = (1.0 - 2.0 ** (st / 12.0)) / self.W  # delay เปลี่ยนต่อ sample (หน่วย = 1 หน้าต่าง)

    def process(self, x):
        t = self.line.write(x)
        ph = (self.phase + self.step * np.arange(1, len(x) + 1)) % 1.0
        self.phase = float(ph[-1])
        out = np.zeros(len(x), np.float32)
        for off in (0.0, 0.5):  # หัวอ่าน 2 หัวห่างกันครึ่งหน้าต่าง น้ำหนักรวมกัน = 1 เสมอ
            p = (ph + off) % 1.0
            out += np.sin(np.pi * p).astype(np.float32) ** 2 * self.line.read(t, p * self.W)
        return out * 1.35  # หัวอ่าน 2 หัวหักล้างกันบางส่วน (~-2.6 dB) ชดเชยให้ดังเท่าเดิม


class VoiceChain:
    """ห่วงโซ่: ระดับเสียง -> หุ่นยนต์ -> สั่น -> ซ้อน -> แตก -> 8-bit -> กรองโทน -> ก้อง"""

    FIR_TAPS = 401

    def __init__(self, sr, params=None):
        self.sr = sr
        self.p = dict(DEFAULT_PARAMS)
        self.pitch = _PitchShifter(sr)
        self.pitch_on = False
        self.vib = _DelayLine()
        self.cho = _DelayLine()
        self.n = 0  # นาฬิกา (จำนวน sample ที่ผ่านไป) ใช้กับคลื่น LFO ทุกตัว ให้ต่อเนื่องข้าม block
        self.ring_phase = 0.0
        self.fir = self.fir_prev = None
        self.fir_tail = np.zeros(self.FIR_TAPS - 1, np.float32)
        self.echo_hist = np.zeros(int(sr * 0.5 * 1.6) + 8192, np.float32)
        self.echo_prev_ms = None
        self.set_params(params or {})

    # ---- ค่า
    def set_params(self, params):
        """เปลี่ยนค่าระหว่างทำงานได้ (สถานะเสียงเดิมคงอยู่ ค่าที่เปลี่ยนจะค่อยๆ ผสมเข้าใน block ถัดไป)"""
        p = dict(DEFAULT_PARAMS)
        p.update({k: float(v) for k, v in params.items() if k in DEFAULT_PARAMS})
        self.pitch.set_semitones(p["pitch"])
        if p["lowcut"] != self.p.get("lowcut") or p["highcut"] != self.p.get("highcut") or self.fir is None:
            if self.fir is not None and self.fir_prev is None:
                self.fir_prev = self.fir  # block ถัดไปจะผสมจาก filter เดิมไป filter ใหม่
            self.fir = self._design_fir(p["lowcut"], p["highcut"])
        if p["echo_ms"] != self.p.get("echo_ms") and self.echo_prev_ms is None:
            self.echo_prev_ms = self.p.get("echo_ms")
        self.p = p

    def _design_fir(self, lowcut, highcut):
        """filter แบบ linear phase หน่วงคงที่ (TAPS-1)/2 เสมอ แม้ไม่กรอง (เป็นแค่ delay) เปิด/ปิดแล้วไม่กระโดด"""
        lo, hi = lowcut > 1, highcut < min(19999, self.sr / 2 - 1)
        if not (lo or hi):
            h = np.zeros(self.FIR_TAPS, np.float32)
            h[(self.FIR_TAPS - 1) // 2] = 1.0
            return h
        k = np.arange(self.FIR_TAPS) - (self.FIR_TAPS - 1) / 2
        win = np.hamming(self.FIR_TAPS)

        def lowpass(fc):
            return np.sinc(2 * fc / self.sr * k) * (2 * fc / self.sr) * win
        h = lowpass(highcut if hi else self.sr / 2 - 1)
        if lo:
            h = h - lowpass(lowcut)
        return h.astype(np.float32)

    @property
    def active(self):
        return self.p != DEFAULT_PARAMS

    # ---- ประมวลผล
    def process(self, mono):
        x = mono.astype(np.float32, copy=True)
        if not self.active and not self.pitch_on:
            return x  # ทุกค่าเป็นค่าเริ่มต้น: ไม่แตะเสียงเลย
        n, p, sr = len(x), self.p, self.sr
        t = self.n + np.arange(n)
        self.n += n
        fade = np.linspace(0, 1, n, dtype=np.float32)  # ผสมจากของเดิมไปของใหม่ตลอด block ที่ค่าเปลี่ยน

        # ระดับเสียง: ตัวเปลี่ยนระดับรับเสียงตลอด (มีเสียงย้อนหลังพร้อม) เปิด/ปิดแล้ว crossfade
        shifted = self.pitch.process(x)
        on = p["pitch"] != 0
        if on and self.pitch_on:
            x = shifted
        elif on != self.pitch_on:
            x = x * (1 - fade) + shifted * fade if on else shifted * (1 - fade) + x * fade
        self.pitch_on = on

        if p["robot"] > 0:  # ผสมตามความแรง: ค่าใกล้ 0 = ใกล้เสียงเดิม
            ph = self.ring_phase + 2 * np.pi * p["robot_freq"] / sr * np.arange(1, n + 1)
            self.ring_phase = float(ph[-1] % (2 * np.pi))
            x = x * (1 - p["robot"]) + p["robot"] * 1.4 * x * np.sin(ph).astype(np.float32)

        # เสียงสั่น: delay แกว่งขึ้นลง ระยะแปรตามความแรง (0 = delay 0 = เสียงเดิมพอดี)
        tt = self.vib.write(x)
        if p["vibrato"] > 0:
            lfo = (1 + np.sin(2 * np.pi * p["vibrato_rate"] * t / sr)) / 2
            x = self.vib.read(tt, sr * 0.008 * p["vibrato"] * lfo)

        # เสียงซ้อน 2 ชั้นที่หน่วงไม่เท่ากัน (เขียน buffer ตลอด เปิดทีหลังจะมีเสียงย้อนหลังพร้อม)
        tt = self.cho.write(x)
        if p["chorus"] > 0:
            d1 = sr * (0.020 + 0.003 * np.sin(2 * np.pi * 0.8 * t / sr))
            d2 = sr * (0.027 + 0.003 * np.sin(2 * np.pi * 1.13 * t / sr + 1.0))
            wet = 0.5 * (self.cho.read(tt, d1) + self.cho.read(tt, d2))
            x = x * (1 - 0.5 * p["chorus"]) + wet * p["chorus"]

        if p["distortion"] > 0:  # ผสมเสียงแตกตามความแรง: ค่าใกล้ 0 = ใกล้เสียงเดิม
            drive = 1 + 20 * p["distortion"]
            dist = np.tanh(x * drive) / np.tanh(drive)
            x = x + min(1.0, 3 * p["distortion"]) * (dist - x)

        if p["bitcrush"] > 0:  # ลดความละเอียดเสียง + ลดอัตราสุ่มตัวอย่าง
            levels = 2 ** (16 - 12 * p["bitcrush"]) / 2
            hold = 1 + int(7 * p["bitcrush"])
            # ค้างค่าไว้ทุก hold sample (ต้น block ที่คร่อมช่วงค้างใช้ sample แรกของ block แทน)
            idx = np.clip((t // hold) * hold - t[0], 0, n - 1)
            x = np.round(x[idx] * levels) / levels

        # โทนเสียง: filter หน่วงคงที่เสมอ ถ้าเพิ่งเปลี่ยนค่าก็ผสมผลของ filter เดิมกับใหม่
        z = np.concatenate([self.fir_tail, x.astype(np.float32)])
        self.fir_tail = z[-len(self.fir_tail):]
        y = np.convolve(z, self.fir, mode="valid")
        if self.fir_prev is not None:
            y = np.convolve(z, self.fir_prev, mode="valid") * (1 - fade) + y * fade
            self.fir_prev = None
        x = y.astype(np.float32)

        if p["echo"] > 0:
            x = self._echo(x, fade)
        else:  # เก็บเสียงย้อนหลังไว้ เปิดก้องทีหลังจะได้ก้องเสียงล่าสุด ไม่ใช่เสียงเก่าค้าง
            self.echo_hist = np.concatenate([self.echo_hist[n:], x])
        self.echo_prev_ms = None
        return x.astype(np.float32)

    def _echo(self, x, fade):
        n, H = len(x), len(self.echo_hist)

        def taps(ms):
            d1 = int(self.sr * ms / 1000)
            d2 = int(d1 * 1.6)
            return (0.45 * self.echo_hist[H - d1:H - d1 + n] + 0.30 * self.echo_hist[H - d2:H - d2 + n]) * self.p["echo"]
        if n > int(self.sr * 0.05):  # block ยาวกว่าระยะสั้นสุด (50 ms): แบ่งย่อย
            half = n // 2
            return np.concatenate([self._echo(x[:half], fade[:half]), self._echo(x[half:], fade[half:])])
        wet = taps(self.p["echo_ms"])
        if self.echo_prev_ms is not None:  # เพิ่งเปลี่ยนระยะ: ผสมจากระยะเดิมไประยะใหม่
            wet = taps(self.echo_prev_ms) * (1 - fade) + wet * fade
        y = (x + wet).astype(np.float32)
        self.echo_hist = np.concatenate([self.echo_hist[n:], y])
        return y


def preset_params(key, user_presets=None):
    """ค่าของชุดเสียง (สำเร็จรูป หรือที่ผู้ใช้บันทึก "u:ชื่อ")"""
    if key in PRESETS:
        return dict(PRESETS[key][1])
    if key.startswith("u:") and user_presets and key[2:] in user_presets:
        return _p(**user_presets[key[2:]])
    return dict(DEFAULT_PARAMS)
