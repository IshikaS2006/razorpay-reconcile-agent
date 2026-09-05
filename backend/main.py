"""
FastAPI backend -- serves the reconciliation pipeline as a real API.

Endpoints:
  POST /run                   -- runs the pipeline fresh, saves to DB, returns summary
  GET  /runs                  -- list all past runs (id, timestamp, match rate)
  GET  /runs/{run_id}         -- full detail: summary + matches + exceptions
  GET  /runs/latest           -- convenience: full detail of the most recent run
  POST /investigate/{run_id}  -- investigate exceptions using refund_dispute_log + LLM
  POST /api/chat              -- tool-based natural-language Q&A about a run
  POST /ask                   -- legacy alias for /api/chat
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from datetime import datetime

from db import get_db
from models import BatchRun, Match, Exception_, Investigation
from pipeline import run_pipeline
from db_writer import save_run, save_investigations
from exception_investigator import investigate_run_exceptions
from qa_layer import answer_question
from cash_forecaster import compute_cash_forecast_timeseries, compute_cash_position
from auto_resolver import auto_resolve_run
from evaluate import build_accuracy_report

app = FastAPI(title="Reconcile API")


SCHEMA_MIGRATION_HINT = (
    "Database schema is behind the current backend code. "
    "Run `python backend/init_db.py` and then retry."
)


def _raise_if_schema_outdated(exc: Exception):
    message = str(getattr(exc, "orig", exc)).lower()
    if "undefinedcolumn" in message or "does not exist" in message:
        raise HTTPException(status_code=503, detail=SCHEMA_MIGRATION_HINT) from exc
    raise exc

# Allow the React dashboard (running on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for a hackathon demo; would restrict in real production
    allow_methods=["*"],
    allow_headers=["*"],
)


def _match_to_dict(m: Match):
    return {
        "settlement_id": m.settlement_id,
        "settled_amount": m.settled_amount,
        "matched_entry_id": m.matched_entry_id,
        "tier": m.tier,
        "confidence": m.confidence,
        "reason": m.reason,
        "match_subtype": getattr(m, "match_subtype", None),
        "expected_amount_paise": getattr(m, "expected_amount_paise", None),
        "actual_amount_paise": getattr(m, "actual_amount_paise", None),
        "amount_gap_paise": getattr(m, "amount_gap_paise", None),
        "status": m.status,
    }


def _exception_to_dict(e: Exception_, investigation=None):
    result = {
        "source": e.source,
        "exception_type": e.exception_type,
        "reference_id": e.reference_id,
        "amount_paise": e.amount_paise,
        "detail": e.detail,
        "recommended_action": e.recommended_action,
        "status": e.status,
    }
    if investigation:
        result["investigation"] = _investigation_to_dict(investigation)
    return result


def _investigation_to_dict(inv: Investigation):
    evidence_ids = _parse_evidence_ids(inv.evidence_used)
    return {
        "exception_reference_id": inv.exception_reference_id,
        "status": inv.status,
        "explanation": inv.explanation,
        "confidence": inv.confidence,
        "evidence_used": evidence_ids,
        "evidence_ids": evidence_ids,
        "reasoning_chain": inv.reasoning_chain,
        "investigated_at": inv.investigated_at.isoformat() if inv.investigated_at else None,
        "resolved_at": inv.resolved_at.isoformat() if inv.resolved_at else None,
        "resolution_type": inv.resolution_type,
        "resolution_action": inv.resolution_action,
    }


def _parse_evidence_ids(value):
    import json
    try:
        return json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []


def _run_to_summary_dict(r: BatchRun):
    return {
        "run_id": r.id,
        "run_at": r.run_at.isoformat() if r.run_at else None,
        "llm_available": r.llm_available,
        "total_settlement_batches": r.total_settlement_batches,
        "matched_batches": r.matched_batches,
        "match_rate_pct": r.match_rate_pct,
        "total_exceptions": r.total_exceptions,
        "db_side_exceptions": r.db_side_exceptions,
        "records_processed": r.records_processed,
        "total_time_sec": r.total_time_sec,
        "records_per_sec": r.records_per_sec,
        "orders_available": r.orders_available,
        "order_reconciliation": "enabled" if r.orders_available else "skipped_optional_source",
    }


def _investigations_by_reference(run):
    investigations = {}
    for investigation in run.investigations:
        investigations.setdefault(investigation.exception_reference_id, []).append(investigation)
    return investigations


def _run_to_detail_dict(run, resolution_summary=None):
    investigations = _investigations_by_reference(run)
    return {
        "summary": _run_to_summary_dict(run),
        "matches": [_match_to_dict(m) for m in run.matches],
        "exceptions": [
            _exception_to_dict(e, investigations.get(e.reference_id, [None])[-1])
            for e in run.exceptions
        ],
        "investigations": [
            _investigation_to_dict(investigation) for investigation in run.investigations
        ],
        "resolution_summary": resolution_summary,
    }


class QuestionRequest(BaseModel):
    question: str
    run_id: int


class ResolveRequest(BaseModel):
    reference_id: str
    action: str  # approve | reject | reviewed | escalate
    reason: str = ""
    actor: str = "Finance Manager"


@app.post("/run")
def trigger_run(db: Session = Depends(get_db)):
    try:
        result = run_pipeline()
        run_id = save_run(db, result)
        resolution_summary = auto_resolve_run(run_id, db)
        run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
        response = _run_to_summary_dict(run)
        response["resolution_summary"] = resolution_summary
        response["matches"] = [_match_to_dict(m) for m in run.matches]
        response["exceptions"] = [_exception_to_dict(e) for e in run.exceptions]
        response["investigations"] = []
        response["order_reconciliation"] = result.get("order_reconciliation")
        return response
    except ProgrammingError as exc:
        _raise_if_schema_outdated(exc)


@app.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(BatchRun).order_by(BatchRun.run_at.desc()).all()
    return [_run_to_summary_dict(r) for r in runs]


@app.get("/runs/latest")
def get_latest_run(db: Session = Depends(get_db)):
    run = db.query(BatchRun).order_by(BatchRun.run_at.desc()).first()
    if not run:
        raise HTTPException(status_code=404, detail="No runs yet -- POST /run first")
    return _run_to_detail_dict(run, auto_resolve_run(run.id, db))


@app.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_detail_dict(run, auto_resolve_run(run.id, db))


@app.get("/accuracy-report/{run_id}")
def get_accuracy_report(run_id: int, db: Session = Depends(get_db)):
    report = build_accuracy_report(run_id, db)
    if report is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return report


@app.post("/resolve/{run_id}")
def resolve_exception(run_id: int, req: ResolveRequest, db: Session = Depends(get_db)):
    """
    Record a human resolution decision for an exception.
    Creates an auditable event — the AI cannot silently change financial records.
    """
    run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    exception = db.query(Exception_).filter(
        Exception_.run_id == run_id,
        Exception_.reference_id == req.reference_id,
    ).first()
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found")

    action_map = {
        "approve": "resolved",
        "reject": "needs_human_review",
        "reviewed": "reviewed",
        "escalate": "escalated",
    }
    new_status = action_map.get(req.action)
    if not new_status:
        raise HTTPException(status_code=400, detail="Invalid action")

    prev_status = exception.status or "needs_human_review"
    exception.status = new_status

    investigation = db.query(Investigation).filter(
        Investigation.run_id == run_id,
        Investigation.exception_reference_id == req.reference_id,
    ).order_by(Investigation.investigated_at.desc()).first()

    resolved_at = datetime.utcnow()
    resolution_action = req.reason.strip() or req.action

    if investigation:
        investigation.status = new_status
        investigation.resolution_type = "manual_resolution"
        investigation.resolution_action = resolution_action
        investigation.resolved_at = resolved_at
        if not investigation.reasoning_chain:
            investigation.reasoning_chain = f"Manual {req.action} by {req.actor}"
        else:
            investigation.reasoning_chain = (
                f"{investigation.reasoning_chain}\n"
                f"Manual {req.action} by {req.actor}: {resolution_action}"
            )
    else:
        investigation = Investigation(
            run_id=run_id,
            exception_reference_id=req.reference_id,
            status=new_status,
            explanation=f"Manually {req.action}d by {req.actor}",
            confidence=1.0,
            evidence_used="[]",
            reasoning_chain=f"Manual {req.action} by {req.actor}: {resolution_action}",
            resolution_type="manual_resolution",
            resolution_action=resolution_action,
            resolved_at=resolved_at,
        )
        db.add(investigation)

    db.commit()
    db.refresh(investigation)

    return {
        "run_id": run_id,
        "reference_id": req.reference_id,
        "action": req.action,
        "actor": req.actor,
        "prev_status": prev_status,
        "new_status": new_status,
        "reason": resolution_action,
        "resolved_at": resolved_at.isoformat(),
        "investigation": _investigation_to_dict(investigation),
    }


@app.post("/investigate/{run_id}")
def investigate_run(run_id: int, db: Session = Depends(get_db)):
    """
    Investigate all exceptions in a run using refund_dispute_log.csv + LLM.
    
    For each exception:
    1. Cross-reference against refund_dispute_log.csv
    2. Call LLM to explain the exception with evidence
    3. Mark as "explained" (confidence >= 0.7) or "escalated" (confidence < 0.7)
    4. Save results to investigations table (audit trail)
    
    Returns: list of investigation results
    """
    # Load the run and its exceptions
    run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if not run.exceptions:
        resolution_summary = auto_resolve_run(run_id, db)
        return {
            "run_id": run_id,
            "investigations": [],
            "message": "No exceptions to investigate in this run",
            "resolution_summary": resolution_summary,
        }
    
    # Convert exceptions to dicts for the investigator
    exception_dicts = [_exception_to_dict(e) for e in run.exceptions]
    # But we also need the internal fields, so use raw ORM objects' attributes
    exception_dicts_full = [
        {
            "reference_id": e.reference_id,
            "exception_type": e.exception_type,
            "source": e.source,
            "amount_paise": e.amount_paise,
            "detail": e.detail,
        }
        for e in run.exceptions
    ]
    
    # Run investigation
    investigations = investigate_run_exceptions(
        run_id=run_id,
        exceptions=exception_dicts_full,
        llm_available=run.llm_available,
    )
    
    # Save investigations to DB
    saved_count = save_investigations(db, run_id, investigations)
    resolution_summary = auto_resolve_run(run_id, db)
    
    # Fetch fresh from DB to return (ensures we return what was actually saved)
    saved_investigations = db.query(Investigation).filter(
        Investigation.run_id == run_id
    ).all()
    
    return {
        "run_id": run_id,
        "investigations_count": saved_count,
        "investigations": [_investigation_to_dict(inv) for inv in saved_investigations],
        "resolution_summary": resolution_summary,
    }


@app.post("/api/chat")
@app.post("/ask")
def ask_question(req: QuestionRequest, db: Session = Depends(get_db)):
    """
    Answer natural language questions about a reconciliation run.
    
    Request: {question: str, run_id: int}
    Response: {answer: str, sources: [str], audit_trail: [..], tool_rounds: int}
    
    The system:
    1. Extracts entities (settlement_id, order_id, amounts) from the question
    2. Queries matches, exceptions, investigations tables for the run
    3. Passes question + retrieved data to LLM
    4. LLM answers only from provided data, citing source IDs
    
    Example questions:
      - "What happened to settlement setl_100002RP?"
      - "Why was order_300008RP flagged as a phantom charge?"
      - "How many exceptions are in this run?"
      - "Tell me about exceptions with amount ₹5000"
    """
    result = answer_question(
        question=req.question,
        run_id=req.run_id,
        db_session=db
    )
    return result


@app.get("/forecast/{run_id}")
def get_cash_forecast(run_id: int, db: Session = Depends(get_db)):
    try:
        result = compute_cash_position(run_id=run_id, db_session=db)
    except ProgrammingError as exc:
        _raise_if_schema_outdated(exc)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/cash-forecast/timeseries/{run_id}")
def get_cash_forecast_timeseries(run_id: int, db: Session = Depends(get_db)):
    try:
        result = compute_cash_forecast_timeseries(run_id=run_id, db_session=db)
    except ProgrammingError as exc:
        _raise_if_schema_outdated(exc)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
