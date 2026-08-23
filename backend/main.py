"""
FastAPI backend -- serves the reconciliation pipeline as a real API.

Endpoints:
  POST /run           -- runs the pipeline fresh, saves to DB, returns summary
  GET  /runs           -- list all past runs (id, timestamp, match rate)
  GET  /runs/{run_id}  -- full detail: summary + matches + exceptions
  GET  /runs/latest    -- convenience: full detail of the most recent run
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db import get_db
from models import BatchRun, Match, Exception_
from pipeline import run_pipeline
from db_writer import save_run

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
        "matched_entry_id": m.matched_entry_id,
        "tier": m.tier,
        "confidence": m.confidence,
        "reason": m.reason,
    }


def _exception_to_dict(e: Exception_):
    return {
        "source": e.source,
        "exception_type": e.exception_type,
        "reference_id": e.reference_id,
        "amount_paise": e.amount_paise,
        "detail": e.detail,
        "recommended_action": e.recommended_action,
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
    }


@app.post("/run")
def trigger_run(db: Session = Depends(get_db)):
    result = run_pipeline()
    run_id = save_run(db, result)
    run = db.query(BatchRun).filter(BatchRun.id == run_id).first()
    return _run_to_summary_dict(run)


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
    }