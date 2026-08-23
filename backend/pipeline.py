"""
Unified Reconciliation Pipeline

Orchestrates all passes into ONE run, producing a single consolidated output:
  1. Tier 1 (exact) + Tier 2 (fuzzy) bank matching
  2. Duplicate-posting warnings
  3. Third-source DB <-> Razorpay reconciliation (phantom charge / ghost order)
  4. Tier 3 (LLM) resolution of genuine bank-matching leftovers
  5. Action-recommendation drafting on every exception (LLM)

Output: one JSON-serializable dict with "matches", "exceptions", and a
summary block -- this is what the backend API and dashboard will consume.

Steps 4 and 5 need GROQ_API_KEY set (via .env) and call the network.
If no key is present, the pipeline still runs and produces a valid result --
it just skips LLM resolution/action-drafting and marks those spots clearly,
so this script is always runnable, even offline.
"""

import os
import sys
import json
import re as _re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "matching"))

from matching.matching_engine import (
    load_data, build_batches, tier1_exact_match, tier2_fuzzy_match,
    flag_duplicate_warnings, extract_utr_candidates, AMOUNT_TOLERANCE_PAISE
)
from matching.db_reconciliation import load_orders, db_vs_razorpay_check

LLM_AVAILABLE = bool(os.environ.get("GROQ_API_KEY"))
if LLM_AVAILABLE:
    from matching.llm_reasoning import resolve_ambiguous_batch, draft_action_recommendation


