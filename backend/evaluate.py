"""
Evaluation harness -- runs the FULL pipeline (all tiers, third source, LLM
reasoning, guardrails) and checks its output against the ground truth we
generated ourselves. This is what proves the "measured accuracy" claim --
not just reporting a match rate, but verifying it against known-correct answers.

Usage: python backend\\evaluate.py   (run from repo root, or anywhere --
paths are resolved relative to this file)
"""

import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from pipeline import run_pipeline

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "generated")


def _csv_or_empty(path, columns):
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=columns)


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0


def _precision_recall(true_positive, predicted, expected):
    return {
        "precision": _rate(true_positive, predicted),
        "recall": _rate(true_positive, expected),
    }


def _exception_metric(expected_ids, predicted_ids):
    expected_ids = set(expected_ids)
    predicted_ids = set(predicted_ids)
    correct = len(expected_ids & predicted_ids)
    return {
        "precision": _rate(correct, len(predicted_ids)),
        "recall": _rate(correct, len(expected_ids)),
        "correct": correct,
        "predicted": len(predicted_ids),
        "expected": len(expected_ids),
    }


def _evidence_ids(investigation):
    if not investigation:
        return []
    try:
        value = investigation.evidence_used
        return value if isinstance(value, list) else json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []


def score_result(result, data_dir=DATA_DIR):
    """Score a pipeline result against the generated ground-truth files."""
    matches = {m["settlement_id"]: m for m in result["matches"]}
    exceptions = result["exceptions"]
    exceptions_by_ref = {}
    for exception in exceptions:
        exceptions_by_ref.setdefault(exception["reference_id"], []).append(exception)

    gt = _csv_or_empty(os.path.join(data_dir, "ground_truth.csv"), ["settlement_id", "expected_match_type", "noise_type"])
    predicted_bank_matches = set(matches)
    if gt.empty:
        bank = {
            "status": "unavailable",
            "matches": len(predicted_bank_matches),
            "total_settlement_batches": result.get("summary", {}).get("total_settlement_batches", len(predicted_bank_matches)),
            "match_rate": None,
            "match_precision": None,
            "match_recall": None,
            "precision": None,
            "recall": None,
            "note": "ground_truth.csv not found; accuracy metrics unavailable for this run.",
        }
        expected_by_noise = {}
    else:
        expected_bank_matches = set(gt.loc[gt["expected_match_type"] != "exception", "settlement_id"])
        bank_true_positive = len(expected_bank_matches & predicted_bank_matches)
        bank = _precision_recall(bank_true_positive, len(predicted_bank_matches), len(expected_bank_matches))
        bank["status"] = "completed"
        bank["matches"] = bank_true_positive
        bank["total_settlement_batches"] = len(gt)
        bank["match_rate"] = _rate(len(predicted_bank_matches), len(gt))
        bank["match_precision"] = bank["precision"]
        bank["match_recall"] = bank["recall"]
        expected_by_noise = {
            noise: set(gt.loc[gt["noise_type"] == noise, "settlement_id"])
            for noise in gt["noise_type"].dropna().unique()
        }
    predicted_by_type = {}
    for exception in exceptions:
        predicted_by_type.setdefault(exception["exception_type"], set()).add(exception["reference_id"])
    gt_available = not gt.empty
    exception_detection = {
        "missing_bank_credit": {
            **_exception_metric(expected_by_noise.get("missing_in_ledger", set()),
                                predicted_by_type.get("unresolved_settlement", set())),
            "ground_truth_category": "missing_in_ledger",
            "status": "completed" if gt_available else "unavailable",
            "note": None if gt_available else "ground_truth.csv not found; missing-credit accuracy unavailable.",
        },
        "duplicate_bank_entry": {
            **_exception_metric(expected_by_noise.get("duplicate_entry", set()),
                                predicted_by_type.get("duplicate_posting", set())),
            "ground_truth_category": "duplicate_entry",
            "status": "completed" if gt_available else "unavailable",
            "note": None if gt_available else "ground_truth.csv not found; duplicate detection accuracy unavailable.",
        },
    }
    for noise in ("fee_deduction", "date_lag", "partial_refund", "reference_mismatch"):
        exception_detection[noise] = {
            "status": "detected_count_only",
            "ground_truth_count": len(expected_by_noise.get(noise, set())),
            "detected_count": 0,
            "note": "The matching result records these as matches, so no exception prediction is emitted.",
        }

    ledger_gt = _csv_or_empty(os.path.join(data_dir, "ledger_ground_truth.csv"), ["entry_id"])
    flagged_entry_ids = {
        e["reference_id"] for e in exceptions
        if e["exception_type"] == "unexplained_ledger_row"
    }
    ledger_entry_ids = set(ledger_gt["entry_id"]) if "entry_id" in ledger_gt.columns else set()
    unrelated_correct = len(ledger_gt) - len(ledger_entry_ids & flagged_entry_ids)

    orders_enabled = result.get("order_reconciliation", {}).get("enabled", False)
    order_gt = _csv_or_empty(os.path.join(data_dir, "order_ground_truth.csv"), ["order_id"])
    if orders_enabled and not order_gt.empty:
        expected_order_ids = set(order_gt["order_id"])
        predicted_order_ids = {
            e["reference_id"] for e in exceptions
            if e["source"] == "db_reconciliation"
            and e["exception_type"] in {"phantom_charge", "ghost_order"}
        }
        order_true_positive = len(expected_order_ids & predicted_order_ids)
        order_dimension = {
            "status": "completed",
            "accuracy": _rate(order_true_positive, len(order_gt)),
            "correct": order_true_positive,
            "total": len(order_gt),
        }
    else:
        order_dimension = {
            "status": "unavailable",
            "accuracy": None,
            "correct": 0,
            "total": 0,
            "note": "Orders DB / order_ground_truth.csv not supplied for this run.",
        }

    tax_path = os.path.join(data_dir, "tax_ground_truth.csv")
    tax_gt = _csv_or_empty(tax_path, ["entity_id"])
    expected_tax_ids = set(tax_gt["entity_id"])
    predicted_tax_ids = {
        e["reference_id"] for e in exceptions
        if e.get("source") == "tax_verification"
        and e["exception_type"] == "tax_line_mismatch"
    }
    tax_metric = {
        **_exception_metric(expected_tax_ids, predicted_tax_ids),
        "ground_truth_count": len(expected_tax_ids),
        "status": "completed" if len(expected_tax_ids) else "unavailable",
        "note": None if len(expected_tax_ids) else "tax_ground_truth.csv not found; tax anomaly accuracy unavailable.",
    }

    return {
        "bank_matching": bank,
        "ground_truth_counts": {
            "available": not gt.empty,
            "settlement_batches": len(gt),
            "by_noise_type": {noise: len(ids) for noise, ids in expected_by_noise.items()},
            "tax_anomalies": len(expected_tax_ids),
        },
        "exception_detection": exception_detection,
        "unrelated_ledger_filter": {
            "status": "completed" if not ledger_gt.empty else "unavailable",
            "accuracy": _rate(unrelated_correct, len(ledger_gt)) if len(ledger_gt) else None,
            "correctly_ignored": unrelated_correct if len(ledger_gt) else 0,
            "total": len(ledger_gt),
            "note": None if len(ledger_gt) else "ledger_ground_truth.csv not found; unrelated-ledger accuracy unavailable.",
        },
        "phantom_ghost_detection": order_dimension,
        "tax_anomaly_detection": tax_metric,
    }


