#!/usr/bin/env python
"""
Integration test: Show that exception_investigator correctly:
1. Loads refund_dispute_log.csv
2. Finds related disputes by order_id and settlement_id
3. Calls LLM to explain exceptions
4. Classifies as "explained" or "escalated" based on confidence threshold
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from exception_investigator import (
    load_dispute_log,
    find_related_disputes,
    investigate_run_exceptions,
)

def main():
    print("=" * 70)
    print("INTEGRATION TEST: Exception Investigator with Refund Dispute Log")
    print("=" * 70)
    
    data_base = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    
    # 1. Load dispute log
    print("\n1. Loading refund_dispute_log.csv...")
    dispute_log = load_dispute_log(data_base)
    print(f"   Loaded {len(dispute_log)} dispute entries")
    
    # 2. Show dispute types
    print("\n2. Dispute log summary:")
    print(f"   - Refunds: {len(dispute_log[dispute_log['type'] == 'refund'])}")
    print(f"   - Disputes: {len(dispute_log[dispute_log['type'] == 'dispute'])}")
    print(f"   - Chargebacks: {len(dispute_log[dispute_log['type'] == 'chargeback'])}")
    
    # 3. Create sample exceptions
    print("\n3. Creating sample exceptions for investigation...")
    test_exceptions = [
        {
            "reference_id": "setl_100002RP",  # partial_refund batch
            "exception_type": "unresolved_settlement",
            "source": "bank_reconciliation",
            "amount_paise": 500000,
            "detail": "Settlement batch partially credited; refund suspected but not fully explained",
        },
        {
            "reference_id": "setl_100004RP",  # reference_mismatch batch
            "exception_type": "unresolved_settlement",
            "source": "bank_reconciliation",
            "amount_paise": 325000,
            "detail": "UTR present but reformatted in bank narration; unclear if it's the same transaction",
        },
        {
            "reference_id": "order_300008RP",  # phantom_charge
            "exception_type": "phantom_charge",
            "source": "db_reconciliation",
            "amount_paise": 750000,
            "detail": "Order marked as failed in internal DB but payment was captured and settled by Razorpay",
        },
    ]
    
    # 4. Investigate
    print("\n4. Running exception investigation (using LLM + dispute log)...\n")
    results = investigate_run_exceptions(
        run_id=0,  # test run
        exceptions=test_exceptions,
        llm_available=True,
        data_base=data_base,
    )
    
    # 5. Display results
    print("=" * 70)
    print("INVESTIGATION RESULTS")
    print("=" * 70)
    
    explained_count = sum(1 for r in results if r["status"] == "explained")
    escalated_count = sum(1 for r in results if r["status"] == "escalated")
    avg_confidence = sum(r["confidence"] for r in results) / len(results) if results else 0
    
    print(f"\nSummary:")
    print(f"  Total exceptions investigated: {len(results)}")
    print(f"  Explained (confidence >= 0.7): {explained_count}")
    print(f"  Escalated (confidence < 0.7):  {escalated_count}")
    print(f"  Average confidence: {avg_confidence:.2f}")
    
    print(f"\nDetailed Results:")
    for i, r in enumerate(results, 1):
        print(f"\n{i}. Exception: {r['exception_reference_id']}")
        print(f"   Status: {r['status'].upper()} (confidence {r['confidence']:.2f})")
        print(f"   Evidence: {r['evidence_used']}")
        print(f"   Explanation: {r['explanation'][:100]}...")
        print(f"   Reasoning: {r['reasoning_chain'][:80]}...")
    
    print("\n" + "=" * 70)
    print("✓ Integration test complete")
    print("=" * 70)

if __name__ == "__main__":
    main()
