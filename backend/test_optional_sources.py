import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pipeline
from pipeline import run_pipeline


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "generated")


def _copy_core_files(destination):
    os.makedirs(destination, exist_ok=True)
    for filename in ("settlement_report.csv", "bank_ledger.csv"):
        shutil.copy(os.path.join(DATA_DIR, filename), os.path.join(destination, filename))


def test_core_pipeline_runs_without_orders_db(tmp_path):
    _copy_core_files(tmp_path)

    previous_llm_available = pipeline.LLM_AVAILABLE
    pipeline.LLM_AVAILABLE = False
    try:
        result = run_pipeline(str(tmp_path))
    finally:
        pipeline.LLM_AVAILABLE = previous_llm_available

    assert result["order_reconciliation"]["status"] == "skipped_optional_source"
    assert not any(exception["source"] == "db_reconciliation" for exception in result["exceptions"])
    assert result["summary"]["matched_batches"] > 0


def test_orders_db_enables_optional_enrichment(tmp_path):
    _copy_core_files(tmp_path)
    shutil.copy(os.path.join(DATA_DIR, "orders_db.csv"), os.path.join(tmp_path, "orders_db.csv"))

    previous_llm_available = pipeline.LLM_AVAILABLE
    pipeline.LLM_AVAILABLE = False
    try:
        result = run_pipeline(str(tmp_path))
    finally:
        pipeline.LLM_AVAILABLE = previous_llm_available

    assert result["order_reconciliation"]["enabled"] is True
    assert any(exception["source"] == "db_reconciliation" for exception in result["exceptions"])