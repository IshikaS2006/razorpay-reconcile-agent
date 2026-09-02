"""
Tier 3: LLM Reasoning Layer (Groq) + Action-Recommendation Drafting

Two jobs, both using Groq's OpenAI-compatible chat completions API:

1. resolve_ambiguous_batch()
   For the genuine leftovers Tier 1 + Tier 2 couldn't resolve -- gives the
   LLM the batch details + candidate ledger rows and asks it to reason
   about whether any of them are plausibly the same transaction.

2. draft_action_recommendation()
   For EVERY exception (regardless of which tier/pass produced it) --
   drafts a short, evidence-specific "what should a human do next" line.
   This does NOT execute anything. It's a recommendation for a human,
   which matches Track 04's "verification," not "action" -- Track 03's job.

NOTE: this file makes real network calls to api.groq.com and needs
GROQ_API_KEY set in your environment. Run this on your own machine, not
in a sandbox with restricted network access.

Setup (Windows):
    pip install groq
    set GROQ_API_KEY=your-key-here          (cmd)
    $env:GROQ_API_KEY="your-key-here"       (PowerShell)

Setup (Mac/Linux):
    pip install groq
    export GROQ_API_KEY=your-key-here
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
MODEL = "openai/gpt-oss-120b"  # current recommended model as of Aug 2026


def _client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable not set. "
            "See the setup instructions at the top of this file."
        )
    return Groq(api_key=api_key)


def resolve_ambiguous_batch(batch: dict, candidate_ledger_rows: list) -> dict:
    """
    batch: {"settlement_id": ..., "settlement_utr": ..., "batch_total": ..., "settled_at": ...}
    candidate_ledger_rows: list of {"entry_id", "date", "narration", "credit"} --
        the leftover, still-unmatched ledger rows to consider.

    Returns: {
        "match": bool,
        "entry_id": str|None,
        "confidence": float,
        "reasoning": str,
        "action": str
    }
    """
    client = _client()

    prompt = f"""You are a financial reconciliation analyst. A Razorpay settlement batch
    could not be matched to any bank ledger entry using exact or fuzzy rules.
    Decide if any of the candidate ledger entries below are plausibly the SAME
    transaction, accounting for real-world noise (extra bank fees, rounding,
    partial refunds, reformatted reference numbers, minor date shifts).

    CRITICAL RULE: A match requires genuine textual evidence connecting the
    narration to Razorpay or this specific settlement's UTR (e.g. the word
    'RAZORPAY', a recognizable fragment of the UTR, or an explicit settlement
    reference). Amount and date proximity ALONE, without such textual evidence,
    is NOT sufficient grounds for a match -- many completely unrelated bank
    transactions (salary, utility autopay, vendor payments) can coincidentally
    have similar amounts. If the narration gives no Razorpay-related evidence
    at all, you must report match: false, regardless of how close the amount is.

    SETTLEMENT BATCH:
    settlement_id: {batch['settlement_id']}
    UTR: {batch['settlement_utr']}
    expected amount (paise): {batch['batch_total']}
    settlement date: {batch['settled_at']}

    CANDIDATE LEDGER ENTRIES (unmatched so far):
    {json.dumps(candidate_ledger_rows, indent=2, default=str)}

    Also draft a concrete "Action:" line — the specific next step a human
    should take (e.g. "verify UTR X with bank, initiate reversal if duplicate
    confirmed"). Not a generic recommendation — name the specific ID and the
    specific check.

    Respond ONLY with a JSON object, no other text:
    {{
    "match": true or false,
    "entry_id": "the matching entry_id, or null if no plausible match",
    "confidence": a number between 0 and 1,
    "reasoning": "one or two sentences citing the SPECIFIC evidence (numbers, UTR fragments, dates) that led to this conclusion",
    "action": "Action: the specific next step a human should take, naming the specific ID and specific check"
    }}"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)

def draft_action_recommendation(exception: dict) -> str:
    """
    exception: any exception dict with at least 'exception_type' and 'detail'/'notes'
               and the specific numbers/IDs involved.

    Returns a short, specific, human-actionable next-step string.
    This is a DRAFT for a human to act on -- it does not execute anything.
    """
    client = _client()

    prompt = f"""You are a financial reconciliation analyst. Below is one unresolved
    exception from a Razorpay settlement reconciliation batch. Write ONE short,
    specific, actionable next step a finance analyst should take -- referencing
    the SPECIFIC evidence (exact amounts, UTRs, order IDs) given below, not a
    generic template. Do not describe yourself taking any action -- this is a
    recommendation for a HUMAN to act on.

    EXCEPTION:
    {json.dumps(exception, indent=2, default=str)}

    Respond with ONLY the recommended action, as a single sentence starting with "Action:". No other text."""

    import time
    last_error = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            time.sleep(1.5 * (attempt + 1))  # brief backoff before retrying
    raise last_error


if __name__ == "__main__":
    # Test 1: resolve the one genuine leftover from our bank matching (setl_100007RP)
    test_batch = {
        "settlement_id": "setl_100007RP",
        "settlement_utr": "2026000092vxp0rj",
        "batch_total": 2856176,
        "settled_at": "2026-08-01",
    }
    test_candidates = [
        {"entry_id": "LDG00029", "date": "2026-08-15", "narration": "FD INTEREST CREDIT", "credit": 1320072},
        {"entry_id": "LDG00023", "date": "2026-07-07", "narration": "AUTOPAY-ELECTRICITY BOARD", "credit": 1886701},
    ]
    print("=== Test 1: resolve_ambiguous_batch (expect no plausible match) ===")
    result = resolve_ambiguous_batch(test_batch, test_candidates)
    print(json.dumps(result, indent=2))

    # Test 2: draft an action for the duplicate-posting warning we found earlier
    test_exception = {
        "exception_type": "duplicate_posting",
        "settlement_id": "setl_100001RP",
        "matched_entry_id": "LDG00002",
        "unused_duplicate_entry_id": "LDG00001",
        "amount_paise": 2582737,
        "narration": "NEFT CR-RAZORPAY SOFTWARE-2026000020vxp0rj-SETTLEMENT",
    }
    print("\n=== Test 2: draft_action_recommendation (duplicate posting) ===")
    action = draft_action_recommendation(test_exception)
    print(action)

    # Test 3: draft an action for a phantom charge
    test_phantom = {
        "exception_type": "phantom_charge",
        "order_id": "order_300048RP",
        "amount_rupees": 6982.63,
        "db_status": "failed",
        "razorpay_status": "captured_and_settled",
    }
    print("\n=== Test 3: draft_action_recommendation (phantom charge) ===")
    action2 = draft_action_recommendation(test_phantom)
    print(action2)
