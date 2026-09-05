# Architecture — Reconcile

## Track 04: AI Finance Controller

**Run the books and the cash position.**

Reconcile is a Track 04 submission for the Razorpay Buildathon. It closes one finance-ops loop across a 50+ record synthetic batch and is built around the actual bar of the track:

- process a batch end-to-end
- report a measured match rate
- surface unresolved exceptions honestly
- support downstream cash-position decisions

This is not a generic finance chatbot. It is a verification system with a controlled amount of model reasoning layered on top.

---

## 1. Problem framing

A merchant receives at least two operational views of the same money movement:

- a **Razorpay settlement report**
- a **bank statement**

In practice these do not line up cleanly. Reasons include:
- fee deductions
- GST lines
- delayed credits
- partial refunds
- reformatted references
- duplicate-looking bank entries
- internal order-system inconsistencies

That creates a real finance-ops burden: someone has to verify what is confirmed, what is unresolved, and what is risky.

The 2026 builder consensus captured in the brief is exactly right here: **verification capacity, not generation speed, is the bottleneck**.

---

## 2. What this system is trying to prove

A single cherry-picked match proves very little.

This project is designed to show three things together:

1. **Throughput** — it can process a meaningful batch, not one transaction at a time.
2. **Measured accuracy** — the core reconciliation logic is evaluated against known synthetic ground truth.
3. **Honest exception handling** — unresolved items are preserved and explained, not hidden by over-eager automation.

---

## 4. High-level system flow

```text
settlement_report.csv ─┐
bank_ledger.csv ───────┼─→ Tier 1 exact → Tier 2 fuzzy → Tier 3 LLM (leftovers only)
orders_db.csv ─────────┘            │                    │
                                    │                    └─ deterministic guardrail
                                    │
                                    ├─ DB reconciliation (phantom charge / ghost order)
                                    ├─ Tax-line verification
                                    ├─ Exception classification + recommended next action
                                    ├─ Persist run / matches / exceptions / investigations
                                    ├─ Forecast aggregation + backtesting
                                    └─ FastAPI → React dashboard + Q&A assistant
```

---

## 5. Data model and persisted outputs

Each reconciliation run is persisted so downstream layers can work from stored evidence rather than recomputing from scratch.

### Core stored entities
- `batch_runs`
- `matches`
- `exceptions`
- `investigations`
- `gl_postings` (demo/mock posting record)

### Why persistence matters
That storage layer enables:
- run history
- report drill-down
- grounded Q&A over prior runs
- audit trail of investigations and human decisions
- forecast aggregation from historical runs

---

## 6. Matching engine design

The matching engine is intentionally **tiered**.

### Tier 1 — exact match
Deterministic only.

A settlement batch is matched when:
- UTR/reference evidence is present in narration
- amount matches exactly
- date matches exactly

This handles the clean cases safely and cheaply.

### Tier 2 — fuzzy match
Still deterministic.

This tier handles realistic operational noise such as:
- amount tolerance
- short date lag windows
- reformatted reference fragments
- UTR-verified partial-refund patterns

The key philosophy is: if a rule can verify a case, use a rule.

### Tier 3 — LLM-assisted match
Only for genuine leftovers after Tiers 1 and 2.

The model is asked to reason about ambiguous candidates, such as:
- noisy narration
- split-looking settlement patterns
- edge-case reference variation

But the model does **not** get the final word by itself.

---

## 7. Deterministic guardrail over model proposals

Any LLM-proposed settlement match must pass a deterministic guardrail before acceptance.

### Guardrail conditions
1. **Amount gap < 5%**
2. **Settlement-specific UTR fragment appears in narration**

If either check fails, the model proposal is rejected and the item remains unresolved.

This is a deliberate response to the nature of finance control:
- model confidence is not the same thing as financial evidence
- narration similarity alone is not enough
- amount proximity alone is not enough

The system would rather preserve an exception than silently accept a bad match.

---

## 8. Exception classification

For every non-clean case, the system stores more than a label.

Each exception carries:
- source
- type
- reference ID
- amount at stake
- reasoning/detail
- recommended next action
- later investigation history if available

### Main exception families
- `unresolved_settlement`
- `duplicate_posting`
- `unexplained_ledger_row`
- `phantom_charge`
- `ghost_order`
- `tax_line_mismatch`

This detail feeds both:
- the dashboard
- the Q&A agent

---

## 9. Third-source reconciliation

The order-database reconciliation runs in both directions.

### Direction A
Settlement exists in Razorpay, but internal order state is failed/pending.

This becomes a **phantom charge** candidate.

