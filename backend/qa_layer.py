"""
QA Layer -- tool-based question answering over one reconciliation run.

This module follows a constrained agent loop:
1. Build a toolset over persisted run data
2. Send the user's question to Groq using OpenAI-compatible tool calling
3. Execute requested tools locally against run data
4. Repeat up to MAX_TOOL_ROUNDS
5. Return a grounded answer plus an audit trail of tool calls/results

If no GROQ API key is configured, the module still returns a deterministic,
retrieval-only answer and the same structured audit format.
"""

import json
import os
import re
from typing import Any, cast

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from models import BatchRun, Exception_, Investigation, Match

load_dotenv()

LLM_AVAILABLE = bool(os.environ.get("GROQ_API_KEY"))
MAX_TOOL_ROUNDS = 4
MODEL = "openai/gpt-oss-120b"

Groq = None
if LLM_AVAILABLE:
    from groq import Groq as _Groq
    Groq = _Groq


def _client():
    if Groq is None:
        raise RuntimeError("Groq client is unavailable")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")
    return Groq(api_key=api_key)


def _fmt_rupees_from_paise(paise: int | None) -> str:
    if paise is None:
        return "—"
    return f"₹{paise / 100:,.2f}"


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _parse_json_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        return json.loads(raw)
    return {}


def extract_entities(question: str) -> dict[str, list[Any]]:
    entities = {
        "settlement_ids": [],
        "order_ids": [],
        "amounts": [],
    }

    settlement_matches = re.findall(r"\bsetl_[A-Za-z0-9_]+\b", question, re.IGNORECASE)
    order_matches = re.findall(r"\border_[A-Za-z0-9_]+\b", question, re.IGNORECASE)

    entities["settlement_ids"] = sorted(set(settlement_matches))
    entities["order_ids"] = sorted(set(order_matches))

    question_for_amounts = re.sub(r"\b(setl|order)_[A-Za-z0-9_]+\b", "", question, flags=re.IGNORECASE)
    amount_matches = re.findall(r"(?:₹|INR\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)", question_for_amounts, re.IGNORECASE)
    parsed_amounts = []
    for match in amount_matches:
        cleaned = match.replace(",", "")
        try:
            if "." in cleaned:
                parsed_amounts.append(int(round(float(cleaned) * 100)))
            else:
                whole = int(cleaned)
                parsed_amounts.append(whole * 100 if whole < 1_000_000 else whole)
        except ValueError:
            continue
    entities["amounts"] = sorted(set(parsed_amounts))
    return entities


def _match_to_dict(m: Match) -> dict[str, Any]:
    return {
        "id": m.id,
        "settlement_id": m.settlement_id,
        "matched_entry_id": m.matched_entry_id,
        "settled_amount": m.settled_amount,
        "tier": m.tier,
        "confidence": m.confidence,
        "reason": m.reason,
        "status": m.status,
    }


def _exception_to_dict(e: Exception_) -> dict[str, Any]:
    return {
        "id": e.id,
        "reference_id": e.reference_id,
        "exception_type": e.exception_type,
        "source": e.source,
        "amount_paise": e.amount_paise,
        "detail": e.detail,
        "recommended_action": e.recommended_action,
        "status": e.status,
    }


def _investigation_to_dict(i: Investigation) -> dict[str, Any]:
    evidence = []
    raw_evidence = i.evidence_used if isinstance(i.evidence_used, str) else "[]"
    try:
        evidence = json.loads(raw_evidence)
    except (TypeError, json.JSONDecodeError):
        evidence = []
    return {
        "id": i.id,
        "exception_reference_id": i.exception_reference_id,
        "status": i.status,
        "explanation": i.explanation,
        "confidence": i.confidence,
        "evidence_used": evidence,
        "reasoning_chain": i.reasoning_chain,
    }


