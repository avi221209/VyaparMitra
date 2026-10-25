import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlmodel import Session, select

from backend.app.config import DATA_DIR
from backend.app.models import (
    Batch,
    DecisionLog,
    InventorySnapshot,
    Lane,
    Location,
    Product,
    SalesDaily,
    SurplusListing,
    ValidationIssue,
)


class FMCGSimulator:
    """
    Seeded FMCG Distribution Network Simulator for VyaparMitra.
    Produces:
      - 2 Warehouses: W1, W2 (pure supply sources, no local sales)
      - 4 Destinations: D1, D2 (Distributors), S1, S2 (Stores)
      - 24 Products across 5 FMCG categories
      - 120 days of daily sales per product-destination with log-normal base demand,
        weekly seasonality, trend, promo bumps, spikes, heavy_tail, level_shift.
      - 8 Lanes (all warehouse-destination pairs) with lead times 1-3 days,
        proportional distance costs, and tight capacity (~70% flow) on exactly 2 lanes.
      - Batches with shelf lives 14-365 days; weekly supply scaled by stock_scenario (0.8, 1.0, 1.3).
      - Variants: 'normal', 'defects' (~20 injected defects), 'low_w1' (W1 stock cut by 20%).
      - All records labelled simulated: True.
    """

    def __init__(
        self,
        seed: int = 1,
        base_date: date = date(2026, 10, 24),
        scenario: str = "balanced",
        variant: str = "normal",
        heavy_tail: bool = True,
        level_shift: bool = True,
        session: Optional[Session] = None,
    ):
        self.seed = seed
        self.base_date = base_date
        self.scenario = scenario.lower() if isinstance(scenario, str) else "balanced"
        self.variant = variant.lower() if isinstance(variant, str) else "normal"
        self.heavy_tail = heavy_tail
        self.level_shift = level_shift
        self.session = session

        # Scenario stock multipliers
        scenario_multipliers = {
            "scarce": 0.8,
            "balanced": 1.0,
            "abundant": 1.3,
        }
        if isinstance(scenario, (int, float)):
            self.stock_multiplier = float(scenario)
        else:
            self.stock_multiplier = scenario_multipliers.get(self.scenario, 1.0)

        self.rng = np.random.default_rng(seed)
        self.defect_manifest: List[Dict[str, Any]] = []

    def generate_locations(self) -> List[Location]:
        """Generate 2 mother warehouses and 4 destinations."""
        return [
            # 2 Warehouses (pure supply sources)
            Location(
                id="W1",
                name="North Central Logistics Hub (W1)",
                type="warehouse",
                city="Gurgaon",
                state="Haryana",
                is_simulated=True,
            ),
            Location(
                id="W2",
                name="Western Mother DC (W2)",
                type="warehouse",
                city="Bhiwandi",
                state="Maharashtra",
                is_simulated=True,
            ),
            # 4 Destinations (2 distributors, 2 stores)
            Location(
                id="D1",
                name="Metro Distributor East (D1)",
                type="distributor",
                city="Kolkata",
                state="West Bengal",
                is_simulated=True,
            ),
            Location(
                id="D2",
                name="Central Wholesale Agency (D2)",
                type="distributor",
                city="Ahmedabad",
                state="Gujarat",
                is_simulated=True,
            ),
            Location(
                id="S1",
                name="South Retail Flagship Store (S1)",
                type="store",
                city="Bengaluru",
                state="Karnataka",
                is_simulated=True,
            ),
            Location(
                id="S2",
                name="Suburban Retail Mart (S2)",
                type="store",
                city="Pune",
                state="Maharashtra",
                is_simulated=True,
            ),
        ]

    def generate_products(self) -> List[Product]:
        """Generate 24 products across 5 FMCG categories with shelf lives 14-365 days."""
        product_specs = [
            # 1. Staples (5 products)
            ("P01", "Chakki Fresh Atta 5kg", "Staples", "bag", 4, 20.0, 180.0, 40.0, 90),
            ("P02", "Basmati Rice 1kg", "Staples", "pouch", 10, 10.0, 95.0, 25.0, 180),
            ("P03", "Refined Sugar 1kg", "Staples", "pouch", 20, 20.0, 42.0, 6.0, 365),
            ("P04", "Toor Dal Premium 1kg", "Staples", "pouch", 15, 15.0, 130.0, 25.0, 180),
            ("P05", "Iodized Salt 1kg", "Staples", "pouch", 25, 25.0, 20.0, 5.0, 365),

            # 2. Packaged Food (5 products)
            ("P06", "Glucose Energy Biscuits 150g", "Packaged Food", "pack", 30, 6.0, 15.0, 5.0, 180),
            ("P07", "Refined Sunflower Oil 1L", "Packaged Food", "pouch", 15, 14.0, 125.0, 20.0, 180),
            ("P08", "Instant Masala Noodles 70g", "Packaged Food", "pack", 48, 5.0, 11.0, 3.0, 120),
            ("P09", "Fresh Tomato Ketchup 500g", "Packaged Food", "bottle", 12, 7.5, 85.0, 20.0, 180),
            ("P10", "Cream Choco Cookies 120g", "Packaged Food", "pack", 24, 4.0, 28.0, 7.0, 90),

            # 3. Personal Care (5 products)
            ("P11", "Herbal Bath Soap 100g", "Personal Care", "bar", 24, 3.0, 35.0, 10.0, 365),
            ("P12", "Anti-Dandruff Shampoo 200ml", "Personal Care", "bottle", 16, 4.0, 140.0, 45.0, 365),
            ("P13", "Herbal Toothpaste 150g", "Personal Care", "tube", 20, 4.0, 75.0, 20.0, 365),
            ("P14", "Daily Moisture Cream 50g", "Personal Care", "jar", 24, 2.0, 95.0, 30.0, 180),
            ("P15", "Gentle Body Wash 250ml", "Personal Care", "bottle", 12, 3.8, 160.0, 50.0, 365),

            # 4. Home Care (5 products)
            ("P16", "Active Detergent Powder 1kg", "Home Care", "pouch", 12, 12.0, 90.0, 25.0, 365),
            ("P17", "Lime Dishwash Gel 500ml", "Home Care", "bottle", 16, 9.0, 80.0, 25.0, 365),
            ("P18", "Citrus Surface Floor Cleaner 1L", "Home Care", "bottle", 8, 9.0, 110.0, 30.0, 365),
            ("P19", "Fabric Conditioner 500ml", "Home Care", "bottle", 12, 6.5, 120.0, 35.0, 365),
            ("P20", "Sparkle Glass Cleaner 500ml", "Home Care", "bottle", 12, 6.5, 75.0, 20.0, 365),

            # 5. Beverages (4 products) - Include short shelf life items (14-30 days) to test caps
            ("P21", "Premium CTC Tea 250g", "Beverages", "pouch", 16, 5.0, 110.0, 30.0, 365),
            ("P22", "Classic Instant Coffee 100g", "Beverages", "jar", 12, 2.5, 190.0, 55.0, 365),
            ("P23", "Fresh Milk Paneer Pack 200g", "Beverages", "pack", 20, 4.5, 80.0, 18.0, 14),   # Short shelf life: 14 days
            ("P24", "Malt Nutrition Health Drink 500g", "Beverages", "jar", 12, 7.0, 210.0, 50.0, 365),
        ]

        products: List[Product] = []
        for pid, name, cat, unit, cp, load, cost, margin, shelf in product_specs:
            products.append(
                Product(
                    id=f"SKU-{pid}",
                    name=name,
                    category=cat,
                    unit=unit,
                    case_pack=cp,
                    load_per_carton=load,
                    unit_cost=cost,
                    unit_margin=margin,
                    min_remaining_shelf_days=min(21, max(7, shelf // 4)),
                    is_simulated=True,
                )
            )
        return products

    def generate_sales_daily(
        self,
        destinations: List[Location],
        products: List[Product],
        history_days: int = 120,
    ) -> List[SalesDaily]:
        """
        Generate 120 days of daily sales per product-destination.
        Warehouses W1 and W2 are pure sources (0 sales).
        Includes:
          - Log-normal base demand
          - Day of week weekly seasonality (weekend peak)
          - Mild linear trend over 120 days
          - Promotion bumps (e.g. days 30-34, days 80-84)
          - Spikes (1% chance of 2.5x spike)
          - heavy_tail=True (Student-t noise)
          - level_shift=True (+/- 30% shift from day 100)
        """
        sales: List[SalesDaily] = []
        start_date = self.base_date - timedelta(days=history_days - 1)

        # Base mean daily cartons per SKU (5 to 30 cartons)
        sku_base_cartons = {
            p.id: float(self.rng.uniform(6.0, 28.0))
            for p in products
        }

        # Destination volume factor
        dest_factors = {
            "D1": 1.4,  # Large Metro Distributor
            "D2": 1.2,  # Wholesale Agency
            "S1": 0.8,  # Flagship Store
            "S2": 0.6,  # Suburban Mart
        }

        # Day of week multiplier (Mon=0 .. Sun=6)
        dow_mults = [0.90, 0.90, 0.95, 1.00, 1.15, 1.30, 1.25]

        # Level shift direction per product (+30% or -30%)
        sku_shift_sign = {
            p.id: 1 if (idx % 2 == 0) else -1
            for idx, p in enumerate(products)
        }

        for day_idx in range(history_days):
            current_date = start_date + timedelta(days=day_idx)
            dow = current_date.weekday()
            dow_factor = dow_mults[dow]

            # Mild upward trend: ~12% growth over 120 days
            trend_factor = 1.0 + (0.001 * day_idx)

            # Promotion bumps on specific days
            is_promo = (30 <= day_idx <= 34) or (80 <= day_idx <= 84)
            promo_factor = 1.50 if is_promo else 1.0

            # Level shift (+/- 30% from day 100 onward)
            is_shifted = (day_idx >= 100) and self.level_shift

            for dest in destinations:
                if dest.type == "warehouse":
                    continue  # Pure sources, no sales

                dest_mult = dest_factors.get(dest.id, 1.0)

                for prod in products:
                    base_carton_mean = sku_base_cartons[prod.id] * dest_mult * dow_factor * trend_factor * promo_factor

                    if is_shifted:
                        shift = sku_shift_sign[prod.id] * 0.30
                        base_carton_mean *= (1.0 + shift)

                    # Noise distribution
                    if self.heavy_tail:
                        # Student-t with df=3 for heavy-tailed shocks
                        t_noise = float(self.rng.standard_t(df=3))
                        noise_factor = np.exp(np.clip(t_noise * 0.15, -0.6, 0.8))
                    else:
                        # Log-normal noise
                        norm_noise = float(self.rng.normal(0, 0.20))
                        noise_factor = np.exp(norm_noise)

                    simulated_cartons = base_carton_mean * noise_factor

                    # Random occasional spike (1% probability)
                    if self.rng.random() < 0.01:
                        simulated_cartons *= 2.5

                    cartons = max(1, int(np.round(simulated_cartons)))
                    units = cartons * prod.case_pack

                    sales.append(
                        SalesDaily(
                            date=current_date,
                            product_id=prod.id,
                            location_id=dest.id,
                            units=units,
                            is_simulated=True,
                        )
                    )

        return sales

    def generate_lanes(
        self,
        warehouses: List[Location],
        destinations: List[Location],
        sales: List[SalesDaily],
        products: List[Product],
    ) -> List[Lane]:
        """
        Generate lanes for all warehouse-destination pairs (2 warehouses x 4 destinations = 8 lanes).
        Lead times: 1 to 3 days.
        Cost per carton: proportional to distance.
        Capacity: set tight (about 70% of unconstrained weekly flow) on exactly 2 lanes.
        """
        # Distances in km
        distance_matrix = {
            ("W1", "D1"): 1500.0,
            ("W1", "D2"): 850.0,
            ("W1", "S1"): 2100.0,
            ("W1", "S2"): 1400.0,
            ("W2", "D1"): 1900.0,
            ("W2", "D2"): 520.0,
            ("W2", "S1"): 1000.0,
            ("W2", "S2"): 160.0,
        }

        # Lead times (1 to 3 days)
        lead_time_matrix = {
            ("W1", "D1"): 3,
            ("W1", "D2"): 2,
            ("W1", "S1"): 3,
            ("W1", "S2"): 2,
            ("W2", "D1"): 3,
            ("W2", "D2"): 1,
            ("W2", "S1"): 2,
            ("W2", "S2"): 1,
        }

        # Compute average weekly carton demand per destination
        case_pack_map = {p.id: p.case_pack for p in products}
        dest_weekly_cartons: Dict[str, float] = {d.id: 0.0 for d in destinations if d.type != "warehouse"}

        for s in sales:
            cp = case_pack_map.get(s.product_id, 1)
            cartons = s.units / cp
            dest_weekly_cartons[s.location_id] += (cartons / (120.0 / 7.0))

        # We have 8 lanes. Exactly 2 lanes get tight capacity:
        # Pick ('W1', 'D2') and ('W2', 'S2') as the 2 tight bottleneck lanes.
        tight_lanes = {("W1", "D2"), ("W2", "S2")}

        lanes: List[Lane] = []
        for wh in warehouses:
            for dst in destinations:
                if dst.type == "warehouse":
                    continue
                pair = (wh.id, dst.id)
                dist = distance_matrix[pair]
                lt = lead_time_matrix[pair]
                # Cost per carton: base 8 INR + 0.028 INR/km
                cost = round(8.0 + (0.028 * dist), 2)

                # Flow capacity
                if pair in tight_lanes:
                    # Unconstrained weekly flow share ~ 50% of destination demand from this warehouse
                    unconstrained_flow = dest_weekly_cartons[dst.id] * 0.50
                    # Tight capacity set to ~70% of unconstrained flow
                    tight_cap = max(100.0, round(unconstrained_flow * 0.70, 0))
                    capacity = tight_cap
                else:
                    capacity = None  # Unconstrained

                lanes.append(
                    Lane(
                        id=f"LANE-{wh.id}-{dst.id}",
                        source_id=wh.id,
                        destination_id=dst.id,
                        lead_time_days=lt,
                        cost_per_carton=cost,
                        capacity_load=capacity,
                        distance_km=dist,
                        is_simulated=True,
                    )
                )

        return lanes

    def generate_inventory_and_batches(
        self,
        warehouses: List[Location],
        destinations: List[Location],
        products: List[Product],
        sales: List[SalesDaily],
    ) -> Tuple[List[Batch], List[InventorySnapshot]]:
        """
        Generate inventory batches at warehouses and destination stock snapshots.
        Warehouse batches are scaled by stock_scenario (0.8, 1.0, 1.3) of mean weekly total demand.
        If variant == 'low_w1', W1 stock is cut by 20%.
        """
        batches: List[Batch] = []
        snapshots: List[InventorySnapshot] = []

        # Calculate mean weekly demand per product across all destinations
        case_pack_map = {p.id: p.case_pack for p in products}
        prod_weekly_cartons: Dict[str, float] = {p.id: 0.0 for p in products}

        for s in sales:
            cp = case_pack_map.get(s.product_id, 1)
            prod_weekly_cartons[s.product_id] += (s.units / cp) / (120.0 / 7.0)

        # 1. Warehouse Batches
        batch_idx = 1
        for prod in products:
            weekly_demand = prod_weekly_cartons[prod.id]
            # Total warehouse supply scaled by stock_scenario
            total_supply_cartons = weekly_demand * self.stock_multiplier

            # Split between W1 and W2 (approx 55% at W1, 45% at W2)
            w1_cartons = int(np.round(total_supply_cartons * 0.55))
            w2_cartons = int(np.round(total_supply_cartons * 0.45))

            # Apply variant 'low_w1': W1 stock cut by 20%
            if self.variant == "low_w1":
                w1_cartons = int(np.round(w1_cartons * 0.80))

            for wh, total_cartons in [(warehouses[0], w1_cartons), (warehouses[1], w2_cartons)]:
                if total_cartons <= 0:
                    total_cartons = 10

                # Split warehouse inventory into 2 batches:
                # Batch 1: Fresh batch (65% qty, expiry in 60-365 days)
                # Batch 2: Aging batch (35% qty, expiry in 18-45 days to test Eshort = 21)
                b1_qty = int(total_cartons * 0.65)
                b2_qty = total_cartons - b1_qty

                # Expiry for fresh batch
                fresh_days = min(365, max(45, int(prod.min_remaining_shelf_days * 4)))
                exp_fresh = self.base_date + timedelta(days=fresh_days)
                mfg_fresh = self.base_date - timedelta(days=15)

                batches.append(
                    Batch(
                        id=f"B-{wh.id}-{prod.id}-01",
                        location_id=wh.id,
                        product_id=prod.id,
                        quantity=b1_qty,
                        expiry_date=exp_fresh,
                        batch_code=f"LOT-{wh.id}-{prod.id}-F",
                        cost_per_carton=prod.unit_cost * prod.case_pack,
                        is_simulated=True,
                    )
                )

                # Expiry for aging batch (some expiring around 18-28 days to test shelf life cap)
                aging_days = 18 if (batch_idx % 4 == 0) else 35
                exp_aging = self.base_date + timedelta(days=aging_days)
                mfg_aging = self.base_date - timedelta(days=40)

                batches.append(
                    Batch(
                        id=f"B-{wh.id}-{prod.id}-02",
                        location_id=wh.id,
                        product_id=prod.id,
                        quantity=b2_qty,
                        expiry_date=exp_aging,
                        batch_code=f"LOT-{wh.id}-{prod.id}-A",
                        cost_per_carton=prod.unit_cost * prod.case_pack * 0.90,
                        is_simulated=True,
                    )
                )
                batch_idx += 1

        # 2. Destination Inventory Snapshots
        for dst in destinations:
            if dst.type == "warehouse":
                continue
            for prod in products:
                # Destinations start with ~2 to 4 days of safety stock + some in-transit
                daily_cartons = max(1, int(np.round(prod_weekly_cartons[prod.id] / 7.0)))
                on_hand = int(daily_cartons * float(self.rng.uniform(2.0, 4.0)))
                in_transit = int(daily_cartons * float(self.rng.uniform(0.5, 1.5)))

                snapshots.append(
                    InventorySnapshot(
                        location_id=dst.id,
                        product_id=prod.id,
                        on_hand=on_hand,
                        reserved=0,
                        in_transit=in_transit,
                        snapshot_date=self.base_date,
                        is_simulated=True,
                    )
                )

        return batches, snapshots

    def inject_defects(
        self,
        products: List[Product],
        locations: List[Location],
        sales: List[SalesDaily],
        batches: List[Batch],
        snapshots: List[InventorySnapshot],
    ) -> Tuple[
        List[Product],
        List[Location],
        List[SalesDaily],
        List[Batch],
        List[InventorySnapshot],
        List[ValidationIssue],
    ]:
        """
        Inject about 20 synthetic defects into data and generate a detailed manifest:
          - Duplicate SKUs (3 defects)
          - Mixed units / invalid case packs (3 defects)
          - Negative stock on hand (4 defects)
          - Invalid / expired dates (4 defects)
          - Missing sales days (6 defects)
        Total injected defects = 20.
        """
        issues: List[ValidationIssue] = []
        manifest_entries: List[Dict[str, Any]] = []

        def record_defect(dtype: str, entity: str, severity: str, desc: str):
            sev = severity.lower()
            issues.append(
                ValidationIssue(
                    type=dtype,
                    entity=entity,
                    severity=sev,
                    status="open",
                    description=desc,
                    fix_first=(sev == "critical"),
                    is_simulated=True,
                )
            )
            manifest_entries.append({
                "defect_id": len(manifest_entries) + 1,
                "type": dtype,
                "entity": entity,
                "severity": sev,
                "description": desc,
            })

        # 1. Duplicate SKUs / Near-duplicate names (3 defects)
        for i in range(1, 4):
            orig = products[i]
            dup = Product(
                id=f"{orig.id}-DUP",
                name=f"{orig.name} (Duplicate Entry)",
                category=orig.category,
                unit=orig.unit,
                case_pack=orig.case_pack,
                load_per_carton=orig.load_per_carton,
                unit_cost=orig.unit_cost,
                unit_margin=orig.unit_margin,
                min_remaining_shelf_days=orig.min_remaining_shelf_days,
                is_simulated=True,
            )
            products.append(dup)
            record_defect(
                "DUPLICATE_SKU",
                f"Product:{dup.id}",
                "critical",
                f"Duplicate SKU entity detected mirroring {orig.id}",
            )

        # 2. Mixed Units / Invalid case packs (3 defects)
        products[5].unit = "UNKNOWN_UNIT"
        record_defect(
            "MIXED_UNITS",
            f"Product:{products[5].id}",
            "warning",
            f"Product has unrecognized unit '{products[5].unit}'",
        )

        products[6].case_pack = -5
        record_defect(
            "MIXED_UNITS",
            f"Product:{products[6].id}",
            "critical",
            f"Negative case_pack ({products[6].case_pack}) detected",
        )

        products[7].case_pack = 0
        record_defect(
            "MIXED_UNITS",
            f"Product:{products[7].id}",
            "critical",
            "Zero case_pack causes division by zero in carton calculation",
        )

        # 3. Negative Stock On Hand (3 defects)
        for idx in range(3):
            snap = snapshots[idx]
            snap.on_hand = -25 - (idx * 10)
            record_defect(
                "NEGATIVE_STOCK",
                f"InventorySnapshot:{snap.location_id}:{snap.product_id}",
                "critical",
                f"Negative on_hand stock ({snap.on_hand} cartons) observed",
            )

        # 4. Invalid / Past Expiry Dates in Batches (4 defects)
        for idx in range(4):
            b = batches[idx]
            b.expiry_date = self.base_date - timedelta(days=15 + idx)
            record_defect(
                "INVALID_DATE",
                f"Batch:{b.id}",
                "critical",
                f"Batch expiry date ({b.expiry_date}) is in the past relative to run date {self.base_date}",
            )

        # 5. Contradictory Stock Records (2 defects: on_hand < reserved)
        for idx in range(3, 5):
            snap = snapshots[idx]
            snap.on_hand = 10
            snap.reserved = 50  # on_hand < reserved !
            record_defect(
                "CONTRADICTORY_STOCK",
                f"InventorySnapshot:{snap.location_id}:{snap.product_id}",
                "critical",
                f"Contradictory stock: on_hand ({snap.on_hand}) is less than reserved ({snap.reserved})",
            )

        # 6. Missing Sales Days (5 defects: gaps longer than 2 days in sales series)
        # Drop 5 consecutive sales records for (D1, SKU-P01)
        target_series_records = [
            s for s in sales
            if s.location_id == "D1" and s.product_id == "SKU-P01"
        ]
        # Pick 5 days in the middle (e.g. days 40 to 44) and remove them
        to_remove = set()
        if len(target_series_records) >= 50:
            removed_subset = target_series_records[40:45]
            for s in removed_subset:
                to_remove.add((s.date, s.location_id, s.product_id))
                record_defect(
                    "MISSING_SALES_DAYS",
                    f"SalesSeries:{s.location_id}:{s.product_id}",
                    "warning",
                    f"Missing sales observation on {s.date} (gap > 2 days in series). Series marked as insufficient data.",
                )
            sales = [s for s in sales if (s.date, s.location_id, s.product_id) not in to_remove]

        self.defect_manifest = manifest_entries
        return products, locations, sales, batches, snapshots, issues

    def generate_all(
        self,
    ) -> Tuple[
        List[Product],
        List[Location],
        List[SalesDaily],
        List[Lane],
        List[Batch],
        List[InventorySnapshot],
        List[ValidationIssue],
    ]:
        """Generate the complete dataset according to parameters and variant."""
        locations = self.generate_locations()
        products = self.generate_products()

        warehouses = [loc for loc in locations if loc.type == "warehouse"]
        destinations = [loc for loc in locations if loc.type != "warehouse"]

        sales = self.generate_sales_daily(destinations, products, history_days=120)
        lanes = self.generate_lanes(warehouses, destinations, sales, products)
        batches, snapshots = self.generate_inventory_and_batches(warehouses, destinations, products, sales)

        issues: List[ValidationIssue] = []
        if self.variant == "defects":
            products, locations, sales, batches, snapshots, issues = self.inject_defects(
                products, locations, sales, batches, snapshots
            )

        return products, locations, sales, lanes, batches, snapshots, issues

    def generate_surplus_listings(self) -> List[SurplusListing]:
        """
        Deterministically seed 12 realistic SurplusListing records for peer distributor / secondary depot rescue.
        Includes:
          - Eligible surplus batches for shortfall rescue across staple, food, and personal care categories.
          - At least 2 listings where on_hand > 0 but verified_spare_cartons == 0 due to seller's own forecast + safety stock.
          - At least 2 listings that fail lead_time_gap > Gmax or remaining shelf life.
        """
        listings = [
            # 1. Eligible rescue for S1/D1: Atta 5kg from Peer Godown P1
            SurplusListing(
                id="SURPLUS-P1-SKU-P01",
                source_id="P1",
                source_name="Peer Godown P1",
                product_id="SKU-P01",
                batch_id="BATCH-SURP-P01-01",
                on_hand=120,
                reserved=0,
                seller_daily_forecast=4.0,
                seller_sigma=1.0,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=60),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 1, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 28.0, "D2": 25.0, "S1": 32.0, "S2": 30.0}),
                seller_unit_cost=180.0,
                salvage_value_per_carton=90.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=180.0,
                is_simulated=True,
            ),
            # 2. Eligible rescue for S2/D1: Instant Masala Noodles from Secondary Depot S1
            SurplusListing(
                id="SURPLUS-S1-SKU-P08",
                source_id="S1_DEPOT",
                source_name="Secondary Depot S1",
                product_id="SKU-P08",
                batch_id="BATCH-SURP-P08-01",
                on_hand=65,
                reserved=0,
                seller_daily_forecast=3.0,
                seller_sigma=0.8,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=45),
                lead_time_days_by_dest=json.dumps({"D1": 3, "D2": 2, "S1": 1, "S2": 1}),
                freight_per_carton_by_dest=json.dumps({"D1": 12.0, "D2": 8.0, "S1": 4.0, "S2": 5.0}),
                seller_unit_cost=11.0,
                salvage_value_per_carton=4.0,
                regular_supplier_lead_time=3,
                regular_supplier_cost_per_carton=11.0,
                is_simulated=True,
            ),
            # 3. Eligible rescue for D2: Tomato Ketchup 500g from Peer Distributor P2
            SurplusListing(
                id="SURPLUS-P2-SKU-P09",
                source_id="P2",
                source_name="Peer Distributor P2",
                product_id="SKU-P09",
                batch_id="BATCH-SURP-P09-01",
                on_hand=95,
                reserved=0,
                seller_daily_forecast=3.0,
                seller_sigma=1.0,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=50),
                lead_time_days_by_dest=json.dumps({"D1": 1, "D2": 2, "S1": 2, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 15.0, "D2": 22.0, "S1": 25.0, "S2": 24.0}),
                seller_unit_cost=85.0,
                salvage_value_per_carton=35.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=85.0,
                is_simulated=True,
            ),
            # 4. Eligible rescue for S2: Herbal Toothpaste 150g from Peer Godown P1
            SurplusListing(
                id="SURPLUS-P1-SKU-P13",
                source_id="P1",
                source_name="Peer Godown P1",
                product_id="SKU-P13",
                batch_id="BATCH-SURP-P13-01",
                on_hand=45,
                reserved=0,
                seller_daily_forecast=2.0,
                seller_sigma=0.5,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=40),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 2, "S2": 1}),
                freight_per_carton_by_dest=json.dumps({"D1": 18.0, "D2": 15.0, "S1": 20.0, "S2": 16.0}),
                seller_unit_cost=75.0,
                salvage_value_per_carton=30.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=75.0,
                is_simulated=True,
            ),
            # 5. Eligible rescue for D1: Toor Dal Premium 1kg from Peer Godown P1
            SurplusListing(
                id="SURPLUS-P1-SKU-P04",
                source_id="P1",
                source_name="Peer Godown P1",
                product_id="SKU-P04",
                batch_id="BATCH-SURP-P04-01",
                on_hand=150,
                reserved=0,
                seller_daily_forecast=5.0,
                seller_sigma=1.2,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=65),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 2, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 25.0, "D2": 20.0, "S1": 28.0, "S2": 26.0}),
                seller_unit_cost=130.0,
                salvage_value_per_carton=60.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=130.0,
                is_simulated=True,
            ),
            # 6. Eligible rescue for S1/S2: Glucose Energy Biscuits from Secondary Depot S1
            SurplusListing(
                id="SURPLUS-S1-SKU-P06",
                source_id="S1_DEPOT",
                source_name="Secondary Depot S1",
                product_id="SKU-P06",
                batch_id="BATCH-SURP-P06-01",
                on_hand=80,
                reserved=0,
                seller_daily_forecast=2.5,
                seller_sigma=0.6,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=50),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 1, "S2": 1}),
                freight_per_carton_by_dest=json.dumps({"D1": 10.0, "D2": 8.0, "S1": 4.0, "S2": 5.0}),
                seller_unit_cost=15.0,
                salvage_value_per_carton=6.0,
                regular_supplier_lead_time=3,
                regular_supplier_cost_per_carton=15.0,
                is_simulated=True,
            ),
            # 7. Eligible rescue for S1: Daily Moisture Cream from Peer Distributor P2
            SurplusListing(
                id="SURPLUS-P2-SKU-P14",
                source_id="P2",
                source_name="Peer Distributor P2",
                product_id="SKU-P14",
                batch_id="BATCH-SURP-P14-01",
                on_hand=60,
                reserved=0,
                seller_daily_forecast=2.0,
                seller_sigma=0.5,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=45),
                lead_time_days_by_dest=json.dumps({"D1": 1, "D2": 2, "S1": 2, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 12.0, "D2": 18.0, "S1": 22.0, "S2": 20.0}),
                seller_unit_cost=95.0,
                salvage_value_per_carton=40.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=95.0,
                is_simulated=True,
            ),
            # 8. Eligible rescue for S1: Lime Dishwash Gel from Peer Godown P1
            SurplusListing(
                id="SURPLUS-P1-SKU-P17",
                source_id="P1",
                source_name="Peer Godown P1",
                product_id="SKU-P17",
                batch_id="BATCH-SURP-P17-01",
                on_hand=70,
                reserved=0,
                seller_daily_forecast=2.2,
                seller_sigma=0.6,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=55),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 1, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 15.0, "D2": 12.0, "S1": 18.0, "S2": 16.0}),
                seller_unit_cost=80.0,
                salvage_value_per_carton=32.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=80.0,
                is_simulated=True,
            ),
            # 9. Gate Failure #1: on_hand > 0 but verified_spare == 0 (Basmati Rice at P1)
            # Need: ceil(5.0 * 7 + 1.65 * 1.8 * sqrt(7)) = ceil(35 + 7.86) = 43. on_hand=35, reserved=5 -> spare = max(0, 30-43) = 0.
            SurplusListing(
                id="SURPLUS-P1-SKU-P02",
                source_id="P1",
                source_name="Peer Godown P1",
                product_id="SKU-P02",
                batch_id="BATCH-SURP-P02-ZERO",
                on_hand=35,
                reserved=5,
                seller_daily_forecast=5.0,
                seller_sigma=1.8,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=60),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 1, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 18.0, "D2": 16.0, "S1": 22.0, "S2": 20.0}),
                seller_unit_cost=95.0,
                salvage_value_per_carton=40.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=95.0,
                is_simulated=True,
            ),
            # 10. Gate Failure #2: on_hand > 0 but verified_spare == 0 (Refined Oil at S1)
            # Need: ceil(4.0 * 7 + 1.65 * 1.5 * sqrt(7)) = ceil(28 + 6.55) = 35. on_hand=28, reserved=0 -> spare = max(0, 28-35) = 0.
            SurplusListing(
                id="SURPLUS-S1-SKU-P07",
                source_id="S1_DEPOT",
                source_name="Secondary Depot S1",
                product_id="SKU-P07",
                batch_id="BATCH-SURP-P07-ZERO",
                on_hand=28,
                reserved=0,
                seller_daily_forecast=4.0,
                seller_sigma=1.5,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=40),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 1, "S2": 1}),
                freight_per_carton_by_dest=json.dumps({"D1": 20.0, "D2": 18.0, "S1": 10.0, "S2": 12.0}),
                seller_unit_cost=125.0,
                salvage_value_per_carton=50.0,
                regular_supplier_lead_time=3,
                regular_supplier_cost_per_carton=125.0,
                is_simulated=True,
            ),
            # 11. Refusal Failure #1: Lead time gap > Gmax for S1 and S2 (Salt from P2: lead time 6 days > Gmax=2)
            SurplusListing(
                id="SURPLUS-P2-SKU-P05",
                source_id="P2",
                source_name="Peer Distributor P2",
                product_id="SKU-P05",
                batch_id="BATCH-SURP-P05-GAP",
                on_hand=120,
                reserved=0,
                seller_daily_forecast=2.0,
                seller_sigma=0.5,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=60),
                lead_time_days_by_dest=json.dumps({"D1": 1, "D2": 2, "S1": 6, "S2": 6}),
                freight_per_carton_by_dest=json.dumps({"D1": 5.0, "D2": 12.0, "S1": 35.0, "S2": 32.0}),
                seller_unit_cost=20.0,
                salvage_value_per_carton=8.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=20.0,
                is_simulated=True,
            ),
            # 12. Refusal Failure #2: Expiry in only 8 days, remaining shelf life at arrival < 14 days
            SurplusListing(
                id="SURPLUS-P1-SKU-P10",
                source_id="P1",
                source_name="Peer Godown P1",
                product_id="SKU-P10",
                batch_id="BATCH-SURP-P10-EXP",
                on_hand=50,
                reserved=0,
                seller_daily_forecast=1.0,
                seller_sigma=0.2,
                protection_days=7,
                expiry_date=self.base_date + timedelta(days=8),
                lead_time_days_by_dest=json.dumps({"D1": 2, "D2": 2, "S1": 2, "S2": 2}),
                freight_per_carton_by_dest=json.dumps({"D1": 8.0, "D2": 7.0, "S1": 10.0, "S2": 9.0}),
                seller_unit_cost=28.0,
                salvage_value_per_carton=10.0,
                regular_supplier_lead_time=4,
                regular_supplier_cost_per_carton=28.0,
                is_simulated=True,
            ),
        ]
        return listings

    def seed_database(self, session: Session) -> Dict[str, Any]:
        """Load simulated data into the database, replacing existing tables."""
        products, locations, sales, lanes, batches, snapshots, issues = self.generate_all()
        surplus_listings = self.generate_surplus_listings()

        # Delete existing data in reverse foreign-key order
        for model_cls in [
            SurplusListing,
            ValidationIssue,
            DecisionLog,
            InventorySnapshot,
            Batch,
            Lane,
            SalesDaily,
            Product,
            Location,
        ]:
            for obj in session.exec(select(model_cls)).all():
                session.delete(obj)
        session.commit()

        # Add entities in foreign-key order
        for loc in locations:
            session.add(loc)
        for prod in products:
            session.add(prod)
        session.commit()

        for lane in lanes:
            session.add(lane)
        for b in batches:
            session.add(b)
        for snap in snapshots:
            session.add(snap)
        for s in sales:
            session.add(s)
        for iss in issues:
            session.add(iss)
        for surp in surplus_listings:
            session.add(surp)

        # Audit decision log
        log = DecisionLog(
            actor_role="system",
            action="SEED",
            note=f"Database seeded with variant={self.variant}, scenario={self.scenario}, seed={self.seed}",
            timestamp=datetime.now(timezone.utc),
        )
        session.add(log)
        session.commit()

        return {
            "variant": self.variant,
            "scenario": self.scenario,
            "seed": self.seed,
            "stock_multiplier": self.stock_multiplier,
            "counts": {
                "locations": len(locations),
                "warehouses": len([l for l in locations if l.type == "warehouse"]),
                "destinations": len([l for l in locations if l.type != "warehouse"]),
                "products": len(products),
                "lanes": len(lanes),
                "batches": len(batches),
                "inventory_snapshots": len(snapshots),
                "sales_daily": len(sales),
                "validation_issues": len(issues),
                "surplus_listings": len(surplus_listings),
            },
            "defect_manifest": self.defect_manifest,
        }

    def seed_deterministic(
        self,
        session: Optional[Session] = None,
        variant: Optional[str] = None,
        seed: Optional[int] = None,
        scenario: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convenience alias for seed_database supporting parameter overrides."""
        target_session = session or getattr(self, "session", None)
        if target_session is None:
            raise ValueError("A database Session is required to seed the database.")
        if seed is not None:
            self.seed = seed
            self.rng = np.random.default_rng(seed)
        if variant is not None:
            self.variant = variant.lower()
        if scenario is not None:
            self.scenario = scenario.lower()
        return self.seed_database(target_session)

    def export_to_csv(self, output_dir: Path = DATA_DIR) -> Dict[str, str]:
        """Export generated simulation data to CSV and write manifest.json."""
        output_dir.mkdir(parents=True, exist_ok=True)
        products, locations, sales, lanes, batches, snapshots, issues = self.generate_all()

        paths = {
            "locations": str(output_dir / "locations.csv"),
            "products": str(output_dir / "products.csv"),
            "lanes": str(output_dir / "lanes.csv"),
            "batches": str(output_dir / "batches.csv"),
            "inventory_snapshots": str(output_dir / "inventory_snapshots.csv"),
            "sales_daily": str(output_dir / "sales_daily.csv"),
        }

        pd.DataFrame([l.model_dump() for l in locations]).to_csv(paths["locations"], index=False)
        pd.DataFrame([p.model_dump() for p in products]).to_csv(paths["products"], index=False)
        pd.DataFrame([l.model_dump() for l in lanes]).to_csv(paths["lanes"], index=False)
        pd.DataFrame([b.model_dump() for b in batches]).to_csv(paths["batches"], index=False)
        pd.DataFrame([s.model_dump() for s in snapshots]).to_csv(paths["inventory_snapshots"], index=False)
        pd.DataFrame([s.model_dump() for s in sales]).to_csv(paths["sales_daily"], index=False)

        manifest = {
            "generator": "VyaparMitra FMCG Simulator",
            "seed": self.seed,
            "scenario": self.scenario,
            "variant": self.variant,
            "base_date": self.base_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_simulated": True,
            "counts": {
                "locations": len(locations),
                "warehouses": len([l for l in locations if l.type == "warehouse"]),
                "destinations": len([l for l in locations if l.type != "warehouse"]),
                "products": len(products),
                "lanes": len(lanes),
                "batches": len(batches),
                "inventory_snapshots": len(snapshots),
                "sales_daily": len(sales),
                "validation_issues": len(issues),
            },
            "tight_lanes": [l.id for l in lanes if l.capacity_load is not None],
            "defect_manifest": self.defect_manifest,
        }

        with open(output_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        if self.defect_manifest:
            with open(output_dir / "defect_manifest.json", "w") as f:
                json.dump(self.defect_manifest, f, indent=2)

        return paths


if __name__ == "__main__":
    from backend.app.db import engine, init_db

    init_db()
    with Session(engine) as session:
        sim = FMCGSimulator(seed=1, scenario="balanced", variant="normal")
        res = sim.seed_database(session)
        paths = sim.export_to_csv()
        print("Database seeded:", res["counts"])
        print("Exported files:", list(paths.keys()))
