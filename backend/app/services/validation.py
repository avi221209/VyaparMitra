import difflib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
from sqlmodel import Session, select

from backend.app.models import (
    Batch,
    DecisionLog,
    InventorySnapshot,
    Lane,
    Location,
    Product,
    SalesDaily,
    ValidationIssue,
)


KNOWN_UNITS = {"pack", "bag", "pouch", "bottle", "bar", "jar", "tube", "box", "can", "kg", "g", "units", "pcs"}


def normalize_text(text: str) -> str:
    """Normalize text by lowercasing and stripping punctuation and whitespace."""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def compute_name_similarity(name1: str, name2: str) -> float:
    """Compute token-level similarity between two product names."""
    n1 = normalize_text(name1)
    n2 = normalize_text(name2)
    if n1 == n2:
        return 1.0

    # Sequence matcher ratio
    seq_ratio = difflib.SequenceMatcher(None, n1, n2).ratio()

    # Token overlap / Jaccard
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    jaccard = len(tokens1 & tokens2) / max(1, len(tokens1 | tokens2))

    return max(seq_ratio, jaccard)


class DataValidator:
    """
    Validation engine for FMCG network data.
    Detects:
      - Duplicate SKU/product identifiers or near-duplicate names
      - Mixed units / invalid case packs / magnitude jumps
      - Negative stock or negative sales
      - Invalid or impossible dates (expiry before snapshot/run date)
      - Missing sales days (gaps longer than 2 days marked 'insufficient data')
      - Contradictory stock records (on_hand < reserved)
    """

    def __init__(self, session: Session, run_date: Optional[date] = None):
        self.session = session
        self.run_date = run_date or date(2026, 10, 24)

    def validate_products(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        products = list(self.session.exec(select(Product)).all())

        seen_ids: Set[str] = set()
        seen_names: Dict[str, Product] = {}

        for p in products:
            # 1. Exact duplicate ID
            if p.id in seen_ids:
                issues.append(
                    ValidationIssue(
                        type="DUPLICATE_SKU",
                        entity=f"Product:{p.id}",
                        severity="critical",
                        status="open",
                        description=f"Duplicate product identifier: {p.id}",
                        fix_first=True,
                        is_simulated=True,
                    )
                )
            else:
                seen_ids.add(p.id)

            # 2. Near-duplicate names (normalized similarity > 0.80 or suffix like '(duplicate)')
            norm_name = normalize_text(p.name)
            is_dup_detected = False
            for existing_norm, existing_p in seen_names.items():
                sim = compute_name_similarity(p.name, existing_p.name)
                # Check for duplicate entry flag or high similarity with matching case_pack/unit
                has_dup_keyword = "duplicate" in norm_name or "dup" in p.id.lower()
                if has_dup_keyword or (sim >= 0.85 and (p.category == existing_p.category or p.unit == existing_p.unit)):
                    issues.append(
                        ValidationIssue(
                            type="DUPLICATE_SKU",
                            entity=f"Product:{p.id}",
                            severity="critical",
                            status="open",
                            description=f"Near-duplicate product name mirroring {existing_p.id} ('{existing_p.name}') with similarity {sim:.2f}",
                            fix_first=True,
                            is_simulated=True,
                        )
                    )
                    is_dup_detected = True
                    break

            if not is_dup_detected:
                seen_names[norm_name] = p

            # 3. Unit validation
            cleaned_unit = p.unit.lower().strip() if p.unit else ""
            if not cleaned_unit or cleaned_unit not in KNOWN_UNITS:
                issues.append(
                    ValidationIssue(
                        type="MIXED_UNITS",
                        entity=f"Product:{p.id}",
                        severity="warning",
                        status="open",
                        description=f"Product has unrecognized or conflicting unit '{p.unit}'",
                        fix_first=False,
                        is_simulated=True,
                    )
                )

            # 4. Case pack validation
            if p.case_pack is None or p.case_pack <= 0:
                issues.append(
                    ValidationIssue(
                        type="MIXED_UNITS",
                        entity=f"Product:{p.id}",
                        severity="critical",
                        status="open",
                        description=f"Invalid non-positive case_pack ({p.case_pack}) detected",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

        return issues

    def validate_inventory(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        snapshots = list(self.session.exec(select(InventorySnapshot)).all())

        for s in snapshots:
            # 1. Negative stock on hand
            if s.on_hand < 0:
                issues.append(
                    ValidationIssue(
                        type="NEGATIVE_STOCK",
                        entity=f"InventorySnapshot:{s.location_id}:{s.product_id}",
                        severity="critical",
                        status="open",
                        description=f"Negative stock on_hand ({s.on_hand} cartons) at location {s.location_id}",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

            # 2. Contradictory stock: on_hand < reserved
            if s.on_hand >= 0 and s.on_hand < s.reserved:
                issues.append(
                    ValidationIssue(
                        type="CONTRADICTORY_STOCK",
                        entity=f"InventorySnapshot:{s.location_id}:{s.product_id}",
                        severity="critical",
                        status="open",
                        description=f"Contradictory stock: on_hand ({s.on_hand}) is less than reserved ({s.reserved})",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

            # 3. Negative in-transit or reserved
            if s.in_transit < 0 or s.reserved < 0:
                issues.append(
                    ValidationIssue(
                        type="NEGATIVE_STOCK",
                        entity=f"InventorySnapshot:{s.location_id}:{s.product_id}",
                        severity="critical",
                        status="open",
                        description=f"Negative reserved or in_transit inventory at location {s.location_id}",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

        return issues

    def validate_batches(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        batches = list(self.session.exec(select(Batch)).all())

        for b in batches:
            # 1. Negative batch quantity
            if b.quantity < 0:
                issues.append(
                    ValidationIssue(
                        type="NEGATIVE_STOCK",
                        entity=f"Batch:{b.id}",
                        severity="critical",
                        status="open",
                        description=f"Negative quantity ({b.quantity} cartons) in batch {b.id}",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

            # 2. Expiry before run date / snapshot date (impossible/expired inventory)
            if b.expiry_date <= self.run_date:
                issues.append(
                    ValidationIssue(
                        type="INVALID_DATE",
                        entity=f"Batch:{b.id}",
                        severity="critical",
                        status="open",
                        description=f"Batch expiry date ({b.expiry_date}) is in the past relative to run date {self.run_date}",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

        return issues

    def validate_sales(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        sales = list(self.session.exec(select(SalesDaily).order_by(SalesDaily.date.asc())).all())  # type: ignore

        # 1. Negative sales units check
        for s in sales:
            if s.units < 0:
                issues.append(
                    ValidationIssue(
                        type="NEGATIVE_SALES",
                        entity=f"SalesDaily:{s.location_id}:{s.product_id}:{s.date}",
                        severity="critical",
                        status="open",
                        description=f"Negative sales observed: {s.units} units on {s.date}",
                        fix_first=True,
                        is_simulated=True,
                    )
                )

        # 2. Group by (location_id, product_id) to check date continuity and missing days
        series_map: Dict[Tuple[str, str], List[SalesDaily]] = {}
        for s in sales:
            key = (s.location_id, s.product_id)
            if key not in series_map:
                series_map[key] = []
            series_map[key].append(s)

        for (loc_id, prod_id), records in series_map.items():
            if len(records) < 2:
                continue

            # Sort records by date
            records.sort(key=lambda r: r.date)

            # Detect missing sales day gaps > 2 days
            has_gap = False
            for i in range(len(records) - 1):
                d1 = records[i].date
                d2 = records[i + 1].date
                gap_days = (d2 - d1).days - 1
                if gap_days > 2:
                    has_gap = True
                    issues.append(
                        ValidationIssue(
                            type="MISSING_SALES_DAYS",
                            entity=f"SalesSeries:{loc_id}:{prod_id}",
                            severity="warning",
                            status="open",
                            description=(
                                f"Missing sales days gap ({gap_days} consecutive days missing between {d1} and {d2}). "
                                "Series marked as 'insufficient data' (never treated as silent zero demand)."
                            ),
                            fix_first=False,
                            is_simulated=True,
                        )
                    )
                    break  # One issue per series is sufficient

            # 3. Magnitude jumps (10x or 1000x jump)
            units_list = [r.units for r in records if r.units > 0]
            if len(units_list) >= 10 and not has_gap:
                median_units = float(np.median(units_list))
                max_units = float(np.max(units_list))
                if median_units > 0 and (max_units / median_units) >= 10.0:
                    issues.append(
                        ValidationIssue(
                            type="MIXED_UNITS",
                            entity=f"SalesSeries:{loc_id}:{prod_id}",
                            severity="warning",
                            status="open",
                            description=f"Extreme magnitude jump detected: peak {max_units} is >10x median {median_units}",
                            fix_first=False,
                            is_simulated=True,
                        )
                    )

        return issues

    def run_all(self, persist: bool = True) -> List[ValidationIssue]:
        """Execute all validation checks and optionally persist issues to database."""
        all_issues: List[ValidationIssue] = []
        all_issues.extend(self.validate_products())
        all_issues.extend(self.validate_inventory())
        all_issues.extend(self.validate_batches())
        all_issues.extend(self.validate_sales())

        if persist:
            # Clear previously open issues to prevent duplicate accumulation
            existing_issues = list(self.session.exec(select(ValidationIssue)).all())
            for old_iss in existing_issues:
                self.session.delete(old_iss)
            self.session.commit()

            for issue in all_issues:
                self.session.add(issue)
            self.session.commit()

        return all_issues


def get_issues_summary(session: Session) -> Dict[str, Any]:
    """Retrieve all validation issues grouped by severity with counts."""
    issues = list(session.exec(select(ValidationIssue)).all())

    critical_list = [i for i in issues if i.severity == "critical"]
    warning_list = [i for i in issues if i.severity == "warning"]

    open_count = len([i for i in issues if i.status == "open"])
    ack_count = len([i for i in issues if i.status == "acknowledged"])
    resolved_count = len([i for i in issues if i.status == "resolved"])
    fix_first_count = len([i for i in issues if i.fix_first and i.status == "open"])

    type_counts: Dict[str, int] = {}
    for i in issues:
        type_counts[i.type] = type_counts.get(i.type, 0) + 1

    return {
        "total": len(issues),
        "critical_count": len(critical_list),
        "warning_count": len(warning_list),
        "open_count": open_count,
        "acknowledged_count": ack_count,
        "resolved_count": resolved_count,
        "fix_first_count": fix_first_count,
        "by_severity": {
            "critical": [i.model_dump() for i in critical_list],
            "warning": [i.model_dump() for i in warning_list],
        },
        "by_type": type_counts,
        "is_simulated": True,
    }


def resolve_validation_issue(
    session: Session,
    issue_id: int,
    actor_role: str = "planner",
    note: Optional[str] = None,
) -> ValidationIssue:
    """Resolve/correct a validation issue."""
    issue = session.get(ValidationIssue, issue_id)
    if not issue:
        raise ValueError(f"Validation issue #{issue_id} not found")

    old_status = issue.status
    issue.status = "resolved"
    issue.fix_first = False
    session.add(issue)

    # Log to DecisionLog
    log = DecisionLog(
        actor_role=actor_role,
        action="RESOLVE_ISSUE",
        old_value=f"status={old_status}",
        new_value="status=resolved",
        note=note or f"Resolved issue #{issue_id} ({issue.type}) for {issue.entity}",
        timestamp=datetime.now(timezone.utc),
    )
    session.add(log)
    session.commit()
    session.refresh(issue)
    return issue


def acknowledge_validation_issue(
    session: Session,
    issue_id: int,
    actor_role: str = "planner",
    note: Optional[str] = None,
) -> ValidationIssue:
    """Acknowledge an issue and explicitly exclude the affected row from planning."""
    issue = session.get(ValidationIssue, issue_id)
    if not issue:
        raise ValueError(f"Validation issue #{issue_id} not found")

    old_status = issue.status
    issue.status = "acknowledged"
    # Acknowledging explicitly excludes the row from planning
    session.add(issue)

    log = DecisionLog(
        actor_role=actor_role,
        action="ACKNOWLEDGE_ISSUE",
        old_value=f"status={old_status}",
        new_value="status=acknowledged",
        note=note or f"Acknowledged issue #{issue_id} ({issue.type}) for {issue.entity}. Row explicitly excluded from planning.",
        timestamp=datetime.now(timezone.utc),
    )
    session.add(log)
    session.commit()
    session.refresh(issue)
    return issue


def get_blocked_entities_for_planning(session: Session) -> Set[str]:
    """
    'Fix first' Gate:
    Entities with critical open issues or acknowledged excluded items must be rejected from planning.
    """
    blocked: Set[str] = set()

    # 1. Critical and open -> "fix first" block
    critical_open = session.exec(
        select(ValidationIssue).where(
            ValidationIssue.severity == "critical",
            ValidationIssue.status == "open",
        )
    ).all()
    for iss in critical_open:
        blocked.add(iss.entity)

    # 2. Acknowledged -> explicitly excluded from planning
    acknowledged = session.exec(
        select(ValidationIssue).where(ValidationIssue.status == "acknowledged")
    ).all()
    for iss in acknowledged:
        blocked.add(iss.entity)

    return blocked
