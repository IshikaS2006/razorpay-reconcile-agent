# Reconcile — AI Finance Controller Agent

## What this is
An AI reconciliation agent built for the Razorpay AI Buildathon 2026 (Track 04:
AI Finance Controller). It closes one finance-ops loop — reconciling Razorpay
settlement data against a bank ledger AND an internal order database — reporting
a measured match rate and an honest, evidence-grounded exception list.

## Why this design
Razorpay's own "Ray" agentic dashboard already does 2-source reconciliation
(settlement report vs. bank statement) in production — confirmed from their own
product demo. This agent deliberately goes further, in two ways Ray's own demo
never shows:
1. A third source (internal order DB) — catches phantom charges and ghost
   orders that Ray has zero visibility into, since it only sees Razorpay's
   and the bank's data.
2. Honest failure handling — Ray's demo is an unbroken happy path; this agent
   is built around showing genuinely unresolved cases and drafted next-actions
   for a human, not a cherry-picked clean run.

## Architecture
Three independent data sources → tiered verification → consolidated output:

    settlement_report.csv ─┐
    bank_ledger.csv ───────┼─→ Tier 1 (exact) → Tier 2 (fuzzy) → Tier 3 (LLM)
    orders_db.csv ─────────┘         │                                │
                                      ▼                                ▼
                            DB↔Razorpay check              Deterministic guardrail
                            (phantom charge/ghost order)    (rejects bad LLM matches)
                                      │                                │
                                      ▼                                ▼
                            Tax-line/MDR-GST check          Action recommendation (LLM)
                                      │                                │
                                      └──────────────┬─────────────────┘
                                                      ▼
                                    Postgres (batch_runs/matches/exceptions)
                                                      ▼
                                          FastAPI → React dashboard

## Current status (as of this commit)
- Bank-side matching (exact + fuzzy + LLM): 19/20 batches, 95% match rate
- Evaluation vs. self-generated ground truth: 100% accuracy across all 3
  checks (bank matching, unrelated-transaction filtering, third-source DB)
- 10 exceptions per run, each with a specific evidence-grounded recommended action
- LLM: Groq (openai/gpt-oss-120b)

## Key design decisions (see .kb/log.md for the full story)
- LLM proposals are never trusted blindly on money — every LLM match must
  pass a deterministic guardrail (amount gap < 5% AND settlement-specific
  UTR fragment found in narration) before being accepted.
- Unrelated bank transactions (salary, GST, vendor payments) are filtered
  using UTR-shape detection (must contain both letters and digits), not
  just "any long number" — pure digit strings (phone/account numbers) are
  explicitly NOT treated as UTR evidence.
- Tax-line verification checks the settlement report's own internal
  arithmetic (fee ≈ 2.36% of gross, tax ≈ 18% of fee) independently of
  bank matching — settled_amount is never touched by this check, so it
  can't silently break bank-side reconciliation.

## Setup
See README.md for install/run instructions.