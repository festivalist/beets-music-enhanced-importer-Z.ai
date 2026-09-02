@echo off
rem musik command shim: runs the tool from this folder's venv.
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo .venv not found - run install.bat first.
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0musik.py" %*
