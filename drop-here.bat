@echo off
rem Drag && drop one or more music folders onto this file.
rem COPIES each folder to the Raspberry Pi dropzone share; the ingest
rem timer there (every 15 min) imports everything into the beets library
rem and empties the dropzone. Sources stay on this PC (delete by hand).
rem
rem Override the target share by setting the MUSIK_DROP environment
rem variable, e.g.:  setx MUSIK_DROP \\192.168.50.99\Musik
setlocal EnableDelayedExpansion
set "SHARE=%MUSIK_DROP%"
if "%SHARE%"=="" set "SHARE=\\192.168.50.43\Musik"
set "DROPZONE=%SHARE%\_incoming\windows"

if "%~1"=="" (
    echo Drag ^& drop one or more music folders onto this file.
    echo Target: %DROPZONE%
    pause
    exit /b 1
)

rem Probe the share once before copying anything.
if not exist "%DROPZONE%\" (
    echo Dropzone not reachable: %DROPZONE%
    echo Check that the Pi is up and that this user may write the share.
    pause
    exit /b 1
)

set /a TOTAL=0
set /a IDX=0
for %%X in (%*) do set /a TOTAL+=1

:loop
if "%~1"=="" goto done
set /a IDX+=1
echo.
echo ============================================================
echo  folder %IDX% of %TOTAL% : %~nx1
echo ============================================================
call :copyone "%~f1" "%~nx1"
shift
goto loop

:done
echo.
echo Fertig: %TOTAL% Ordner im Staging. Der Pi importiert sie beim
echo naechsten Timer-Lauf (15-Minuten-Takt) und leert die Dropzone.
echo Status im Blick behalten: Telegram-Bot /status oder Plexamp.
pause
exit /b 0

:copyone
rem %1 = absolute source path, %2 = display/target name
set "SRC=%~f1"
set "BASE=%~2"
if "%BASE%"=="" set "BASE=musik-%RANDOM%"
set "DEST=%DROPZONE%\%BASE%"
if exist "%DEST%\" call :uniquename
mkdir "%DEST%" >nul 2>&1
rem /E all subdirs, /R:2 /W:2 retries, /NFL /NDL /NJH /NJS compact;
rem robocopy exit level ^<8 means success.
robocopy "%SRC%" "%DEST%" /E /R:2 /W:2 /NP /NFL /NDL /NJH /NJS
if errorlevel 8 (
    echo  FEHLER beim Kopieren von %BASE% - bitte erneut versuchen.
) else (
    echo  OK - liegt im Staging, der Pi uebernimmt es automatisch.
)
goto :eof

:uniquename
rem Append -2, -3, ... on collision so two different drops of
rem same-named folders never merge into one album dir.
set /a N=1
:uniqueloop
set /a N+=1
set "DEST=%DROPZONE%\%BASE%-%N%"
if exist "%DEST%\" goto uniqueloop
goto :eof
