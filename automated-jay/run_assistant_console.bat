@echo off
rem Starts the automated-jay assistant WITH a console that shows the log (run_assistant.bat starts it without one).
rem Safe to double-click. Start it before or after the game. Close the assistant window to stop.
setlocal
title automated-jay assistant
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && py -3.14 -c "import sys" >nul 2>nul && set "PY=py -3.14"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :nopython

echo automated-jay: starting the assistant with "%PY%" in %CD%
echo Close the assistant window, or press Ctrl+C here, to stop. This console shows the log.
echo.
%PY% -X utf8 -m assist.runner %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" goto :end
if "%RC%"=="130" (
    echo Stopped with the kill switch ^(Shift+Esc^).
    goto :end
)
if "%RC%"=="3" (
    echo The assistant is already running: use its widget over the game. This window closes.
    timeout /t 5 >nul
    goto :end
)
echo.
echo The assistant stopped with an error, exit code %RC%. The messages above say why.
echo If a module is missing, install the requirements once:  %PY% -m pip install -r requirements.txt
pause
goto :end

:nopython
echo Python 3.14 was not found. Install it from python.org, tick "Add python.exe to PATH", then run once:
echo     py -3.14 -m pip install -r requirements.txt
pause
set "RC=1"

:end
endlocal & exit /b %RC%
