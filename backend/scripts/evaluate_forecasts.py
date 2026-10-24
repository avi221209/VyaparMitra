"""
VyaparMitra - Forecast Evaluation Script
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Evaluates the Demand Forecasting Service across all simulated series:
 - Compares Chosen Models vs Seasonal-Naive baseline on WAPE and Bias.
 - Reports model selection distribution.
 - Reports category-wise and location-wise performance.
"""

from datetime import date as dt_date, timedelta
from pathlib import Path
import sys
from typing import Dict, List

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import numpy as np
import pandas as pd
from sqlmodel import Session, select


from backend.app.db import engine, init_db
from backend.app.models import Location, Product, SalesDaily
from backend.app.services.forecast import (
    ForecastService,
    compute_bias,
    compute_wape,
    evaluate_rolling_origin,
    is_zero_heavy,
)
from backend.app.services.simulator import FMCGSimulator


def run_evaluation() -> None:
    print("=" * 80)
    print("VyaparMitra: Demand Forecasting Engine Evaluation")
    print("Team Stark | Triwizathon 2026 | PS2 | SIMULATED Indian FMCG Data")
    print("=" * 80)

    init_db()
    with Session(engine) as session:
        # Check if DB has sales data
        has_sales = session.exec(select(SalesDaily)).first()
        if not has_sales:
            print("[INFO] Seeding simulator data...")
            sim = FMCGSimulator(seed=42)
            sim.seed_database(session)

        products = session.exec(select(Product)).all()
        destinations = session.exec(
            select(Location).where(Location.type.in_(["distributor", "store"]))  # type: ignore
        ).all()
        prod_map = {p.id: p for p in products}
        dest_map = {d.id: d for d in destinations}

        service = ForecastService(session)
        print(f"\n[INFO] Running rolling-origin 3-fold evaluation across {len(products) * len(destinations)} series...")
        results = service.fit_and_select_all()

        # Compare each series against pure seasonal-naive baseline
        comparison_records: List[Dict] = []
        for res in results:
            pid = res["product_id"]
            lid = res["location_id"]
            p = prod_map.get(pid)
            d = dest_map.get(lid)
            as_of = res["as_of_date"]

            series = service.get_series_data(pid, lid)

            # Evaluate pure seasonal-naive on 3 folds for baseline comparison
            if not is_zero_heavy(series, as_of):
                eval_3folds = evaluate_rolling_origin(series, as_of)
                sn_res = eval_3folds["candidate_results"]["seasonal_naive"]
                sn_wape = sn_res["wape"]
                sn_bias = sn_res["bias"]
            else:
                # If zero heavy, calculate baseline WAPE using zero forecast or seasonal naive
                dates_21 = [as_of - timedelta(days=i) for i in range(21, 0, -1)]
                actuals_21 = [float(series.get(dt, 0.0)) for dt in dates_21]
                sn_preds = [float(series.get(dt - timedelta(days=7), 0.0)) for dt in dates_21]
                sn_wape = compute_wape(actuals_21, sn_preds)
                sn_bias = compute_bias(actuals_21, sn_preds)

            comparison_records.append({
                "product_id": pid,
                "category": p.category if p else "Unknown",
                "location_id": lid,
                "location_type": d.type if d else "Unknown",
                "chosen_model": res["chosen_model"],
                "chosen_wape": res["wape"],
                "chosen_bias": res["bias"],
                "chosen_sigma": res["sigma"],
                "sn_wape": sn_wape,
                "sn_bias": sn_bias,
            })

    df = pd.DataFrame(comparison_records)

    # 1. Overall Summary
    print("\n" + "-" * 80)
    print("1. OVERALL FORECAST PERFORMANCE COMPARISON")
    print("-" * 80)
    mean_chosen_wape = df["chosen_wape"].mean()
    mean_sn_wape = df["sn_wape"].mean()
    wape_reduction = ((mean_sn_wape - mean_chosen_wape) / mean_sn_wape) * 100.0 if mean_sn_wape > 0 else 0.0

    mean_chosen_bias = df["chosen_bias"].mean()
    mean_sn_bias = df["sn_bias"].mean()

    print(f"Total Evaluated Series:        {len(df)}")
    print(f"Chosen Engine Mean WAPE:       {mean_chosen_wape:.4f} ({mean_chosen_wape*100:.2f}%)")
    print(f"Seasonal-Naive Baseline WAPE:  {mean_sn_wape:.4f} ({mean_sn_wape*100:.2f}%)")
    print(f"WAPE Improvement:              {wape_reduction:+.2f}%")
    print(f"Chosen Engine Mean Bias:       {mean_chosen_bias:+.4f}")
    print(f"Seasonal-Naive Baseline Bias:  {mean_sn_bias:+.4f}")

    # 2. Model Selection Distribution
    print("\n" + "-" * 80)
    print("2. CHOSEN MODEL SELECTION BREAKDOWN")
    print("-" * 80)
    model_counts = df["chosen_model"].value_counts()
    for model, count in model_counts.items():
        pct = (count / len(df)) * 100.0
        avg_w = df[df["chosen_model"] == model]["chosen_wape"].mean()
        avg_b = df[df["chosen_model"] == model]["chosen_bias"].mean()
        print(f" - {model:<22}: {count:>3} series ({pct:>5.1f}%) | Mean WAPE: {avg_w:.4f} | Mean Bias: {avg_b:+.4f}")

    # 3. Category Breakdown
    print("\n" + "-" * 80)
    print("3. CATEGORY-WISE PERFORMANCE (CHOSEN vs SEASONAL-NAIVE)")
    print("-" * 80)
    cat_grp = df.groupby("category").agg({
        "chosen_wape": "mean",
        "sn_wape": "mean",
        "chosen_bias": "mean",
        "sn_bias": "mean",
        "chosen_sigma": "mean",
        "product_id": "count",
    }).rename(columns={"product_id": "series_count"})

    print(f"{'Category':<18} | {'Series':<6} | {'Engine WAPE':<11} | {'SN WAPE':<11} | {'Engine Bias':<11} | {'Mean Sigma':<10}")
    print("-" * 80)
    for cat, row in cat_grp.iterrows():
        print(
            f"{cat:<18} | {int(row['series_count']):<6} | {row['chosen_wape']:<11.4f} | "
            f"{row['sn_wape']:<11.4f} | {row['chosen_bias']:<+11.4f} | {row['chosen_sigma']:<10.2f}"
        )

    # 4. Location Breakdown
    print("\n" + "-" * 80)
    print("4. LOCATION-WISE PERFORMANCE")
    print("-" * 80)
    loc_grp = df.groupby(["location_id", "location_type"]).agg({
        "chosen_wape": "mean",
        "sn_wape": "mean",
        "chosen_bias": "mean",
        "chosen_sigma": "mean",
        "product_id": "count",
    }).rename(columns={"product_id": "series_count"})

    print(f"{'Location':<8} | {'Type':<12} | {'Series':<6} | {'Engine WAPE':<11} | {'SN WAPE':<11} | {'Engine Bias':<11}")
    print("-" * 80)
    for (loc_id, loc_type), row in loc_grp.iterrows():
        print(
            f"{loc_id:<8} | {loc_type:<12} | {int(row['series_count']):<6} | {row['chosen_wape']:<11.4f} | "
            f"{row['sn_wape']:<11.4f} | {row['chosen_bias']:<+11.4f}"
        )

    print("\n" + "=" * 80)
    print("Evaluation Complete. All metrics computed from deterministic simulated data.")
    print("=" * 80)


if __name__ == "__main__":
    run_evaluation()
