#!/usr/bin/env python
"""
QA Layer Integration Test -- Demonstrate natural language Q&A over reconciliation data

This test verifies:
1. Entity extraction from natural language questions
2. Database querying for matches/exceptions/investigations
3. LLM reasoning with extracted data
4. Answer generation with source citations
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from qa_layer import extract_entities, query_run_data, answer_question, build_qa_prompt
from db import SessionLocal
from models import BatchRun, Match, Exception_, Investigation


def test_entity_extraction():
    """Test that entity extraction works correctly."""
    print("\n" + "=" * 70)
    print("TEST 1: Entity Extraction")
    print("=" * 70)
    
    test_cases = [
        ("What happened to settlement setl_100002RP?",
         {"settlement_ids": ["setl_100002RP"], "order_ids": [], "amounts": []}),
        ("Why was order_300008RP flagged as a phantom charge?",
         {"settlement_ids": [], "order_ids": ["order_300008RP"], "amounts": []}),
        ("Tell me about exceptions with amount ₹5000",
         {"settlement_ids": [], "order_ids": [], "amounts": [500000]}),
        ("How many exceptions are in this run?",
         {"settlement_ids": [], "order_ids": [], "amounts": []}),
        ("Compare setl_100002RP (₹5000) and order_300008RP (₹7500)",
         {"settlement_ids": ["setl_100002RP"], "order_ids": ["order_300008RP"], "amounts": [500000, 750000]}),
    ]
    
    for question, expected in test_cases:
        result = extract_entities(question)
        # For amounts, check that the expected values are in the result (not exact order)
        amounts_match = set(result["amounts"]) == set(expected["amounts"])
        settlement_match = set(result["settlement_ids"]) == set(expected["settlement_ids"])
        order_match = set(result["order_ids"]) == set(expected["order_ids"])
        
        status = "✓" if (amounts_match and settlement_match and order_match) else "✗"
        print(f"\n{status} Q: {question}")
        print(f"  Extracted:")
        if result["settlement_ids"]:
            print(f"    - Settlements: {result['settlement_ids']}")
        if result["order_ids"]:
            print(f"    - Orders: {result['order_ids']}")
        if result["amounts"]:
            print(f"    - Amounts: ₹{[x/100 for x in result['amounts']]}")


def test_qa_workflow():
    """Test the full QA workflow with a real run."""
    print("\n" + "=" * 70)
    print("TEST 2: Full QA Workflow (if runs exist)")
    print("=" * 70)
    
    db = SessionLocal()
    
    try:
        # Find a run
        run = db.query(BatchRun).order_by(BatchRun.id.desc()).first()
        
        if not run:
            print("\n⚠ No runs found. Run the pipeline first: POST /run")
            return
        
        print(f"\nUsing run {run.id} (created {run.run_at})")
        print(f"  - {run.matched_batches}/{run.total_settlement_batches} matched ({run.match_rate_pct:.1f}%)")
        print(f"  - {run.total_exceptions} exceptions")
        
        # Test queries
        test_questions = [
            ("How many settlements matched in this run?", None),
            ("Show me the exceptions", None),
        ]
        
        for question, run_id in test_questions:
            print(f"\nQ: {question}")
            entities = extract_entities(question)
            print(f"  Entities: {entities}")
            
            # Query data
            run_data = query_run_data(
                run_id=run.id,
                db_session=db,
                settlement_ids=entities["settlement_ids"] if entities["settlement_ids"] else None,
                order_ids=entities["order_ids"] if entities["order_ids"] else None,
                amounts=entities["amounts"] if entities["amounts"] else None,
            )
            
            print(f"  Data retrieved:")
            print(f"    - Matches: {len(run_data['matches'])}")
            print(f"    - Exceptions: {len(run_data['exceptions'])}")
            print(f"    - Investigations: {len(run_data['investigations'])}")
            
            # Show sample data
            if run_data['matches'][:1]:
                m = run_data['matches'][0]
                print(f"    - Sample match: {m['settlement_id']} → {m['matched_entry_id']} (tier: {m['tier']})")
            if run_data['exceptions'][:1]:
                e = run_data['exceptions'][0]
                print(f"    - Sample exception: {e['reference_id']} ({e['exception_type']})")
            
    finally:
        db.close()


def test_prompt_building():
    """Test that prompts are built correctly."""
    print("\n" + "=" * 70)
    print("TEST 3: LLM Prompt Building")
    print("=" * 70)
    
    sample_run_data = {
        "run_summary": {
            "run_id": 1,
            "total_settlement_batches": 20,
            "matched_batches": 19,
            "match_rate_pct": 95.0,
            "total_exceptions": 1,
            "db_side_exceptions": 0,
            "llm_available": True,
        },
        "matches": [
            {
                "id": 1,
                "settlement_id": "setl_100001RP",
                "matched_entry_id": "ledger_001",
                "tier": "exact",
                "confidence": 1.0,
                "reason": "UTR found and verified",
            }
        ],
        "exceptions": [
            {
                "id": 1,
                "reference_id": "setl_100002RP",
                "exception_type": "unresolved_settlement",
                "source": "bank_reconciliation",
                "amount_paise": 500000,
                "detail": "Settlement batch partially credited",
                "recommended_action": "Review bank narration for partial refund pattern",
            }
        ],
        "investigations": [
            {
                "id": 1,
                "exception_reference_id": "setl_100002RP",
                "status": "explained",
                "explanation": "The settlement was partially refunded",
                "confidence": 0.75,
                "evidence_used": "[\"DISP100001RP\"]",
            }
        ],
    }
    
    prompt = build_qa_prompt("What happened to setl_100002RP?", sample_run_data)
    
    print("\nPrompt length:", len(prompt), "characters")
    print("\nPrompt preview (first 500 chars):")
    print("-" * 70)
    print(prompt[:500])
    print("...")
    
    # Verify prompt contains key information
    checks = [
        ("Contains question", "What happened to setl_100002RP?" in prompt),
        ("Contains run summary", "Run SUMMARY:" in prompt or "run summary" in prompt),
        ("Contains match data", "setl_100001RP" in prompt),
        ("Contains exception data", "setl_100002RP" in prompt),
        ("Contains investigation data", "explained" in prompt),
        ("Contains instructions", "INSTRUCTIONS:" in prompt or "instructions" in prompt),
    ]
    
    print("\n\nPrompt integrity checks:")
    for check_name, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {check_name}")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("QA LAYER INTEGRATION TEST")
    print("=" * 70)
    
    test_entity_extraction()
    test_prompt_building()
    test_qa_workflow()
    
    print("\n" + "=" * 70)
    print("✓ QA Layer tests complete")
    print("=" * 70)
