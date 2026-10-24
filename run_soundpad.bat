@echo off
cd /d "%~dp0"
python -c "import sounddevice, soundfile, numpy, pynput" 2>nul || pip install sounddevice soundfile numpy pynput
python -c "import yt_dlp, imageio_ffmpeg" 2>nul || pip install yt-dlp imageio-ffmpeg
start "" pythonw soundpad.py
