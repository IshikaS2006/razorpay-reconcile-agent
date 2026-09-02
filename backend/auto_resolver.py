"""Deterministic post-processing for automatic reconciliation resolution."""

from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from models import BatchRun, Exception_, Investigation, Match, GLPosting

CONFIDENCE_THRESHOLD = 0.7


def automatic_resolution_confirmed(investigation: Investigation) -> bool:
    """Only treat an investigation as automatic when an action was confirmed."""
    return (
        investigation.resolution_type == "automatic_action_completion"
        and bool(investigation.resolution_action)
        and investigation.resolved_at is not None
        and investigation.investigated_at is not None
        and investigation.resolved_at >= investigation.investigated_at
    )


def _resolution_summary(auto_reconciled: int, auto_resolved: int, needs_human_review: int) -> Dict:
    total = auto_reconciled + auto_resolved + needs_human_review
    closed = auto_reconciled + auto_resolved
    return {
        "auto_reconciled_count": auto_reconciled,
        "auto_resolved_count": auto_resolved,
        "needs_human_review_count": needs_human_review,
        "auto_close_rate_pct": round(closed / total * 100, 1) if total else 0.0,
    }


def auto_resolve_run(run_id: int, db_session: Session) -> Dict:
    """Apply deterministic statuses and simulated GL postings for one run."""
    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return _resolution_summary(0, 0, 0)

    matches = db_session.query(Match).filter(Match.run_id == run_id).all()
    exceptions = db_session.query(Exception_).filter(Exception_.run_id == run_id).all()
    investigations = db_session.query(Investigation).filter(Investigation.run_id == run_id).all()

    auto_reconciled = 0
    for match in matches:
        if match.tier in ("exact", "fuzzy"):
            match.status = "auto_reconciled"
            auto_reconciled += 1
            existing_posting = db_session.query(GLPosting).filter(
                GLPosting.run_id == run_id,
                GLPosting.entry_id == match.matched_entry_id,
            ).first()
            if existing_posting is None:
                db_session.add(GLPosting(
                    run_id=run_id,
                    entry_id=match.matched_entry_id,
                    settlement_id=match.settlement_id,
                    debit=0,
                    credit=match.settled_amount or 0,
                    posted_at=datetime.utcnow(),
                ))
        else:
            match.status = "needs_human_review"

    investigations_by_reference = {}
    for investigation in investigations:
        investigations_by_reference.setdefault(investigation.exception_reference_id, []).append(investigation)

    auto_resolved = 0
    needs_human_review = 0
    for exception in exceptions:
        related = investigations_by_reference.get(exception.reference_id, [])
        qualifying = [
            investigation for investigation in related
            if investigation.confidence is not None
            and investigation.confidence >= CONFIDENCE_THRESHOLD
            and automatic_resolution_confirmed(investigation)
        ]
        if qualifying:
            investigation = max(qualifying, key=lambda item: item.confidence)
            exception.status = "auto_resolved"
            investigation.status = "auto_resolved"
            auto_resolved += 1
        else:
            exception.status = "needs_human_review"
            needs_human_review += 1
            for investigation in related:
                investigation.status = "needs_human_review"

    summary = _resolution_summary(auto_reconciled, auto_resolved, needs_human_review)
    db_session.commit()
    return summary
