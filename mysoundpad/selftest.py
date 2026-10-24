"""MySoundpad.exe --selftest <ไฟล์ผล>: ตรวจทุกส่วนแล้วเขียนผลลงไฟล์ (exe ไม่มีคอนโซลให้ดู)"""


import subprocess
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from . import config
from .audio import OutputMixer
from .config import APP_VERSION, DATA_DIR, FROZEN
from .hotkeys import HotkeyManager
from .streaming import StreamSource
from .youtube import import_ytdlp, youtube_download, youtube_info, youtube_stream_url


def selftest(out_path):
    """MySoundpad.exe --selftest <ไฟล์ผล> : ตรวจทุกส่วนแล้วเขียนผลลงไฟล์ (exe ไม่มีคอนโซลให้ดู)"""
    import tempfile
    lines = []

    def check(label, fn):
        t0 = time.perf_counter()
        try:
            lines.append(f"OK   {label}: {fn()} ({time.perf_counter() - t0:.2f}s)")
        except Exception as e:
            lines.append(f"FAIL {label}: {type(e).__name__}: {str(e)[:200]}")

    zoo = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    check("app", lambda: f"v{APP_VERSION} frozen={FROZEN} data={DATA_DIR}")
    check("cable device", lambda: [d["name"] for d in sd.query_devices() if "CABLE Input" in d["name"]][:1] or 1 / 0)

    def ffmpeg():
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([exe, "-version"], capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return r.stdout.split("\n")[0][:40]
    check("ffmpeg", ffmpeg)

    def ytdlp():
        m = import_ytdlp()
        return f"{m.version.__version__} from {'updated zip' if '.zip' in m.__file__ else 'bundled'}"
    check("yt-dlp", ytdlp)
    check("youtube info", lambda: youtube_info(zoo)["title"])

    def stream():
        url, headers = youtube_stream_url(zoo)
        src = StreamSource(url, headers, 44100, 2, 4)
        while not src.done:
            time.sleep(0.05)
        src.stop()
        return f"{src.n / 44100:.2f}s decoded error={src.error}"
    check("stream", stream)

    def download():
        old, config.YT_DIR = config.YT_DIR, tempfile.mkdtemp()
        try:
            p = youtube_download(zoo, "selftest", 2, 4, lambda m: None)
            return f"{sf.info(p).duration:.2f}s mp3 readable"
        finally:
            config.YT_DIR = old
    check("download", download)

    def hotkeys():
        h = HotkeyManager()
        time.sleep(0.2)
        alive = h.listener.is_alive()
        h.stop()
        return f"listener alive={alive}"
    check("hotkey listener", hotkeys)

    def cable_loop():
        devs = sd.query_devices()
        out = next(i for i, d in enumerate(devs) if "CABLE Input" in d["name"] and d["hostapi"] == 0)
        rec_dev = next(i for i, d in enumerate(devs) if "CABLE Output" in d["name"] and d["hostapi"] == 0)
        m = OutputMixer(out, lambda: 1.0)
        tone = np.repeat((0.3 * np.sin(np.arange(m.sr) * 2 * np.pi * 440 / m.sr)).astype(np.float32)[:, None], 2, 1)
        rec = sd.rec(int(m.sr * 1.4), samplerate=m.sr, channels=1, device=rec_dev, dtype="float32")
        time.sleep(0.2)
        m.play(tone, 0)
        sd.wait()
        m.close()
        peak = float(np.abs(rec).max())
        return f"recorded peak {peak:.3f}" if peak > 0.2 else 1 / 0
    check("play into CABLE", cable_loop)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
