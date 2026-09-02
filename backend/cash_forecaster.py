"""Transparent cash-position projection for a completed reconciliation run."""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import BatchRun, Exception_, Investigation, Match


AT_RISK_BUCKETS = ("phantom_charge", "ghost_order", "low_confidence_investigation")


def _amount(value: Optional[int]) -> int:
    return int(value or 0)


def _exception_item(exception: Exception_) -> Dict:
    return {
        "id": f"exception_{exception.id}",
        "reference_id": exception.reference_id,
        "amount_paise": _amount(exception.amount_paise),
        "recommended_next_step": exception.recommended_action,
    }


def _top_items(items: List[Dict]) -> List[Dict]:
    return sorted(items, key=lambda item: -item["amount_paise"])[:3]


def compute_cash_position(run_id: int, db_session: Session) -> Dict:
    """Return a traceable cash snapshot made only from one run's stored rows."""
    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found"}

    matches = db_session.query(Match).filter(Match.run_id == run_id).all()
    exceptions = db_session.query(Exception_).filter(Exception_.run_id == run_id).all()
    investigations = db_session.query(Investigation).filter(Investigation.run_id == run_id).all()

    confirmed_total = sum(_amount(match.settled_amount) for match in matches)
    exceptions_by_reference = {exception.reference_id: exception for exception in exceptions}

    bucket_items = {bucket: [] for bucket in AT_RISK_BUCKETS}
    for exception in exceptions:
        if exception.exception_type in ("phantom_charge", "ghost_order"):
            bucket_items[exception.exception_type].append(_exception_item(exception))

    for investigation in investigations:
        if investigation.confidence is not None and investigation.confidence < 0.7:
            exception = exceptions_by_reference.get(investigation.exception_reference_id)
            if exception is None:
                continue
            item = _exception_item(exception)
            item["id"] = f"investigation_{investigation.id}"
            item["investigation_id"] = investigation.id
            item["investigation_confidence"] = investigation.confidence
            bucket_items["low_confidence_investigation"].append(item)

    breakdown = []
    recommended_next_steps = []
    for bucket in AT_RISK_BUCKETS:
        top_items = _top_items(bucket_items[bucket])
        bucket_total = sum(item["amount_paise"] for item in bucket_items[bucket])
        breakdown.append({
            "bucket": bucket,
            "total_paise": bucket_total,
            "top_items": top_items,
        })
        for item in top_items:
            recommended_next_steps.append({
                "bucket": bucket,
                "source_id": item["id"],
                "reference_id": item["reference_id"],
                "amount_paise": item["amount_paise"],
                "action": item["recommended_next_step"],
            })

    at_risk_total = sum(bucket["total_paise"] for bucket in breakdown)
    recommended_next_steps.sort(key=lambda item: -item["amount_paise"])

    return {
        "confirmed_total": confirmed_total,
        "at_risk_total": at_risk_total,
        "at_risk_breakdown": breakdown,
        "recommended_next_steps": recommended_next_steps,
    }
