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
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from pipeline import run_pipeline

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "generated")


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

    # --- Overall ---
    total_correct = correct + (len(ledger_gt) - false_positives) + db_correct
    total_cases = (correct + wrong) + len(ledger_gt) + (db_correct + db_wrong)
    print(f"\n{'='*70}")
    print(f"OVERALL: {total_correct}/{total_cases} correct ({total_correct/total_cases*100:.1f}%)")
    print(f"LLM available this run: {result['llm_available']}")
    print(f"{'='*70}")


if __name__ == "__main__":
    evaluate()