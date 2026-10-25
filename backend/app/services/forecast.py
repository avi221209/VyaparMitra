"""
VyaparMitra - Demand Forecasting Service
Distribution Planning and Inventory Optimization Engine

Per product-destination series, evaluates candidate models:
 (a) seasonal-naive (same weekday last week)
 (b) 7-day moving average
 (c) exponential smoothing with day-of-week factors (alpha=0.25, multiplicative weekday factors)

Model Selection:
 - Rolling-origin scoring on three 7-day folds covering the last 21 days.
 - Score = WAPE = sum|actual - forecast| / sum(actual).
 - Lowest WAPE wins; ties go to the simpler model (seasonal_naive > moving_average_7 > exp_smoothing_dow).

Strict No-Leakage Guarantee:
 - Every forecast function takes an `as_of` date and strictly filters data < as_of.
 - The exact same functions are used inside rolling evaluation and final forecasting.

Uncertainty Sigma:
 - Standard deviation of pooled fold errors, shrunk toward pooled sigma of same product category and destination type:
     sigma = (1 - shrinkage) * sigma_series + shrinkage * sigma_group (default shrinkage = 0.5)
 - Zero-heavy fallback (> 50% zero days in 28-day window):
     forecast = 28-day flat mean, sigma = sqrt(mean) (Poisson spread).

Warnings:
 - Warning emitted if history < 60 days or marked insufficient data.
"""

from datetime import date as dt_date, datetime as dt_datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlmodel import Session, select, func

from backend.app.models import (
    ForecastResult,
    Location,
    Product,
    SalesDaily,
    ValidationIssue,
)
from backend.app.settings import get_current_settings


# Simplicity ranks for deterministic tie-breaking (Rule 2)
# Lower rank = simpler model
MODEL_SIMPLICITY_RANK: Dict[str, int] = {
    "seasonal_naive": 1,
    "moving_average_7": 2,
    "exp_smoothing_dow": 3,
    "poisson_fallback": 4,
}


# =====================================================================
# Core Metric Calculations
# =====================================================================
def compute_wape(actual: List[float], forecast: List[float]) -> float:
    """
    Compute Weighted Absolute Percentage Error (WAPE):
        WAPE = sum(|actual_i - forecast_i|) / sum(actual_i)
    Avoids division by zero on zero-demand days.
    """
    if len(actual) != len(forecast) or len(actual) == 0:
        return 0.0

    sum_actual = float(np.sum(actual))
    sum_abs_err = float(np.sum(np.abs(np.array(actual) - np.array(forecast))))

    if sum_actual > 0:
        return float(sum_abs_err / sum_actual)
    elif sum_abs_err == 0.0:
        return 0.0
    else:
        return 1.0


def compute_bias(actual: List[float], forecast: List[float]) -> float:
    """
    Compute normalized forecast bias:
        bias = mean(actual - forecast) / mean(actual) = sum(actual - forecast) / sum(actual)
    Positive bias indicates under-forecasting (actual > forecast).
    Negative bias indicates over-forecasting (forecast > actual).
    """
    if len(actual) != len(forecast) or len(actual) == 0:
        return 0.0

    sum_actual = float(np.sum(actual))
    sum_err = float(np.sum(np.array(actual) - np.array(forecast)))

    if sum_actual > 0:
        return float(sum_err / sum_actual)
    return 0.0