def run_pipeline(base=None):
    if base is None:
        base = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
    settlement, ledger = load_data(base)
    orders = load_orders(base)
    batches = build_batches(settlement)

    # --- Bank-side reconciliation (Tiers 1 + 2) ---
    m1, rem_b1, rem_l1 = tier1_exact_match(batches, ledger)
    m2, rem_b2, rem_l2 = tier2_fuzzy_match(rem_b1, rem_l1)
    bank_matches = m1 + m2
    dup_warnings = flag_duplicate_warnings(bank_matches, ledger)

    exceptions = []

    # Duplicate-posting warnings (batch matched, but flagged anyway)
    duplicate_leftover_entry_ids = set()
    for w in dup_warnings:
        amt = 0
        if "credit of" in w["warning"]:
            try:
                amt = int(w["warning"].split("credit of ")[1].split("p ")[0])
            except Exception:
                amt = 0
        exceptions.append({
            "source": "bank_reconciliation",
            "exception_type": "duplicate_posting",
            "reference_id": w["settlement_id"],
            "matched_entry_id": w["matched_entry_id"],
            "amount_paise": amt,
            "detail": w["warning"],
            "recommended_action": None,
        })
        for eid in _re.findall(r"\['?(LDG\d+)", w["warning"]):
            duplicate_leftover_entry_ids.add(eid)

    # Genuine leftovers -- Tier 3 candidates
    for _, b in rem_b2.iterrows():
        candidates = rem_l2.to_dict("records")
        verdict = None
        if LLM_AVAILABLE and candidates:
            verdict = resolve_ambiguous_batch(
                {"settlement_id": b["settlement_id"], "settlement_utr": b["settlement_utr"],
                 "batch_total": int(b["batch_total"]), "settled_at": str(b["settled_at"])},
                candidates
            )
            if verdict.get("match"):
                matched_row = next((c for c in candidates if c["entry_id"] == verdict["entry_id"]), None)
                amount_gap_pct = None
                if matched_row is not None:
                    amount_gap_pct = abs(matched_row["credit"] - b["batch_total"]) / b["batch_total"] * 100

                GUARDRAIL_MAX_GAP_PCT = 5.0
                narration_has_evidence = False
                if matched_row is not None:
                    narr = str(matched_row.get("narration", "")).upper()
                    utr_fragment = b["settlement_utr"][-6:].upper()  # the random suffix, not the predictable prefix
                    narration_has_evidence = utr_fragment in narr  # must match THIS settlement's UTR specifically, not just any Razorpay-looking text

                if matched_row is not None and amount_gap_pct <= GUARDRAIL_MAX_GAP_PCT and narration_has_evidence:
                    bank_matches.append({
                        "settlement_id": b["settlement_id"],
                        "matched_entry_id": verdict["entry_id"],
                        "tier": "llm",
                        "confidence": verdict.get("confidence"),
                        "reason": verdict.get("reasoning"),
                    })
                    continue
                else:
                    verdict["reasoning"] = (
                        f"LLM proposed a match to {verdict['entry_id']} (confidence {verdict.get('confidence')}), "
                        f"but it was REJECTED by the deterministic guardrail: amount gap "
                        f"{amount_gap_pct:.1f}% / narration evidence found = {narration_has_evidence}. "
                        f"Original LLM reasoning: {verdict.get('reasoning')}"
                    )
        exceptions.append({
            "source": "bank_reconciliation",
            "exception_type": "unresolved_settlement",
            "reference_id": b["settlement_id"],
            "amount_paise": int(b["batch_total"]),
            "detail": (verdict.get("reasoning") if verdict
                       else "No Tier-1/Tier-2 match found; Tier-3 LLM resolution not run (no GROQ_API_KEY set)."),
            "recommended_action": None,
        })

    # Truly unexplained ledger rows -- re-apply unrelated-transaction filter.
    # A real UTR-like token has BOTH digits and letters mixed (e.g. "2026000020vxp0rj").
    # A pure digit string (phone/account number) is common in unrelated bank narrations
    # and should NOT be treated as UTR evidence.
    unmatched_batch_totals = [int(b["batch_total"]) for _, b in rem_b2.iterrows()]

    for _, l in rem_l2.iterrows():
        if l["entry_id"] in duplicate_leftover_entry_ids:
            continue  # already explained above, don't double-report

        raw_candidates = extract_utr_candidates(str(l["narration"]))
        has_utr_token = any(any(c.isalpha() for c in tok) for tok in raw_candidates)
        net_amount = int(l["credit"] - l["debit"])
        amount_plausible = any(abs(net_amount - t) <= AMOUNT_TOLERANCE_PAISE * 5 for t in unmatched_batch_totals)

        if not has_utr_token and not amount_plausible:
            continue  # correctly recognized as unrelated

        exceptions.append({
            "source": "bank_reconciliation",
            "exception_type": "unexplained_ledger_row",
            "reference_id": l["entry_id"],
            "amount_paise": abs(net_amount),
            "detail": f"Ledger row '{l['narration']}' (amount {net_amount/100:+.2f} rupees) has no linked settlement batch, "
                      f"and its narration/amount don't clearly rule out a Razorpay connection.",
            "recommended_action": None,
        })

    # --- Third source: DB <-> Razorpay reconciliation ---
    db_exceptions = db_vs_razorpay_check(orders, settlement)
    for e in db_exceptions:
        exceptions.append({
            "source": "db_reconciliation",
            "exception_type": e["exception_type"],
            "reference_id": e["order_id"],
            "amount_paise": e["severity_paise"],
            "detail": e["detail"],
            "recommended_action": None,
        })

    # --- Action-recommendation drafting (LLM) on every exception ---
    if LLM_AVAILABLE:
        for exc in exceptions:
            try:
                exc["recommended_action"] = draft_action_recommendation(exc)
            except Exception as e:
                exc["recommended_action"] = f"(action drafting failed: {e})"

    exceptions.sort(key=lambda e: -(e.get("amount_paise") or 0))

    total_batches = len(batches)
    matched_count = len(bank_matches)

    result = {
        "run_at": datetime.now().isoformat(),
        "llm_available": LLM_AVAILABLE,
        "summary": {
            "total_settlement_batches": total_batches,
            "matched_batches": matched_count,
            "match_rate_pct": round(matched_count / total_batches * 100, 1) if total_batches else 0,
            "total_exceptions": len(exceptions),
            "db_side_exceptions": len(db_exceptions),
        },
        "matches": bank_matches,
        "exceptions": exceptions,
    }
    return result


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result["summary"], indent=2))
    print(f"\nLLM available this run: {result['llm_available']}")
    print(f"\n=== EXCEPTIONS (sorted by amount at stake) ===")
    for e in result["exceptions"]:
        print(f"\n[{e['exception_type']}] {e['reference_id']} -- Rs{(e.get('amount_paise') or 0)/100:,.2f}")
        print(f"  {e['detail']}")
        if e.get("recommended_action"):
            print(f"  -> {e['recommended_action']}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "pipeline_output.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nFull output saved to {out_path}")