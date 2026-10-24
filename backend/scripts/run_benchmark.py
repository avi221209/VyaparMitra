"""
VyaparMitra - Offline Runner for Full Walk-Forward Evaluation Benchmark
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine
"""

import json
import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.config import DATA_DIR
from backend.app.services.replay import EvaluationEngine, CACHE_FILE


def main():
    print("=" * 80)
    print("VYAPARMITRA: FULL 5-SEED WALK-FORWARD BENCHMARK EVALUATION")
    print("Methods: A, B, C, V, V-SS, V-SL, O | Scenarios: scarce, balanced, abundant")
    print("=" * 80)

    engine = EvaluationEngine(seeds=[1, 2, 3, 4, 5])
    t0 = time.time()

    def on_progress(p, msg):
        pct = p * 100.0
        print(f"[{pct:5.1f}%] {msg}")

    report = engine.run_all(progress_callback=on_progress)
    elapsed = time.time() - t0

    print("\n" + "=" * 80)
    print(f"FULL BENCHMARK COMPLETED IN {elapsed:.2f} SECONDS ({elapsed/60:.2f} MINUTES)")
    print(f"Cache persisted to: {CACHE_FILE}")
    print("=" * 80)

    for scen, data in report["scenarios_aggregate"].items():
        print(f"\nScenario: {scen.upper()} (Stock Multiplier: {data['stock_multiplier']:.1f}x)")
        print(f"  Headroom Gap (Oracle - Baseline A) : {data['headroom_gap']:+.2f} percentage points")
        print(f"  Headroom Status                    : {data['headroom_status']}")
        print(f"  Pass/Fail Evaluation               : {data['targets_evaluation'].get('overall_status')}")
        print(f"  Seeds where Method V Wins vs A     : {data['v_wins_count']} / 5 seeds")

        print("  Method Performance Matrix:")
        print("  " + "-" * 75)
        print(f"  {'Method':6s} | {'Fill Rate':14s} | {'Unmet Units':12s} | {'Expiry Waste':12s} | {'Cost-to-Serve':15s} | {'Trans/Unit':10s}")
        print("  " + "-" * 75)

        for m in ["A", "B", "C", "V", "V-SS", "V-SL", "O"]:
            met = data["method_metrics"][m]
            fr_str = f"{met['fill_rate_mean']:.2f}% ± {met['fill_rate_std']:.2f}"
            unmet_str = f"{met['unmet_units_mean']:,.0f}"
            waste_str = f"{met['expiry_waste_mean']*100:.2f}%"
            cts_str = f"Rs {met['cost_to_serve_mean']:,.0f}"
            trans_str = f"Rs {met['transport_per_unit_mean']:.2f}"
            print(f"  {m:6s} | {fr_str:14s} | {unmet_str:12s} | {waste_str:12s} | {cts_str:15s} | {trans_str:10s}")
        print("  " + "-" * 75)

        if data["targets_evaluation"].get("checks"):
            print("  Pre-Registered Target Results:")
            for target_name, t_info in data["targets_evaluation"]["checks"].items():
                status_str = "PASS" if t_info.get("passed") else "FAIL"
                print(f"    - {target_name:18s}: [{status_str}] (Target: {t_info.get('target')})")
                if not t_info.get("passed") and t_info.get("likely_cause"):
                    print(f"      Likely cause: {t_info.get('likely_cause')}")

    return report


if __name__ == "__main__":
    main()