# =====================================================================
# Candidate Forecast Functions (Strict No-Leakage Guarantee)
# =====================================================================
def forecast_seasonal_naive(
    series: pd.Series,
    as_of: dt_date,
    horizon: int = 7,
) -> List[float]:
    """
    Candidate (a): Seasonal-Naive (same weekday last week).
    Uses ONLY data strictly before `as_of`.

    For day t (0 <= t < horizon), forecast corresponds to the observation
    from the same day of week in the most recent week strictly prior to as_of.
    """
    # Strict no-leakage filter
    history = series[series.index < as_of]
    if history.empty:
        return [0.0] * horizon

    forecasts: List[float] = []
    for step in range(horizon):
        target_date = as_of + timedelta(days=step)
        target_dow = target_date.weekday()

        # Step back 7 days from target date
        prev_week_date = target_date - timedelta(days=7)
        if prev_week_date < as_of and prev_week_date in history.index:
            val = float(history.loc[prev_week_date])
        else:
            # Multi-step horizon or missing calendar date:
            # find most recent past date with matching weekday strictly before as_of
            dow_matches = history[history.index.map(lambda d: d.weekday()) == target_dow]
            if not dow_matches.empty:
                val = float(dow_matches.iloc[-1])
            else:
                val = float(history.iloc[-1]) if not history.empty else 0.0

        forecasts.append(max(0.0, float(val)))

    return forecasts


def forecast_moving_average_7(
    series: pd.Series,
    as_of: dt_date,
    horizon: int = 7,
) -> List[float]:
    """
    Candidate (b): 7-Day Moving Average.
    Uses ONLY data strictly before `as_of`.
    Computes the mean of the 7 calendar days directly preceding as_of.
    """
    # Strict no-leakage filter
    history = series[series.index < as_of]
    if history.empty:
        return [0.0] * horizon

    # 7 calendar days strictly prior to as_of: [as_of - 7d, as_of - 1d]
    window_dates = [as_of - timedelta(days=i) for i in range(7, 0, -1)]
    window_values = [float(history.get(d, 0.0)) for d in window_dates]

    # If entire history is shorter than 7 days, fallback to available history mean
    if len(history) < 7 and sum(window_values) == 0.0:
        ma_val = float(history.mean())
    else:
        ma_val = float(np.mean(window_values))

    ma_val = max(0.0, ma_val)
    return [ma_val] * horizon


def forecast_exp_smoothing_dow(
    series: pd.Series,
    as_of: dt_date,
    horizon: int = 7,
    alpha: float = 0.25,
) -> List[float]:
    """
    Candidate (c): Simple Exponential Smoothing with Day-of-Week factors.
    Uses ONLY data strictly before `as_of`.

    Multiplicative factors per weekday:
      gamma_w = mean(sales on weekday w) / overall_mean
    Level is smoothed on de-seasonalized series:
      L_t = alpha * (y_t / gamma_w) + (1 - alpha) * L_{t-1}
    Forecast for target weekday w:
      hat{y} = L_T * gamma_w
    """
    history = series[series.index < as_of].sort_index()
    if history.empty:
        return [0.0] * horizon

    # Build continuous daily index strictly up to as_of - 1d
    min_date = history.index.min()
    max_date = as_of - timedelta(days=1)
    if min_date > max_date:
        return [0.0] * horizon

    full_dates = [min_date + timedelta(days=i) for i in range((max_date - min_date).days + 1)]
    daily_vals = np.array([float(history.get(d, 0.0)) for d in full_dates], dtype=float)

    overall_mean = float(np.mean(daily_vals))
    if overall_mean <= 1e-4:
        return [0.0] * horizon

    # Day-of-week multipliers
    dow_means = np.zeros(7, dtype=float)
    dow_counts = np.zeros(7, dtype=int)
    for d, val in zip(full_dates, daily_vals):
        w = d.weekday()
        dow_means[w] += val
        dow_counts[w] += 1

    dow_factors = np.ones(7, dtype=float)
    for w in range(7):
        if dow_counts[w] > 0 and overall_mean > 0:
            mean_w = dow_means[w] / dow_counts[w]
            # Clip factors to reasonable range to avoid division-by-zero and explosive multipliers
            dow_factors[w] = float(np.clip(mean_w / overall_mean, 0.1, 4.0))

    # De-seasonalize and apply simple exponential smoothing
    deseasonalized = np.zeros_like(daily_vals)
    for idx, (d, val) in enumerate(zip(full_dates, daily_vals)):
        deseasonalized[idx] = val / dow_factors[d.weekday()]

    level = deseasonalized[0]
    for idx in range(1, len(deseasonalized)):
        level = (alpha * deseasonalized[idx]) + ((1.0 - alpha) * level)

    forecasts: List[float] = []
    for step in range(horizon):
        target_date = as_of + timedelta(days=step)
        target_dow = target_date.weekday()
        pred = max(0.0, float(level * dow_factors[target_dow]))
        forecasts.append(pred)

    return forecasts


