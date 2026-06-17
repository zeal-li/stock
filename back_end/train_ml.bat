@echo off
cd /d "%~dp0"
echo ========================================
echo   ML XGBoost Training
echo ========================================
..\venv\Scripts\python -m ml_train.train
echo.
echo ========================================
echo   Done
echo ========================================
pause
