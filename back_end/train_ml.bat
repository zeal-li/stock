@echo off
cd /d "%~dp0"
echo ========================================
echo   ML XGBoost 模型训练
echo ========================================
echo.
..\venv\Scripts\python -m ml_train.train
echo.
echo ========================================
echo   训练完成
echo ========================================
pause
