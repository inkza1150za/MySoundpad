@echo off
cd /d "%~dp0"
python -c "import sounddevice, soundfile, numpy, pynput" 2>nul || pip install sounddevice soundfile numpy pynput
python -c "import yt_dlp, imageio_ffmpeg" 2>nul || pip install yt-dlp imageio-ffmpeg
python -c "import tkinterdnd2" 2>nul || pip install tkinterdnd2
start "" pythonw soundpad.py
