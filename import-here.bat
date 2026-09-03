@echo off
rem Drag && drop one or more music folders onto this file.
rem Runs: scan -> import -> interactive review -> library report.
setlocal
if "%~1"=="" (
    echo Drag ^& drop a music folder onto this file ^(or pass it as a parameter^).
    pause
    exit /b 1
)
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo .venv not found - run install.bat first.
    pause
    exit /b 1
)
:loop
if "%~1"=="" goto done
echo.
echo ============================================================
echo  [%~1]
echo  step 1/3 - scan
echo ============================================================
"%~dp0.venv\Scripts\python.exe" "%~dp0musik.py" scan --root "%~1"
echo.
echo ============================================================
echo  [%~1]
echo  step 2/3 - import (this talks to MusicBrainz, be patient)
echo ============================================================
"%~dp0.venv\Scripts\python.exe" "%~dp0musik.py" import --unit "%~1"
echo.
echo ============================================================
echo  [%~1]
echo  step 3/3 - interactive review of doubtful units
echo  A = accept candidate, O = new search, I = by MBID,
echo  W = import as-is, S = skip, X = ignore, Q = abort rest
echo ============================================================
"%~dp0.venv\Scripts\python.exe" "%~dp0musik.py" review --unit "%~1"
shift
goto loop
:done
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0musik.py" report --verify
echo.
echo All done. Reports: %~dp0reports  Library: see config.yaml "directory"
pause
