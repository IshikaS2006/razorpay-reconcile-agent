# QA Layer Implementation Summary

## Overview
The QA layer enables natural language question-answering over reconciliation runs. Users can ask questions about settlement matches, exceptions, and investigation results through a conversational interface.

## Architecture

### Three-Layer System
1. **Entity Extraction** (Lightweight regex)
   - Extracts settlement_ids, order_ids, and amounts from questions
   - No LLM call needed (efficient)
   - Patterns: `setl_*`, `order_*`, amount values in rupees/paise

2. **Database Querying** (SQL)
   - Queries matches, exceptions, investigations tables
   - Filters by extracted entities if present
   - Returns run-level summary stats if no entities found

3. **LLM Reasoning** (Groq)
   - Takes question + limited data rows (max 10 per category)
   - Constrained to provided data only
   - Structured JSON response format
   - Fallback to data-only summary if LLM unavailable

## Components Created

### 1. Backend: `backend/qa_layer.py` (300+ lines)

**Key Functions:**

```python
extract_entities(question: str) -> Dict
    Returns: {"settlement_ids": [...], "order_ids": [...], "amounts": [...]}
    
query_run_data(run_id, db_session, settlement_ids=None, order_ids=None, amounts=None) -> Dict
    Returns: {"run_summary": {...}, "matches": [...], "exceptions": [...], "investigations": [...]}

build_qa_prompt(question: str, run_data: Dict) -> str
    Constructs LLM prompt with data and instructions

answer_question(question: str, run_id: int, db_session) -> Dict
    Main entry point: orchestrates extraction → querying → LLM → parsing
    Returns: {"answer": str, "sources": [ids]}
```

**Entity Extraction Patterns:**
- Settlement IDs: `setl_*`, `SETL_*`, `settlement_*`
- Order IDs: `order_*`, `ORDER_*`, `order_id*`
- Amounts: Regex captures currency symbols (₹, $, ₨) and keywords (rupees, paise, INR)
  - Auto-converts rupees to paise (multiply by 100)
  - ±5% tolerance for matching exceptions

**LLM Configuration:**
- Model: `openai/gpt-oss-120b` (via Groq API)
- Temperature: 0.3 (deterministic)
- Max tokens: 300
- Required response format: JSON with `answer` and `sources` keys

### 2. Backend: `backend/main.py` (Modified)

**New Endpoint:**
```python
@app.post("/ask")
async def ask(req: QuestionRequest, db: Session = Depends(get_db)) -> Dict:
    """
    Ask natural language questions about a reconciliation run.
    
    Request:
        {
            "question": "What happened to setl_100002RP?",
            "run_id": 11
        }
    
    Response:
        {
            "answer": "Settlement setl_100002RP had a partial credit due to...",
            "sources": ["exception_1", "investigation_1"]
        }
    """
```

**Request Model:**
```python
class QuestionRequest(BaseModel):
    question: str
    run_id: int
```

### 3. Frontend: `frontend/src/components/QueryBox.jsx` (150+ lines)

**Props:**
- `runId` (integer) - The batch run ID to query

**State:**
- `question` - User's input text
- `answer` - LLM response
- `sources` - Array of cited IDs
- `loading` - Boolean for async state
- `error` - Error message

**Features:**
- Textarea for multi-line questions
- Shift+Enter for newline, Enter to submit
- Displays answer with source citations
- Error banner for failures
- Disabled state when no run is available

**Styling:** Consistent with existing dashboard (kebab-case CSS classes)

### 4. Frontend: CSS Additions to `frontend/src/App.css`

**New Classes:**
```css
.query-box-container       /* Main container */
.query-box-header          /* Header section */
.query-input-wrapper       /* Input + button wrapper */
.query-input               /* Textarea styling */
.query-button              /* Submit button */
.query-error               /* Error banner */
.query-result              /* Result container */
.query-answer              /* Answer text */
.query-sources             /* Sources section */
.source-badge              /* Individual source ID badge */
```

### 5. Frontend: App.jsx Integration

**Changes:**
- Import: `import QueryBox from './components/QueryBox'`
- Render: `<QueryBox runId={run.summary?.run_id} />` after exceptions section

## Usage

### Backend Setup
```bash
# 1. Install dependencies (if not already done)
cd backend
pip install -r ../requirements.txt

# 2. Initialize database (creates tables)
python init_db.py

# 3. Start FastAPI server
python main.py
# Server runs at http://127.0.0.1:8000
```

