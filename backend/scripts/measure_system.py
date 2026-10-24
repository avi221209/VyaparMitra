import time
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from datetime import date
from sqlmodel import Session
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.main import app
from backend.app.db import engine, get_session
from backend.app.services.optimizer import OptimizationService


def measure():
    print("--- 1. Measuring Plan Optimization Time (24x4x2 network) ---")
    with Session(engine) as session:
        service = OptimizationService(session)
        t0 = time.perf_counter()
        res = service.run_plan(plan_date=date(2026, 10, 24))
        t1 = time.perf_counter()
        plan_time_sec = t1 - t0
        print(f"Plan Time: {plan_time_sec*1000:.2f} ms ({plan_time_sec:.4f} s)")
        print(f"Solved lines: {len(res.lines)}, Total cartons: {res.total_cartons}, Total cost: {res.total_cost}")

    print("\n--- 2. Measuring API Endpoint Latencies (TestClient) ---")
    client = TestClient(app)
    
    endpoints = [
        ("POST", "/api/data/seed", None),
        ("GET", "/api/data/issues", None),
        ("POST", "/api/plan", {"horizon": 7}),
        ("GET", "/api/plan/latest", None),
        ("POST", "/api/scenario/override", {"source_id": "W1", "stock_percent": -20.0}),
        ("GET", "/api/evaluate", None),
        ("GET", "/api/audit", None),
    ]

    latencies = {}
    for method, path, payload in endpoints:
        times = []
        for _ in range(5):
            t_start = time.perf_counter()
            if method == "POST":
                r = client.post(path, json=payload or {})
            else:
                r = client.get(path)
            t_end = time.perf_counter()
            if r.status_code in (200, 201):
                times.append((t_end - t_start) * 1000)
            else:
                print(f"Error {r.status_code} on {path}: {r.text[:100]}")
        avg_ms = sum(times) / len(times) if times else 0
        min_ms = min(times) if times else 0
        max_ms = max(times) if times else 0
        latencies[f"{method} {path}"] = {"mean_ms": avg_ms, "min_ms": min_ms, "max_ms": max_ms}
        print(f"{method:4s} {path:25s} -> Mean: {avg_ms:6.2f} ms (Min: {min_ms:6.2f} ms, Max: {max_ms:6.2f} ms)")

    return plan_time_sec, latencies

if __name__ == "__main__":
    measure()