def forecast_poisson_fallback(
    series: pd.Series,
    as_of: dt_date,
    horizon: int = 7,
) -> Tuple[List[float], float]:
    """
    Fallback for zero-heavy series (> 50% zero days):
      forecast = 28-day flat mean, sigma = sqrt(mean) (Poisson spread).
    """
    history = series[series.index < as_of]
    if history.empty:
        return [0.0] * horizon, 0.0

    # 28 calendar days strictly prior to as_of
    dates_28 = [as_of - timedelta(days=i) for i in range(28, 0, -1)]
    vals_28 = [float(history.get(d, 0.0)) for d in dates_28]

    mean_28 = float(np.mean(vals_28))
    mean_28 = max(0.0, mean_28)
    sigma_poisson = float(np.sqrt(mean_28))

    return [mean_28] * horizon, sigma_poisson


def is_zero_heavy(series: pd.Series, as_of: dt_date) -> bool:
    """
    Determine if a series is zero-heavy (more than half zero days).
    Checked on the last 28 days strictly prior to as_of.
    """
    history = series[series.index < as_of]
    if history.empty:
        return True

    dates_28 = [as_of - timedelta(days=i) for i in range(28, 0, -1)]
    vals_28 = [float(history.get(d, 0.0)) for d in dates_28]
    zero_count = sum(1 for v in vals_28 if v <= 0.0)

    return (zero_count / len(vals_28)) > 0.5


# =====================================================================
# Rolling-Origin 3-Fold Evaluation & Model Selection
# =====================================================================
def evaluate_rolling_origin(
    series: pd.Series,
    as_of: dt_date,
    alpha: float = 0.25,
) -> Dict[str, Any]:
    """
    Rolling-origin scoring on three 7-day folds covering the last 21 days strictly prior to as_of.

    Fold 1: origin = as_of - 21d, test = [as_of - 21d, as_of - 15d], train < as_of - 21d
    Fold 2: origin = as_of - 14d, test = [as_of - 14d, as_of - 8d],  train < as_of - 14d
    Fold 3: origin = as_of - 7d,  test = [as_of - 7d,  as_of - 1d],  train < as_of - 7d

    Evaluates candidates:
      - seasonal_naive
      - moving_average_7
      - exp_smoothing_dow

    Returns scoring dictionary with candidate WAPEs, biases, fold errors, and the chosen model.
    """
    candidate_names = ["seasonal_naive", "moving_average_7", "exp_smoothing_dow"]

    # Candidate forecast generators
    generators = {
        "seasonal_naive": lambda s, origin: forecast_seasonal_naive(s, origin, horizon=7),
        "moving_average_7": lambda s, origin: forecast_moving_average_7(s, origin, horizon=7),
        "exp_smoothing_dow": lambda s, origin: forecast_exp_smoothing_dow(s, origin, horizon=7, alpha=alpha),
    }

    # Setup the three 7-day origins covering the last 21 days
    origins = [
        as_of - timedelta(days=21),
        as_of - timedelta(days=14),
        as_of - timedelta(days=7),
    ]

    candidate_results: Dict[str, Dict[str, Any]] = {}

    for name in candidate_names:
        pooled_actuals: List[float] = []
        pooled_forecasts: List[float] = []
        pooled_errors: List[float] = []

        for origin in origins:
            # 7-day test fold
            test_dates = [origin + timedelta(days=i) for i in range(7)]
            actuals = [float(series.get(d, 0.0)) for d in test_dates]

            # Generate forecast with strict no-leakage (uses only data < origin)
            pred = generators[name](series, origin)

            pooled_actuals.extend(actuals)
            pooled_forecasts.extend(pred)
            for act, pr in zip(actuals, pred):
                pooled_errors.append(act - pr)

        wape = compute_wape(pooled_actuals, pooled_forecasts)
        bias = compute_bias(pooled_actuals, pooled_forecasts)
        sigma_series = float(np.std(pooled_errors)) if len(pooled_errors) > 1 else 0.0

        candidate_results[name] = {
            "wape": float(round(wape, 5)),
            "bias": float(round(bias, 5)),
            "sigma_series": float(round(sigma_series, 4)),
            "errors": pooled_errors,
        }

    # Lowest WAPE wins; ties go to simpler model (seasonal_naive > moving_average_7 > exp_smoothing_dow)
    sorted_candidates = sorted(
        candidate_names,
        key=lambda m: (candidate_results[m]["wape"], MODEL_SIMPLICITY_RANK[m]),
    )
    chosen_model = sorted_candidates[0]

    return {
        "chosen_model": chosen_model,
        "candidate_results": candidate_results,
        "chosen_wape": candidate_results[chosen_model]["wape"],
        "chosen_bias": candidate_results[chosen_model]["bias"],
        "chosen_sigma_series": candidate_results[chosen_model]["sigma_series"],
        "chosen_errors": candidate_results[chosen_model]["errors"],
    }


