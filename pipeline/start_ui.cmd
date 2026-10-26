@echo off
rem Unified pipeline dashboard: http://127.0.0.1:8765
cd /d "%~dp0"
.venv\Scripts\python.exe -u -m uvicorn ui.server:app --host 127.0.0.1 --port 8765 --log-level warning
