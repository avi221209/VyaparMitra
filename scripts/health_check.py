#!/usr/bin/env python3
"""
VyaparMitra - Step 2 Fast Pass Automated Health Check Script
Runs all 15 QA release engineer checks against http://127.0.0.1:8000 with precise latency measurement.
Generates docs/HEALTH_REPORT.md and prints summary results.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

BASE_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


class HealthChecker:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self.results: List[Dict[str, Any]] = []

    def record(
        self,
        check_id: int,
        name: str,
        status: str,  # PASS, FAIL, SKIP, WARN
        latency_ms: float,
        details: str = "",
        measured_values: Optional[Dict[str, Any]] = None,
    ):
        self.results.append({
            "id": check_id,
            "name": name,
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "details": details,
            "measured": measured_values or {},
        })

    def run_all(self) -> List[Dict[str, Any]]:
        print(f"\n=====================================================================")
        print(f" VYAPARMITRA FAST PASS HEALTH CHECK (Target: {self.base_url})")
        print(f" Timestamp: {datetime.now(timezone.utc).isoformat()}")
        print(f"=====================================================================\n")

        # -------------------------------------------------------------
        # Check 1: GET /api/health and /api/status (<= 500 ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        r1 = self.client.get("/api/health")
        t_health = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        r2 = self.client.get("/api/status")
        t_status = (time.perf_counter() - t0) * 1000.0

        ok1 = r1.status_code == 200 and r2.status_code == 200 and t_health <= 500 and t_status <= 500
        self.record(
            1,
            "GET /api/health & /api/status",
            "PASS" if ok1 else "FAIL",
            max(t_health, t_status),
            f"/api/health: {r1.status_code} ({t_health:.1f}ms), /api/status: {r2.status_code} ({t_status:.1f}ms)",
            {"health_status": r1.status_code, "status_status": r2.status_code, "health_ms": t_health, "status_ms": t_status},
        )

        # -------------------------------------------------------------
        # Check 2: POST /api/data/seed?variant=normal + Entity GETs
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        r_seed = self.client.post("/api/data/seed?variant=normal")
        t_seed = (time.perf_counter() - t0) * 1000.0

        entities = ["locations", "products", "lanes", "batches", "snapshots", "settings"]
        entity_times = {}
        entity_counts = {}
        all_ok = r_seed.status_code == 200
        max_entity_time = 0.0

        for ent in entities:
            t0 = time.perf_counter()
            r_ent = self.client.get(f"/api/{ent}")
            t_ent = (time.perf_counter() - t0) * 1000.0
            entity_times[ent] = round(t_ent, 1)
            max_entity_time = max(max_entity_time, t_ent)
            if r_ent.status_code != 200 or t_ent > 500:
                all_ok = False
            try:
                data = r_ent.json()
                entity_counts[ent] = len(data) if isinstance(data, list) else 1
            except Exception:
                entity_counts[ent] = 0

        self.record(
            2,
            "Seed normal + GET master data (<= 500ms)",
            "PASS" if all_ok else "FAIL",
            max_entity_time,
            f"Counts: {entity_counts}; Seed: {t_seed:.1f}ms; Max GET: {max_entity_time:.1f}ms",
            {"counts": entity_counts, "times_ms": entity_times, "seed_ms": t_seed},
        )

        # -------------------------------------------------------------
        # Check 3: GET /api/data/issues after seeding defects variant
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        self.client.post("/api/data/seed?variant=defects")
        r_issues = self.client.get("/api/data/issues")
        t_issues = (time.perf_counter() - t0) * 1000.0
        # Re-seed normal immediately
        self.client.post("/api/data/seed?variant=normal")

        issues_data = r_issues.json() if r_issues.status_code == 200 else {}
        total_issues = issues_data.get("total", 0)
        # Requirement: >= 90% of injected defects detected (20 injected defects)
        pass_recall = total_issues >= 18
        self.record(
            3,
            "Defect detection recall (>=90%)",
            "PASS" if pass_recall else "FAIL",
            t_issues,
            f"Detected {total_issues}/20 injected defects ({total_issues/20*100:.1f}% recall)",
            {"total_issues": total_issues, "expected": 20, "recall_pct": total_issues / 20 * 100},
        )

        # -------------------------------------------------------------
        # Check 4: POST /api/forecast/run (<= 8s) & GET /api/forecast/{prod}/{loc} (<= 300ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        r_fc = self.client.post("/api/forecast/run")
        t_fc_run = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        r_fc_single = self.client.get("/api/forecast/SKU-P01/D1")
        t_fc_single = (time.perf_counter() - t0) * 1000.0

        ok4 = (
            r_fc.status_code == 200
            and t_fc_run <= 8000.0
            and r_fc_single.status_code == 200
            and t_fc_single <= 300.0
        )
        self.record(
            4,
            "Forecast run (<=8s) & series (<=300ms)",
            "PASS" if ok4 else "FAIL",
            t_fc_run,
            f"Run: {r_fc.status_code} ({t_fc_run:.1f}ms); SKU-P01/D1: {r_fc_single.status_code} ({t_fc_single:.1f}ms)",
            {"run_ms": t_fc_run, "single_ms": t_fc_single, "status_run": r_fc.status_code},
        )

        # -------------------------------------------------------------
        # Check 5: POST /api/plan horizon 7 (<= 5s) & GET plan, latest, lines (<= 500ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        r_plan = self.client.post("/api/plan", json={"horizon": 7})
        t_plan = (time.perf_counter() - t0) * 1000.0

        plan_data = r_plan.json() if r_plan.status_code == 200 else {}
        run_id = plan_data.get("run_id", "")
        lines = plan_data.get("lines", [])
        first_line_id = lines[0]["id"] if lines else ""

        t0 = time.perf_counter()
        r_latest = self.client.get("/api/plan/latest")
        t_latest = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        r_run = self.client.get(f"/api/plan/{run_id}") if run_id else r_latest
        t_run = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        r_line = self.client.get(f"/api/plan/lines/{first_line_id}") if first_line_id else r_latest
        t_line = (time.perf_counter() - t0) * 1000.0

        ok5 = (
            r_plan.status_code == 200
            and t_plan <= 5000.0
            and r_latest.status_code == 200
            and t_latest <= 500.0
            and r_run.status_code == 200
            and t_run <= 500.0
            and r_line.status_code == 200
            and t_line <= 500.0
        )
        self.record(
            5,
            "Optimization plan (<=5s) & fetch (<=500ms)",
            "PASS" if ok5 else "FAIL",
            t_plan,
            f"POST /api/plan: {t_plan:.1f}ms, latest: {t_latest:.1f}ms, run: {t_run:.1f}ms, line: {t_line:.1f}ms",
            {"plan_ms": t_plan, "latest_ms": t_latest, "run_ms": t_run, "line_ms": t_line, "run_id": run_id},
        )

        # -------------------------------------------------------------
        # Check 6: Plan Integrity (batch <= qty, cost sum, unmet >= 0, etc.)
        # -------------------------------------------------------------
        # Retrieve batches for inventory check
        batches_map = {b["id"]: b["quantity"] for b in self.client.get("/api/batches").json()}
        integrity_ok = True
        integrity_reasons = []

        total_cost = plan_data.get("total_cost", 0.0)
        lines_cost_sum = sum(l.get("cost", 0.0) for l in lines)
        if abs(total_cost - lines_cost_sum) > 0.1:
            integrity_ok = False
            integrity_reasons.append(f"Total cost {total_cost} != line cost sum {lines_cost_sum:.2f}")

        # Check batch shipment <= quantity
        batch_usage = {}
        for l in lines:
            b_id = l.get("batch_id")
            batch_usage[b_id] = batch_usage.get(b_id, 0) + l.get("cartons", 0)

        for b_id, used in batch_usage.items():
            max_qty = batches_map.get(b_id, 0)
            if used > max_qty:
                integrity_ok = False
                integrity_reasons.append(f"Batch {b_id} overdrawn: used {used} > max {max_qty}")

        unmet_dem = plan_data.get("total_unmet_demand_cartons", 0)
        if unmet_dem < 0:
            integrity_ok = False
            integrity_reasons.append(f"Negative unmet demand: {unmet_dem}")

        required_line_fields = ["id", "product_id", "source_id", "destination_id", "batch_id", "cartons", "cost", "status", "arrival_date"]
        for l in lines:
            missing = [f for f in required_line_fields if f not in l]
            if missing:
                integrity_ok = False
                integrity_reasons.append(f"Line {l.get('id')} missing fields: {missing}")
                break

        self.record(
            6,
            "Plan domain integrity checks",
            "PASS" if integrity_ok else "FAIL",
            0.0,
            "All domain invariants hold (batch limit, cost sum, unmet>=0, complete fields)" if integrity_ok else "; ".join(integrity_reasons),
            {"lines_count": len(lines), "total_cost": total_cost, "unmet_demand": unmet_dem},
        )

        # -------------------------------------------------------------
        # Check 7: Determinism Across 3 Runs (sha256 match)
        # -------------------------------------------------------------
        hashes = []
        for run_idx in range(3):
            res_det = self.client.post("/api/plan", json={"horizon": 7})
            lines_det = res_det.json().get("lines", [])
            # Normalize lines ignoring dynamic run_id and line id
            norm = [
                (
                    l["destination_id"],
                    l["product_id"],
                    l["source_id"],
                    l["batch_id"],
                    l["cartons"],
                    round(float(l["cost"]), 2),
                )
                for l in lines_det
            ]
            norm.sort()
            h = hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()
            hashes.append(h)

        det_ok = (hashes[0] == hashes[1] == hashes[2])
        self.record(
            7,
            "Optimization determinism (3 runs sha256 match)",
            "PASS" if det_ok else "FAIL",
            0.0,
            f"SHA256: {hashes[0][:16]}... Match: {det_ok}",
            {"hash_run_1": hashes[0], "hash_run_2": hashes[1], "hash_run_3": hashes[2]},
        )

        # -------------------------------------------------------------
        # Check 8: Roles - Warehouse 403, Planner approve/reject, Audit trail
        # -------------------------------------------------------------
        # Test line approve with warehouse role -> expect 403
        r_wh = self.client.post(f"/api/plan/lines/{first_line_id}/approve", headers={"X-Role": "warehouse"})
        wh_refused = r_wh.status_code == 403

        # Test line approve with planner role -> expect 200
        r_pl_appr = self.client.post(f"/api/plan/lines/{first_line_id}/approve", headers={"X-Role": "planner"})
        pl_appr_ok = r_pl_appr.status_code == 200

        # Test line reject without reason -> expect 400
        second_line_id = lines[1]["id"] if len(lines) > 1 else first_line_id
        r_rej_no_reason = self.client.post(f"/api/plan/lines/{second_line_id}/reject", headers={"X-Role": "planner"})
        rej_no_reason_refused = r_rej_no_reason.status_code == 400

        # Test line reject with reason -> expect 200
        r_rej_with_reason = self.client.post(
            f"/api/plan/lines/{second_line_id}/reject",
            json={"reason": "Damaged goods in warehouse bay 4"},
            headers={"X-Role": "planner"},
        )
        rej_with_reason_ok = r_rej_with_reason.status_code == 200

        # Verify audit trail contains both APPROVE and REJECT
        r_audit = self.client.get("/api/audit")
        audit_logs = r_audit.json() if r_audit.status_code == 200 else []
        actions = [log.get("action") for log in audit_logs]
        audit_ok = "APPROVE" in actions and "REJECT" in actions

        ok8 = wh_refused and pl_appr_ok and rej_no_reason_refused and rej_with_reason_ok and audit_ok
        self.record(
            8,
            "Role gating & action audit trail",
            "PASS" if ok8 else "FAIL",
            0.0,
            f"Warehouse 403: {wh_refused}; Planner approve: {pl_appr_ok}; Reject w/o reason 400: {rej_no_reason_refused}; Reject w/ reason: {rej_with_reason_ok}; Audit logged: {audit_ok}",
            {"warehouse_status": r_wh.status_code, "reject_no_reason_status": r_rej_no_reason.status_code, "audit_actions": actions[:5]},
        )

        # -------------------------------------------------------------
        # Check 9: Rule-checked edit -> HTTP 409 naming rule & logged attempt
        # -------------------------------------------------------------
        # Attempt to edit line with massive overdraw
        r_overdraw = self.client.post(
            f"/api/plan/lines/{first_line_id}/approve",
            json={"edited_cartons": 999999},
            headers={"X-Role": "planner"},
        )
        overdraw_409 = r_overdraw.status_code == 409
        detail = r_overdraw.json().get("detail", "") if overdraw_409 else ""
        rule_named = "rule" in detail.lower() or "c1" in detail.lower() or "stock" in detail.lower()

        # Check audit trail for EDIT_REFUSED
        r_audit = self.client.get("/api/audit")
        audit_actions = [l.get("action") for l in r_audit.json()] if r_audit.status_code == 200 else []
        refused_logged = "EDIT_REFUSED" in audit_actions

        ok9 = overdraw_409 and rule_named and refused_logged
        self.record(
            9,
            "Rule-checked edit refusal (HTTP 409 & audit)",
            "PASS" if ok9 else "FAIL",
            0.0,
            f"Status 409: {overdraw_409}; Rule named: {rule_named}; EDIT_REFUSED in audit: {refused_logged}",
            {"status_code": r_overdraw.status_code, "detail": detail, "logged": refused_logged},
        )

        # -------------------------------------------------------------
        # Check 10: What-if Scenario Override (stock -20% on W1)
        # -------------------------------------------------------------
        r_override = self.client.post(
            "/api/scenario/override",
            json={"source_id": "W1", "stock_percent": -20},
            headers={"X-Role": "planner"},
        )
        override_data = r_override.json() if r_override.status_code == 200 else {}
        after_unmet = override_data.get("after_unmet_demand_cartons", 0)
        before_unmet = override_data.get("before_unmet_demand_cartons", 0)
        # Unmet demand must not decrease when stock is cut by 20%
        unmet_did_not_decrease = after_unmet >= before_unmet
        ok10 = r_override.status_code == 200 and unmet_did_not_decrease

        self.record(
            10,
            "What-if override: W1 -20% stock",
            "PASS" if ok10 else "FAIL",
            0.0,
            f"Status: {r_override.status_code}; Before unmet: {before_unmet}, After unmet: {after_unmet} (Did not decrease: {unmet_did_not_decrease})",
            {"before_unmet": before_unmet, "after_unmet": after_unmet, "status": r_override.status_code},
        )

        # Re-seed normal to return to clean state
        self.client.post("/api/data/seed?variant=normal")

        # -------------------------------------------------------------
        # Check 11: GET /api/plan/{id}/dead-stock, /api/surplus/listings, /api/evaluate, /api/evaluate/status (<= 500ms)
        # -------------------------------------------------------------
        # Re-run plan to get fresh run_id
        r_fresh_plan = self.client.post("/api/plan", json={"horizon": 7})
        fresh_run_id = r_fresh_plan.json().get("run_id")

        chk11_routes = [
            f"/api/plan/{fresh_run_id}/dead-stock",
            "/api/surplus/listings",
            "/api/evaluate",
            "/api/evaluate/status",
        ]
        chk11_times = {}
        all_chk11_ok = True
        max_c11_time = 0.0

        for rt in chk11_routes:
            t0 = time.perf_counter()
            r_chk = self.client.get(rt)
            t_chk = (time.perf_counter() - t0) * 1000.0
            chk11_times[rt] = round(t_chk, 1)
            max_c11_time = max(max_c11_time, t_chk)
            if r_chk.status_code != 200 or t_chk > 500.0:
                all_chk11_ok = False

        self.record(
            11,
            "Surplus, Dead-Stock, Evaluate endpoints (<=500ms)",
            "PASS" if all_chk11_ok else "FAIL",
            max_c11_time,
            f"All <= 500ms: {all_chk11_ok}; Times: {chk11_times}",
            {"times_ms": chk11_times},
        )

        # -------------------------------------------------------------
        # Check 12: Malformed CSV upload (4xx error, never 500) & template download
        # -------------------------------------------------------------
        # Malformed upload
        malformed_bytes = b"bad,corrupted\x00data\n1,2,3,4,5\n"
        r_malformed = self.client.post(
            "/api/data/upload",
            files={"file": ("malformed.csv", malformed_bytes, "text/csv")},
            headers={"X-Role": "planner"},
        )
        is_4xx = 400 <= r_malformed.status_code < 500
        error_names_problem = len(r_malformed.text) > 0

        # Template download
        r_tpl = self.client.get("/api/data/template/products")
        tpl_ok = r_tpl.status_code == 200 and "text/csv" in r_tpl.headers.get("content-type", "")

        ok12 = is_4xx and error_names_problem and tpl_ok
        self.record(
            12,
            "CSV upload validation (4xx, no 500) & template",
            "PASS" if ok12 else "FAIL",
            0.0,
            f"Malformed status: {r_malformed.status_code} (4xx: {is_4xx}); Template status: {r_tpl.status_code}",
            {"malformed_status": r_malformed.status_code, "template_status": r_tpl.status_code},
        )

        # -------------------------------------------------------------
        # Check 13: GET /api/dashboard/summary (<= 500ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        r_dash = self.client.get("/api/dashboard/summary")
        t_dash = (time.perf_counter() - t0) * 1000.0
        ok13 = r_dash.status_code == 200 and t_dash <= 500.0

        self.record(
            13,
            "GET /api/dashboard/summary (<=500ms)",
            "PASS" if ok13 else "FAIL",
            t_dash,
            f"Status: {r_dash.status_code} ({t_dash:.1f}ms)",
            {"status": r_dash.status_code, "latency_ms": t_dash},
        )

        # -------------------------------------------------------------
        # Check 14: Chat Endpoints (Rule 5: check presence, mark not present if absent)
        # -------------------------------------------------------------
        # Chat endpoints are optional per Rule 5: if not present (404/405), mark 'not present' and skip
        r_chat_status = self.client.get("/api/chat/status")
        r_chat = self.client.post("/api/chat", json={"message": "hello"})
        chat_present = (r_chat_status.status_code == 200 or r_chat.status_code == 200)

        if not chat_present:
            self.record(
                14,
                "Chat assistant endpoints",
                "SKIP",
                0.0,
                "Not present (marked not present per Rule 5)",
                {"present": False, "status_code": r_chat_status.status_code},
            )
        else:
            self.record(
                14,
                "Chat assistant endpoints",
                "PASS",
                0.0,
                f"Status: {r_chat_status.status_code}",
                {"present": True},
            )

        # -------------------------------------------------------------
        # Check 15: POST /api/seed/reset idempotent state
        # -------------------------------------------------------------
        r_rst1 = self.client.post("/api/seed/reset")
        st1 = self.client.get("/api/status").json().get("counts", {})
        r_rst2 = self.client.post("/api/seed/reset")
        st2 = self.client.get("/api/status").json().get("counts", {})

        idempotent = (r_rst1.status_code == 200 and r_rst2.status_code == 200 and st1 == st2)
        self.record(
            15,
            "POST /api/seed/reset idempotency",
            "PASS" if idempotent else "FAIL",
            0.0,
            f"Reset 1: {r_rst1.status_code}, Reset 2: {r_rst2.status_code}, Counts match: {st1 == st2}",
            {"counts_1": st1, "counts_2": st2},
        )

        return self.results

    def generate_report(self) -> Tuple[str, str]:
        passed_count = sum(1 for r in self.results if r["status"] == "PASS")
        skipped_count = sum(1 for r in self.results if r["status"] == "SKIP")
        failed_count = sum(1 for r in self.results if r["status"] == "FAIL")
        total_count = len(self.results)

        verdict = "GREEN" if failed_count == 0 else "RED"

        # Build Markdown Report
        md = []
        md.append("# VyaparMitra Health & Release Verification Report")
        md.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        md.append(f"**Target:** {self.base_url}")
        md.append(f"**Overall Verdict:** **{verdict}** ({passed_count}/{total_count} Passed, {skipped_count} Skipped, {failed_count} Failed)\n")
        md.append("## Automated Fast Pass Checks (Step 2)\n")
        md.append("| # | Check | Status | Latency | Details |")
        md.append("|---|-------|--------|---------|---------|")

        for r in self.results:
            lat = f"{r['latency_ms']:.1f}ms" if r['latency_ms'] > 0 else "-"
            status_icon = "PASS" if r['status'] == "PASS" else ("SKIP" if r['status'] == "SKIP" else "FAIL")
            md.append(f"| {r['id']} | {r['name']} | **{status_icon}** | {lat} | {r['details']} |")

        md.append("\n## Environment Details\n")
        md.append(f"- Python: {sys.version.split()[0]}")
        md.append(f"- Platform: {sys.platform}")
        md.append(f"- Backend: FastAPI + SQLite + PuLP (CBC Solver)")
        md.append(f"- Frontend: React 18 + Vite + Tailwind CSS")

        report_content = "\n".join(md)
        return verdict, report_content


if __name__ == "__main__":
    checker = HealthChecker()
    checker.run_all()
    verdict, report_md = checker.generate_report()

    # Write report to docs/HEALTH_REPORT.md
    os.makedirs("docs", exist_ok=True)
    with open("docs/HEALTH_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\n---------------------------------------------------------------------")
    print(f" FAST PASS SUMMARY: {verdict}")
    print("---------------------------------------------------------------------")
    for r in checker.results:
        print(f"[{r['status']:4s}] #{r['id']:02d}: {r['name']:45s} ({r['latency_ms']:.1f}ms) -> {r['details']}")
    print("---------------------------------------------------------------------")
    print(f"Report saved to docs/HEALTH_REPORT.md\n")

    if verdict == "RED":
        sys.exit(1)
    sys.exit(0)
