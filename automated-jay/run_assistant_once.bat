@echo off
rem One turn-start pass right now (tech, skills, buildings, army), without the window; prints what each step did.
rem Same checks as "Run now" in the assistant window: only on your turn, after 3 s without input from you, and
rem not while a decision popup is open. Don't use it while run_assistant.bat is running; press Run now there.
setlocal
title automated-jay - one pass
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && py -3.14 -c "import sys" >nul 2>nul && set "PY=py -3.14"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :nopython

echo This runs every turn-start automation ONCE, right now: tech, skills, buildings, army.
echo It brings the game to the front and clicks in it without waiting for your turn or for you to stop clicking,
echo so use it only on the campaign map during your turn. Switching away from the game stops it.
echo.
choice /C YN /M "Run one pass now"
if errorlevel 2 (
    set "RC=0"
    goto :end
)
%PY% -X utf8 -m assist.runner --once
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo The pass stopped with an error, exit code %RC%. The messages above say why.
pause
goto :end

:nopython
echo Python 3.14 was not found. Install it from python.org, tick "Add python.exe to PATH", then run once:
echo     py -3.14 -m pip install -r requirements.txt
pause
set "RC=1"

:end
endlocal & exit /b %RC%
