@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Der Python Launcher fehlt. Bitte Python 3.11 oder neuer von python.org installieren.
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Python 3.11 oder neuer erforderlich.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo Virtuelle Umgebung konnte nicht erstellt werden.& pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Installation fehlgeschlagen.& pause & exit /b 1)
echo Python + yt-dlp[default] installiert. Bei YouTube-Problemen kann Deno noetig sein.
echo Siehe README.md. Keine automatische Deno-Installation.
pause
