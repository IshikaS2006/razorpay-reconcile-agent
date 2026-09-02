# Exception Investigator — Post-Pipeline Investigation Module

## Overview

The **Exception Investigator** is a post-pipeline module that augments Reconcile's exception list with evidence-grounded explanations using cross-reference matching + LLM reasoning.

**Architecture:**
```
Pipeline Output (exceptions)
          ↓
   [Load disputes from refund_dispute_log.csv]
          ↓
   [For each exception: find related disputes by order_id or settlement_id]
          ↓
   [Call Groq LLM to explain exception with matched evidence]
          ↓
   [Mark "explained" (confidence ≥ 0.7) or "escalated" (confidence < 0.7)]
          ↓
   [Persist to investigations table (audit trail)]
```

## Key Design Decisions

### 1. **Deterministic Evidence Matching**
Disputes are matched by:
- `related_order_id` ← used if exception reference_id is an order (e.g., `order_123RP`)
- `related_settlement_id` ← used if exception reference_id is a settlement (e.g., `setl_456RP`)

No fuzzy matching; exact string equality only. This prevents false correlations.

### 2. **Groq LLM with Confidence Scoring**
The LLM is asked to:
1. Explain the exception using **only the provided evidence** (matched disputes + exception detail)
2. Score confidence 0–1:
   - **0.9–1.0:** Clear explanation; evidence directly supports it
   - **0.7–0.8:** Reasonable explanation; some gaps but plausible
   - **0.4–0.6:** Partial explanation; significant uncertainty
   - **0.0–0.3:** Cannot explain with available evidence

**Threshold:** Only exceptions with confidence ≥ 0.7 are marked "explained"; others remain "escalated" for human review.

### 3. **Audit Trail via investigations Table**
Every investigation result is persisted in the `investigations` table with:
- `exception_reference_id` — link to the original exception
- `status` — "explained" or "escalated"
- `explanation` — LLM's plain-language reasoning
- `confidence` — 0–1 score
- `evidence_used` — JSON array of dispute log IDs found
- `reasoning_chain` — full LLM reasoning for traceability
- `investigated_at` — timestamp

This doubles as both a result store and a reasoning audit trail for compliance/debugging.

## Data Source Integration

The investigator cross-references against **refund_dispute_log.csv**, which contains:
- `log_id` (PK)
- `related_order_id` — the order this dispute is about (links to orders_db.csv)
- `related_settlement_id` — the settlement this dispute is about (links to settlement_report.csv)
- `type` — "refund", "dispute", or "chargeback"
- `amount` — dispute amount in paise
- `status` — "initiated", "completed", "rejected"
- `created_at` — timestamp
- `notes` — human-readable description

**Example correlation:**
```
Exception: setl_100002RP (partial_refund, missing ₹5,000)
Matched dispute: DISP100001RP (refund of ₹6,016.97 for the same settlement)
LLM explanation: "The settlement batch credited only ₹5,000 while a refund of 
                  ₹6,016.97 was initiated, indicating a partial refund scenario."
Confidence: 0.75 (explained)
```

## API Endpoint

### **POST /investigate/{run_id}**

Investigate all exceptions in a completed run.

**Request:**
```bash
curl -X POST http://localhost:8000/investigate/1
```

**Response:**
```json
{
  "run_id": 1,
  "investigations_count": 10,
  "investigations": [
    {
      "exception_reference_id": "setl_100002RP",
      "status": "explained",
      "explanation": "The settlement batch credited only ₹5,000 while a refund...",
      "confidence": 0.75,
      "evidence_used": "[\"DISP100001RP\"]",
      "reasoning_chain": "Evidence found: 1 disputes. LLM reasoning: ...",
      "investigated_at": "2026-08-10T14:32:18.123456"
    },
    {
      "exception_reference_id": "order_300008RP",
      "status": "escalated",
      "explanation": "No related disputes found in log...",
      "confidence": 0.0,
      "evidence_used": "[]",
      "reasoning_chain": "No evidence or LLM reasoning available.",
      "investigated_at": "2026-08-10T14:32:19.654321"
    },
    ...
  ]
}
```

## Code Structure

### **backend/exception_investigator.py**
Main investigator module with:
- `load_dispute_log(base)` — Load refund_dispute_log.csv
- `find_related_disputes(exception_ref, dispute_log)` — Find disputes by order/settlement ID
- `draft_investigation_prompt(exception, related_disputes)` — Build LLM prompt
- `investigate_exception(exception, dispute_log)` — Investigate single exception
- `investigate_run_exceptions(run_id, exceptions, llm_available, data_base)` — Main entry point

