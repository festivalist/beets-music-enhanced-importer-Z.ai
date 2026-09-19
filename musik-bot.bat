@echo off
rem Telegram bot service starter: runs in this console window, keep it open.
rem (Windows test setup; on the Pi this is a systemd service instead.)
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo .venv not found - run install.bat first.
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0musik.py" bot
pause