### Direction B
Internal order is marked complete, but no corresponding Razorpay payment/settlement exists.

This becomes a **ghost order** candidate.

This layer is important because it extends the system from “bank matching” to actual finance control logic.

---

## 10. Tax-line verification

Tax verification is run as an independent pass.

The system checks whether the settlement report is internally consistent:
- fee is approximately **2.36%** of gross
- GST is approximately **18%** of the fee

This pass is deliberately isolated from bank-side matching so a tax anomaly cannot silently mutate the core settlement-vs-bank result.

---

## 11. Reporting layer

The reporting layer consolidates the run into metrics and drill-down views.

### Reported metrics include
- total batches processed
- matched batches
- match rate
- total exceptions
- exception categories
- detailed report rows
- investigation status

The report is built to make unresolved work visible rather than smoothing it away.

---

## 12. Grounded Q&A layer

The project includes a run-aware AI assistant on top of persisted reconciliation data.

### Tool-based approach
The assistant answers questions using retrieval tools over stored run data, including functions like:
- record lookup
- bank-line lookup (within currently persisted scope)
- amount search
- exception listing
- tax breakdown lookup
- unreconciled aggregation
- investigation history lookup

### Why this matters
This keeps the Q&A layer anchored to actual retrieved facts instead of free-form narrative generation.

The UI also exposes an audit trail of tool usage so a judge or user can inspect what the assistant actually consulted.

---

## 13. Cash forecasting layer

The forecast layer is downstream of reconciliation.

It uses persisted matched settlements as a historical signal to estimate:
- confirmed cash
- projected inflows
- projected fee/outflow rows
- at-risk cash
- forward cash position at `+7 / +14 / +30`

### Modeling choice
The forecast is intentionally simple and explainable:
- average settlement cycle
- average daily matched amount
- variance-based confidence
- naive moving-average projection

This is a conscious design choice. For Track 04, a transparent model with honest backtesting is more credible than a complicated model with unclear assumptions.

### Backtesting
The forecaster holds out recent matched settlements and compares projected values to realized totals, producing real error metrics such as:
- MAPE
- MAE

This is specifically intended to avoid suspicious zero-error reporting.

---

## 14. Frontend architecture

The React dashboard is organized around the outputs of the persisted run model.

### Main screens
- **Reconciliations list** — historical runs and summary KPIs
- **Run details / report** — detailed report rows, filters, investigation panel
- **New reconciliation** — upload/validation flow
- **Forecast** — confirmed cash, projected inflows/outflows, backtesting

### UI goals
- make report rows inspectable
- make exception evidence easy to review
- make the assistant feel interactive without hiding the audit trail
- keep navigation centered on reconciliation runs

---

## 15. Accuracy philosophy

This project tries to distinguish three different ideas clearly.

### A. Reconciliation accuracy
Measured against synthetic ground truth for the matching and classification pipeline.

### B. Forecast error
Measured through holdout-style backtesting, not circular self-comparison.

### C. Match rate
An operational KPI, not the same thing as accuracy.

This distinction matters because a high match rate alone does not prove the system is correct.

---

## 16. Design principles

### Deterministic where possible
Exact and fuzzy matching handle everything that can be safely rule-verified.

### LLM only where ambiguity remains
Model reasoning is reserved for edge cases and downstream explanation, not the bulk path.

### Guardrails over confidence
No model-proposed financial match is accepted without deterministic evidence.

### Preserve unresolved cases
The system is built to show what it cannot safely close.

### Optimize for demo credibility
Better to show a constrained, explainable system with honest limitations than an over-broad assistant that overclaims.

---

## 17. Known limitations

### Synthetic-data scope
The current project is built on synthetic datasets rather than a live Razorpay sandbox integration.

### Upload-to-normalized-storage gap
The UI has upload and validation flow, but a fully generalized upload-driven normalized staging pipeline is still a natural next step.

### Persisted raw bank-line depth
The current schema is strongest for persisted matches, exceptions, and investigations. Raw bank-line retrieval for the assistant is more limited than a production ledger model would be.

### Forecast simplicity
The forecast model is intentionally naive. That is acceptable for the current stage, but it is not trying to be a production treasury model.

---

## 18. Why this architecture is strong for Track 04

Track 04 asks for an agent that can run one finance-ops loop across a batch, report its match rate, and honestly surface what it could not resolve.

This architecture is aligned to that requirement because it combines:
- multi-source reconciliation
- deterministic verification
- constrained LLM assistance
- persistent auditability
- honest unresolved exceptions
- downstream cash-position support

That combination is what turns the project from “AI around finance words” into an actual finance-controller workflow.
