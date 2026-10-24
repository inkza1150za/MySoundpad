@echo off
rem Builds MySoundpad.exe and the installer -> build\installer\MySoundpad-Setup-<version>.exe
rem Needs: pip install pyinstaller pillow sounddevice soundfile numpy pynput yt-dlp imageio-ffmpeg
rem        and Inno Setup 6 (winget install JRSoftware.InnoSetup)
setlocal
cd /d "%~dp0"
set ASSETS=%~dp0build_assets
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe

if not exist "%ASSETS%\icon.ico" python "%ASSETS%\make_icon.py" || goto :fail

echo === [1/2] PyInstaller ===
python -m PyInstaller --noconfirm --clean --windowed --name MySoundpad ^
  --icon "%ASSETS%\icon.ico" --add-data "%ASSETS%\icon.ico;." --add-data "%ASSETS%\icon.png;." ^
  --version-file "%ASSETS%\version_info.txt" ^
  --collect-data imageio_ffmpeg --collect-submodules yt_dlp ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --distpath build\dist --workpath build\work --specpath build ^
  soundpad.py || goto :fail

echo === [2/2] Inno Setup ===
"%ISCC%" /Q installer.iss || goto :fail

echo.
echo Done: build\installer
dir /b build\installer
exit /b 0

:fail
echo.
echo *** BUILD FAILED ***
exit /b 1
