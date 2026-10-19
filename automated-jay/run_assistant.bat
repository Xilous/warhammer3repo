@echo off
rem Starts the automated-jay assistant without a console window (player request 2026-10-18): its widget over the
rem game, and the automations. What it prints goes to runs\console.log. Safe to double-click; before or after the
rem game. For a console that shows the log live, use run_assistant_console.bat.
setlocal
cd /d "%~dp0"
set "PYW="
where pyw >nul 2>nul && pyw -3.14 -c "import sys" >nul 2>nul && set "PYW=pyw -3.14"
if not defined PYW (
    where pythonw >nul 2>nul && set "PYW=pythonw"
)
if not defined PYW goto :nopython
start "" %PYW% -X utf8 -m assist.runner %*
endlocal & exit /b 0

:nopython
echo Python 3.14 (pythonw) was not found. Install it from python.org, tick "Add python.exe to PATH", then run once:
echo     py -3.14 -m pip install -r requirements.txt
pause
endlocal & exit /b 1
