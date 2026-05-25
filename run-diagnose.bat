@echo off
cd /d "%~dp0"

echo ============================================================
echo Trading Terminal — Diagnostic Test
echo ============================================================
echo.
".venv\Scripts\python.exe" diagnose.py 2>&1
echo.
echo ============================================================
echo Diagnostic exit code: %ERRORLEVEL%
echo ============================================================
echo.
pause
