"""เสียง: โหลดไฟล์ + cache (16-bit), ผสมเสียงหลายเสียงส่งออกอุปกรณ์, ส่งเสียงไมค์จริงผ่าน"""


import threading
from collections import OrderedDict

import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import BLOCK


CACHE_LIMIT = 128 * 2**20  # bytes (เก็บเฉพาะเสียงสั้น แบบ 16-bit)


_cache = OrderedDict()  # LRU: ตัวที่เพิ่งใช้อยู่ท้ายสุด


LONG_SOUND_SECONDS = 30  # ไฟล์ยาวกว่านี้อ่านจากดิสก์ทีละช่วง (FileSource) แทนการโหลดทั้งไฟล์เข้า RAM


HEAD_SECONDS = 2         # เก็บต้นเพลงยาวไว้ใน RAM ให้กดซ้ำแล้วออกทันที


HEAD_CACHE_LIMIT = 32 * 2**20


_head_cache = OrderedDict()


def _cache_put(cache, key, data, limit):
    cache[key] = data
    total = sum(d.nbytes for d in cache.values())
    while total > limit and len(cache) > 1:
        _, old = cache.popitem(last=False)  # เสียงที่กำลังเล่นยังอยู่ใน voices ไม่หาย
        total -= old.nbytes


def to_int16(x):
    """float32 [-1,1] -> int16 (ใช้ RAM ครึ่งเดียว; แปลงกลับตอนผสมเสียงทีละช่วงเล็กๆ)"""
    return np.round(np.clip(x, -1.0, 1.0) * 32767).astype(np.int16)


def load_audio(path, target_sr):
    """อ่านไฟล์เป็น stereo int16 ที่ sample rate ของอุปกรณ์ (มี cache จำกัดขนาด)"""
    key = (path, target_sr)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != target_sr and len(data) > 1:
        n = int(round(len(data) * target_sr / sr))
        x_old = np.arange(len(data))
        x_new = np.linspace(0, len(data) - 1, n)
        data = np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(2)], axis=1)
    data = np.ascontiguousarray(to_int16(data))
    _cache_put(_cache, key, data, CACHE_LIMIT)
    return data


LIMIT_KNEE = 0.8


def soft_limit(x):
    """กดเสียงที่ดังเกิน knee ให้โค้งเข้าหา 1.0 แทนการตัดแข็ง (ลดเสียงแตก)"""
    over = np.abs(x) > LIMIT_KNEE
    if over.any():
        v = x[over]
        room = 1.0 - LIMIT_KNEE
        x[over] = np.sign(v) * (LIMIT_KNEE + room * np.tanh((np.abs(v) - LIMIT_KNEE) / room))
    return x


class MicPassthrough:
    """อ่านไมค์จริงเก็บลง buffer เพื่อผสมเข้ากับไมค์เสมือน"""

    def __init__(self, device, sr, get_volume):
        self.sr = sr
        self.get_volume = get_volume
        self.buf = np.zeros((0, 2), np.float32)
        self.lock = threading.Lock()
        ch = min(2, sd.query_devices(device)["max_input_channels"])
        self.stream = sd.InputStream(device=device, samplerate=sr, channels=ch,
                                     dtype="float32", blocksize=BLOCK, callback=self._cb)
        self.stream.start()

    def _cb(self, indata, frames, t, status):
        mono = indata.mean(axis=1, keepdims=True)
        stereo = np.repeat(mono, 2, axis=1)
        with self.lock:
            self.buf = np.concatenate([self.buf, stereo])
            limit = int(self.sr * 0.15)  # กัน latency สะสม
            if len(self.buf) > limit:
                self.buf = self.buf[-limit:]

    def read(self, frames):
        with self.lock:
            chunk = self.buf[:frames]
            self.buf = self.buf[frames:]
        if len(chunk) < frames:
            chunk = np.concatenate([chunk, np.zeros((frames - len(chunk), 2), np.float32)])
        return chunk * self.get_volume()

    def close(self):
        self.stream.stop()
        self.stream.close()


class OutputMixer:
    """ผสมเสียงหลายเสียงพร้อมกันส่งออกอุปกรณ์หนึ่งตัว"""

    def __init__(self, device, get_volume, mic=None):
        info = sd.query_devices(device)
        self.sr = int(info["default_samplerate"])
        self.channels = min(2, info["max_output_channels"])
        self.get_volume = get_volume
        self.mic = mic
        self.voices = []  # [data (ndarray int16/float32 หรือ StreamSource/FileSource), pos, sound_id]
        self.paused = False  # พัก: เก็บตำแหน่งเสียงไว้ ไม่เดินหน้า (เสียงไมค์จริงยังผ่านตามปกติ)
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(device=device, samplerate=self.sr, channels=self.channels,
                                      dtype="float32", blocksize=BLOCK, callback=self._cb)
        self.stream.start()

    def play(self, data, sound_id):
        with self.lock:
            self.voices.append([data, 0, sound_id])

    def stop_all(self):
        with self.lock:
            self.voices = []

    def playing_ids(self):
        with self.lock:
            return [v[2] for v in self.voices]

    def _cb(self, outdata, frames, t, status):
        out = np.zeros((frames, 2), np.float32)
        with self.lock:
            if not self.paused:  # พักอยู่ = ไม่แตะ voices เลย ตำแหน่งจึงค้างไว้ที่เดิม
                alive = []
                for v in self.voices:
                    data, pos = v[0], v[1]
                    if not isinstance(data, np.ndarray):  # StreamSource / FileSource
                        chunk = data.read(pos, frames)  # ข้อมูลมาไม่ทัน = เงียบชั่วครู่ ไม่ข้ามเสียง
                        v[1] = pos + len(chunk)
                        finished = data.finished_at(v[1])
                    else:
                        chunk = data[pos:pos + frames]
                        if chunk.dtype == np.int16:
                            chunk = chunk.astype(np.float32) * (1 / 32768)
                        v[1] = pos + frames
                        finished = v[1] >= len(data)
                    out[:len(chunk)] += chunk
                    if not finished:
                        alive.append(v)
                self.voices = alive
        out *= self.get_volume()
        if self.mic is not None:
            out += self.mic.read(frames)
        soft_limit(out)
        if self.channels == 1:
            outdata[:, 0] = out.mean(axis=1)
        else:
            outdata[:] = out

    def close(self):
        self.stream.stop()
        self.stream.close()


def list_devices(kind):
    """คืน [(label, index)] ของอุปกรณ์ input/output"""
    apis = sd.query_hostapis()
    out = []
    for i, d in enumerate(sd.query_devices()):
        n = d["max_input_channels"] if kind == "in" else d["max_output_channels"]
        if n > 0:
            out.append((f"{d['name']} [{apis[d['hostapi']]['name']}]", i))
    return out