def build_accuracy_report(run_id, db_session, data_dir=DATA_DIR):
    """Build an accuracy report from persisted run, match, exception, and investigation rows."""
    from models import BatchRun

    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return None

    result = {
        "summary": {
            "total_settlement_batches": run.total_settlement_batches or 0,
        },
        "matches": [{"settlement_id": m.settlement_id} for m in run.matches],
        "exceptions": [{
            "source": e.source,
            "exception_type": e.exception_type,
            "reference_id": e.reference_id,
        } for e in run.exceptions],
        "order_reconciliation": {"enabled": bool(run.orders_available)},
    }
    dimensions = score_result(result, data_dir)
    investigations_by_ref = {}
    for investigation in run.investigations:
        investigations_by_ref.setdefault(investigation.exception_reference_id, []).append(investigation)

    exception_list = []
    for exception in run.exceptions:
        investigations = investigations_by_ref.get(exception.reference_id, [])
        investigation = max(investigations, key=lambda item: item.confidence or 0, default=None)
        auto_resolved = exception.status == "auto_resolved"
        exception_list.append({
            "type": exception.exception_type,
            "source": exception.source,
            "reference_id": exception.reference_id,
            "status": exception.status or "needs_human_review",
            "auto_resolved": auto_resolved,
            "llm_investigated": investigation is not None,
            "confidence": investigation.confidence if investigation else None,
            "evidence_ids": _evidence_ids(investigation),
            "reason": (
                investigation.reasoning_chain if investigation and not auto_resolved
                else exception.detail
            ),
        })

    auto_resolved_count = sum(item["auto_resolved"] for item in exception_list)
    human_review_count = sum(item["status"] == "needs_human_review" for item in exception_list)
    total_exceptions = len(exception_list)
    unresolved_settlement_count = sum(item["type"] == "unresolved_settlement" for item in exception_list)
    duplicate_posting_count = sum(item["type"] == "duplicate_posting" for item in exception_list)
    refund_exception_count = sum(item["type"] in {"refund_not_debited", "unexplained_debit"} for item in exception_list)
    tax_exception_count = sum(item["type"] == "tax_line_mismatch" for item in exception_list)
    partial_credit_count = sum(
        1 for match in run.matches
        if getattr(match, "match_subtype", None) == "settlement_partial_credit"
    )
    exact_match_count = sum(1 for match in run.matches if str(match.tier).lower() == "exact")
    fuzzy_match_count = sum(1 for match in run.matches if str(match.tier).lower() == "fuzzy")

    return {
        "run_id": run.id,
        "overall_match_rate": {
            "matches": run.matched_batches or 0,
            "total_settlement_batches": run.total_settlement_batches or 0,
            "rate": _rate(run.matched_batches or 0, run.total_settlement_batches or 0),
        },
        "dimensions": dimensions,
        "exceptions": exception_list,
        "throughput": {
            "total_records_processed": run.records_processed or 0,
            "total_time_sec": run.total_time_sec or 0.0,
            "records_per_sec": run.records_per_sec or 0.0,
        },
        "resolution": {
            "auto_resolved_count": auto_resolved_count,
            "auto_resolved_rate_pct": _rate(auto_resolved_count, total_exceptions) * 100,
            "human_review_count": human_review_count,
            "unresolved_count": human_review_count,
            "total_exceptions": total_exceptions,
        },
        "matching": {
            "status": "completed",
            "matched_records": run.matched_batches or 0,
            "total_records": run.total_settlement_batches or 0,
            "match_rate_pct": _rate(run.matched_batches or 0, run.total_settlement_batches or 0) * 100,
            "note": dimensions["bank_matching"].get("note"),
        },
        "live_metrics": {
            "exact_match_count": exact_match_count,
            "fuzzy_match_count": fuzzy_match_count,
            "partial_credit_count": partial_credit_count,
            "unresolved_settlement_count": unresolved_settlement_count,
            "duplicate_posting_count": duplicate_posting_count,
            "refund_exception_count": refund_exception_count,
            "tax_exception_count": tax_exception_count,
            "review_queue_count": human_review_count,
        },
    }


def evaluate():
    result = run_pipeline()
    report = score_result({
        "summary": result.get("summary", {}),
        "matches": result.get("matches", []),
        "exceptions": result.get("exceptions", []),
        "order_reconciliation": result.get("order_reconciliation", {}),
    })

    print("=" * 70)
    print("EVALUATION")
    print("=" * 70)
    print(json.dumps(report, indent=2))
    print(f"LLM available this run: {result['llm_available']}")


if __name__ == "__main__":
    evaluate()