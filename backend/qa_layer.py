"""
QA Layer -- Question-answering module that queries run data and uses LLM to answer questions.

This module:
1. Extracts entities (settlement_id, order_id, amounts) from natural language questions
2. Queries matches, exceptions, investigations tables for the run
3. Passes question + retrieved data (NOT whole DB) to LLM
4. LLM answers only from provided data, citing source IDs
5. Returns {answer, sources} to the user
"""

import re
import os
import json
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models import Match, Exception_, Investigation, BatchRun

load_dotenv()

LLM_AVAILABLE = bool(os.environ.get("GROQ_API_KEY"))
if LLM_AVAILABLE:
    from matching.llm_reasoning import _client


def extract_entities(question: str) -> Dict:
    """
    Extract settlement_id, order_id, and/or amounts from the question.
    
    Returns: {
        "settlement_ids": [],
        "order_ids": [],
        "amounts": []
    }
    """
    entities = {
        "settlement_ids": [],
        "order_ids": [],
        "amounts": []
    }
    
    # Find settlement IDs: patterns like setl_XXX, settlement_XXX, SETL_XXX
    settlement_pattern = r'(setl_\w+|SETL_\w+|settlement[\s_]id[\s:]*(\w+))'
    settlement_matches = re.findall(settlement_pattern, question, re.IGNORECASE)
    for match in settlement_matches:
        if isinstance(match, tuple):
            if match[1]:
                entities["settlement_ids"].append(match[1].strip())
            else:
                entities["settlement_ids"].append(match[0].strip())
        else:
            entities["settlement_ids"].append(match.strip())
    
    # Find order IDs: patterns like order_XXX, order_id_XXX, ORDER_XXX
    order_pattern = r'(order[\s_]id[\s:]*(\w+)|order_\w+|ORDER_\w+)'
    order_matches = re.findall(order_pattern, question, re.IGNORECASE)
    for match in order_matches:
        if isinstance(match, tuple):
            if match[1]:
                entities["order_ids"].append(match[1].strip())
            else:
                entities["order_ids"].append(match[0].strip())
        else:
            entities["order_ids"].append(match.strip())
    
    # Find amounts: patterns like ₹XXX, $XXX, XXX rupees, XXX paise
    # But NOT amounts that are part of settlement/order IDs
    # Remove settlement/order IDs from question before extracting amounts
    question_for_amounts = re.sub(r'(setl_\w+|order_\w+|SETL_\w+|ORDER_\w+)', '', question, flags=re.IGNORECASE)
    
    amount_pattern = r'(?:₹|[\$]|₨)?\s*(\d+(?:,\d{3})*(?:.\d{2})?)\s*(?:rupees?|paise|INR)?'
    amount_matches = re.findall(amount_pattern, question_for_amounts, re.IGNORECASE)
    for match in amount_matches:
        # Clean and convert to paise (if in rupees)
        clean_amount = match.replace(",", "").replace(".", "")
        try:
            amount_val = int(clean_amount)
            # If it looks like a round number in rupees (< 1,000,000), assume it's rupees
            if amount_val < 1000000:
                entities["amounts"].append(amount_val * 100)  # Convert to paise
            else:
                entities["amounts"].append(amount_val)  # Already in paise
        except ValueError:
            pass
    
    # Remove duplicates
    entities["settlement_ids"] = list(set(entities["settlement_ids"]))
    entities["order_ids"] = list(set(entities["order_ids"]))
    entities["amounts"] = list(set(entities["amounts"]))
    
    return entities


