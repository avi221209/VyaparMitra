"""
VyaparMitra - Net Requirement Calculation Service
Distribution Planning and Inventory Optimization Engine

PURE FUNCTIONS ONLY - NO DATABASE ACCESS INSIDE.

Computes net carton requirement per (destination d, product k):
 - pos = on_hand - reserved + confirmed_in_transit
 - cover = pos / f (f = daily forecast mean; if f = 0, cover = infinity)
 - Ld = longest lead time among eligible lanes into d (or fastest if configured)
 - P = H + Ld
 - F = sum of daily forecast over P days
 - SS = z * sigma * sqrt(P)
 - Ndem = max(0, F - pos)
 - Ntot = max(0, F + SS - pos)
 - Cartons conversion: round up with ceil. Computed ONCE per run.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional


@dataclass
class LaneInfo:
    """Pure data representation of a network transportation lane."""
    source_id: str
    destination_id: str
    lead_time_days: int
    cost_per_carton: float = 0.0
    capacity_load: Optional[float] = None
    distance_km: float = 0.0


@dataclass
class NetRequirement:
    """Calculated net requirement record for a destination-product pair."""
    destination_id: str
    product_id: str
    on_hand: float
    reserved: float
    confirmed_in_transit: float
    pos: float                          # Effective position: on_hand - reserved + in_transit
    daily_forecast_mean: float          # f (units/day)
    cover: float                        # Days of inventory cover: pos / f (inf if f=0)
    eligible_lead_times: List[int]      # Lead times of lanes passing lane gap G <= Gmax
    Ld: int                             # Governing lead time (longest or fastest eligible)
    P: int                              # Planning horizon + governing lead time: H + Ld
    F: float                            # Cumulative forecast demand over P days
    SS: float                           # Safety stock: z * sigma * sqrt(P)
    Ndem: int                           # Base demand net requirement in cartons: ceil(max(0, F - pos) / case_pack)
    Ntot: int                           # Total net requirement with safety stock: ceil(max(0, F + SS - pos) / case_pack)
    unrounded_Ndem: float               # Raw unrounded net demand
    unrounded_Ntot: float               # Raw unrounded net total with SS
    case_pack: int = 1
    sigma: float = 0.0
    flags: List[str] = field(default_factory=list)


def compute_net_requirement(
    destination_id: str,
    product_id: str,
    on_hand: float,
    reserved: float = 0.0,
    confirmed_in_transit: float = 0.0,
    daily_forecast: Optional[List[float]] = None,
    daily_forecast_mean: Optional[float] = None,
    sigma: float = 0.0,
    lanes: Optional[List[LaneInfo]] = None,
    H: int = 7,
    z: float = 1.28,
    Gmax: int = 1,
    case_pack: int = 1,
    use_fastest_lead_time: bool = False,
) -> NetRequirement:
    """
    Pure calculation of net requirements for a single product at a destination.

    Parameters:
      destination_id: Target location ID (e.g. D1, D2, S1)
      product_id: SKU identifier (e.g. SKU-P01)
      on_hand: Current stock on hand in primary units or cartons
      reserved: Stock reserved for orders
      confirmed_in_transit: In-transit inbound stock
      daily_forecast: List of daily forecasted demand values for upcoming days
      daily_forecast_mean: Precomputed mean daily demand f (fallback if vector not provided)
      sigma: Forecast uncertainty standard deviation
      lanes: Candidate inbound lanes into destination_id
      H: Planning horizon in days (default 7)
      z: Safety stock z-factor (default 1.28 for ~90% service level)
      Gmax: Maximum allowed lane gap in days (default 1)
      case_pack: Units per carton (default 1)
      use_fastest_lead_time: If True, uses fastest eligible lane; default is longest eligible lane

    Returns:
      NetRequirement dataclass with all intermediate and final integer carton values.
    """
    flags: List[str] = []

    # 1. Effective Stock Position
    pos = float(on_hand - reserved + confirmed_in_transit)

    # 2. Daily Forecast Mean (f)
    if daily_forecast is not None and len(daily_forecast) > 0:
        f = float(sum(daily_forecast) / len(daily_forecast))
    elif daily_forecast_mean is not None:
        f = float(daily_forecast_mean)
    else:
        f = 0.0

    # 3. Inventory Cover (days)
    if f > 1e-6:
        cover = pos / f
    else:
        cover = float("inf")

    # 4. Filter Eligible Lanes by Lane Gap (G <= Gmax)
    inbound_lanes = [lane for lane in (lanes or []) if lane.destination_id == destination_id]
    eligible_lead_times: List[int] = []

    for lane in inbound_lanes:
        lead_time = lane.lead_time_days
        # Lane gap G = max(0, lead_time - cover)
        if math.isinf(cover):
            gap = 0.0
        else:
            gap = max(0.0, float(lead_time) - cover)

        if gap <= Gmax:
            eligible_lead_times.append(lead_time)

    # Determine Governing Lead Time Ld
    if eligible_lead_times:
        if use_fastest_lead_time:
            Ld = min(eligible_lead_times)
        else:
            Ld = max(eligible_lead_times)
    else:
        # Fallback if no inbound lane meets G <= Gmax
        if inbound_lanes:
            Ld = min(lane.lead_time_days for lane in inbound_lanes)
            flags.append("NO_LANE_WITHIN_GMAX_FALLBACK_FASTEST")
        else:
            Ld = 1
            flags.append("NO_INBOUND_LANES_DEFAULT_LD_1")

    # 5. Planning Horizon with Lead Time (P = H + Ld)
    P = H + Ld

    # 6. Cumulative Forecast Demand (F) over P days
    if daily_forecast is not None and len(daily_forecast) >= P:
        F = float(sum(daily_forecast[:P]))
    elif daily_forecast is not None and len(daily_forecast) > 0:
        # If vector is shorter than P, extend with daily mean
        F = float(sum(daily_forecast) + (P - len(daily_forecast)) * f)
    else:
        F = float(P * f)

    # 7. Safety Stock (SS = z * sigma * sqrt(P))
    SS = float(z * sigma * math.sqrt(P))

    # 8. Unrounded and Whole Carton Net Requirements
    # Conversion to cartons: ceil(max(0, requirement) / case_pack)
    cp = max(1, case_pack)
    unrounded_Ndem = max(0.0, F - pos)
    unrounded_Ntot = max(0.0, F + SS - pos)

    Ndem_cartons = int(math.ceil(unrounded_Ndem / cp))
    Ntot_cartons = int(math.ceil(unrounded_Ntot / cp))

    return NetRequirement(
        destination_id=destination_id,
        product_id=product_id,
        on_hand=on_hand,
        reserved=reserved,
        confirmed_in_transit=confirmed_in_transit,
        pos=pos,
        daily_forecast_mean=f,
        cover=cover,
        eligible_lead_times=eligible_lead_times,
        Ld=Ld,
        P=P,
        F=F,
        SS=SS,
        Ndem=Ndem_cartons,
        Ntot=Ntot_cartons,
        unrounded_Ndem=unrounded_Ndem,
        unrounded_Ntot=unrounded_Ntot,
        case_pack=cp,
        sigma=sigma,
        flags=flags,
    )


def compute_all_net_requirements(
    destinations: List[str],
    products: List[str],
    inventory_positions: Dict[str, Dict[str, float]],  # dest_id -> {prod_id: on_hand}
    forecast_means: Dict[str, Dict[str, float]],        # dest_id -> {prod_id: mean_f}
    forecast_sigmas: Dict[str, Dict[str, float]],       # dest_id -> {prod_id: sigma}
    lanes: List[LaneInfo],
    daily_forecasts: Optional[Dict[str, Dict[str, List[float]]]] = None,
    reserved_map: Optional[Dict[str, Dict[str, float]]] = None,
    in_transit_map: Optional[Dict[str, Dict[str, float]]] = None,
    case_packs: Optional[Dict[str, int]] = None,
    H: int = 7,
    z: float = 1.28,
    Gmax: int = 1,
    use_fastest_lead_time: bool = False,
) -> Dict[str, Dict[str, NetRequirement]]:
    """
    Batch pure calculation of net requirements for all (destination, product) pairs.
    Computed ONCE per run and stored.
    """
    results: Dict[str, Dict[str, NetRequirement]] = {}

    for dest_id in destinations:
        results[dest_id] = {}
        for prod_id in products:
            on_hand = inventory_positions.get(dest_id, {}).get(prod_id, 0.0)
            reserved = reserved_map.get(dest_id, {}).get(prod_id, 0.0) if reserved_map else 0.0
            in_transit = in_transit_map.get(dest_id, {}).get(prod_id, 0.0) if in_transit_map else 0.0

            f_mean = forecast_means.get(dest_id, {}).get(prod_id, 0.0)
            sig = forecast_sigmas.get(dest_id, {}).get(prod_id, 0.0)
            d_fc = daily_forecasts.get(dest_id, {}).get(prod_id) if daily_forecasts else None
            cp = case_packs.get(prod_id, 1) if case_packs else 1

            req = compute_net_requirement(
                destination_id=dest_id,
                product_id=prod_id,
                on_hand=on_hand,
                reserved=reserved,
                confirmed_in_transit=in_transit,
                daily_forecast=d_fc,
                daily_forecast_mean=f_mean,
                sigma=sig,
                lanes=lanes,
                H=H,
                z=z,
                Gmax=Gmax,
                case_pack=cp,
                use_fastest_lead_time=use_fastest_lead_time,
            )
            results[dest_id][prod_id] = req

    return results