### Frontend Setup
```bash
# 1. Install dependencies (if not already done)
cd frontend
npm install

# 2. Start dev server
npm run dev
# Dashboard at http://localhost:5173
```

### API Usage (Curl Example)
```bash
# Ask a question about run 11
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What happened to settlement setl_100002RP?",
    "run_id": 11
  }'

# Response:
{
  "answer": "Settlement setl_100002RP experienced an exception due to partial crediting. Investigation ID 1 explains: ...",
  "sources": ["exception_1", "investigation_1"]
}
```

## Database Schema

### Match Table (for QA)
```
id              - Primary key
run_id          - Foreign key to BatchRun
settlement_id   - Settlement identifier
matched_entry_id - Bank ledger entry matched to
tier            - "exact", "fuzzy", or "llm"
confidence      - 0.0-1.0
reason          - Match explanation
```

### Exception_ Table (for QA)
```
id              - Primary key
run_id          - Foreign key to BatchRun
reference_id    - Settlement or order ID
exception_type  - "unresolved_settlement", "phantom_charge", "ghost_order"
source          - "bank_reconciliation" or "db_reconciliation"
amount_paise    - Amount in paise (multiply by 100 for rupees)
detail          - Exception description
recommended_action - Next steps
```

### Investigation Table (for QA)
```
id              - Primary key
run_id          - Foreign key to BatchRun
exception_reference_id - Foreign key to Exception_
status          - "unexplained", "explained", "action_taken"
explanation     - Investigation findings
confidence      - 0.0-1.0
evidence_used   - JSON array of evidence IDs (e.g., dispute IDs)
```

## Testing

### Entity Extraction Test
```bash
cd backend
python -c "from qa_layer import extract_entities; print(extract_entities('What happened to setl_100002RP?'))"
# Output: {'settlement_ids': ['setl_100002RP'], 'order_ids': [], 'amounts': []}
```

### Full QA Workflow Test
```bash
cd backend
python test_qa_layer.py
```

## Error Handling

### Graceful Fallback
1. **LLM Unavailable**: Returns data-only summary without LLM reasoning
2. **JSON Parse Failure**: Entire response treated as answer text
3. **No Entity Matches**: Returns run-level summary statistics
4. **Database Error**: Returns error message with specific details

### Amount Tolerance
When matching exception amounts to user input:
- Extracted amount ±5% considered a match
- Computed as: `amount_val × 0.95 to amount_val × 1.05`

## Examples

### Example 1: Settlement-Specific Question
```
Q: "What happened to setl_100002RP?"
Entities: {"settlement_ids": ["setl_100002RP"], "order_ids": [], "amounts": []}
Database Query: Filter exceptions/matches where settlement_id = "setl_100002RP"
LLM Prompt: "QUESTION: What happened to setl_100002RP?\n\nEXCEPTIONS:\n- Exception 1: setl_100002RP (partial credit)...\n\nINVESTIGATIONS:\n- Investigation 1: Explained via dispute..."
Response: {"answer": "Settlement setl_100002RP had...", "sources": ["exception_1", "investigation_1"]}
```

### Example 2: Amount-Based Query
```
Q: "Show me exceptions with amount 5000 rupees"
Entities: {"settlement_ids": [], "order_ids": [], "amounts": [500000]}  // in paise
Database Query: Filter exceptions where amount_paise BETWEEN 475000 AND 525000
Response: {"answer": "There are 2 exceptions with amounts near 5000 rupees: ...", "sources": ["exception_2", "exception_5"]}
```

### Example 3: Run-Level Summary
```
Q: "How many settlements matched?"
Entities: {"settlement_ids": [], "order_ids": [], "amounts": []}
Database Query: Return run summary stats (no entity filtering)
Response: {"answer": "Run 11 had 19/20 matched settlements (95% match rate)...", "sources": ["run_summary"]}
```

## Performance Considerations

1. **Token Efficiency**
   - LLM receives max 10 rows per category (matches, exceptions, investigations)
   - Keeps tokens under 300 words typically

2. **Database Optimization**
   - Entity-based filtering reduces query results
   - Indexes on (run_id, settlement_id, order_id) recommended

3. **Frontend Performance**
   - Async POST request with loading state
   - Prevents double-submission with disabled button

## Security Notes

- LLM is constrained to provided data only (no external knowledge)
- Secrets (GROQ_API_KEY) stored in `.env`, not in code
- Amount matching uses hardcoded 5% tolerance (tamper-proof)
- Database queries are parameterized (SQL injection safe)