def query_run_data(
    run_id: int,
    db_session: Session,
    settlement_ids: list[str] | None = None,
    order_ids: list[str] | None = None,
    amounts: list[int] | None = None,
) -> dict[str, Any]:
    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found"}

    matches_query = db_session.query(Match).filter(Match.run_id == run_id)
    if settlement_ids:
        matches_query = matches_query.filter(Match.settlement_id.in_(settlement_ids))

    exceptions_query = db_session.query(Exception_).filter(Exception_.run_id == run_id)
    if settlement_ids or order_ids:
        filter_ids = (settlement_ids or []) + (order_ids or [])
        exceptions_query = exceptions_query.filter(Exception_.reference_id.in_(filter_ids))
    if amounts:
        target = amounts[0]
        tolerance = max(5_000, int(target * 0.05))
        exceptions_query = exceptions_query.filter(Exception_.amount_paise.between(target - tolerance, target + tolerance))

    investigations_query = db_session.query(Investigation).filter(Investigation.run_id == run_id)
    if settlement_ids or order_ids:
        filter_ids = (settlement_ids or []) + (order_ids or [])
        investigations_query = investigations_query.filter(Investigation.exception_reference_id.in_(filter_ids))

    return {
        "run_summary": {
            "run_id": run.id,
            "run_at": run.run_at.isoformat() if getattr(run, "run_at", None) else None,
            "total_settlement_batches": run.total_settlement_batches,
            "matched_batches": run.matched_batches,
            "match_rate_pct": run.match_rate_pct,
            "total_exceptions": run.total_exceptions,
            "db_side_exceptions": run.db_side_exceptions,
            "llm_available": run.llm_available,
        },
        "matches": [_match_to_dict(m) for m in matches_query.all()],
        "exceptions": [_exception_to_dict(e) for e in exceptions_query.all()],
        "investigations": [_investigation_to_dict(i) for i in investigations_query.all()],
    }


def get_record(run_id: int, reference_id: str, db_session: Session) -> dict[str, Any]:
    match = db_session.query(Match).filter(Match.run_id == run_id, Match.settlement_id == reference_id).first()
    exception = db_session.query(Exception_).filter(Exception_.run_id == run_id, Exception_.reference_id == reference_id).first()
    investigation = db_session.query(Investigation).filter(
        Investigation.run_id == run_id,
        Investigation.exception_reference_id == reference_id,
    ).order_by(Investigation.investigated_at.desc()).first()

    return {
        "reference_id": reference_id,
        "match": _match_to_dict(match) if match else None,
        "exception": _exception_to_dict(exception) if exception else None,
        "investigation": _investigation_to_dict(investigation) if investigation else None,
    }


def get_bank_line(run_id: int, line_id: str, db_session: Session) -> dict[str, Any]:
    match = db_session.query(Match).filter(Match.run_id == run_id, Match.matched_entry_id == line_id).first()
    return {
        "line_id": line_id,
        "matched_record": _match_to_dict(match) if match else None,
        "note": "Only persisted matched bank-line references are available in the current schema.",
    }


def search_by_amount(run_id: int, amount_paise: int, db_session: Session) -> dict[str, Any]:
    tolerance = max(5_000, int(amount_paise * 0.05))
    matches = db_session.query(Match).filter(
        Match.run_id == run_id,
        Match.settled_amount.between(amount_paise - tolerance, amount_paise + tolerance),
    ).all()
    exceptions = db_session.query(Exception_).filter(
        Exception_.run_id == run_id,
        Exception_.amount_paise.between(amount_paise - tolerance, amount_paise + tolerance),
    ).all()
    return {
        "amount_paise": amount_paise,
        "tolerance_paise": tolerance,
        "matches": [_match_to_dict(m) for m in matches],
        "exceptions": [_exception_to_dict(e) for e in exceptions],
    }


def get_tax_breakdown(run_id: int, reference_id: str | None, db_session: Session) -> dict[str, Any]:
    query = db_session.query(Exception_).filter(
        Exception_.run_id == run_id,
        Exception_.exception_type == "tax_line_mismatch",
    )
    if reference_id:
        query = query.filter(Exception_.reference_id == reference_id)
    rows = query.all()
    return {
        "reference_id": reference_id,
        "tax_exceptions": [_exception_to_dict(e) for e in rows],
    }


def get_history(run_id: int, reference_id: str, db_session: Session) -> dict[str, Any]:
    investigations = db_session.query(Investigation).filter(
        Investigation.run_id == run_id,
        Investigation.exception_reference_id == reference_id,
    ).order_by(Investigation.investigated_at.asc()).all()
    exception = db_session.query(Exception_).filter(
        Exception_.run_id == run_id,
        Exception_.reference_id == reference_id,
    ).first()
    return {
        "reference_id": reference_id,
        "exception": _exception_to_dict(exception) if exception else None,
        "history": [_investigation_to_dict(i) for i in investigations],
    }


