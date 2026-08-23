# Architecture — Reconcile (AI Finance Controller)

## Problem

Every merchant using Razorpay receives a settlement report (what Razorpay says it paid out) and a separate bank statement (what actually landed in the account). These rarely match exactly — fees, GST, date lags, partial refunds, and reformatted reference numbers make manual reconciliation slow and error-prone.

This is a real, acknowledged industry problem — Razorpay's own 2026 buildathon brief frames it directly: *"verification capacity, not generation speed, is the bottleneck."*

Razorpay's own "Ray" agentic dashboard already solves the 2-source version of this problem in production: settlement report vs. bank statement. This project deliberately goes further in two ways Ray's own product demo does not show.

## What Makes This Different from Ray

### 1. A third data source

Ray only ever sees Razorpay's and the bank's data — it has zero visibility into a merchant's internal order/database system.

This agent adds that third source, catching two failure modes Ray structurally cannot see:

* **Phantom charge:** A payment is captured and settled by Razorpay, but the merchant's own order database shows it as failed or pending due to a dropped webhook. Money was collected, but the product may never have been shipped.
* **Ghost order:** An order is marked as completed internally with no real Razorpay payment behind it — indicating a data-entry error or potential revenue leak.

### 2. Honest failure handling, shown rather than hidden

Ray's own demo video follows an unbroken happy path where every query succeeds cleanly.

This agent is deliberately built around the opposite: showing genuinely unresolved cases, using a deterministic guardrail that rejects bad AI guesses involving real money, and drafting a next action for a human reviewer for every exception.

## System Architecture

```text
settlement_report.csv ─┐
bank_ledger.csv ───────┼──► Tier 1 (Exact Match) ──► Tier 2 (Fuzzy Match) ──► Tier 3 (LLM Reasoning)
orders_db.csv ─────────┘         │                          │                          │
                                 │                          │                          ▼
                                 │                          │             Deterministic Guardrail
                                 │                          │          (Amount gap < 5% AND
                                 │                          │           settlement-specific UTR
                                 │                          │           fragment required)
                                 ▼                          ▼                          │
                    DB ↔ Razorpay Reconciliation    Tax-line / MDR-GST Check           │
                    (phantom charge / ghost order)  (Fee ≈ 2.36%, GST ≈ 18% of fee)    │
                                 │                          │                          │
                                 └──────────────┬───────────┴──────────────────────────┘
                                                ▼
                                Action-Recommendation Drafting (LLM)
                                                ▼
                          Postgres (batch_runs / matches / exceptions)
                                                ▼
                           FastAPI (/run, /runs/latest, /runs/{id})
                                                ▼
                                        React Dashboard
```

## Tiered Matching Design

### Tier 1 — Exact Matching

UTR is present in the bank narration, amount matches exactly, and date matches exactly.

This layer uses pure deterministic code with no AI involved.

### Tier 2 — Fuzzy Matching

Rule-based tolerance matching handles:

* Fee deductions
* Date lags of up to ±3 days
* Reference-number reformatting using UTR fragment extraction
* UTR-verified partial refunds

This layer still uses no AI. Rules are used wherever deterministic verification is sufficient.

### Tier 3 — LLM Reasoning

Only genuine leftovers reach the LLM through Groq using `openai/gpt-oss-120b`.

The LLM proposes a possible match and provides reasoning, but its proposal is never trusted blindly.

Every LLM-generated match must pass a deterministic guardrail before being accepted:

1. The amount gap must be below **5%**
2. The settlement's specific UTR fragment must appear in the candidate bank narration

This reserves model reasoning for genuine edge cases while deterministic checks remain responsible for verification.

## Third Source: Database Reconciliation

A targeted join is performed on `order_id` between the internal order database and Razorpay's settlement data.

The reconciliation runs in both directions:

* Razorpay shows a payment, but the internal database says the order failed or is pending
* The internal database says an order was completed, but no corresponding Razorpay payment exists

This allows the system to detect phantom charges and ghost orders that cannot be discovered from settlement and bank data alone.

## Tax-Line Verification

The system independently checks whether each payment's reported fee and GST are internally consistent:

* Expected fee: approximately **2.36% of gross amount**
* Expected GST: approximately **18% of the fee**

This validation is deliberately isolated from `settled_amount`, ensuring that tax anomalies can never silently alter bank-side reconciliation results.

## Evaluation Methodology

All data is synthetically generated with known ground truth. Therefore, every result can be independently verified rather than merely asserted.

| Check                                | Result                                          |
| ------------------------------------ | ----------------------------------------------- |
| Bank-side batch matching             | 20/20 correct (100%)                            |
| Unrelated-transaction filtering      | 8/8 correctly ignored, 0 false positives        |
| Third-source order DB reconciliation | 5/5 correct (100%)                              |
| Tax-line verification                | 3/3 planted anomalies caught, 0 false positives |

## Known Limitations

The project states its limitations explicitly:

* **Synthetic data:** The project does not currently use a live Razorpay sandbox integration. This was a deliberate scope decision because the track explicitly allows and expects synthetic data.
* **Guardrail calibration:** The 5% amount-gap threshold and UTR-fragment requirement were tuned against the noise patterns in this specific dataset. A production system would require broader calibration.
* **Bug-fix history:** The evaluation did not begin at 100%. Two real issues were discovered and fixed during development:

  * A UTR-collision issue in the synthetic data generation
  * A fuzzy-matching rule that was too loose

The complete development and debugging record is maintained in `.kb/log.md`.
