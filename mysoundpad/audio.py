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
    """อ่านไมค์จริงเก็บลง buffer เพื่อผสมเข้ากับไมค์เสมือน (ผ่าน voice changer ถ้าตั้งไว้)"""

    def __init__(self, device, sr, get_volume):
        self.sr = sr
        self.get_volume = get_volume
        self.fx = None            # VoiceFX หรือ None (สลับได้ระหว่างทำงาน แค่แทน object)
        self.monitor_on = False   # ส่งเสียงที่ผ่านเอฟเฟกต์ไปหูฟังด้วย (ไว้ลองเสียงตัวเอง)
        self.buf = np.zeros((0, 2), np.float32)
        self.mbuf = np.zeros((0, 2), np.float32)
        self.lock = threading.Lock()
        ch = min(2, sd.query_devices(device)["max_input_channels"])
        self.stream = sd.InputStream(device=device, samplerate=sr, channels=ch,
                                     dtype="float32", blocksize=BLOCK, callback=self._cb)
        self.stream.start()

    def _cb(self, indata, frames, t, status):
        mono = indata.mean(axis=1)
        fx = self.fx
        if fx is not None:
            mono = fx.process(mono)
        stereo = np.repeat(mono[:, None], 2, axis=1)
        limit = int(self.sr * 0.15)  # กัน latency สะสม
        with self.lock:
            self.buf = np.concatenate([self.buf, stereo])[-limit:]
            if self.monitor_on:
                self.mbuf = np.concatenate([self.mbuf, stereo])[-limit:]

    @staticmethod
    def _take(buf, frames):
        chunk, rest = buf[:frames], buf[frames:]
        if len(chunk) < frames:
            chunk = np.concatenate([chunk, np.zeros((frames - len(chunk), 2), np.float32)])
        return chunk, rest

    def read(self, frames):
        with self.lock:
            chunk, self.buf = self._take(self.buf, frames)
        return chunk * self.get_volume()

    def read_monitor(self, frames):
        with self.lock:
            chunk, self.mbuf = self._take(self.mbuf, frames)
        return chunk * self.get_volume()

    def close(self):
        self.stream.stop()
        self.stream.close()


class MonitorTap:
    """ให้ mixer ของหูฟังอ่านเสียงไมค์ที่ผ่านเอฟเฟกต์ (ปุ่ม "ฟังเสียงตัวเอง")"""

    def __init__(self, mic):
        self.mic = mic

    def read(self, frames):
        return self.mic.read_monitor(frames)


