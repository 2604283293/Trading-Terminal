@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m desktop_shell
echo.
echo ============================================================
echo Python exit code: %ERRORLEVEL%
echo ============================================================
echo.
pause
