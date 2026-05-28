@echo off
echo Stopping Stock Info Server...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000.*LISTENING') do (
    echo Killing PID %%a on port 5000...
    taskkill /F /PID %%a >nul 2>&1
)
echo Server stopped.
pause