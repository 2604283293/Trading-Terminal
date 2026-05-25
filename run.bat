@echo off
REM 启动 Trading Terminal 桌面客户端
cd /d "%~dp0"
".venv\Scripts\python.exe" -m desktop_shell
