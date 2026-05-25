@echo off
REM 启动 Trading Terminal 共享数据服务（FastAPI on 127.0.0.1:8000）
cd /d "%~dp0"
".venv\Scripts\python.exe" -m uvicorn shared.api.main:app --host 127.0.0.1 --port 8000 --reload
