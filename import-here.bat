@echo off
rem Drag && drop one or more music folders onto this file.
rem Runs for each folder: scan -> import -> interactive review -> cleanup.
rem Finally prints the library report.
setlocal EnableDelayedExpansion
rem Anchor the tool directory BEFORE any shift: %~dp0 can be re-resolved
rem against the console's working directory after shift (drag&drop sets a
rem different CWD), which breaks later venv calls.
set "TOOLDIR=%~dp0"
if "%TOOLDIR:~-1%"=="\" set "TOOLDIR=%TOOLDIR:~0,-1%"
set "PY=%TOOLDIR%\.venv\Scripts\python.exe"

if "%~1"=="" (
    echo Drag ^& drop a music folder onto this file ^(or pass it as a parameter^).
    pause
    exit /b 1
)
if not exist "%PY%" (
    echo .venv not found in %TOOLDIR% - run install.bat first.
    pause
    exit /b 1
)

rem Count dropped folders for the progress display.
set /a TOTAL=0
set /a IDX=0
for %%X in (%*) do set /a TOTAL+=1

:loop
if "%~1"=="" goto done
set /a IDX+=1
echo.
echo ============================================================
echo  folder !IDX! of %TOTAL% : %~1
echo ============================================================
echo.
echo ------------------------------------------------------------
echo  step 1/4 - scan
echo ------------------------------------------------------------
"%PY%" "%TOOLDIR%\musik.py" scan --root "%~1"
echo ------------------------------------------------------------
echo  step 2/4 - import (this talks to MusicBrainz, be patient)
echo ------------------------------------------------------------
"%PY%" "%TOOLDIR%\musik.py" import --unit "%~1"
echo.
echo ------------------------------------------------------------
echo  step 3/4 - interactive review of doubtful units
echo  A = accept candidate, O = new search, I = by MBID,
echo  W = import as-is, S = skip, X = ignore, Q = abort rest
echo ------------------------------------------------------------
"%PY%" "%TOOLDIR%\musik.py" review --unit "%~1"
echo.
echo ------------------------------------------------------------
echo  step 4/4 - cleanup: archive leftovers (.nfo/.sfv/.m3u/...) of
echo  imported albums to _trash, delete folders left empty
echo ------------------------------------------------------------
"%PY%" "%TOOLDIR%\musik.py" cleanup --root "%~1"
shift
goto loop
:done
echo.
"%PY%" "%TOOLDIR%\musik.py" report --verify
echo.
echo All done. Reports: %TOOLDIR%\reports   Library: see config.yaml "directory"
pause
