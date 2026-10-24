"""
Measure Recall and False Flags of DataValidator against the Simulator's Injected Defect Manifest.
Target:
  - Recall >= 0.90 (target 20 of 20 = 1.0)
  - False flags <= 5% of clean rows (target 0.0)
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from typing import Any, Dict, List, Set, Tuple
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from backend.app.models import SQLModel
from backend.app.services.simulator import FMCGSimulator
from backend.app.services.validation import DataValidator


def evaluate_validation_metrics(seed: int = 1) -> Dict[str, Any]:
    """
    Evaluates validation recall and false flag rate on both defect and clean datasets.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # 1. Seed dataset with injected defects
        sim = FMCGSimulator(seed=seed, scenario="balanced", variant="defects")
        seed_res = sim.seed_database(session)
        defect_manifest = sim.defect_manifest

        # 2. Run DataValidator
        validator = DataValidator(session)
        detected_issues = validator.run_all(persist=True)

        # 3. Match detected issues to defect manifest
        # Build set of manifest signatures: (type, normalized_entity)
        manifest_signatures = set()
        for m in defect_manifest:
            m_type = m["type"]
            m_entity = m["entity"].split("(")[0].strip()
            manifest_signatures.add((m_type, m_entity))

        detected_signatures = set()
        for iss in detected_issues:
            detected_signatures.add((iss.type, iss.entity))

        # True Positives: manifest defects matched by detected issues
        tp = 0
        unmatched_defects = []
        for m in defect_manifest:
            m_type = m["type"]
            m_entity = m["entity"]
            # Look for match in detected issues
            matched = False
            for iss in detected_issues:
                # Check type match and entity key containment
                if iss.type == m_type:
                    # Entity matching (e.g. Product:SKU-P01-DUP in entity)
                    clean_m = m_entity.replace(" ", "").lower()
                    clean_iss = iss.entity.replace(" ", "").lower()
                    if clean_m in clean_iss or clean_iss in clean_m:
                        matched = True
                        break
            if matched:
                tp += 1
            else:
                unmatched_defects.append(m)

        total_injected = len(defect_manifest)
        fn = total_injected - tp
        recall = tp / max(1, total_injected)

        # False Flags: detected issues that do NOT correspond to any defect in manifest
        fp = 0
        false_flag_items = []
        for iss in detected_issues:
            is_valid_detection = False
            clean_iss = iss.entity.replace(" ", "").lower()
            for m in defect_manifest:
                clean_m = m["entity"].replace(" ", "").lower()
                if iss.type == m["type"] and (clean_m in clean_iss or clean_iss in clean_m):
                    is_valid_detection = True
                    break
            if not is_valid_detection:
                fp += 1
                false_flag_items.append(iss)

        # Total clean entities across dataset
        total_clean_rows = (
            seed_res["counts"]["products"]
            + seed_res["counts"]["batches"]
            + seed_res["counts"]["inventory_snapshots"]
            + (seed_res["counts"]["sales_daily"] // 120)  # number of sales series
        ) - total_injected

        false_flag_rate = fp / max(1, total_clean_rows)

        # 4. Clean Run Check (verify clean dataset has 0 critical issues)
        clean_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(clean_engine)
        with Session(clean_engine) as clean_session:
            clean_sim = FMCGSimulator(seed=seed, scenario="balanced", variant="normal")
            clean_sim.seed_database(clean_session)
            clean_validator = DataValidator(clean_session)
            clean_issues = clean_validator.run_all(persist=True)
            clean_critical = [i for i in clean_issues if i.severity == "critical"]

        return {
            "total_injected_defects": total_injected,
            "true_positives": tp,
            "false_negatives": fn,
            "recall": round(recall, 4),
            "false_positives": fp,
            "total_clean_rows": total_clean_rows,
            "false_flag_rate": round(false_flag_rate, 4),
            "unmatched_defects": unmatched_defects,
            "false_flag_items": [i.model_dump() for i in false_flag_items],
            "clean_dataset_critical_issues": len(clean_critical),
            "passes_recall_threshold": recall >= 0.90,
            "passes_false_flag_threshold": false_flag_rate <= 0.05,
        }


def main():
    print("=" * 78)
    print("VYAPARMITRA: DATA VALIDATION BENCHMARK (RECALL & FALSE FLAGS)")
    print("=" * 78)

    res = evaluate_validation_metrics(seed=1)

    print(f"\nInjected Defects in Manifest : {res['total_injected_defects']}")
    print(f"Detected True Positives (TP) : {res['true_positives']}")
    print(f"Missed False Negatives (FN)  : {res['false_negatives']}")
    print(f"Recall                       : {res['recall'] * 100:.2f}% (Threshold: >= 90.0%)")
    print(f"Status                       : {'PASS' if res['passes_recall_threshold'] else 'FAIL'}")

    print(f"\nClean Rows in Network        : {res['total_clean_rows']}")
    print(f"False Positives (FP)         : {res['false_positives']}")
    print(f"False Flag Rate              : {res['false_flag_rate'] * 100:.2f}% (Threshold: <= 5.0%)")
    print(f"Status                       : {'PASS' if res['passes_false_flag_threshold'] else 'FAIL'}")

    print(f"\nClean Dataset Check:")
    print(f"Critical Issues on Clean Data: {res['clean_dataset_critical_issues']} (Expected: 0)")

    if res["unmatched_defects"]:
        print("\nUnmatched Defects:")
        for d in res["unmatched_defects"]:
            print(" -", d)

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