### **backend/models.py**
SQLAlchemy ORM model:
```python
class Investigation(Base):
    __tablename__ = "investigations"
    
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("batch_runs.id"))
    exception_reference_id = Column(String)
    status = Column(String)  # "explained" or "escalated"
    explanation = Column(Text)
    confidence = Column(Float)  # 0-1
    evidence_used = Column(Text)  # JSON array
    reasoning_chain = Column(Text)
    investigated_at = Column(DateTime, default=datetime.utcnow)
    
    run = relationship("BatchRun", back_populates="investigations")
```

### **backend/db_writer.py**
Helper function:
```python
def save_investigations(db, run_id: int, investigations: list) -> int:
    """Save investigation results to the investigations table."""
    ...
```

### **backend/main.py**
New endpoint wired in:
```python
@app.post("/investigate/{run_id}")
def investigate_run(run_id: int, db: Session = Depends(get_db)):
    """Investigate all exceptions in a run using refund_dispute_log + LLM."""
    ...
```

## Workflow Example

1. **User runs the reconciliation pipeline:**
   ```bash
   POST /run
   ```
   → Returns run_id=1, match_rate_pct=95%, total_exceptions=10

2. **User fetches run details:**
   ```bash
   GET /runs/1
   ```
   → Shows summary + 10 unresolved exceptions

3. **User starts investigation:**
   ```bash
   POST /investigate/1
   ```
   → Investigator loads disputes, calls LLM, saves results to DB

4. **User views investigation results:**
   ```bash
   GET /runs/1
   ```
   → API now includes investigations in response (related by run_id)

## Testing

### Unit Test: Test Investigation Module
```bash
cd backend
python exception_investigator.py
```

Output:
```
Investigation Results:
====================
Reference: setl_100002RP
Status: explained (confidence 0.75)
Explanation: The ₹5,000 settlement gap likely arises because...
```

### Integration Test: Full Pipeline + Investigation
```bash
python test_integration.py
```

Output:
```
INTEGRATION TEST: Exception Investigator with Refund Dispute Log
=================================================================

1. Loading refund_dispute_log.csv...
   Loaded 7 dispute entries

2. Dispute log summary:
   - Refunds: 3
   - Disputes: 0
   - Chargebacks: 4

3. Creating sample exceptions for investigation...
4. Running exception investigation (using LLM + dispute log)...

INVESTIGATION RESULTS:
======================
Summary:
  Total exceptions investigated: 3
  Explained (confidence >= 0.7): 3
  Escalated (confidence < 0.7):  0
  Average confidence: 0.77

Detailed Results:
1. Exception: setl_100002RP
   Status: EXPLAINED (confidence 0.75)
   Evidence: ["DISP100001RP"]
   ...
```

## Deployment

### Prerequisites
- `GROQ_API_KEY` environment variable set (for LLM calls)
- `DATABASE_URL` environment variable set (for DB persistence)
- refund_dispute_log.csv in `data/generated/` directory

### Database Migration
On first run, SQLAlchemy auto-creates the `investigations` table via:
```bash
python backend/init_db.py
```

### API Server
```bash
python -m uvicorn backend.main:app --reload
```

Then:
```bash
curl -X POST http://localhost:8000/investigate/1
```

## Behavior When Evidence Is Sparse

- **No disputes found + LLM unavailable:** Marked "escalated" with confidence 0.0
- **No disputes found + LLM available:** Still investigated; LLM may provide reasoning based on exception detail alone (confidence typically 0.3–0.5)
- **Disputes found + LLM unavailable:** Marked "escalated" with confidence 0.5 (evidence presence alone)
- **Disputes found + LLM available:** Full investigation; confidence typically 0.7–0.9

## Non-Breaking Changes

The exception investigator **does NOT modify the main `/run` pipeline**:
- `/run` endpoint behavior unchanged
- Pipeline output format unchanged
- Existing matches + exceptions unchanged
- Investigation is a **separate POST-pipeline workflow**

This allows:
1. Running investigations asynchronously after pipeline completion
2. Re-investigating exceptions without re-running the full pipeline
3. Running the pipeline without investigation (backward compatible)

## Future Extensions

1. **Batch Re-Investigation:** `POST /reinvestigate/{run_id}` — re-examine with updated dispute log
2. **Dispute Log Streaming:** Real-time investigation updates as new disputes arrive
3. **Fuzzy Evidence Matching:** Allow amount/date tolerance in dispute-exception correlation
4. **Custom Prompt Templates:** Per-exception-type investigation instructions
