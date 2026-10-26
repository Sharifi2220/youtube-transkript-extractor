@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Erst INSTALL_WINDOWS.bat ausfuehren.
 pause
 exit /b 1
)
echo Dieses Update installiert yt-dlp und yt-dlp-ejs aus PyPI neu.
echo Es ist NICHT automatisch. Bitte nur von vertrauenswuerdigen Netzen aktualisieren.
choice /M "Jetzt bewusst aktualisieren"
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default]"
if errorlevel 1 (echo Update fehlgeschlagen.& pause & exit /b 1)
".venv\Scripts\python.exe" -m yt_dlp --version
pause
