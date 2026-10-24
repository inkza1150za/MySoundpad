"""ถอดรหัสเสียงแบบอ่านทีละช่วงด้วย ffmpeg: สตรีมจาก URL (YouTube) และเพลงยาวจากดิสก์"""


import subprocess
import threading
import time

import numpy as np

from .audio import HEAD_CACHE_LIMIT, HEAD_SECONDS, _cache_put, _head_cache, to_int16
from .config import STREAM_AHEAD, STREAM_KEEP


class StreamSource:
    """ถอดรหัสเสียงจาก URL ด้วย ffmpeg แบบสด

    ตำแหน่ง (pos, n) นับจากต้นเสียงเสมอ แต่ buffer เก็บแค่ช่วงรอบตำแหน่งที่กำลังเล่น:
    ถอดรหัสล่วงหน้าไม่เกิน STREAM_AHEAD วินาที และทิ้งส่วนที่เล่นผ่านไปแล้ว RAM จึงคงที่แม้คลิปยาวเป็นชั่วโมง
    """

    def __init__(self, url, headers, sr, start=None, end=None, network=True):
        import imageio_ffmpeg
        self.sr = sr
        self.data = np.zeros((sr * (STREAM_AHEAD + STREAM_KEEP * 2), 2), np.float32)
        self.base = 0      # ตำแหน่งของ data[0]
        self.n = 0         # ถอดรหัสมาแล้วถึงตำแหน่งนี้
        self.read_pos = 0  # ตำแหน่งที่เล่นไปไกลสุด
        self.stopped = False
        self.done = False
        self.error = None
        self.lock = threading.Lock()
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
        if network:  # ตัวเลือก reconnect ใช้ได้เฉพาะ http (ไฟล์ในเครื่องไม่ต้องใช้)
            cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        if headers:
            cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
        if start is not None:
            cmd += ["-ss", str(start)]
        if end is not None:
            cmd += ["-to", str(end)]
        cmd += ["-i", url, "-vn", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        rest = b""
        try:
            while not self.stopped:
                if self.n - self.read_pos > self.sr * STREAM_AHEAD:  # ล่วงหน้าพอแล้ว รอให้เล่นตามทัน
                    time.sleep(0.05)
                    continue
                raw = self.proc.stdout.read1(65536)
                if not raw:
                    break
                raw = rest + raw
                usable = len(raw) - len(raw) % 8  # 1 frame = 2ch x float32
                rest = raw[usable:]
                frames = np.frombuffer(raw[:usable], np.float32).reshape(-1, 2)
                with self.lock:
                    drop = self.read_pos - self.base - self.sr * STREAM_KEEP
                    if drop > 0:  # ทิ้งส่วนที่เล่นผ่านไปแล้ว
                        used = self.n - self.base
                        self.data[:used - drop] = self.data[drop:used]
                        self.base += drop
                    end = self.n - self.base + len(frames)
                    if end > len(self.data):
                        grown = np.zeros((end * 2, 2), np.float32)
                        grown[:self.n - self.base] = self.data[:self.n - self.base]
                        self.data = grown
                    self.data[self.n - self.base:end] = frames
                    self.n += len(frames)
            self.proc.wait()
            if self.proc.returncode not in (0, None) and self.n == 0:
                err = self.proc.stderr.read().decode("utf-8", "replace").strip()
                self.error = err[-200:] or f"ffmpeg exit {self.proc.returncode}"
        except Exception as e:
            self.error = str(e)
        finally:
            self.done = True

    def read(self, pos, frames):
        with self.lock:
            i = max(pos - self.base, 0)
            chunk = self.data[i:min(i + frames, self.n - self.base)].copy()
            self.read_pos = max(self.read_pos, pos + len(chunk))
            return chunk

    def finished_at(self, pos):
        return self.done and pos >= self.n

    def stop(self):
        self.stopped = True
        if self.proc.poll() is None:
            self.proc.kill()


class FileSource:
    """เพลงยาวจากไฟล์ในเครื่อง: อ่านจากดิสก์ทีละช่วงด้วย ffmpeg (RAM คงที่ ~14 MB ไม่ว่าเพลงยาวแค่ไหน)

    ต้นเพลง HEAD_SECONDS วินาทีแรกเก็บไว้ใน RAM ตั้งแต่เล่นครั้งแรก ครั้งต่อไปจึงเริ่มเล่นทันที
    ระหว่างที่ ffmpeg เริ่มถอดรหัสจากต้นเพลงอยู่เบื้องหลัง ต้นเพลงกับส่วนที่เหลือมาจาก ffmpeg ตัวเดียวกัน
    รอยต่อจึงตรงกันทุก sample
    """

    def __init__(self, path, sr):
        self.key = (path, sr)
        self.sr = sr
        self.head = _head_cache.get(self.key)  # int16 หรือ None (ยังไม่เคยเล่น)
        if self.head is not None:
            _head_cache.move_to_end(self.key)
        self.head_frames = sr * HEAD_SECONDS
        self.stream = StreamSource(path, None, sr, network=False)

    @property
    def done(self):
        return self.stream.done

    @property
    def error(self):
        return self.stream.error

    def read(self, pos, frames):
        if self.head is None:
            self._save_head()
        elif pos < len(self.head):
            chunk = self.head[pos:pos + frames].astype(np.float32) * (1 / 32768)
            if len(chunk) < frames:  # คร่อมรอยต่อ: ต่อด้วยข้อมูลจาก ffmpeg
                rest = self.stream.read(pos + len(chunk), frames - len(chunk))
                chunk = np.concatenate([chunk, rest])
            return chunk
        return self.stream.read(pos, frames)

    def _save_head(self):
        s = self.stream
        with s.lock:
            if s.base == 0 and s.n >= self.head_frames:
                self.head = to_int16(s.data[:self.head_frames])
                _cache_put(_head_cache, self.key, self.head, HEAD_CACHE_LIMIT)

    def finished_at(self, pos):
        return self.stream.finished_at(pos)

    def stop(self):
        self.stream.stop()
