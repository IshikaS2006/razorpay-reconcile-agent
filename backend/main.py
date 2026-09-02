"""
FastAPI backend -- serves the reconciliation pipeline as a real API.

Endpoints:
  POST /run                   -- runs the pipeline fresh, saves to DB, returns summary
  GET  /runs                   -- list all past runs (id, timestamp, match rate)
  GET  /runs/{run_id}          -- full detail: summary + matches + exceptions
  GET  /runs/latest            -- convenience: full detail of the most recent run
  POST /investigate/{run_id}   -- investigate exceptions using refund_dispute_log + LLM
  POST /ask                    -- answer natural language questions about a run
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models import BatchRun, Match, Exception_, Investigation
from pipeline import run_pipeline
from db_writer import save_run, save_investigations
from exception_investigator import investigate_run_exceptions
from qa_layer import answer_question
from cash_forecaster import compute_cash_position
from auto_resolver import auto_resolve_run

app = FastAPI(title="Reconcile API")

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
        "status": m.status,
    }


def _exception_to_dict(e: Exception_):
    return {
        "source": e.source,
        "exception_type": e.exception_type,
        "reference_id": e.reference_id,
        "amount_paise": e.amount_paise,
        "detail": e.detail,
        "recommended_action": e.recommended_action,
        "status": e.status,
    }


def _investigation_to_dict(inv: Investigation):
    return {
        "exception_reference_id": inv.exception_reference_id,
        "status": inv.status,
        "explanation": inv.explanation,
        "confidence": inv.confidence,
        "evidence_used": inv.evidence_used,
        "reasoning_chain": inv.reasoning_chain,
        "investigated_at": inv.investigated_at.isoformat() if inv.investigated_at else None,
        "resolved_at": inv.resolved_at.isoformat() if inv.resolved_at else None,
        "resolution_type": inv.resolution_type,
        "resolution_action": inv.resolution_action,
    }


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
    }


class QuestionRequest(BaseModel):
    question: str
    run_id: int


@app.post("/run")
def trigger_run(db: Session = Depends(get_db)):
    result = run_pipeline()
    run_id = save_run(db, result)
    resolution_summary = auto_resolve_run(run_id, db)
    run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
    response = _run_to_summary_dict(run)
    response["resolution_summary"] = resolution_summary
    return response


@app.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(BatchRun).order_by(BatchRun.run_at.desc()).all()
    return [_run_to_summary_dict(r) for r in runs]


@app.get("/runs/latest")
def get_latest_run(db: Session = Depends(get_db)):
    run = db.query(BatchRun).order_by(BatchRun.run_at.desc()).first()
    if not run:
        raise HTTPException(status_code=404, detail="No runs yet -- POST /run first")
    return {
        "summary": _run_to_summary_dict(run),
        "matches": [_match_to_dict(m) for m in run.matches],
        "exceptions": [_exception_to_dict(e) for e in run.exceptions],
        "resolution_summary": auto_resolve_run(run.id, db),
    }


@app.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "summary": _run_to_summary_dict(run),
        "matches": [_match_to_dict(m) for m in run.matches],
        "exceptions": [_exception_to_dict(e) for e in run.exceptions],
        "resolution_summary": auto_resolve_run(run.id, db),
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


@app.post("/ask")
def ask_question(req: QuestionRequest, db: Session = Depends(get_db)):
    """
    Answer natural language questions about a reconciliation run.
    
    Request: {question: str, run_id: int}
    Response: {answer: str, sources: [str]}
    
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
    result = compute_cash_position(run_id=run_id, db_session=db)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result