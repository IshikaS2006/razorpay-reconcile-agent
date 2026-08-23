"""
Saves a pipeline_output.json-shaped result dict into Postgres.
"""
from datetime import datetime
from models import BatchRun, Match, Exception_


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
    )
    db.add(run)
    db.flush()  # assigns run.id without committing yet

    for m in result["matches"]:
        db.add(Match(
            run_id=run.id,
            settlement_id=m.get("settlement_id"),
            matched_entry_id=m.get("matched_entry_id"),
            tier=m.get("tier"),
            confidence=m.get("confidence"),
            reason=m.get("reason"),
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