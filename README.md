# Reconcile -- AI Finance Controller Agent (Razorpay Buildathon)

Reconciles Razorpay settlement reports against a bank ledger AND an internal
order database (the third source Razorpay's own "Ray" agent can't see),
using a tiered matching pipeline: exact -> fuzzy -> LLM reasoning.

## Setup
    pip install -r requirements.txt
    set GROQ_API_KEY=your-key-here      (Windows cmd)

## Run
    python data\generate_data.py
    python backend\matching\matching_engine.py
    python backend\matching\db_reconciliation.py
    python backend\matching\llm_reasoning.py
    python backend\evaluate.py

## Status
- [x] Exact + fuzzy matching (Tier 1 + 2) -- 95% batch accuracy vs ground truth
- [x] Unrelated-transaction filtering -- 100% accuracy
- [x] Duplicate-posting detection
- [x] Third source: internal Order DB reconciliation (phantom charge / ghost order) -- 100% accuracy
- [ ] Tier 3 LLM reasoning (Groq) -- built, needs local test with your API key
- [ ] Action-recommendation drafting -- built, needs local test
- [ ] Postgres + FastAPI backend
- [ ] React dashboard