def query_run_data(
    run_id: int,
    db_session: Session,
    settlement_ids: List[str] = None,
    order_ids: List[str] = None,
    amounts: List[int] = None
) -> Dict:
    """
    Query matches, exceptions, and investigations for the run,
    optionally filtered by entities.
    
    Returns: {
        "run_summary": {...},
        "matches": [...],
        "exceptions": [...],
        "investigations": [...]
    }
    """
    # Verify run exists
    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found"}
    
    result = {
        "run_summary": {
            "run_id": run.id,
            "total_settlement_batches": run.total_settlement_batches,
            "matched_batches": run.matched_batches,
            "match_rate_pct": run.match_rate_pct,
            "total_exceptions": run.total_exceptions,
            "db_side_exceptions": run.db_side_exceptions,
            "llm_available": run.llm_available,
        },
        "matches": [],
        "exceptions": [],
        "investigations": []
    }
    
    # Query matches
    matches_query = db_session.query(Match).filter(Match.run_id == run_id)
    if settlement_ids:
        matches_query = matches_query.filter(Match.settlement_id.in_(settlement_ids))
    matches = matches_query.all()
    result["matches"] = [
        {
            "id": m.id,
            "settlement_id": m.settlement_id,
            "matched_entry_id": m.matched_entry_id,
            "tier": m.tier,
            "confidence": m.confidence,
            "reason": m.reason,
        }
        for m in matches
    ]
    
    # Query exceptions
    exceptions_query = db_session.query(Exception_).filter(Exception_.run_id == run_id)
    if settlement_ids or order_ids:
        filter_ids = (settlement_ids or []) + (order_ids or [])
        exceptions_query = exceptions_query.filter(Exception_.reference_id.in_(filter_ids))
    if amounts:
        # Allow ±5% tolerance for amount matching
        tolerance = 0.05
        exceptions_query = exceptions_query.filter(
            Exception_.amount_paise.between(
                int(amounts[0] * (1 - tolerance)),
                int(amounts[0] * (1 + tolerance))
            )
        )
    exceptions = exceptions_query.all()
    result["exceptions"] = [
        {
            "id": e.id,
            "reference_id": e.reference_id,
            "exception_type": e.exception_type,
            "source": e.source,
            "amount_paise": e.amount_paise,
            "detail": e.detail,
            "recommended_action": e.recommended_action,
        }
        for e in exceptions
    ]
    
    # Query investigations
    investigations_query = db_session.query(Investigation).filter(Investigation.run_id == run_id)
    if settlement_ids or order_ids:
        filter_ids = (settlement_ids or []) + (order_ids or [])
        investigations_query = investigations_query.filter(
            Investigation.exception_reference_id.in_(filter_ids)
        )
    investigations = investigations_query.all()
    result["investigations"] = [
        {
            "id": i.id,
            "exception_reference_id": i.exception_reference_id,
            "status": i.status,
            "explanation": i.explanation,
            "confidence": i.confidence,
            "evidence_used": i.evidence_used,
        }
        for i in investigations
    ]
    
    return result


def build_qa_prompt(question: str, run_data: Dict) -> str:
    """
    Build a prompt for the LLM to answer the question based on provided data.
    """
    prompt = f"""You are a financial reconciliation analyst. Answer the following question 
ONLY using the provided reconciliation data. Do not make assumptions or guess.

QUESTION: {question}

RUN SUMMARY:
  - Total settlement batches: {run_data['run_summary']['total_settlement_batches']}
  - Matched batches: {run_data['run_summary']['matched_batches']}
  - Match rate: {run_data['run_summary']['match_rate_pct']:.1f}%
  - Total exceptions: {run_data['run_summary']['total_exceptions']}
  - DB-side exceptions: {run_data['run_summary']['db_side_exceptions']}

MATCHED SETTLEMENTS ({len(run_data['matches'])} total):
"""
    
    if run_data['matches']:
        for m in run_data['matches'][:10]:  # Limit to first 10 for token efficiency
            prompt += f"""
  - Match ID {m['id']}: Settlement {m['settlement_id']} → Ledger Entry {m['matched_entry_id']}
    Tier: {m['tier']}, Confidence: {m['confidence']:.1%}, Reason: {m['reason']}"""
        if len(run_data['matches']) > 10:
            prompt += f"\n  ... and {len(run_data['matches']) - 10} more matches"
    else:
        prompt += "\n  (No matches)"
    
    prompt += f"""

UNRESOLVED EXCEPTIONS ({len(run_data['exceptions'])} total):
"""
    
    if run_data['exceptions']:
        for e in run_data['exceptions'][:10]:  # Limit to first 10
            prompt += f"""
  - Exception ID {e['id']}: {e['reference_id']} ({e['exception_type']})
    Source: {e['source']}, Amount: ₹{e['amount_paise']/100:.2f}
    Detail: {e['detail']}
    Recommended action: {e['recommended_action']}"""
        if len(run_data['exceptions']) > 10:
            prompt += f"\n  ... and {len(run_data['exceptions']) - 10} more exceptions"
    else:
        prompt += "\n  (No exceptions)"
    
    prompt += f"""

INVESTIGATION RESULTS ({len(run_data['investigations'])} total):
"""
    
    if run_data['investigations']:
        for inv in run_data['investigations'][:10]:  # Limit to first 10
            prompt += f"""
  - Investigation ID {inv['id']}: Exception {inv['exception_reference_id']}
    Status: {inv['status']}, Confidence: {inv['confidence']:.1%}
    Explanation: {inv['explanation']}"""
        if len(run_data['investigations']) > 10:
            prompt += f"\n  ... and {len(run_data['investigations']) - 10} more investigations"
    else:
        prompt += "\n  (No investigations)"
    
    prompt += """

ANSWER INSTRUCTIONS:
1. Answer the question using ONLY the data provided above
2. Cite specific ID(s) you're referring to (Match ID, Exception ID, Investigation ID, or "run summary")
3. If you don't have relevant data to answer the question, say: "I don't have data on that"
4. Be concise (2-3 sentences max)
5. Format your response as JSON:
{
  "answer": "Your answer here",
  "sources": ["match_id", "exception_id", "investigation_id", etc] or ["run_summary"]
}
"""
    
    return prompt


