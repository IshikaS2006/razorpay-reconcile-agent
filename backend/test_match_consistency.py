import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from pipeline import validate_match_consistency


def test_validate_match_consistency_passes_for_consistent_fuzzy_match():
    result = validate_match_consistency([
        {
            "settlement_id": "setl_ok",
            "tier": "fuzzy",
            "reason": "UTR exact, amount gap 1402p, date gap 0d",
            "expected_amount_paise": 1909636,
            "actual_amount_paise": 1908234,
            "amount_gap_paise": 1402,
        }
    ])
    assert result["ok"] is True
    assert result["failures"] == []


def test_validate_match_consistency_flags_missing_gap_fields_when_reason_mentions_gap():
    result = validate_match_consistency([
        {
            "settlement_id": "setl_bad",
            "tier": "fuzzy",
            "reason": "Amount within 1402p, date within 0d",
            "expected_amount_paise": None,
            "actual_amount_paise": None,
            "amount_gap_paise": None,
        }
    ])
    assert result["ok"] is False
    assert any(f["problem"] == "missing_gap_fields" for f in result["failures"])


def test_validate_match_consistency_flags_reason_gap_mismatch():
    result = validate_match_consistency([
        {
            "settlement_id": "setl_wrong_reason",
            "tier": "fuzzy",
            "reason": "UTR exact, amount gap 999p, date gap 0d",
            "expected_amount_paise": 5000,
            "actual_amount_paise": 4500,
            "amount_gap_paise": 500,
        }
    ])
    assert result["ok"] is False
    assert any(f["problem"] == "reason_gap_mismatch" for f in result["failures"])
