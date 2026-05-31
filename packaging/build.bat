@echo off
setlocal
cd /d "%~dp0\.."

if "%VERSION%"=="" set VERSION=0.0.0
echo === Building Trading-Terminal v%VERSION% ===

if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [1/3] Running PyInstaller...
uv run pyinstaller packaging\Trading-Terminal.spec
if %ERRORLEVEL% neq 0 (
    echo PyInstaller failed!
    exit /b 1
)

echo [2/3] Building NSIS installer...
"C:\Program Files (x86)\NSIS\makensis.exe" /DVERSION=%VERSION% packaging\installer.nsi
if %ERRORLEVEL% neq 0 (
    echo NSIS failed!
    exit /b 1
)

echo [3/3] Build complete!
dir dist\Trading-Terminal-Setup-*.exe
