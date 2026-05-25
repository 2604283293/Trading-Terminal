@echo off
REM 启动 Trading Terminal 桌面客户端
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -m desktop_shell
echo.
echo ============================================================
echo Python exit code: %ERRORLEVEL%
echo ============================================================
echo.
pause
