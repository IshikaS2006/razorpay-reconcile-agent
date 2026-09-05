import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from evaluate import score_result


def _write_ground_truth(directory):
    pd.DataFrame([
        {"settlement_id": "s1", "expected_match_type": "exact", "noise_type": "clean_exact"},
        {"settlement_id": "s2", "expected_match_type": "exception", "noise_type": "duplicate_entry"},
        {"settlement_id": "s3", "expected_match_type": "exception", "noise_type": "missing_in_ledger"},
        {"settlement_id": "s4", "expected_match_type": "fuzzy", "noise_type": "date_lag"},
    ]).to_csv(os.path.join(directory, "ground_truth.csv"), index=False)
    pd.DataFrame([{"entry_id": "l1"}]).to_csv(os.path.join(directory, "ledger_ground_truth.csv"), index=False)
    pd.DataFrame([{"entity_id": "p1"}, {"entity_id": "p2"}]).to_csv(os.path.join(directory, "tax_ground_truth.csv"), index=False)


def test_score_result_uses_full_batch_for_match_metrics(tmp_path):
    _write_ground_truth(tmp_path)
    result = score_result({
        "matches": [{"settlement_id": "s1"}, {"settlement_id": "s4"}],
        "exceptions": [
            {"reference_id": "s2", "source": "bank_reconciliation", "exception_type": "duplicate_posting"},
            {"reference_id": "s3", "source": "bank_reconciliation", "exception_type": "unresolved_settlement"},
        ],
        "order_reconciliation": {"enabled": False},
    }, str(tmp_path))

    matching = result["bank_matching"]
    assert matching["match_rate"] == 0.5
    assert matching["match_precision"] == 1.0
    assert matching["match_recall"] == 1.0
    assert result["exception_detection"]["duplicate_bank_entry"]["recall"] == 1.0
    assert result["exception_detection"]["missing_bank_credit"]["recall"] == 1.0


def test_score_result_measures_tax_precision_and_recall(tmp_path):
    _write_ground_truth(tmp_path)
    result = score_result({
        "matches": [],
        "exceptions": [
            {"reference_id": "p1", "source": "tax_verification", "exception_type": "tax_line_mismatch"},
            {"reference_id": "other", "source": "tax_verification", "exception_type": "tax_line_mismatch"},
        ],
        "order_reconciliation": {"enabled": False},
    }, str(tmp_path))

    tax = result["tax_anomaly_detection"]
    assert tax["precision"] == 0.5
    assert tax["recall"] == 0.5
    assert result["ground_truth_counts"]["tax_anomalies"] == 2