class OutputMixer:
    """ผสมเสียงหลายเสียงพร้อมกันส่งออกอุปกรณ์หนึ่งตัว"""

    def __init__(self, device, get_volume, mic=None):
        info = sd.query_devices(device)
        self.sr = int(info["default_samplerate"])
        self.channels = min(2, info["max_output_channels"])
        self.get_volume = get_volume
        self.mic = mic  # อะไรก็ได้ที่มี read(frames): เสียงไมค์จริง (CABLE) หรือเสียงตัวเองที่ผ่านเอฟเฟกต์ (หูฟัง)
        # [data (ndarray int16/float32 หรือ StreamSource/FileSource), pos, sound_id, loop, fade_left]
        self.voices = []
        self.paused = False  # พัก: เก็บตำแหน่งเสียงไว้ ไม่เดินหน้า (เสียงไมค์จริงยังผ่านตามปกติ)
        self.fade_frames = int(self.sr * 0.03)  # หยุดเสียงเดี่ยวแบบค่อยๆ เบาลง 30 ms กันเสียงคลิก
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(device=device, samplerate=self.sr, channels=self.channels,
                                      dtype="float32", blocksize=BLOCK, callback=self._cb)
        self.stream.start()

    def play(self, data, sound_id, loop=False):
        """loop: เสียงใน RAM วนต่อกันไม่มีรอยต่อ (เพลงยาว/สตรีมวนที่ฝั่ง ffmpeg แทน)"""
        with self.lock:
            self.voices.append([data, 0, sound_id, loop, None])

    def stop_sound(self, sound_id):
        """หยุดเฉพาะเสียงนี้ (ค่อยๆ เบาลง) เสียงอื่นเล่นต่อ"""
        with self.lock:
            if self.paused:  # พักอยู่ เวลาไม่เดิน ค่อยๆ เบาลงไม่ได้ -> เอาออกเลย
                self.voices = [v for v in self.voices if v[2] != sound_id]
                return
            for v in self.voices:
                if v[2] == sound_id and v[4] is None:
                    v[4] = self.fade_frames

    def stop_all(self):
        with self.lock:
            self.voices = []

    def playing_ids(self):
        with self.lock:
            return [v[2] for v in self.voices]

    def positions(self):
        """[(sound_id, ตำแหน่ง วินาที, ความยาว วินาที หรือ None)] ของเสียงที่เล่นอยู่ เรียงตามลำดับที่เริ่มเล่น
        (ความยาวรู้เฉพาะเสียงใน RAM สตรีม/เพลงยาวให้ผู้เรียกใช้ความยาวที่บันทึกไว้)"""
        with self.lock:
            return [(v[2], v[1] / self.sr, len(v[0]) / self.sr if isinstance(v[0], np.ndarray) else None)
                    for v in self.voices if v[4] is None]

    def sources(self, sound_id):
        """ตัวถอดรหัส (StreamSource/FileSource) ของเสียงนี้ ไว้สร้างตัวใหม่ตอนกระโดดไปช่วงอื่น"""
        with self.lock:
            return [v[0] for v in self.voices if v[2] == sound_id and v[4] is None
                    and not isinstance(v[0], np.ndarray)]

    def seek(self, sound_id, seconds, replace=None):
        """กระโดดไปตำแหน่งใหม่: เสียงใน RAM ย้ายตำแหน่งทันที ตัวถอดรหัสเปลี่ยนเป็นตัวใหม่จาก replace {id(ตัวเดิม): ตัวใหม่}
        (ตัวใหม่สร้างไว้ก่อนนอก lock เพราะเปิด ffmpeg ช้า ไม่ให้ audio callback ต้องรอ)"""
        with self.lock:
            for v in self.voices:
                if v[2] != sound_id or v[4] is not None:
                    continue
                if isinstance(v[0], np.ndarray):
                    n, pos = len(v[0]), int(seconds * self.sr)
                    v[1] = pos % n if v[3] and n else min(max(pos, 0), n)
                elif replace and id(v[0]) in replace:
                    v[0] = replace[id(v[0])]
                    v[1] = v[0].offset

    def _cb(self, outdata, frames, t, status):
        out = np.zeros((frames, 2), np.float32)
        with self.lock:
            if not self.paused:  # พักอยู่ = ไม่แตะ voices เลย ตำแหน่งจึงค้างไว้ที่เดิม
                alive = []
                for v in self.voices:
                    data, pos, _, loop, fade = v
                    if not isinstance(data, np.ndarray):  # StreamSource / FileSource
                        chunk = data.read(pos, frames)  # ข้อมูลมาไม่ทัน = เงียบชั่วครู่ ไม่ข้ามเสียง
                        v[1] = pos + len(chunk)
                        finished = data.finished_at(v[1])
                    else:
                        chunk = data[pos:pos + frames]
                        if loop and len(chunk) < frames and len(data):  # ต่อหัวเสียงทันทีที่ถึงท้าย
                            parts, need = [chunk], frames - len(chunk)
                            while need > 0:
                                parts.append(data[:need])
                                need -= len(parts[-1])
                            chunk = np.concatenate(parts)
                            v[1] = (pos + frames) % len(data)
                        else:
                            v[1] = pos + frames
                        if chunk.dtype == np.int16:
                            chunk = chunk.astype(np.float32) * (1 / 32768)
                        finished = not loop and v[1] >= len(data)
                    if fade is not None:  # กำลังค่อยๆ เบาลงก่อนหยุด
                        ramp = np.clip((fade - np.arange(len(chunk))) / self.fade_frames, 0, 1)
                        chunk = chunk * ramp[:, None]
                        v[4] = fade - len(chunk)
                        finished = finished or v[4] <= 0
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
