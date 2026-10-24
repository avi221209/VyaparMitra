@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo VyaparMitra: Distribution Intelligence and Inventory Optimization
echo Regional FMCG Distributor Planning Desk
echo =====================================================================

:: 1. Verify Prerequisites
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js / npm is not installed or not in PATH.
    pause
    exit /b 1
)

echo [OK] Python and Node.js detected.

:: 2. Check Node dependencies
if not exist "node_modules\" (
    echo Installing frontend dependencies...
    call npm install
)

:: 3. Check Evaluation Benchmark Cache
if not exist "data\evaluation_cache.json" (
    echo Evaluation benchmark cache missing. Running initial benchmark...
    python backend\scripts\run_benchmark.py
)

:: 4. Start backend and frontend
echo Starting VyaparMitra Backend (FastAPI on http://127.0.0.1:8000)...
start "VyaparMitra Backend" cmd /k "python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"

echo Starting VyaparMitra Frontend (Vite on http://localhost:5173)...
start "VyaparMitra Frontend" cmd /k "npm run dev"

echo =====================================================================
echo Application started!
echo Frontend: http://localhost:5173
echo API Docs: http://127.0.0.1:8000/docs
echo =====================================================================
