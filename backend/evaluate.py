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


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0


def _precision_recall(true_positive, predicted, expected):
    return {
        "precision": _rate(true_positive, predicted),
        "recall": _rate(true_positive, expected),
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

    gt = pd.read_csv(os.path.join(data_dir, "ground_truth.csv"))
    expected_bank_matches = set(gt.loc[gt["expected_match_type"] != "exception", "settlement_id"])
    predicted_bank_matches = set(matches)
    bank_true_positive = len(expected_bank_matches & predicted_bank_matches)
    bank = _precision_recall(bank_true_positive, len(predicted_bank_matches), len(expected_bank_matches))
    bank["matches"] = bank_true_positive
    bank["total_settlement_batches"] = len(gt)
    bank["match_rate"] = _rate(len(predicted_bank_matches), len(gt))

    ledger_gt = pd.read_csv(os.path.join(data_dir, "ledger_ground_truth.csv"))
    flagged_entry_ids = {
        e["reference_id"] for e in exceptions
        if e["exception_type"] == "unexplained_ledger_row"
    }
    unrelated_correct = len(ledger_gt) - len(set(ledger_gt["entry_id"]) & flagged_entry_ids)

    order_gt = pd.read_csv(os.path.join(data_dir, "order_ground_truth.csv"))
    expected_order_ids = set(order_gt["order_id"])
    predicted_order_ids = {
        e["reference_id"] for e in exceptions
        if e["source"] == "db_reconciliation"
        and e["exception_type"] in {"phantom_charge", "ghost_order"}
    }
    order_true_positive = len(expected_order_ids & predicted_order_ids)

    tax_gt = pd.read_csv(os.path.join(data_dir, "tax_ground_truth.csv"))
    expected_tax_ids = set(tax_gt["entity_id"])
    predicted_tax_ids = {
        e["reference_id"] for e in exceptions
        if e["source"] == "tax_verification"
        and e["exception_type"] == "tax_line_mismatch"
    }
    tax_true_positive = len(expected_tax_ids & predicted_tax_ids)

    return {
        "bank_matching": bank,
        "unrelated_ledger_filter": {
            "accuracy": _rate(unrelated_correct, len(ledger_gt)),
            "correctly_ignored": unrelated_correct,
            "total": len(ledger_gt),
        },
        "phantom_ghost_detection": {
            "accuracy": _rate(order_true_positive, len(order_gt)),
            "correct": order_true_positive,
            "total": len(order_gt),
        },
        "tax_anomaly_detection": {
            **_precision_recall(tax_true_positive, len(predicted_tax_ids), len(expected_tax_ids)),
            "correct": tax_true_positive,
            "total": len(expected_tax_ids),
        },
    }


def build_accuracy_report(run_id, db_session, data_dir=DATA_DIR):
    """Build an accuracy report from persisted run, match, exception, and investigation rows."""
    from models import BatchRun

    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return None

    result = {
        "matches": [{"settlement_id": m.settlement_id} for m in run.matches],
        "exceptions": [{
            "source": e.source,
            "exception_type": e.exception_type,
            "reference_id": e.reference_id,
        } for e in run.exceptions],
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
    }


def evaluate():
    result = run_pipeline()
    matches = {m["settlement_id"]: m for m in result["matches"]}
    exceptions_by_ref = {}
    for e in result["exceptions"]:
        exceptions_by_ref.setdefault(e["reference_id"], []).append(e)

    print("=" * 70)
    print("EVALUATION -- checking pipeline output against known ground truth")
    print("=" * 70)

    # --- 1. Bank-side batch-level accuracy ---
    gt = pd.read_csv(os.path.join(DATA_DIR, "ground_truth.csv"))
    correct, wrong, wrong_details = 0, 0, []

    for _, row in gt.iterrows():
        sid = row["settlement_id"]
        expected = row["expected_match_type"]
        got_match = matches.get(sid)
        got_exceptions = exceptions_by_ref.get(sid, [])

        if expected == "exception":
            # Special case: a "duplicate_entry" ground-truth case is correctly handled
            # if EITHER it's left unmatched, OR it's matched but a duplicate_posting
            # warning was also raised for it -- both are valid, honest outcomes.
            if row["noise_type"] == "duplicate_entry" and got_match is not None:
                has_dup_warning = any(e["exception_type"] == "duplicate_posting" for e in got_exceptions)
                is_correct = has_dup_warning
            else:
                is_correct = got_match is None
        else:
            is_correct = got_match is not None

        if is_correct:
            correct += 1
        else:
            wrong += 1
            wrong_details.append({
                "settlement_id": sid, "noise_type": row["noise_type"],
                "expected": expected,
                "got": f"matched to {got_match['matched_entry_id']}" if got_match else "left as exception",
            })

    print(f"\n[1] BANK-SIDE BATCH MATCHING")
    print(f"    {correct}/{correct+wrong} correct ({correct/(correct+wrong)*100:.1f}%)")
    for w in wrong_details:
        print(f"    WRONG: {w['settlement_id']} ({w['noise_type']}) -- expected {w['expected']}, got {w['got']}")

    # --- 2. Unrelated-ledger-row filtering accuracy ---
    ledger_gt = pd.read_csv(os.path.join(DATA_DIR, "ledger_ground_truth.csv"))
    flagged_entry_ids = set()
    for e in result["exceptions"]:
        if e["exception_type"] == "unexplained_ledger_row":
            flagged_entry_ids.add(e["reference_id"])
        if e["exception_type"] == "duplicate_posting":
            pass  # duplicates are a separate, legitimate category

    false_positives = 0
    for _, row in ledger_gt.iterrows():
        if row["entry_id"] in flagged_entry_ids:
            false_positives += 1

    print(f"\n[2] UNRELATED-TRANSACTION FILTERING")
    print(f"    {len(ledger_gt) - false_positives}/{len(ledger_gt)} correctly ignored "
          f"({(len(ledger_gt)-false_positives)/len(ledger_gt)*100:.1f}%)")
    if false_positives:
        print(f"    {false_positives} unrelated transaction(s) incorrectly flagged as exceptions")

    # --- 3. Third-source (DB reconciliation) accuracy ---
    order_gt = pd.read_csv(os.path.join(DATA_DIR, "order_ground_truth.csv"))
    db_correct, db_wrong = 0, 0
    for _, row in order_gt.iterrows():
        oid = row["order_id"]
        expected_type = row["exception_type"]
        got = exceptions_by_ref.get(oid, [])
        got_types = [e["exception_type"] for e in got]
        if expected_type in got_types:
            db_correct += 1
        else:
            db_wrong += 1
            print(f"    WRONG: {oid} -- expected '{expected_type}', got {got_types or 'nothing'}")

    print(f"\n[3] THIRD-SOURCE (ORDER DB) RECONCILIATION")
    print(f"    {db_correct}/{db_correct+db_wrong} correct ({db_correct/(db_correct+db_wrong)*100:.1f}%)")

    # --- 4. Tax anomaly detection accuracy ---
    tax_gt = pd.read_csv(os.path.join(DATA_DIR, "tax_ground_truth.csv"))
    expected_tax_ids = set(tax_gt["entity_id"])
    predicted_tax_ids = {
        e["reference_id"] for e in result["exceptions"]
        if e["source"] == "tax_verification" and e["exception_type"] == "tax_line_mismatch"
    }
    tax_true_positive = len(expected_tax_ids & predicted_tax_ids)
    tax_scores = _precision_recall(tax_true_positive, len(predicted_tax_ids), len(expected_tax_ids))
    print(f"\n[4] TAX ANOMALY DETECTION")
    print(f"    Precision: {tax_scores['precision']*100:.1f}% ({tax_true_positive}/{len(predicted_tax_ids) or 0})")
    print(f"    Recall:    {tax_scores['recall']*100:.1f}% ({tax_true_positive}/{len(expected_tax_ids)})")

    # --- Overall ---
    total_correct = correct + (len(ledger_gt) - false_positives) + db_correct + tax_true_positive
    total_cases = (correct + wrong) + len(ledger_gt) + (db_correct + db_wrong) + len(expected_tax_ids)
    print(f"\n{'='*70}")
    print(f"OVERALL: {total_correct}/{total_cases} correct ({total_correct/total_cases*100:.1f}%)")
    print(f"LLM available this run: {result['llm_available']}")
    print(f"{'='*70}")


if __name__ == "__main__":
    evaluate()