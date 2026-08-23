# Build Log

## Data generation
- Fixed a UTR-suffix collision bug: original generator gave every UTR the
  same shared suffix ("vxp0rj"), which later caused an LLM false-positive
  match (a coincidental suffix match with no real connection). Fixed by
  making UTR suffixes genuinely random per batch.

## Matching engine
- Fixed a fuzzy-match rule that matched on "PARTIAL" narration keyword
  alone, without checking UTR relevance — this let one batch steal another
  batch's legitimate partial-refund match. Fixed by requiring UTR evidence
  in that rule too.

## Pipeline
- Fixed double-counting: a duplicate-posting leftover ledger row was being
  reported both as its own warning AND as a generic "unexplained" exception.
- Fixed unrelated-transaction filtering not being applied in the unified
  pipeline (it existed in the matching engine but wasn't wired through) —
  restored it with a UTR-shape heuristic (must contain letters, not just
  digits, to avoid treating phone/account numbers as UTR evidence).

## LLM guardrails (found via real testing, not hypothetical)
- First guardrail (amount gap < 5%) caught a bad match but a second false
  positive slipped through with only a ~2% amount gap (a coincidental match
  to an unrelated "AUTOPAY-ELECTRICITY BOARD" transaction) — proved amount
  proximity alone isn't sufficient evidence.
- Added a second guardrail layer requiring narration evidence of the
  specific settlement's UTR fragment. First version of this check was too
  loose (accepted the generic word "RAZORPAY" as evidence, which appears
  in every real Razorpay narration regardless of which settlement it is)
  — tightened to require the settlement-specific UTR fragment specifically.
- Added retry logic (3 attempts, backoff) after an intermittent Groq
  connection error silently dropped one action recommendation.

## Tax verification
- Deliberately isolated tax/fee anomalies from settled_amount during data
  generation, so injecting these anomalies could never silently break
  bank-side matching (verified: bank matching stayed at 19/20 before and
  after this feature was added).

## Evaluation
- evaluate.py originally flagged the duplicate_entry ground-truth case as
  "wrong" even when the pipeline correctly matched AND flagged it — this
  was a limitation in the evaluation script's binary logic, not a real
  pipeline bug. Fixed evaluate.py to recognize "matched + flagged" as the
  correct outcome for that specific case.