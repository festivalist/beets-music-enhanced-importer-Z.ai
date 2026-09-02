@echo off
rem One-click installer for musik (beets-based MusicBrainz tagger).
rem Installs Python if needed, creates a venv, installs dependencies,
rem downloads the fpcalc fingerprinter, and starts the setup wizard.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
