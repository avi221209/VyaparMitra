"""
VyaparMitra - Evaluation & Benchmark API Router
FMCG Distribution Intelligence and Inventory Optimization Engine
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.services.replay import (
    CACHE_FILE,
    get_cached_evaluation,
    global_eval_runner,
)

router = APIRouter(prefix="/api/v1/evaluate", tags=["Evaluation & Benchmarks"])


@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any])
def get_evaluation_results() -> Dict[str, Any]:
    """
    Get cached evaluation results across methods (A, B, C, V, V-SS, V-SL, O),
    scenarios (scarce, balanced, abundant), and seeds.
    Returns instantaneously from disk cache or memory.
    If a rerun has failed, retains the existing good cache and includes the error notification.
    """
    cached = get_cached_evaluation(compute_if_missing=False)

    runner_status = global_eval_runner.get_status()

    # If cache is not yet on disk, return empty or pending status
    if not cached:
        # If cache file exists on disk, read it
        if CACHE_FILE.exists():
            cached = get_cached_evaluation(compute_if_missing=False)

    response = dict(cached) if cached else {
        "status": "pending_first_run",
        "message": "Evaluation has not completed its initial run. Call POST /api/evaluate/rerun to trigger.",
    }

    # If background runner has error, include error details without overwriting cached results
    if runner_status.get("last_error"):
        response["background_rerun_error"] = runner_status["last_error"]
        response["background_rerun_status"] = runner_status["status"]

    return response


@router.post("/rerun")
def trigger_evaluation_rerun() -> Dict[str, Any]:
    """
    Trigger a background re-run of the walk-forward replay simulation.
    Progress can be monitored via GET /api/evaluate/status.
    If the rerun fails, previous cached results are preserved.
    """
    started = global_eval_runner.start_rerun()
    current_status = global_eval_runner.get_status()

    if not started:
        return {
            "status": "already_running",
            "message": "An evaluation re-run is already in progress.",
            "progress": current_status["progress"],
            "current_step": current_status["current_step"],
        }

    return {
        "status": "started",
        "message": "Walk-forward evaluation re-run started in background.",
        "progress": 0.0,
        "current_step": current_status["current_step"],
    }


@router.get("/status")
def get_rerun_status() -> Dict[str, Any]:
    """Check current status and progress percentage of background evaluation job."""
    return global_eval_runner.get_status()