# =====================================================================
# Main Demand Forecasting Service
# =====================================================================
class ForecastService:
    """
    Forecasting service executing fit, model selection, uncertainty shrinkage,
    and DB caching for FMCG distribution planning.
    """

    def __init__(
        self,
        session: Optional[Session] = None,
        sales_cache: Optional[Dict[Tuple[str, str], pd.Series]] = None,
        settings_override: Optional[Any] = None,
    ):
        self.session = session
        self.sales_cache = sales_cache
        if settings_override:
            self.settings = settings_override
        elif session:
            self.settings = get_current_settings(session)
        else:
            from backend.app.models import Settings
            self.settings = Settings()

    def get_series_data(self, product_id: str, location_id: str) -> pd.Series:
        """Fetch all sales records for a product-location series ordered by date."""
        if self.sales_cache is not None:
            return self.sales_cache.get((product_id, location_id), pd.Series(dtype=float))

        if not self.session:
            return pd.Series(dtype=float)

        records = self.session.exec(
            select(SalesDaily)
            .where(SalesDaily.product_id == product_id)
            .where(SalesDaily.location_id == location_id)
            .order_by(SalesDaily.date.asc())  # type: ignore
        ).all()

        if not records:
            return pd.Series(dtype=float)

        dates = [r.date for r in records]
        units = [float(r.units) for r in records]
        return pd.Series(units, index=dates)

    def check_series_warning(
        self,
        product_id: str,
        location_id: str,
        history_len: int,
    ) -> Optional[str]:
        """
        Produce warning if history < 60 days or marked insufficient data in ValidationIssue.
        """
        warnings: List[str] = []

        if history_len < 60:
            warnings.append(f"History < 60 days ({history_len} days observed)")

        if not self.session:
            return "; ".join(warnings) if warnings else None

        # Check for open/acknowledged missing sales day issues
        issue_entity = f"SalesSeries:{location_id}:{product_id}"
        issue = self.session.exec(
            select(ValidationIssue)
            .where(ValidationIssue.entity == issue_entity)
            .where(ValidationIssue.type == "MISSING_SALES_DAYS")
        ).first()

        if issue:
            warnings.append("Marked insufficient data (missing sales days detected)")

        return "; ".join(warnings) if warnings else None

    def fit_and_select_series(
        self,
        product_id: str,
        location_id: str,
        as_of: dt_date,
        horizon: int = 7,
        alpha: float = 0.25,
    ) -> Dict[str, Any]:
        """
        Fit and select candidate model for a single series.
        Strictly observes no-leakage: all features derived from data < as_of.
        """
        series = self.get_series_data(product_id, location_id)
        history = series[series.index < as_of] if not series.empty else pd.Series(dtype=float)
        history_len = len(history)

        warning = self.check_series_warning(product_id, location_id, history_len)

        # Check zero-heavy condition (> 50% zero days in 28-day window)
        if is_zero_heavy(series, as_of):
            forecast_vec, sigma = forecast_poisson_fallback(series, as_of, horizon=horizon)
            # Evaluate WAPE on last 21 days for consistency
            dates_21 = [as_of - timedelta(days=i) for i in range(21, 0, -1)]
            actuals_21 = [float(series.get(d, 0.0)) for d in dates_21]
            pred_21 = [forecast_vec[0]] * 21
            wape = compute_wape(actuals_21, pred_21)
            bias = compute_bias(actuals_21, pred_21)

            return {
                "product_id": product_id,
                "location_id": location_id,
                "as_of_date": as_of,
                "chosen_model": "poisson_fallback",
                "daily_forecast": [round(v, 2) for v in forecast_vec],
                "wape": round(wape, 4),
                "bias": round(bias, 4),
                "sigma": round(sigma, 4),
                "sigma_series": round(sigma, 4),
                "warning": warning,
                "details": {
                    "is_zero_heavy": True,
                    "poisson_mean_28": round(forecast_vec[0], 2),
                },
                "fold_errors": [act - pr for act, pr in zip(actuals_21, pred_21)],
                "is_simulated": True,
            }

        # Non-zero heavy: Run 3-fold rolling-origin scoring
        eval_result = evaluate_rolling_origin(series, as_of, alpha=alpha)
        chosen_model = eval_result["chosen_model"]

        # Final forecast for the horizon using the chosen model at as_of
        if chosen_model == "seasonal_naive":
            daily_forecast = forecast_seasonal_naive(series, as_of, horizon=horizon)
        elif chosen_model == "moving_average_7":
            daily_forecast = forecast_moving_average_7(series, as_of, horizon=horizon)
        else:
            daily_forecast = forecast_exp_smoothing_dow(series, as_of, horizon=horizon, alpha=alpha)

        return {
            "product_id": product_id,
            "location_id": location_id,
            "as_of_date": as_of,
            "chosen_model": chosen_model,
            "daily_forecast": [round(v, 2) for v in daily_forecast],
            "wape": round(eval_result["chosen_wape"], 4),
            "bias": round(eval_result["chosen_bias"], 4),
            "sigma": round(eval_result["chosen_sigma_series"], 4),  # Will be adjusted by group shrinkage
            "sigma_series": round(eval_result["chosen_sigma_series"], 4),
            "warning": warning,
            "details": {
                "candidate_wapes": {
                    m: res["wape"] for m, res in eval_result["candidate_results"].items()
                },
                "candidate_biases": {
                    m: res["bias"] for m, res in eval_result["candidate_results"].items()
                },
            },
            "fold_errors": eval_result["chosen_errors"],
            "is_simulated": True,
        }

    def fit_and_select_all(
        self,
        as_of: Optional[dt_date] = None,
        horizon: Optional[int] = None,
        products_override: Optional[List[Product]] = None,
        destinations_override: Optional[List[Location]] = None,
        persist: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fit and select candidate model for ALL product-destination series.
        Applies group-level uncertainty shrinkage:
          sigma = (1 - shrinkage) * sigma_series + shrinkage * sigma_group
        where group = (product.category, location.type).
        Caches all results in the database table `ForecastResult` if persist=True and session exists.
        """
        h = horizon or self.settings.H
        alpha = self.settings.alpha
        shrinkage = self.settings.shrinkage

        # If as_of not specified, default to day after max sales date
        if as_of is None:
            if self.session:
                max_sales_date = self.session.exec(select(func.max(SalesDaily.date))).one()
                if max_sales_date:
                    as_of = max_sales_date + timedelta(days=1)
                else:
                    as_of = dt_date(2026, 10, 24)
            else:
                as_of = dt_date(2026, 10, 24)

        # Retrieve all products and destinations (locations with type distributor or store)
        if products_override is not None:
            products = products_override
        elif self.session:
            products = list(self.session.exec(select(Product)).all())
        else:
            products = []

        if destinations_override is not None:
            destinations = destinations_override
        elif self.session:
            destinations = list(
                self.session.exec(
                    select(Location).where(Location.type.in_(["distributor", "store"]))  # type: ignore
                ).all()
            )
        else:
            destinations = []

        prod_map = {p.id: p for p in products}
        dest_map = {d.id: d for d in destinations}

        # Step 1: Fit and evaluate all series
        series_results: List[Dict[str, Any]] = []
        for prod in products:
            for dest in destinations:
                res = self.fit_and_select_series(
                    product_id=prod.id,
                    location_id=dest.id,
                    as_of=as_of,
                    horizon=h,
                    alpha=alpha,
                )
                series_results.append(res)

        # Step 2: Pooled group sigma shrinkage
        # Group key: (product.category, location.type)
        group_errors: Dict[Tuple[str, str], List[float]] = {}
        for res in series_results:
            if res["chosen_model"] == "poisson_fallback":
                continue  # Poisson fallback uses sqrt(mean) directly

            p = prod_map.get(res["product_id"])
            d = dest_map.get(res["location_id"])
            if not p or not d:
                continue

            grp_key = (p.category, d.type)
            if grp_key not in group_errors:
                group_errors[grp_key] = []
            group_errors[grp_key].extend(res.get("fold_errors", []))

        # Compute group sigmas
        group_sigmas: Dict[Tuple[str, str], float] = {}
        for grp_key, errs in group_errors.items():
            if len(errs) > 1:
                group_sigmas[grp_key] = float(np.std(errs))
            else:
                group_sigmas[grp_key] = 0.0

        # Step 3: Apply shrinkage to non-zero-heavy series and cache in DB
        final_results: List[Dict[str, Any]] = []

        # Remove existing cached forecasts for this as_of date to ensure idempotency if persisting
        if persist and self.session:
            existing_records = self.session.exec(
                select(ForecastResult).where(ForecastResult.as_of_date == as_of)
            ).all()
            for rec in existing_records:
                self.session.delete(rec)
            self.session.commit()

        for res in series_results:
            pid = res["product_id"]
            lid = res["location_id"]
            p = prod_map.get(pid)
            d = dest_map.get(lid)

            sigma_series = res["sigma_series"]
            if res["chosen_model"] == "poisson_fallback":
                final_sigma = sigma_series
            else:
                grp_key = (p.category, d.type) if p and d else ("", "")
                sigma_group = group_sigmas.get(grp_key, sigma_series)
                final_sigma = (1.0 - shrinkage) * sigma_series + shrinkage * sigma_group

            res["sigma"] = float(round(final_sigma, 4))
            res["details"]["sigma_series"] = sigma_series
            res["details"]["shrinkage"] = shrinkage
            if res["chosen_model"] != "poisson_fallback" and p and d:
                res["details"]["sigma_group"] = float(round(group_sigmas.get((p.category, d.type), 0.0), 4))
                res["details"]["group"] = f"{p.category}:{d.type}"

            if persist and self.session:
                # Save in ForecastResult DB table
                db_record = ForecastResult(
                    as_of_date=as_of,
                    product_id=pid,
                    location_id=lid,
                    chosen_model=res["chosen_model"],
                    daily_forecast_json=json.dumps(res["daily_forecast"]),
                    wape=res["wape"],
                    bias=res["bias"],
                    sigma=res["sigma"],
                    warning=res["warning"],
                    details_json=json.dumps(res["details"]),
                    is_simulated=True,
                )
                self.session.add(db_record)
            final_results.append(res)

        if persist and self.session:
            self.session.commit()
        return final_results
