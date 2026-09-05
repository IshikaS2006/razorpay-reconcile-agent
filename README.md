# Reconcile — Track 04 AI Finance Controller

Reconcile is a Razorpay Buildathon submission for **Track 04: AI Finance Controller**.
It closes one finance-ops loop across a 50+ record batch of synthetic data:

- reconcile Razorpay settlements against a bank ledger
- cross-check with a third source: the merchant's internal order database
- report a measured match rate
- surface an honest exception list for what could not be safely resolved
- project forward cash position from the reconciled output
- answer follow-up questions with a grounded Q&A layer

This project is designed for the buildathon's stated bar: **throughput + measured accuracy + an honest exception list**. A demo that only shows a clean happy-path match is not enough.

## Why this fits Track 04

The brief says the bottleneck is **verification capacity, not generation speed**. That is exactly the problem this project attacks.

Finance teams still spend time manually:
- checking whether settlement credits actually landed
- tracing missing or duplicate-looking bank entries
- spotting phantom charges and ghost orders
- reviewing fee/GST anomalies
- estimating what cash is truly confirmed vs only expected

Reconcile automates the verification loop, but does **not** pretend every case can be auto-closed. When ambiguity remains, it returns evidence and a specific next step instead of silently guessing.

## What the agent does

### 1. Multi-source reconciliation
It compares three independent sources:
- `settlement_report.csv`
- `bank_ledger.csv`
- `orders_db.csv`

The third source matters because it catches issues a 2-source settlement-vs-bank workflow cannot see:
- **phantom charge**: money settled, but internal order state is failed/pending
- **ghost order**: internal order completed, but no real Razorpay settlement exists

### 2. Tiered matching engine
Matching is intentionally staged:
- **Tier 1 — exact**: reference/UTR, amount, date
- **Tier 2 — fuzzy**: amount tolerance, date window, narration/reference variation
- **Tier 3 — LLM-assisted**: only for genuine leftovers

The LLM is not allowed to blindly decide money movement. Any LLM-proposed settlement match must pass deterministic guardrails before acceptance.

### 3. Exception classification
For non-clean cases, the pipeline records:
- exception type
- source
- amount at stake
- evidence-grounded detail
- recommended next action

### 4. Reporting + dashboard
The UI shows:
- reconciliation runs
- match rate
- exceptions by type
- reconciled vs unresolved records
- investigation details
- forecast and cash-position views

### 5. Grounded Q&A assistant
The project includes a run-aware AI assistant that answers questions about:
- settlements
- exceptions
- unmatched amounts
- tax mismatches
- investigation history

It uses tool-style retrieval over stored run data and returns an audit trail of what was looked up.

### 6. Forward cash forecaster
The forecast layer uses persisted reconciliation runs to compute:
- confirmed cash
- projected inflows
- projected fee/outflow rows
- at-risk cash
- simple pattern-based backtesting

The model is intentionally naive and explainable rather than overfit.

## Architecture

```text
settlement_report.csv ─┐
bank_ledger.csv ───────┼─→ Tier 1 exact → Tier 2 fuzzy → Tier 3 LLM (leftovers only)
orders_db.csv ─────────┘            │                    │
                                    │                    └─ deterministic guardrail
                                    │
                                    ├─ DB reconciliation (phantom charge / ghost order)
                                    ├─ Tax-line verification
                                    ├─ Exception storage + investigation history
                                    ├─ Forecast aggregation + backtesting
                                    └─ FastAPI → React dashboard + Q&A assistant
```

## Current project highlights

As implemented in this codebase:
- exact + fuzzy settlement matching
- unrelated transaction filtering
- duplicate posting detection
- third-source DB reconciliation
- tax-line mismatch checks
- grounded exception investigation trail
- reconciliation dashboard
- chat-style run Q&A assistant
- explainable forward cash forecaster

## Tech stack

### Backend
- FastAPI
- SQLAlchemy
- Postgres / SQL database via `DATABASE_URL`
- Pandas
- Groq OpenAI-compatible chat API for LLM-assisted reasoning

### Frontend
- React
- Vite
- Axios
- Lucide icons

## Project structure

```text
backend/
  main.py                  FastAPI app
  pipeline.py              end-to-end reconciliation pipeline
  cash_forecaster.py       forecast aggregation and backtesting
  qa_layer.py              grounded Q&A layer
  db_writer.py             persistence for runs/investigations
  matching/
    matching_engine.py     exact + fuzzy matching
    llm_reasoning.py       Groq-based LLM reasoning
    db_reconciliation.py   order DB cross-checks
    tax_verification.py    fee/GST consistency checks
frontend/
  src/pages/               reconciliations, report, forecast pages
  src/components/          dashboard, table, chat assistant components
data/
  generated/               synthetic dataset used by the pipeline
```

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- A SQL database reachable via `DATABASE_URL`
- Optional: `GROQ_API_KEY` for LLM-assisted matching/investigation/Q&A

### Backend install

```bash
pip install -r requirements.txt
```

Create environment variables:

```env
DATABASE_URL=your_database_url
GROQ_API_KEY=your_groq_api_key
```

### Frontend install

```bash
cd frontend
npm install
```

## Running the project

### Start backend

```bash
python backend/init_db.py
python backend/main.py
```

If you run FastAPI through uvicorn instead:

```bash
uvicorn backend.main:app --reload
```

### Start frontend

```bash
cd frontend
npm run dev
```

## Typical demo flow

1. Open **New Reconciliation**
2. Upload / validate settlement + bank files
3. Run reconciliation
4. Open the generated run report
5. Show exact/fuzzy/LLM-assisted matching behavior
6. Click into unresolved exceptions
7. Show phantom charge / ghost order examples from the third source
8. Ask the assistant a grounded question
9. Open **Forecast** and show confirmed cash, projected inflows, at-risk cash, and backtesting

## Validation and evaluation

This project aims to make **measured** claims, not aesthetic claims.

There are two different ideas here:

### Reconciliation accuracy
The matching/evaluation side checks pipeline output against known synthetic ground truth.

### Forecast credibility
The forecast side now uses simple holdout-style backtesting so reported error is an honest projection error, not a circular self-comparison.

## Design principles

- deterministic rules first
- LLM only where ambiguity genuinely remains
- never trust LLM output on money without guardrails
- preserve an audit trail
- show unresolved exceptions honestly
- optimize for explainability in a live demo

## Why this is a strong buildathon submission

Track 04 is not asking for a generic chatbot on top of finance words.
It is asking for a system that can actually run part of the books and cash-position workflow.

This project does that by combining:
- operational throughput across a 50+ row batch
- a measured match rate
- third-source verification beyond a 2-source demo
- explicit exception handling
- explainable cash forecasting
- a grounded Q&A layer for finance follow-up

## Notes

- LLM-assisted features require `GROQ_API_KEY`
- without the key, deterministic reconciliation still runs
- some legacy demo copy/screens may still mention older metrics until all UI text is fully synchronized with the latest backend behavior

## Track

**Razorpay Buildathon 2026 — Track 04: AI Finance Controller**

Run the books. Own the cash position. Report the truth, including what the system could not resolve.
