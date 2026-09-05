"""Transparent and explainable cash forecasting built from persisted reconciliation runs."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, cast

from sqlalchemy.orm import Session

from models import BatchRun, Exception_, Investigation, Match


logger = logging.getLogger(__name__)

AT_RISK_BUCKETS = ("phantom_charge", "ghost_order", "low_confidence_investigation")
DEFAULT_FORECAST_PERIODS = (0, 7, 14, 30)
SETTLEMENT_FEE_BPS = 236  # 2.36%
OUTLIER_SIGMA_THRESHOLD = 1.75
BACKTEST_HOLDOUT_COUNT = 5
IDENTITY_TOLERANCE_PAISE = 100
GROWTH_WARNING_THRESHOLD = 100.0


def _amount(value: Any) -> int:
    return int(cast(int | None, value) or 0)


def _exception_item(exception: Exception_) -> dict[str, Any]:
    return {
        "id": f"exception_{exception.id}",
        "reference_id": exception.reference_id,
        "amount_paise": _amount(exception.amount_paise),
        "recommended_next_step": exception.recommended_action,
    }


def _top_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: -item["amount_paise"])[:3]


def build_cash_forecast(
    opening_cash_paise: int,
    transactions: Iterable[dict[str, Any]] | None = None,
    periods: Sequence[int] = DEFAULT_FORECAST_PERIODS,
) -> list[dict[str, Any]]:
    ordered_periods = sorted({int(period) for period in periods if int(period) >= 0})
    if not ordered_periods:
        return []

    events: list[tuple[int, str, int]] = []
    for transaction in transactions or []:
        amount = _amount(transaction.get("amount_paise"))
        direction = str(transaction.get("direction", "")).lower()
        if amount <= 0 or direction not in ("inflow", "outflow"):
            continue
        due_in_days = max(0, int(transaction.get("due_in_days", 0)))
        events.append((due_in_days, direction, amount))

    forecast = []
    closing_cash = _amount(opening_cash_paise)
    for period in ordered_periods:
        cumulative_inflow = sum(
            amount for due, direction, amount in events
            if direction == "inflow" and due <= period
        )
        cumulative_outflow = sum(
            amount for due, direction, amount in events
            if direction == "outflow" and due <= period
        )
        period_inflow = sum(
            amount for due, direction, amount in events
            if direction == "inflow" and due == period
        )
        period_outflow = sum(
            amount for due, direction, amount in events
            if direction == "outflow" and due == period
        )
        closing_cash = opening_cash_paise + cumulative_inflow - cumulative_outflow
        forecast.append({
            "period": "today" if period == 0 else f"+{period} days",
            "days": period,
            "opening_cash_paise": opening_cash_paise,
            "period_inflow_paise": period_inflow,
            "period_outflow_paise": period_outflow,
            "cumulative_inflows_paise": cumulative_inflow,
            "cumulative_outflows_paise": cumulative_outflow,
            "expected_inflow_paise": cumulative_inflow,
            "expected_outflow_paise": cumulative_outflow,
            "projected_cash_paise": closing_cash,
        })
    return forecast


def validate_forecast_identity(
    opening_cash_paise: int,
    forecast: Sequence[dict[str, Any]],
    tolerance_paise: int = IDENTITY_TOLERANCE_PAISE,
) -> dict[str, Any]:
    failures = []
    for row in forecast:
        expected = opening_cash_paise + _amount(row.get("cumulative_inflows_paise")) - _amount(row.get("cumulative_outflows_paise"))
        actual = _amount(row.get("projected_cash_paise"))
        diff = actual - expected
        if abs(diff) > tolerance_paise:
            failures.append({
                "period": row.get("period"),
                "expected_closing_cash_paise": expected,
                "actual_closing_cash_paise": actual,
                "difference_paise": diff,
            })

    if failures:
        for failure in failures:
            logger.error(
                "Forecast identity failed for %s: expected %s, got %s, diff %s paise",
                failure["period"],
                failure["expected_closing_cash_paise"],
                failure["actual_closing_cash_paise"],
                failure["difference_paise"],
            )
    return {
        "ok": not failures,
        "tolerance_paise": tolerance_paise,
        "failures": failures,
    }


def validate_forecast_growth(
    opening_cash_paise: int,
    forecast: Sequence[dict[str, Any]],
    threshold_pct: float = GROWTH_WARNING_THRESHOLD,
) -> dict[str, Any]:
    row_30 = next((row for row in forecast if row.get("days") == 30), None)
    if row_30 is None or opening_cash_paise <= 0:
        return {"warning": False, "growth_pct": None, "threshold_pct": threshold_pct}

    closing_cash = _amount(row_30.get("projected_cash_paise"))
    growth_pct = ((closing_cash - opening_cash_paise) / opening_cash_paise) * 100
    warning = growth_pct > threshold_pct
    if warning:
        logger.warning(
            "Forecast growth warning: +%.2f%% over 30 days exceeds threshold %.2f%%",
            growth_pct,
            threshold_pct,
        )
    return {
        "warning": warning,
        "growth_pct": round(growth_pct, 2),
        "threshold_pct": threshold_pct,
    }


def _safe_date(run_at: Any) -> date:
    value = cast(datetime | None, run_at)
    return (value or datetime.now()).date()


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return variance ** 0.5


def _historical_runs(current_run_id: int, db_session: Session, days_back: int = 30) -> list[BatchRun]:
    current_run = db_session.query(BatchRun).filter(BatchRun.id == current_run_id).first()
    if not current_run:
        return []

    current_run_at = cast(datetime | None, current_run.run_at)
    anchor = current_run_at or datetime.now()
    cutoff = anchor - timedelta(days=days_back)
    return db_session.query(BatchRun).filter(
        BatchRun.run_at >= cutoff,
        BatchRun.run_at <= anchor,
    ).order_by(BatchRun.run_at.asc()).all()


def _collect_match_rows(runs: list[BatchRun]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        run_date = _safe_date(run.run_at)
        for match in run.matches:
            amount = _amount(match.settled_amount)
            if amount <= 0:
                continue
            days_to_credit = 2 if str(match.tier).lower() == "exact" else 3
            rows.append({
                "run_id": run.id,
                "run_date": run_date,
                "settlement_id": match.settlement_id,
                "matched_entry_id": match.matched_entry_id,
                "amount_paise": amount,
                "tier": match.tier,
                "confidence": match.confidence,
                "days_to_credit": days_to_credit,
            })
    return rows


def _extract_patterns(match_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not match_rows:
        return {
            "avg_cycle_days": 3,
            "avg_daily_amount_paise": 0,
            "avg_settlement_amount_paise": 0,
            "avg_settlements_per_day": 0,
            "daily_amount_variance": 0,
            "amount_stddev_paise": 0,
            "sample_days": 0,
            "sample_settlements": 0,
        }

    daily_totals: dict[date, int] = defaultdict(int)
    daily_counts: dict[date, int] = defaultdict(int)
    cycle_days: list[float] = []
    settlement_amounts: list[float] = []
    for row in match_rows:
        run_date = row["run_date"]
        amount = row["amount_paise"]
        daily_totals[run_date] += amount
        daily_counts[run_date] += 1
        cycle_days.append(float(row["days_to_credit"]))
        settlement_amounts.append(float(amount))

    totals = list(daily_totals.values())
    counts = list(daily_counts.values())
    avg_settlement_amount = round(mean(settlement_amounts)) if settlement_amounts else 0
    avg_settlements_per_day = mean(counts) if counts else 0
    avg_daily = avg_settlement_amount
    variance = _stddev([float(value) for value in totals])
    amount_stddev = _stddev(settlement_amounts)
    avg_cycle = mean(cycle_days) if cycle_days else 3.0

    return {
        "avg_cycle_days": round(avg_cycle, 1),
        "avg_daily_amount_paise": avg_daily,
        "avg_settlement_amount_paise": avg_settlement_amount,
        "avg_settlements_per_day": round(avg_settlements_per_day, 2),
        "daily_amount_variance": round(variance, 2),
        "amount_stddev_paise": round(amount_stddev, 2),
        "sample_days": len(totals),
        "sample_settlements": len(match_rows),
    }


def _build_confirmed_inflows(current_run: BatchRun, avg_cycle_days: float) -> list[dict[str, Any]]:
    base_date = _safe_date(cast(Any, current_run.run_at))
    confirmed = []
    for match in current_run.matches:
        amount = _amount(match.settled_amount)
        if amount <= 0:
            continue
        due_in_days = 0 if str(match.tier).lower() == "exact" else max(1, round(avg_cycle_days) - 1)
        expected_date = base_date + timedelta(days=due_in_days)
        confirmed.append({
            "reference_id": match.settlement_id,
            "settlement_id": match.settlement_id,
            "matched_entry_id": match.matched_entry_id,
            "amount_paise": amount,
            "due_in_days": due_in_days,
            "expected_date": expected_date.isoformat(),
            "direction": "inflow",
            "confirmed": True,
            "probability_pct": 100,
            "source": "Razorpay",
            "description": f"Settlement ({match.settlement_id})",
        })
    return confirmed


def _build_projected_inflows(current_run: BatchRun, patterns: dict[str, Any], periods: Sequence[int]) -> list[dict[str, Any]]:
    base_date = _safe_date(cast(Any, current_run.run_at))
    avg_daily = max(0, int(patterns.get("avg_daily_amount_paise", 0)))
    amount_stddev = float(patterns.get("amount_stddev_paise", 0) or 0)
    avg_cycle_days = max(1, int(round(patterns.get("avg_cycle_days", 3))))
    max_days = max(periods) if periods else 30
    if avg_daily <= 0:
        return []

    projected_rows: list[dict[str, Any]] = []
    projected_days = [day for day in sorted(set(periods)) if day > 0]
    if not projected_days:
        projected_days = [7, 14, 30]

    previous = 0
    for due_in_days in projected_days:
        incremental_window = due_in_days - previous
        previous = due_in_days
        amount = avg_daily * incremental_window
        confidence = 92
        if amount_stddev > 0 and avg_daily > 0:
            rel_stddev = min(1.0, amount_stddev / avg_daily)
            confidence = max(62, round(95 - rel_stddev * 35))
        expected_date = base_date + timedelta(days=avg_cycle_days if due_in_days == 0 else due_in_days)
        projected_rows.append({
            "reference_id": f"proj_{current_run.id}_{due_in_days}",
            "settlement_id": f"proj_{current_run.id}_{due_in_days}",
            "matched_entry_id": None,
            "amount_paise": amount,
            "due_in_days": due_in_days,
            "expected_date": expected_date.isoformat(),
            "direction": "inflow",
            "confirmed": False,
            "probability_pct": confidence,
            "source": "Projected",
            "description": f"Projected settlement inflow window ending +{due_in_days}d",
        })
    return projected_rows


def _build_outflow_rows(projected_inflows: list[dict[str, Any]], at_risk_breakdown: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for inflow in projected_inflows:
        fee_amount = int(round(inflow["amount_paise"] * SETTLEMENT_FEE_BPS / 10000))
        rows.append({
            "reference_id": f"fee_{inflow['reference_id']}",
            "expected_date": inflow["expected_date"],
            "type": "Fee",
            "description": f"Projected Razorpay fee for {inflow['settlement_id']}",
            "amount_paise": fee_amount,
            "probability_pct": inflow["probability_pct"],
            "due_in_days": inflow["due_in_days"],
        })

    for bucket in at_risk_breakdown:
        for item in bucket.get("top_items", []):
            rows.append({
                "reference_id": item["reference_id"],
                "expected_date": None,
                "type": bucket["bucket"],
                "description": item.get("recommended_next_step") or bucket["bucket"],
                "amount_paise": item["amount_paise"],
                "probability_pct": 90,
                "due_in_days": 0,
            })

    return rows[:12]


def _build_backtest(match_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(match_rows) < BACKTEST_HOLDOUT_COUNT + 3:
        return None

    ordered = sorted(match_rows, key=lambda row: (row["run_date"], row["settlement_id"]))
    holdout = ordered[-BACKTEST_HOLDOUT_COUNT:]
    train = ordered[:-BACKTEST_HOLDOUT_COUNT]
    if not train:
        return None

    train_patterns = _extract_patterns(train)
    avg_daily = max(1, int(train_patterns["avg_daily_amount_paise"]))

    holdout_by_day: dict[date, int] = defaultdict(int)
    for row in holdout:
        holdout_by_day[row["run_date"]] += row["amount_paise"]

    day_pairs = []
    cumulative_actual = 0
    for current_day in sorted(holdout_by_day):
        day_index = (current_day - min(holdout_by_day)).days + 1
        actual = holdout_by_day[current_day]
        predicted = avg_daily * day_index
        cumulative_actual += actual
        abs_err = abs(predicted - cumulative_actual)
        pct_err = (abs_err / cumulative_actual * 100) if cumulative_actual > 0 else 0
        day_pairs.append({
            "period": f"+{day_index} days",
            "predicted": predicted,
            "actual": cumulative_actual,
            "absErr": abs_err,
            "pctErr": pct_err,
        })

    if not day_pairs:
        return None

    mape = sum(pair["pctErr"] for pair in day_pairs) / len(day_pairs)
    mae = sum(pair["absErr"] for pair in day_pairs) / len(day_pairs)
    return {
        "pairs": day_pairs,
        "mape": round(mape, 2),
        "mae": round(mae, 2),
        "holdout_count": len(holdout),
        "method": "Hold out the most recent matched settlements and compare naive moving-average projection to realized totals.",
    }


def compute_cash_position(run_id: int, db_session: Session) -> dict[str, Any]:
    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found"}

    matches = db_session.query(Match).filter(Match.run_id == run_id).all()
    exceptions = db_session.query(Exception_).filter(Exception_.run_id == run_id).all()
    investigations = db_session.query(Investigation).filter(Investigation.run_id == run_id).all()

    historical_runs = _historical_runs(run_id, db_session)
    historical_match_rows = _collect_match_rows(historical_runs)
    patterns = _extract_patterns(historical_match_rows)
    confirmed_inflows = _build_confirmed_inflows(run, patterns["avg_cycle_days"])
    confirmed_total = sum(item["amount_paise"] for item in confirmed_inflows)
    exceptions_by_reference = {exception.reference_id: exception for exception in exceptions}

    bucket_items = {bucket: [] for bucket in AT_RISK_BUCKETS}
    for exception in exceptions:
        exception_type = str(exception.exception_type)
        if exception_type in ("phantom_charge", "ghost_order"):
            bucket_items[exception_type].append(_exception_item(exception))

    avg_settlement = mean([row["amount_paise"] for row in historical_match_rows]) if historical_match_rows else 0
    amount_stddev = float(patterns.get("amount_stddev_paise", 0) or 0)
    if avg_settlement > 0:
        high_water_mark = avg_settlement + OUTLIER_SIGMA_THRESHOLD * amount_stddev
        for match in matches:
            amount = _amount(match.settled_amount)
            if amount_stddev > 0 and amount > high_water_mark:
                bucket_items["low_confidence_investigation"].append({
                    "id": f"outlier_match_{match.id}",
                    "reference_id": match.settlement_id,
                    "amount_paise": amount,
                    "recommended_next_step": "Review unusually large settlement against rolling average before treating forecast as reliable.",
                    "investigation_confidence": None,
                })

    for investigation in investigations:
        investigation_confidence = cast(float | None, investigation.confidence)
        if investigation_confidence is not None and investigation_confidence < 0.7:
            exception = exceptions_by_reference.get(investigation.exception_reference_id)
            if exception is None:
                continue
            item = _exception_item(exception)
            item["id"] = f"investigation_{investigation.id}"
            item["investigation_id"] = investigation.id
            item["investigation_confidence"] = investigation_confidence
            bucket_items["low_confidence_investigation"].append(item)

    breakdown = []
    recommended_next_steps = []
    for bucket in AT_RISK_BUCKETS:
        top_items = _top_items(bucket_items[bucket])
        bucket_total = sum(item["amount_paise"] for item in bucket_items[bucket])
        breakdown.append({
            "bucket": bucket,
            "total_paise": bucket_total,
            "top_items": top_items,
        })
        for item in top_items:
            recommended_next_steps.append({
                "bucket": bucket,
                "source_id": item["id"],
                "reference_id": item["reference_id"],
                "amount_paise": item["amount_paise"],
                "action": item.get("recommended_next_step"),
            })

    at_risk_total = sum(bucket["total_paise"] for bucket in breakdown)
    recommended_next_steps.sort(key=lambda item: -item["amount_paise"])

    return {
        "confirmed_total": confirmed_total,
        "at_risk_total": at_risk_total,
        "at_risk_breakdown": breakdown,
        "recommended_next_steps": recommended_next_steps,
        "patterns": patterns,
        "confirmed_inflows": confirmed_inflows,
    }


def compute_cash_forecast_timeseries(
    run_id: int,
    db_session: Session,
    periods: Sequence[int] = DEFAULT_FORECAST_PERIODS,
) -> dict[str, Any]:
    snapshot = compute_cash_position(run_id=run_id, db_session=db_session)
    if "error" in snapshot:
        return snapshot

    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found"}

    historical_runs = _historical_runs(run_id, db_session)
    historical_match_rows = _collect_match_rows(historical_runs)
    patterns = snapshot["patterns"]
    opening_cash_paise = snapshot["confirmed_total"]
    projected_inflows = _build_projected_inflows(run, patterns, periods)
    outflow_rows = _build_outflow_rows(projected_inflows, snapshot["at_risk_breakdown"])

    transactions = [
        {
            "amount_paise": row["amount_paise"],
            "direction": "inflow",
            "due_in_days": row["due_in_days"],
        }
        for row in projected_inflows
    ] + [
        {
            "amount_paise": row["amount_paise"],
            "direction": "outflow",
            "due_in_days": _amount(row.get("due_in_days")),
        }
        for row in outflow_rows
    ]

    forecast = build_cash_forecast(
        opening_cash_paise=opening_cash_paise,
        transactions=transactions,
        periods=periods,
    )

    identity_check = validate_forecast_identity(opening_cash_paise, forecast)
    growth_check = validate_forecast_growth(opening_cash_paise, forecast)
    expected_inflow_total = sum(item["amount_paise"] for item in projected_inflows if item["due_in_days"] <= max(periods))
    backtest = _build_backtest(historical_match_rows)

    return {
        "run_id": run_id,
        "current_cash_paise": opening_cash_paise,
        "confirmed_cash_paise": opening_cash_paise,
        "expected_inflow_paise": expected_inflow_total,
        "at_risk_cash_paise": snapshot["at_risk_total"],
        "forecast": forecast,
        "patterns": patterns,
        "backtest": backtest,
        "identity_check": identity_check,
        "growth_check": growth_check,
        "inflow_rows": {
            "confirmed": snapshot["confirmed_inflows"],
            "projected": projected_inflows,
        },
        "outflow_rows": outflow_rows,
    }
