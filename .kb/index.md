# Knowledge Base Index

- `backend/matching/matching_engine.py` — Tier 1 (exact) + Tier 2 (fuzzy) bank matching, duplicate-posting detection
- `backend/matching/db_reconciliation.py` — third-source (order DB) check: phantom charges, ghost orders
- `backend/matching/tax_verification.py` — fee/GST line-item consistency check
- `backend/matching/llm_reasoning.py` — Groq LLM calls: Tier 3 resolution + action-recommendation drafting
- `backend/pipeline.py` — orchestrates all of the above into one consolidated run
- `backend/main.py` — FastAPI server (`POST /run`, `GET /runs/latest`, `GET /runs/{id}`)
- `backend/models.py` / `backend/db.py` / `backend/db_writer.py` — Postgres persistence layer
- `backend/evaluate.py` — checks pipeline output against self-generated ground truth
- `data/generate_data.py` — synthetic data generator (settlement report, bank ledger, order DB, all ground truth files, deliberate anomalies)
- `frontend/` — React dashboard

See `.kb/log.md` for the chronological decision/bug-fix history.