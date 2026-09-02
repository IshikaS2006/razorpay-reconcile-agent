"""
Exception Investigator -- Post-pipeline cross-reference module

After the main reconciliation pipeline produces its final exceptions list,
this module:

1. Loads the refund_dispute_log.csv (5th synthetic data source)
2. For each unresolved exception, searches for related disputes by:
   - Matching related_order_id against the exception's reference ID
   - Matching related_settlement_id against the exception's reference ID
3. Calls the LLM (Groq) to explain the exception using the matched evidence
4. Marks as "explained" (confidence >= 0.7) or "escalated" (confidence < 0.7)
5. Returns investigation results for persistence in the DB audit trail

Usage:
    from exception_investigator import investigate_run_exceptions
    results = investigate_run_exceptions(
        run_id=123,
        exceptions=[...],
        llm_available=True,
        data_base="/path/to/data/generated"
    )
"""

import os
import pandas as pd
import json
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LLM_AVAILABLE = bool(os.environ.get("GROQ_API_KEY"))
if LLM_AVAILABLE:
    from matching.llm_reasoning import _client


def load_dispute_log(base: str) -> pd.DataFrame:
    """Load the refund_dispute_log.csv"""
    path = os.path.join(base, "refund_dispute_log.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def find_related_disputes(exception_ref: str, dispute_log: pd.DataFrame) -> List[Dict]:
    """
    Find all disputes that relate to this exception.
    
    Matches on:
      - related_order_id (if exception is from order DB, e.g. order_123RP)
      - related_settlement_id (if exception is from bank matching, e.g. setl_123RP)
    """
    if dispute_log.empty:
        return []
    
    matches = []
    
    # Try order_id match
    order_matches = dispute_log[dispute_log["related_order_id"] == exception_ref]
    if not order_matches.empty:
        matches.extend(order_matches.to_dict("records"))
    
    # Try settlement_id match
    settlement_matches = dispute_log[dispute_log["related_settlement_id"] == exception_ref]
    if not settlement_matches.empty:
        matches.extend(settlement_matches.to_dict("records"))
    
    return matches


def draft_investigation_prompt(exception: Dict, related_disputes: List[Dict]) -> str:
    """
    Build an LLM prompt asking it to explain this exception
    using the provided dispute log evidence.
    """
    prompt = f"""You are a financial reconciliation investigator. An unresolved transaction 
exception needs your explanation. You have access to customer disputes related to this exception.

EXCEPTION DETAILS:
  - Reference ID: {exception['reference_id']}
  - Type: {exception['exception_type']}
  - Source: {exception['source']}
  - Amount: ₹{exception['amount_paise'] / 100:.2f} ({exception['amount_paise']} paise)
  - Detail: {exception['detail']}

RELATED DISPUTES/CHARGEBACKS (from refund_dispute_log.csv):
"""
    
    if related_disputes:
        for i, dispute in enumerate(related_disputes, 1):
            prompt += f"""
  {i}. Log ID: {dispute['log_id']}
     Type: {dispute['type']}
     Amount: ₹{dispute['amount'] / 100:.2f} ({dispute['amount']} paise)
     Status: {dispute['status']}
     Created: {dispute['created_at']}
     Notes: {dispute['notes']}
"""
    else:
        prompt += "\n  (No related disputes found in log.)\n"
    
    prompt += """
TASK:
Using ONLY the evidence provided above (exception detail + related disputes),
explain why this exception exists. Your explanation should be:
1. Grounded in the specific evidence (cite dispute types, amounts, dates)
2. Honest about uncertainty (if evidence is inconclusive, say so)
3. 1-3 sentences maximum

Also provide a confidence score (0-1) indicating how well the evidence explains this exception:
  - 0.9-1.0: Clear explanation, evidence directly supports it
  - 0.7-0.8: Reasonable explanation, some evidence gaps but plausible
  - 0.4-0.6: Partial explanation, significant uncertainty
  - 0.0-0.3: Cannot explain with available evidence

Format your response as JSON:
{
  "explanation": "...",
  "confidence": 0.8,
  "evidence_summary": "..."
}
"""
    return prompt


def investigate_exception(exception: Dict, dispute_log: pd.DataFrame) -> Dict:
    """
    Investigate a single exception using LLM reasoning.
    
    Returns: {
        "exception_reference_id": str,
        "status": "explained" | "escalated",
        "explanation": str,
        "confidence": float (0-1),
        "evidence_used": str (JSON array of dispute log IDs, or "[]"),
        "reasoning_chain": str
    }
    """
    related_disputes = find_related_disputes(exception["reference_id"], dispute_log)
    evidence_ids = [d.get("log_id", "") for d in related_disputes]
    
    # If no disputes found and LLM not available, mark as escalated with minimal reasoning
    if not related_disputes and not LLM_AVAILABLE:
        return {
            "exception_reference_id": exception["reference_id"],
            "status": "escalated",
            "explanation": "No related disputes found in log, and LLM reasoning not available.",
            "confidence": 0.0,
            "evidence_used": json.dumps([]),
            "reasoning_chain": "No investigation performed (LLM unavailable, no disputes found).",
        }
    
    # If LLM available, use it to reason about the exception
    if LLM_AVAILABLE:
        try:
            client = _client()
            prompt = draft_investigation_prompt(exception, related_disputes)
            
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Low temperature for consistency
                max_tokens=500,
            )
            
            response_text = response.choices[0].message.content
            
            # Try to parse JSON response
            try:
                result = json.loads(response_text)
                explanation = result.get("explanation", "")
                confidence = result.get("confidence", 0.0)
                evidence_summary = result.get("evidence_summary", "")
            except json.JSONDecodeError:
                # Fallback: treat entire response as explanation
                explanation = response_text
                confidence = 0.5  # uncertain parse
                evidence_summary = "Could not parse structured response"
            
            status = "explained" if confidence >= 0.7 else "escalated"
            
            return {
                "exception_reference_id": exception["reference_id"],
                "status": status,
                "explanation": explanation,
                "confidence": min(1.0, max(0.0, confidence)),  # clamp to [0, 1]
                "evidence_used": json.dumps(evidence_ids),
                "reasoning_chain": f"Evidence found: {len(related_disputes)} disputes. LLM reasoning: {evidence_summary}",
            }
        except Exception as e:
            # LLM call failed
            return {
                "exception_reference_id": exception["reference_id"],
                "status": "escalated",
                "explanation": f"LLM investigation attempted but failed: {str(e)}",
                "confidence": 0.0,
                "evidence_used": json.dumps(evidence_ids) if evidence_ids else json.dumps([]),
                "reasoning_chain": f"Error during LLM reasoning: {str(e)}",
            }
    else:
        # No LLM, but we have related disputes - still provide value
        if related_disputes:
            dispute_summary = "; ".join([
                f"{d['type']} ({d['status']}) for ₹{d['amount']/100:.2f}"
                for d in related_disputes
            ])
            return {
                "exception_reference_id": exception["reference_id"],
                "status": "escalated",  # Without LLM, always escalate
                "explanation": f"Related disputes found: {dispute_summary}. LLM reasoning not available.",
                "confidence": 0.5,  # Moderate confidence from evidence presence alone
                "evidence_used": json.dumps(evidence_ids),
                "reasoning_chain": f"Found {len(related_disputes)} related dispute(s) in log, but LLM not available to reason.",
            }
        else:
            return {
                "exception_reference_id": exception["reference_id"],
                "status": "escalated",
                "explanation": "No related disputes found, and LLM reasoning not available.",
                "confidence": 0.0,
                "evidence_used": json.dumps([]),
                "reasoning_chain": "No evidence or LLM reasoning available.",
            }