def answer_question(question: str, run_id: int, db_session: Session) -> Dict:
    """
    Main QA entry point: answer a question about a reconciliation run.
    
    Args:
        question: Natural language question
        run_id: The batch run ID
        db_session: SQLAlchemy session
    
    Returns: {
        "answer": str,
        "sources": [str] (IDs of data rows cited)
    }
    """
    # Extract entities from question
    entities = extract_entities(question)
    
    # Query run data
    run_data = query_run_data(
        run_id=run_id,
        db_session=db_session,
        settlement_ids=entities["settlement_ids"] if entities["settlement_ids"] else None,
        order_ids=entities["order_ids"] if entities["order_ids"] else None,
        amounts=entities["amounts"] if entities["amounts"] else None
    )
    
    if "error" in run_data:
        return {
            "answer": run_data["error"],
            "sources": []
        }
    
    # If no LLM available, return data-only answer
    if not LLM_AVAILABLE:
        summary = f"Run {run_id} summary: {run_data['run_summary']['matched_batches']} of "
        summary += f"{run_data['run_summary']['total_settlement_batches']} matched "
        summary += f"({run_data['run_summary']['match_rate_pct']:.1f}%). "
        summary += f"{run_data['run_summary']['total_exceptions']} exceptions found."
        
        sources = ["run_summary"]
        if run_data["matches"]:
            sources.extend([f"match_{m['id']}" for m in run_data["matches"][:3]])
        if run_data["exceptions"]:
            sources.extend([f"exception_{e['id']}" for e in run_data["exceptions"][:3]])
        
        return {
            "answer": summary,
            "sources": sources
        }
    
    # Call LLM to answer the question
    try:
        client = _client()
        prompt = build_qa_prompt(question, run_data)
        
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Low temperature for consistency
            max_tokens=300,
        )
        
        response_text = response.choices[0].message.content
        
        # Try to parse JSON response, including one nested JSON string.
        try:
            result = json.loads(response_text)
            if isinstance(result, str):
                result = json.loads(result)

            if isinstance(result, dict):
                answer = result.get("answer", "Could not parse LLM response")
                sources = result.get("sources", [])
            else:
                raise ValueError("LLM JSON response was not an object")
        except (json.JSONDecodeError, TypeError, ValueError):
            # Fallback: treat plain-text responses as the answer.
            answer = response_text
            sources = ["run_summary"]  # Best guess

        if not isinstance(answer, str):
            answer = str(answer)
        if not isinstance(sources, list):
            sources = []
        
        return {
            "answer": answer,
            "sources": sources
        }
    
    except Exception as e:
        return {
            "answer": f"Error during question answering: {str(e)}",
            "sources": []
        }


if __name__ == "__main__":
    # Test entity extraction
    test_questions = [
        "What happened to settlement setl_100002RP?",
        "Why was order_300008RP flagged as a phantom charge?",
        "Tell me about the exception with amount ₹5000",
        "How many exceptions are in this run?",
    ]
    
    print("Testing entity extraction:")
    print("=" * 70)
    for q in test_questions:
        entities = extract_entities(q)
        print(f"Q: {q}")
        print(f"   Entities: {entities}")
        print()
