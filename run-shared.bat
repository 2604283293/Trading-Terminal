@echo off
REM Trading Terminal shared data service (FastAPI on 127.0.0.1:8000)
cd /d "%~dp0"

REM Check if port 8000 is already in use
netstat -ano 2>nul | findstr ":8000.*LISTENING" >nul
if %ERRORLEVEL% equ 0 (
    echo [WARN] Port 8000 is already in use — service may already be running.
    echo.
    echo If you need to restart, first close the other terminal running
    echo run-shared.bat or kill the process manually:
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000.*LISTENING"') do echo   taskkill /PID %%a
    echo.
    pause
    exit /b 1
)

echo Starting shared data service...
echo Logs written to: shared-api.log
echo.
".venv\Scripts\python.exe" -m uvicorn shared.api.main:app --host 127.0.0.1 --port 8000 --reload
pause
