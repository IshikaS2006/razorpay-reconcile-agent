"""
Saves a pipeline_output.json-shaped result dict into Postgres.
Also handles saving investigation results from the exception_investigator module.
"""
from datetime import datetime
import json
from models import BatchRun, Match, Exception_, Investigation


def save_run(db, result: dict) -> int:
    """
    result: the dict returned by run_pipeline() in pipeline.py
    Returns: the new run's id
    """
    summary = result["summary"]

    run = BatchRun(
        run_at=datetime.now(),
        llm_available=result["llm_available"],
        total_settlement_batches=summary["total_settlement_batches"],
        matched_batches=summary["matched_batches"],
        match_rate_pct=summary["match_rate_pct"],
        total_exceptions=summary["total_exceptions"],
        db_side_exceptions=summary["db_side_exceptions"],
        records_processed=summary["records_processed"],
        total_time_sec=summary["total_time_sec"],
        records_per_sec=summary["records_per_sec"],
        orders_available=result.get("order_reconciliation", {}).get("enabled", False),
    )
    db.add(run)
    db.flush()  # assigns run.id without committing yet

    for m in result["matches"]:
        db.add(Match(
            run_id=run.id,
            settlement_id=m.get("settlement_id"),
            settled_amount=m.get("settled_amount"),
            matched_entry_id=m.get("matched_entry_id"),
            tier=m.get("tier"),
            confidence=m.get("confidence"),
            reason=m.get("reason"),
            match_subtype=m.get("match_subtype"),
            expected_amount_paise=m.get("expected_amount_paise"),
            actual_amount_paise=m.get("actual_amount_paise"),
            amount_gap_paise=m.get("amount_gap_paise"),
        ))

    for e in result["exceptions"]:
        db.add(Exception_(
            run_id=run.id,
            source=e.get("source"),
            exception_type=e.get("exception_type"),
            reference_id=e.get("reference_id"),
            amount_paise=e.get("amount_paise"),
            detail=e.get("detail"),
            recommended_action=e.get("recommended_action"),
        ))

    db.commit()
    return run.id


def save_investigations(db, run_id: int, investigations: list) -> int:
    """
    Save investigation results to the investigations table.
    
    Args:
        db: SQLAlchemy session
        run_id: The batch run ID
        investigations: List of dicts from exception_investigator.investigate_run_exceptions()
    
    Returns: Count of saved investigations
    """
    investigated_at = datetime.utcnow()
    for inv in investigations:
        evidence = inv.get("evidence_used", inv.get("evidence_ids", []))
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                evidence = []
        db.add(Investigation(
            run_id=run_id,
            exception_reference_id=inv.get("exception_reference_id"),
            status=inv.get("status"),
            explanation=inv.get("explanation"),
            confidence=inv.get("confidence"),
            evidence_used=json.dumps(evidence or []),
            reasoning_chain=inv.get("reasoning_chain"),
            investigated_at=investigated_at,
        ))
    
    db.commit()
    return len(investigations)