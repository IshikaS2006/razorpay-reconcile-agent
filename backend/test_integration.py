#!/usr/bin/env python
"""
Integration test: Show that exception_investigator correctly:
1. Loads refund_dispute_log.csv
2. Finds related disputes by order_id and settlement_id
3. Calls LLM to explain exceptions
4. Classifies as "explained" or "escalated" based on confidence threshold
"""
import sys
import os
import json
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))

from exception_investigator import (
    load_dispute_log,
    find_related_disputes,
    investigate_run_exceptions,
)
from evaluate import score_result
from pipeline import run_pipeline
from auto_resolver import automatic_resolution_confirmed
from db_writer import save_investigations
from models import Investigation


def test_pipeline_accuracy():
    result = run_pipeline()
    scores = score_result(result)
    assert scores["bank_matching"]["match_rate"] >= 0.90
    assert scores["tax_anomaly_detection"]["recall"] == 1.0
    

def test_exception_investigator():
    data_base = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    dispute_log = load_dispute_log(data_base)
    assert not dispute_log.empty

    test_exceptions = [
        {
            "reference_id": "setl_100002RP",  # partial_refund batch
            "exception_type": "unresolved_settlement",
            "source": "bank_reconciliation",
            "amount_paise": 500000,
            "detail": "Settlement batch partially credited; refund suspected but not fully explained",
        },
        {
            "reference_id": "setl_100004RP",  # reference_mismatch batch
            "exception_type": "unresolved_settlement",
            "source": "bank_reconciliation",
            "amount_paise": 325000,
            "detail": "UTR present but reformatted in bank narration; unclear if it's the same transaction",
        },
        {
            "reference_id": "order_300008RP",  # phantom_charge
            "exception_type": "phantom_charge",
            "source": "db_reconciliation",
            "amount_paise": 750000,
            "detail": "Order marked as failed in internal DB but payment was captured and settled by Razorpay",
        },
    ]
    
    results = investigate_run_exceptions(
        run_id=0,  # test run
        exceptions=test_exceptions,
        llm_available=True,
        data_base=data_base,
    )
    
    assert len(results) == len(test_exceptions)
    assert all(0.0 <= result["confidence"] <= 1.0 for result in results)
    assert all(result["confidence"] is not None for result in results)
    assert all(result["reasoning_chain"] for result in results)


def test_investigation_recommendation_requires_human_review():
    investigation = Investigation(
        confidence=0.99,
        resolution_type=None,
        resolution_action="Open a Razorpay support ticket",
        investigated_at=datetime.utcnow(),
    )
    assert not automatic_resolution_confirmed(investigation)


def test_completed_automatic_resolution_is_confirmed():
    investigated_at = datetime.utcnow()
    investigation = Investigation(
        confidence=0.99,
        resolution_type="automatic_action_completion",
        resolution_action="Create confirmed GL posting",
        investigated_at=investigated_at,
        resolved_at=investigated_at + timedelta(seconds=1),
    )
    assert automatic_resolution_confirmed(investigation)
    assert investigation.resolved_at >= investigation.investigated_at


def test_investigation_evidence_and_timestamp_are_persisted():
    class CapturingSession:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)

        def commit(self):
            pass

    session = CapturingSession()
    save_investigations(session, 1, [{
        "exception_reference_id": "setl_100002RP",
        "status": "escalated",
        "confidence": 0.5,
        "evidence_used": ["DISP100001RP"],
        "reasoning_chain": "Evidence requires human review.",
    }])
    saved = session.items[0]
    assert json.loads(saved.evidence_used) == ["DISP100001RP"]
    assert saved.investigated_at is not None
    assert saved.resolved_at is None
