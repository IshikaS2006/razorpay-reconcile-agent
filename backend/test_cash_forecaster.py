import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from cash_forecaster import (
    build_cash_forecast,
    validate_forecast_growth,
    validate_forecast_identity,
)


def test_forecast_accumulates_multiple_periods():
    result = build_cash_forecast(
        10000,
        [
            {"amount_paise": 2000, "direction": "inflow", "due_in_days": 0},
            {"amount_paise": 3000, "direction": "inflow", "due_in_days": 7},
            {"amount_paise": 1500, "direction": "outflow", "due_in_days": 14},
        ],
    )

    assert [item["projected_cash_paise"] for item in result] == [12000, 15000, 13500, 13500]
    assert result[1]["cumulative_inflows_paise"] == 5000
    assert result[2]["cumulative_outflows_paise"] == 1500


def test_forecast_handles_no_transactions():
    result = build_cash_forecast(5000, [])

    assert all(item["expected_inflow_paise"] == 0 for item in result)
    assert all(item["expected_outflow_paise"] == 0 for item in result)
    assert all(item["projected_cash_paise"] == 5000 for item in result)


def test_forecast_supports_only_inflows_and_only_outflows():
    inflows = build_cash_forecast(1000, [{"amount_paise": 2500, "direction": "inflow", "due_in_days": 7}])
    outflows = build_cash_forecast(5000, [{"amount_paise": 1200, "direction": "outflow", "due_in_days": 14}])

    assert inflows[1]["projected_cash_paise"] == 3500
    assert outflows[2]["projected_cash_paise"] == 3800


def test_forecast_ignores_missing_or_invalid_transactions():
    result = build_cash_forecast(
        7000,
        [{}, {"amount_paise": 100, "direction": "unknown"}, {"amount_paise": None, "direction": "inflow"}],
    )

    assert all(item["projected_cash_paise"] == 7000 for item in result)


def test_forecast_identity_validation_passes_for_valid_series():
    forecast = build_cash_forecast(
        921818,
        [
            {"amount_paise": 500000, "direction": "inflow", "due_in_days": 7},
            {"amount_paise": 300000, "direction": "inflow", "due_in_days": 14},
            {"amount_paise": 50761, "direction": "outflow", "due_in_days": 30},
        ],
    )

    validation = validate_forecast_identity(921818, forecast)

    assert validation["ok"] is True
    assert validation["failures"] == []


def test_forecast_identity_validation_catches_mismatch():
    forecast = build_cash_forecast(100000, [{"amount_paise": 50000, "direction": "inflow", "due_in_days": 7}])
    broken = [dict(row) for row in forecast]
    broken[1]["projected_cash_paise"] += 12345

    validation = validate_forecast_identity(100000, broken)

    assert validation["ok"] is False
    assert validation["failures"][0]["period"] == "+7 days"
    assert validation["failures"][0]["difference_paise"] == 12345


def test_forecast_growth_warning_flags_implausible_growth():
    forecast = build_cash_forecast(
        100000,
        [{"amount_paise": 250000, "direction": "inflow", "due_in_days": 30}],
    )

    growth = validate_forecast_growth(100000, forecast)

    assert growth["warning"] is True
    assert growth["growth_pct"] == 250.0
