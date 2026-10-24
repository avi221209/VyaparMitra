#!/usr/bin/env bash
set -e

echo "====================================================================="
echo "VyaparMitra: Distribution Intelligence and Inventory Optimization"
echo "Regional FMCG Distributor Planning Desk"
echo "====================================================================="

# 1. Verify Prerequisites
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python is not installed or not in PATH."
    exit 1
fi

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

if ! command -v npm &> /dev/null; then
    echo "[ERROR] Node.js / npm is not installed or not in PATH."
    exit 1
fi

echo "[OK] Python and Node.js detected."

# 2. Check Node dependencies
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# 3. Check Evaluation Benchmark Cache
if [ ! -f "data/evaluation_cache.json" ]; then
    echo "Evaluation benchmark cache missing. Running initial benchmark..."
    $PYTHON_CMD backend/scripts/run_benchmark.py
fi

# 4. Start backend and frontend
echo "Starting VyaparMitra Backend (FastAPI on http://127.0.0.1:8000)..."
$PYTHON_CMD -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

echo "Starting VyaparMitra Frontend (Vite on http://localhost:5173)..."
npm run dev &
FRONTEND_PID=$!

echo "====================================================================="
echo "Application started!"
echo "Frontend: http://localhost:5173"
echo "API Docs: http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to stop both servers."
echo "====================================================================="

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" SIGINT SIGTERM EXIT
wait
