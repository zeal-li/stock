@echo off
cd /d "%~dp0"

echo ============================
echo   Git Push
echo ============================
echo.

:: 如果本地仓库未配置 git 用户信息，自动设置
git config user.name >nul 2>&1
if errorlevel 1 (
    echo Setting local git user info...
    git config user.name "zeal-li"
    git config user.email "64367160@qq.com"
)

echo.
echo Adding changes...
git add .

echo Git Status...
git status
echo.
set /p confirm="Proceed with commit & push? (Y/n): "
if /i not "%confirm%"=="Y" (
    echo Cancelled.
    pause
    exit /b
)

set /p msg="Enter commit message: "
if "%msg%"=="" (
    echo Commit message cannot be empty!
    pause
    exit /b 1
)
echo Committing...
git commit -m "%msg%"
if errorlevel 1 (
    echo Commit failed! Check the error above.
    pause
    exit /b 1
)

echo Pushing to remote...
git push
if errorlevel 1 (
    echo Push failed! Check your network or credentials.
    pause
    exit /b 1
)

echo.
echo Done!
pause
