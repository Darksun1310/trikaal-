@echo off
echo Starting GitHub Codebase AI...
echo.

REM Start backend server
echo [1/2] Starting backend server on port 3001...
start "GitHub AI - Backend" cmd /k "cd /d "%~dp0server" && node index.js"

REM Wait a moment for backend to boot
timeout /t 2 /nobreak >nul

REM Start frontend dev server
echo [2/2] Starting frontend on port 5173...
start "GitHub AI - Frontend" cmd /k "cd /d "%~dp0client" && npm run dev"

echo.
echo ✅ Both servers starting!
echo    Frontend: http://localhost:5173
echo    Backend:  http://localhost:3001
echo.
echo Make sure you have a Gemini API key ready at aistudio.google.com
pause