def investigate_run_exceptions(
    run_id: int,
    exceptions: List[Dict],
    llm_available: bool,
    data_base: str = None
) -> List[Dict]:
    """
    Main entry point: investigate all exceptions in a run.
    
    Args:
        run_id: The batch run ID
        exceptions: List of exception dicts from the pipeline
        llm_available: Whether GROQ_API_KEY is set
        data_base: Path to data/generated directory (defaults to relative path)
    
    Returns: List of investigation results, one per exception
    """
    if data_base is None:
        data_base = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    
    dispute_log = load_dispute_log(data_base)
    
    results = []
    for exception in exceptions:
        investigation = investigate_exception(exception, dispute_log)
        # Add run_id for DB persistence
        investigation["run_id"] = run_id
        results.append(investigation)
    
    return results


if __name__ == "__main__":
    # Test standalone
    import sys
    
    test_exceptions = [
        {
            "reference_id": "setl_100002RP",
            "exception_type": "unresolved_settlement",
            "source": "bank_reconciliation",
            "amount_paise": 500000,
            "detail": "Partial refund suspected; amount gap not explained by bank fees",
        },
        {
            "reference_id": "order_300008RP",
            "exception_type": "phantom_charge",
            "source": "db_reconciliation",
            "amount_paise": 750000,
            "detail": "Order marked as failed in DB but Razorpay settled it",
        },
    ]
    
    results = investigate_run_exceptions(
        run_id=0,  # test run
        exceptions=test_exceptions,
        llm_available=LLM_AVAILABLE,
    )
    
    print("Investigation Results:")
    print("=" * 70)
    for r in results:
        print(f"Reference: {r['exception_reference_id']}")
        print(f"Status: {r['status']} (confidence {r['confidence']:.2f})")
        print(f"Explanation: {r['explanation']}")
        print(f"Evidence used: {r['evidence_used']}")
        print()
