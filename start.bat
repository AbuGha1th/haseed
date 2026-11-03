@echo off
rem Haseed for Windows: double-click to start. Close this window to stop.
cd /d "%~dp0"
where py >nul 2>nul || (
  echo Haseed needs Python 3. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and open this file again.
  pause & exit /b 1
)
if not exist .venv (
  echo First run: setting up Haseed ^(takes a minute^)...
  py -3 -m venv .venv || (pause & exit /b 1)
)
rem -U keeps yt-dlp current; sites change often and old versions stop working
.venv\Scripts\python -m pip install -q -U --disable-pip-version-check -r requirements.txt || (echo Setup failed, see above. & pause & exit /b 1)
.venv\Scripts\python server.py
pause
