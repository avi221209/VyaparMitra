"""
VyaparMitra - Forecasting API Router
Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine

Endpoints:
 - POST /api/forecast/run: Fit and select best forecasting model for all series, cache in DB.
 - GET /api/forecast/{product}/{location}: Fetch forecast, metrics, uncertainty sigma, and warnings.
"""

from datetime import date as dt_date, timedelta
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func

from backend.app.db import get_session
from backend.app.models import (
    ForecastResult,
    Location,
    Product,
    SalesDaily,
)
from backend.app.schemas import (
    ForecastRunRequest,
    ForecastRunResponse,
    ForecastSeriesResponse,
)
from backend.app.services.forecast import ForecastService


router = APIRouter(tags=["Forecasting"])


def resolve_product_id(session: Session, product_input: str) -> str:
    """Resolve user product identifier to canonical SKU ID in DB."""
    # Try exact match
    exact = session.exec(select(Product).where(Product.id == product_input)).first()
    if exact:
        return exact.id

    # Try prepending SKU-
    if not product_input.startswith("SKU-"):
        with_sku = session.exec(select(Product).where(Product.id == f"SKU-{product_input}")).first()
        if with_sku:
            return with_sku.id

    # Try name match
    by_name = session.exec(select(Product).where(Product.name == product_input)).first()
    if by_name:
        return by_name.id

    # If still not found, return original string
    return product_input


def resolve_location_id(session: Session, location_input: str) -> str:
    """Resolve location identifier to canonical Location ID in DB."""
    loc = session.exec(select(Location).where(Location.id == location_input.upper())).first()
    if loc:
        return loc.id
    loc_by_name = session.exec(select(Location).where(Location.name == location_input)).first()
    if loc_by_name:
        return loc_by_name.id
    return location_input.upper()


@router.post(
    "/api/forecast/run",
    response_model=ForecastRunResponse,
    summary="Fit and select candidate model for all series and cache in DB",
)
@router.post(
    "/api/v1/forecast/run",
    response_model=ForecastRunResponse,
    include_in_schema=False,
)
def run_forecast(
    request: Optional[ForecastRunRequest] = Body(default=None),
    as_of: Optional[dt_date] = Query(default=None),
    horizon: Optional[int] = Query(default=None, ge=1, le=30),
    session: Session = Depends(get_session),
) -> ForecastRunResponse:
    """
    Fit candidate models across 3 rolling-origin folds for all product-destination series.
    Caches chosen model, daily forecast vector, WAPE, bias, and uncertainty sigma in the database.
    """
    as_of_date = as_of or (request.as_of if request else None)
    h = horizon or (request.horizon if request else None)

    service = ForecastService(session)
    results = service.fit_and_select_all(as_of=as_of_date, horizon=h)

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No product-destination series found to forecast.",
        )

    # Determine effective as_of_date
    effective_as_of = results[0]["as_of_date"]

    # Model selection counts
    models_selected: Dict[str, int] = {}
    total_wape = 0.0
    total_bias = 0.0

    series_responses: List[ForecastSeriesResponse] = []
    for r in results:
        m = r["chosen_model"]
        models_selected[m] = models_selected.get(m, 0) + 1
        total_wape += r["wape"]
        total_bias += r["bias"]

        series_responses.append(
            ForecastSeriesResponse(
                product_id=r["product_id"],
                location_id=r["location_id"],
                as_of_date=r["as_of_date"],
                chosen_model=r["chosen_model"],
                daily_forecast=r["daily_forecast"],
                wape=r["wape"],
                bias=r["bias"],
                sigma=r["sigma"],
                warning=r.get("warning"),
                details=r.get("details"),
                is_simulated=True,
            )
        )

    n = len(results)
    mean_wape = round(total_wape / n, 4) if n > 0 else 0.0
    mean_bias = round(total_bias / n, 4) if n > 0 else 0.0

    return ForecastRunResponse(
        status="success",
        as_of_date=effective_as_of,
        total_series=n,
        models_selected=models_selected,
        mean_wape=mean_wape,
        mean_bias=mean_bias,
        forecasts=series_responses,
        is_simulated=True,
    )


@router.get(
    "/api/forecast/{product}/{location}",
    response_model=ForecastSeriesResponse,
    summary="Get forecast for a specific product and destination location",
)
@router.get(
    "/api/v1/forecast/{product}/{location}",
    response_model=ForecastSeriesResponse,
    include_in_schema=False,
)
def get_series_forecast(
    product: str,
    location: str,
    as_of: Optional[dt_date] = Query(default=None),
    session: Session = Depends(get_session),
) -> ForecastSeriesResponse:
    """
    Retrieve forecast for a single product-destination series.
    Returns chosen model, daily forecast vector, WAPE, bias, uncertainty sigma, and warnings.
    """
    pid = resolve_product_id(session, product)
    lid = resolve_location_id(session, location)

    # Check cached results first
    query = select(ForecastResult).where(
        ForecastResult.product_id == pid,
        ForecastResult.location_id == lid,
    )
    if as_of:
        query = query.where(ForecastResult.as_of_date == as_of)
    query = query.order_by(ForecastResult.as_of_date.desc(), ForecastResult.created_at.desc())  # type: ignore

    cached = session.exec(query).first()
    if cached:
        daily_forecast = json.loads(cached.daily_forecast_json)
        details = json.loads(cached.details_json) if cached.details_json else {}
        return ForecastSeriesResponse(
            product_id=cached.product_id,
            location_id=cached.location_id,
            as_of_date=cached.as_of_date,
            chosen_model=cached.chosen_model,
            daily_forecast=daily_forecast,
            wape=cached.wape,
            bias=cached.bias,
            sigma=cached.sigma,
            warning=cached.warning,
            details=details,
            is_simulated=True,
        )

    # If not cached, fit on the fly
    service = ForecastService(session)
    if as_of is None:
        max_sales_date = session.exec(select(func.max(SalesDaily.date))).one()
        as_of = (max_sales_date + timedelta(days=1)) if max_sales_date else dt_date(2026, 10, 24)

    res = service.fit_and_select_series(pid, lid, as_of=as_of)
    return ForecastSeriesResponse(
        product_id=res["product_id"],
        location_id=res["location_id"],
        as_of_date=res["as_of_date"],
        chosen_model=res["chosen_model"],
        daily_forecast=res["daily_forecast"],
        wape=res["wape"],
        bias=res["bias"],
        sigma=res["sigma"],
        warning=res.get("warning"),
        details=res.get("details"),
        is_simulated=True,
    )
