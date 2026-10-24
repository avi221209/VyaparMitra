import json
from pathlib import Path

cache_file = Path("data/evaluation_cache.json")
data = json.loads(cache_file.read_text(encoding="utf-8"))

print("=== SCENARIOS EVALUATION SUMMARY ===")
for scen, sdata in data["scenarios_aggregate"].items():
    print(f"\n--- SCENARIO: {scen.upper()} ---")
    print(f"Stock Multiplier: {sdata['stock_multiplier']}")
    print(f"Headroom Gap (O - A): {sdata['headroom_gap']:+.2f} percentage points")
    print(f"Headroom Status: {sdata['headroom_status']}")
    print(f"V Wins Count: {sdata['v_wins_count']} / 5")
    print(f"Overall Status: {sdata['targets_evaluation']['overall_status']}")
    
    print("\nMethod Performance:")
    for m in ["A", "B", "C", "V", "V-SS", "V-SL", "O"]:
        met = sdata["method_metrics"][m]
        print(f"  Method {m:6s}: FillRate={met['fill_rate_mean']:5.2f}% ± {met['fill_rate_std']:4.2f} | Unmet={met['unmet_units_mean']:6.0f} | Waste={met['expiry_waste_mean']*100:4.2f}% | CTS=Rs {met['cost_to_serve_mean']:9,.0f} | Trans/Unit=Rs {met['transport_per_unit_mean']:4.2f}")
    
    print("\nPre-Registered Target Checks:")
    for t_name, t_info in sdata["targets_evaluation"]["checks"].items():
        print(f"  Target: {t_name:18s} -> Status: {'PASS' if t_info['passed'] else 'FAIL'} | Value: {t_info.get('value')} vs Target: {t_info.get('target')}")
        if not t_info["passed"] and t_info.get("likely_cause"):
            print(f"    Likely Cause: {t_info['likely_cause']}")