def list_exceptions(run_id: int, status: str | None, exception_type: str | None, db_session: Session) -> dict[str, Any]:
    query = db_session.query(Exception_).filter(Exception_.run_id == run_id)
    if status:
        query = query.filter(Exception_.status == status)
    if exception_type:
        query = query.filter(Exception_.exception_type == exception_type)
    rows = query.all()
    return {
        "count": len(rows),
        "exceptions": [_exception_to_dict(e) for e in rows],
    }


def aggregate_unreconciled(run_id: int, db_session: Session) -> dict[str, Any]:
    exceptions = db_session.query(Exception_).filter(Exception_.run_id == run_id).all()
    total_paise = sum(int(cast(Any, e.amount_paise) or 0) for e in exceptions)
    by_type: dict[str, dict[str, Any]] = {}
    for exc in exceptions:
        exc_type = str(exc.exception_type)
        amount_paise = int(cast(Any, exc.amount_paise) or 0)
        bucket = by_type.setdefault(exc_type, {"count": 0, "total_paise": 0})
        bucket["count"] += 1
        bucket["total_paise"] += amount_paise
    return {
        "total_unreconciled_paise": total_paise,
        "total_unreconciled_rupees": round(total_paise / 100, 2),
        "by_type": by_type,
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_record",
            "description": "Get one reconciliation record by settlement_id or order/reference_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": "string"},
                },
                "required": ["reference_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bank_line",
            "description": "Get persisted information about a bank ledger line by line_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "line_id": {"type": "string"},
                },
                "required": ["line_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_amount",
            "description": "Search matches and exceptions by amount in paise with tolerance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_paise": {"type": "integer"},
                },
                "required": ["amount_paise"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tax_breakdown",
            "description": "List tax mismatch exception details, optionally scoped to one reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": ["string", "null"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_history",
            "description": "Get investigation history for one reference ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": "string"},
                },
                "required": ["reference_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_exceptions",
            "description": "List exceptions for the run, optionally filtered by status or type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": ["string", "null"]},
                    "exception_type": {"type": ["string", "null"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_unreconciled",
            "description": "Get total unreconciled amount and counts grouped by exception type.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def _execute_tool(name: str, args: dict[str, Any], run_id: int, db_session: Session) -> dict[str, Any]:
    if name == "get_record":
        return get_record(run_id, args["reference_id"], db_session)
    if name == "get_bank_line":
        return get_bank_line(run_id, args["line_id"], db_session)
    if name == "search_by_amount":
        return search_by_amount(run_id, int(args["amount_paise"]), db_session)
    if name == "get_tax_breakdown":
        return get_tax_breakdown(run_id, args.get("reference_id"), db_session)
    if name == "get_history":
        return get_history(run_id, args["reference_id"], db_session)
    if name == "list_exceptions":
        return list_exceptions(run_id, args.get("status"), args.get("exception_type"), db_session)
    if name == "aggregate_unreconciled":
        return aggregate_unreconciled(run_id, db_session)
    return {"error": f"Unknown tool: {name}"}


def _fallback_answer(question: str, run_id: int, db_session: Session) -> dict[str, Any]:
    entities = extract_entities(question)
    audit_trail: list[dict[str, Any]] = []

    if entities["settlement_ids"] or entities["order_ids"]:
        reference_id = (entities["settlement_ids"] or entities["order_ids"])[0]
        result = get_record(run_id, reference_id, db_session)
        audit_trail.append({"tool": "get_record", "arguments": {"reference_id": reference_id}, "result": result})

        exception = result.get("exception")
        match = result.get("match")
        if exception:
            answer = (
                f"Reference `{reference_id}` is flagged as `{exception['exception_type']}`"
                f" for {_fmt_rupees_from_paise(exception.get('amount_paise'))}. "
                f"Reason: {exception.get('detail') or 'No detail recorded.'}"
            )
            sources = [reference_id]
        elif match:
            answer = (
                f"Reference `{reference_id}` matched bank line `{match.get('matched_entry_id')}` "
                f"via `{match.get('tier')}` matching for {_fmt_rupees_from_paise(match.get('settled_amount'))}."
            )
            sources = [reference_id, match.get("matched_entry_id")]
        else:
            answer = f"I don't have a persisted record for `{reference_id}` in run {run_id}."
            sources = []
        return {"answer": answer, "sources": [s for s in sources if s], "audit_trail": audit_trail, "tool_rounds": len(audit_trail)}

    if entities["amounts"]:
        amount_paise = entities["amounts"][0]
        result = search_by_amount(run_id, amount_paise, db_session)
        audit_trail.append({"tool": "search_by_amount", "arguments": {"amount_paise": amount_paise}, "result": result})
        answer = (
            f"Found {len(result['matches'])} match(es) and {len(result['exceptions'])} exception(s) "
            f"near {_fmt_rupees_from_paise(amount_paise)} in run {run_id}."
        )
        sources = [*(m["settlement_id"] for m in result["matches"][:5]), *(e["reference_id"] for e in result["exceptions"][:5])]
        return {"answer": answer, "sources": sources, "audit_trail": audit_trail, "tool_rounds": 1}

    result = aggregate_unreconciled(run_id, db_session)
    audit_trail.append({"tool": "aggregate_unreconciled", "arguments": {}, "result": result})
    answer = (
        f"Run {run_id} has total unreconciled value {_fmt_rupees_from_paise(result['total_unreconciled_paise'])} "
        f"across {sum(bucket['count'] for bucket in result['by_type'].values())} exception record(s)."
    )
    return {"answer": answer, "sources": ["run_summary"], "audit_trail": audit_trail, "tool_rounds": 1}


def _system_prompt(run_id: int) -> str:
    return (
        "You are a finance reconciliation QA agent. "
        "Answer only from tool results retrieved for this run. "
        "Cite reference IDs or line IDs when stating facts. "
        "If a fact is not retrieved, say you do not have data on it. "
        "Label any estimate or forecast explicitly as an estimate. "
        f"You may use tools for run {run_id} only. Use at most {MAX_TOOL_ROUNDS} tool rounds."
    )


def answer_question(question: str, run_id: int, db_session: Session) -> dict[str, Any]:
    run = db_session.query(BatchRun).filter(BatchRun.id == run_id).first()
    if not run:
        return {"answer": f"Run {run_id} not found", "sources": [], "audit_trail": [], "tool_rounds": 0}

    if not LLM_AVAILABLE:
        return _fallback_answer(question, run_id, db_session)

    client = _client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(run_id)},
        {"role": "user", "content": question},
    ]
    audit_trail: list[dict[str, Any]] = []

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = client.chat.completions.create(
                model=MODEL,
                messages=cast(Any, messages),
                tools=cast(Any, TOOLS),
                tool_choice="auto",
                temperature=0.1,
                max_tokens=500,
            )
            message = response.choices[0].message

            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                assistant_message = {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [],
                }
                for call in tool_calls:
                    assistant_message["tool_calls"].append({
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    })
                messages.append(assistant_message)

                for call in tool_calls:
                    args = _parse_json_arguments(call.function.arguments)
                    result = _execute_tool(call.function.name, args, run_id, db_session)
                    audit_trail.append({
                        "tool": call.function.name,
                        "arguments": args,
                        "result": result,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": _safe_json(result),
                    })
                continue

            content = message.content or ""
            answer = content
            sources = sorted(set(re.findall(r"\b(?:setl|order|LDG|run_summary)[A-Za-z0-9_\-]*\b", content, re.IGNORECASE)))

            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    answer = parsed.get("answer", answer)
                    raw_sources = parsed.get("sources", sources)
                    if isinstance(raw_sources, list):
                        sources = [str(s) for s in raw_sources]
            except (TypeError, json.JSONDecodeError):
                pass

            return {
                "answer": answer,
                "sources": sources,
                "audit_trail": audit_trail,
                "tool_rounds": min(MAX_TOOL_ROUNDS, len(audit_trail)),
            }

        fallback = _fallback_answer(question, run_id, db_session)
        fallback["answer"] = (
            "I reached the maximum tool rounds before the model finalized an answer. "
            + fallback["answer"]
        )
        fallback["audit_trail"] = audit_trail + fallback["audit_trail"]
        fallback["tool_rounds"] = MAX_TOOL_ROUNDS
        return fallback
    except Exception as e:
        fallback = _fallback_answer(question, run_id, db_session)
        fallback["answer"] = f"Error during question answering: {e}. {fallback['answer']}"
        fallback["audit_trail"] = audit_trail + fallback["audit_trail"]
        fallback["tool_rounds"] = len(audit_trail)
        return fallback
