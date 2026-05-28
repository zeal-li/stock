@echo off
cd /d "%~dp0"
echo Starting Stock Info Server...
.\venv\Scripts\python app.py
pause