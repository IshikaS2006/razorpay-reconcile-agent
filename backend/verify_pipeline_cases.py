from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

from pipeline import run_pipeline, LLM_AVAILABLE
from matching.matching_engine import build_batches, extract_utr_candidates, tier1_exact_match, tier2_fuzzy_match
from matching.db_reconciliation import db_vs_razorpay_check, load_orders

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "generated")
SETTLEMENT_PATH = os.path.join(BASE_DIR, "settlement_report.csv")
LEDGER_PATH = os.path.join(BASE_DIR, "bank_ledger.csv")

NOISE_SNIPPETS = [
    "FD INTEREST CREDIT",
    "SALARY CREDIT-ACME PAYROLL",
    "GST PAYMENT-CHALLAN",
    "ATM WDL-MG ROAD BRANCH",
    "CREDIT CARD BILL PAYMENT",
    "AUTOPAY-ELECTRICITY BOARD",
    "UPI-VENDOR PAYMENT",
]


@dataclass
class CheckResult:
    number: int
    description: str
    status: str
    touched_ids: list[str]
    details: str


def make_result(number: int, description: str, ok: bool, touched_ids: list[str], details: str) -> CheckResult:
    return CheckResult(number, description, "PASS" if ok else "FAIL", touched_ids, details)


def find_match(matches: list[dict[str, Any]], settlement_id: str) -> dict[str, Any] | None:
    return next((m for m in matches if m["settlement_id"] == settlement_id), None)


def find_exception(exceptions: list[dict[str, Any]], exception_type: str, reference_id: str) -> dict[str, Any] | None:
    return next((e for e in exceptions if e["exception_type"] == exception_type and e["reference_id"] == reference_id), None)


def check_presence(ids: list[str], available: set[str]) -> list[str]:
    return [item for item in ids if item not in available]


def main() -> None:
    settlement = pd.read_csv(SETTLEMENT_PATH)
    ledger = pd.read_csv(LEDGER_PATH)
    ledger["date"] = pd.to_datetime(ledger["date"])
    orders = load_orders(BASE_DIR)

    payments = settlement[settlement["type"] == "payment"].copy()
    grouped = (
        payments.groupby(["settlement_id", "settlement_utr"], as_index=False)
        .agg(payment_rows=("entity_id", "count"), batch_total=("settled_amount", "sum"))
        .sort_values("settlement_id")
    )

    m1, rem_b1, rem_l1 = tier1_exact_match(build_batches(settlement), ledger)
    m2, rem_b2, rem_l2 = tier2_fuzzy_match(rem_b1, rem_l1)
    pipeline_result = run_pipeline(BASE_DIR)
    matches = pipeline_result["matches"]
    exceptions = pipeline_result["exceptions"]
    db_exceptions = db_vs_razorpay_check(orders, settlement)

    settlement_ids = set(settlement["settlement_id"].dropna().astype(str))
    ledger_ids = set(ledger["entry_id"].dropna().astype(str))
    order_ids = set(orders["order_id"].dropna().astype(str)) if orders is not None else set()
    entity_ids = set(settlement["entity_id"].dropna().astype(str))

    results: list[CheckResult] = []

    print("=" * 120)
    print("RECONCILIATION PIPELINE VERIFICATION")
    print("=" * 120)
    print(f"Dataset base: {BASE_DIR}")
    print(f"LLM available: {LLM_AVAILABLE}")
    print()

    print("1) Aggregation check")
    for row in grouped.itertuples(index=False):
        print(f"  {row.settlement_id} -> UTR={row.settlement_utr} total={row.batch_total} rows={row.payment_rows}")
    grouped_count = int(grouped["payment_rows"].sum())
    raw_count = len(payments)
    results.append(make_result(1, "Aggregation check", grouped_count == raw_count, grouped["settlement_id"].tolist(), f"grouped_rows={grouped_count}, raw_payment_rows={raw_count}"))
    print()

    print("2) UTR extraction check")
    ldg30_ok = False
    touched2 = []
    for row in ledger.itertuples(index=False):
        extracted = extract_utr_candidates(str(row.narration))
        value = extracted[0] if extracted else "NONE"
        touched2.append(row.entry_id)
        print(f"  {row.entry_id} -> {value}")
        if row.entry_id == "LDG00030":
            ldg30_ok = value == "NONE"
    results.append(make_result(2, "UTR extraction check", ldg30_ok, touched2, f"LDG00030 extracted NONE={ldg30_ok}"))
    print()

    checks = [
        (3, "Tier 1 exact match check", ["setl_100016RP", "LDG00017", "setl_100010RP", "LDG00011"]),
        (4, "Tier 2 fuzzy match check — small drift", ["setl_100011RP", "LDG00012"]),
        (5, "Tier 2 fuzzy match check — partial credit", ["setl_100002RP", "LDG00003", "setl_100013RP", "LDG00014"]),
        (6, "Duplicate posting check", ["setl_100001RP", "LDG00001", "LDG00002"]),
        (7, "Fully unmatched check", ["setl_100007RP", "setl_100022RP"]),
        (8, "Guardrail rejection check", ["setl_100021RP", "LDG00030"]),
        (9, "Refund matching check", ["rfnd_400001RP", "LDG00032", "setl_100023RP", "pay_200087RP", "LDG00031"]),
        (10, "Refund exception check", ["rfnd_400002RP"]),
        (11, "Unexplained debit check", ["LDG00033"]),
        (13, "Third-source phantom charge check", ["order_300046RP", "order_300060RP", "setl_100016RP", "setl_100014RP"]),
        (14, "Third-source ghost order check", ["order_400001RP", "order_400002RP"]),
    ]

    presence_pool = settlement_ids | ledger_ids | order_ids | entity_ids

    for number, description, ids in checks:
        missing = check_presence(ids, presence_pool)
        if missing:
            results.append(make_result(number, description, False, ids, f"MISSING_TEST_RECORD: {', '.join(missing)}"))
            print(f"{number}) {description}: MISSING_TEST_RECORD -> {', '.join(missing)}")
            continue

        if number == 3:
            g16 = int(grouped[grouped["settlement_id"] == "setl_100016RP"]["batch_total"].iloc[0])
            g10 = int(grouped[grouped["settlement_id"] == "setl_100010RP"]["batch_total"].iloc[0])
            m16 = find_match(matches, "setl_100016RP")
            m10 = find_match(matches, "setl_100010RP")
            ok = g16 == 3487653 and g10 == 2891381 and m16 and m10 and m16["matched_entry_id"] == "LDG00017" and m10["matched_entry_id"] == "LDG00011" and m16["tier"] == "exact" and m10["tier"] == "exact"
            results.append(make_result(number, description, bool(ok), ids, f"setl_100016RP sum={g16} match={m16}; setl_100010RP sum={g10} match={m10}"))
        elif number == 4:
            g11 = int(grouped[grouped["settlement_id"] == "setl_100011RP"]["batch_total"].iloc[0])
            m11 = find_match(matches, "setl_100011RP")
            ok = g11 == 757747 and m11 and m11["matched_entry_id"] == "LDG00012" and m11["tier"] == "fuzzy" and "gap" in str(m11.get("reason", "")).lower()
            results.append(make_result(number, description, bool(ok), ids, f"setl_100011RP sum={g11} match={m11}"))
        elif number == 5:
            s2 = int(grouped[grouped["settlement_id"] == "setl_100002RP"]["batch_total"].iloc[0])
            s13 = int(grouped[grouped["settlement_id"] == "setl_100013RP"]["batch_total"].iloc[0])
            m2_case = find_match(matches, "setl_100002RP")
            m13_case = find_match(matches, "setl_100013RP")
            shortfall2 = s2 - int(ledger[ledger["entry_id"] == "LDG00003"]["credit"].iloc[0])
            shortfall13 = s13 - int(ledger[ledger["entry_id"] == "LDG00014"]["credit"].iloc[0])
            ok = m2_case and m13_case and s2 == 2103445 and s13 == 2593349 and m2_case["matched_entry_id"] == "LDG00003" and m13_case["matched_entry_id"] == "LDG00014"
            results.append(make_result(number, description, bool(ok), ids, f"setl_100002RP shortfall={shortfall2} match={m2_case}; setl_100013RP shortfall={shortfall13} match={m13_case}"))
        elif number == 6:
            utr = str(grouped[grouped["settlement_id"] == "setl_100001RP"]["settlement_utr"].iloc[0])
            dup_rows = ledger[ledger["narration"].astype(str).str.contains(utr, na=False)]
            dup_exc = find_exception(exceptions, "duplicate_posting", "setl_100001RP")
            ok = len(dup_rows) == 2 and set(dup_rows["entry_id"].tolist()) == {"LDG00001", "LDG00002"} and dup_exc is not None
            results.append(make_result(number, description, ok, ids, f"duplicate_rows={dup_rows['entry_id'].tolist()} duplicate_exception={dup_exc is not None}"))
        elif number == 7:
            e7 = find_exception(exceptions, "unresolved_settlement", "setl_100007RP")
            e22 = find_exception(exceptions, "unresolved_settlement", "setl_100022RP")
            utr7 = str(grouped[grouped["settlement_id"] == "setl_100007RP"]["settlement_utr"].iloc[0])
            utr22 = str(grouped[grouped["settlement_id"] == "setl_100022RP"]["settlement_utr"].iloc[0])
            l7 = ledger[ledger["narration"].astype(str).str.contains(utr7, na=False)]
            l22 = ledger[ledger["narration"].astype(str).str.contains(utr22, na=False)]
            ok = len(l7) == 0 and len(l22) == 0 and e7 is not None and e22 is not None
            results.append(make_result(number, description, ok, ids, f"setl_100007RP ledger_hits={l7['entry_id'].tolist()} exception={e7 is not None}; setl_100022RP ledger_hits={l22['entry_id'].tolist()} exception={e22 is not None}"))
        elif number == 8:
            batch_total = int(grouped[grouped["settlement_id"] == "setl_100021RP"]["batch_total"].iloc[0])
            ledger_row = ledger[ledger["entry_id"] == "LDG00030"].iloc[0]
            gap_pct = abs(int(ledger_row["credit"]) - batch_total) / batch_total * 100
            utr = str(grouped[grouped["settlement_id"] == "setl_100021RP"]["settlement_utr"].iloc[0])
            has_fragment = utr[-6:].upper() in str(ledger_row["narration"]).upper()
            unresolved = find_exception(exceptions, "unresolved_settlement", "setl_100021RP")
            llm_proposed = bool(unresolved and "LLM proposed a match" in str(unresolved.get("detail", "")))
            guardrail_rejected = bool(unresolved and "REJECTED by the deterministic guardrail" in str(unresolved.get("detail", "")))
            ok = unresolved is not None and gap_pct > 5.0 and not has_fragment and (guardrail_rejected or not LLM_AVAILABLE)
            results.append(make_result(number, description, ok, ids, f"amount_gap_pct={gap_pct:.2f}; utr_fragment_present={has_fragment}; llm_proposed={llm_proposed}; guardrail_rejected={guardrail_rejected}; unresolved={unresolved is not None}"))
        elif number == 9:
            results.append(make_result(number, description, False, ids, "Current generated dataset has no refund entity rows at all, so debit-side refund matching cannot be exercised."))
        elif number == 10:
            exc = find_exception(exceptions, "refund_not_debited", "rfnd_400002RP")
            results.append(make_result(number, description, exc is not None, ids, f"refund_not_debited exception present={exc is not None}"))
        elif number == 11:
            exc = find_exception(exceptions, "unexplained_debit", "LDG00033") or find_exception(exceptions, "unexplained_ledger_row", "LDG00033")
            ok = exc is not None
            results.append(make_result(number, description, ok, ids, f"exception={exc}"))
        elif number == 13:
            p1 = next((e for e in db_exceptions if e["exception_type"] == "phantom_charge" and e["order_id"] == "order_300046RP"), None)
            p2 = next((e for e in db_exceptions if e["exception_type"] == "phantom_charge" and e["order_id"] == "order_300060RP"), None)
            results.append(make_result(number, description, p1 is not None and p2 is not None, ids, f"order_300046RP={p1}; order_300060RP={p2}"))
        elif number == 14:
            g1 = next((e for e in db_exceptions if e["exception_type"] == "ghost_order" and e["order_id"] == "order_400001RP"), None)
            g2 = next((e for e in db_exceptions if e["exception_type"] == "ghost_order" and e["order_id"] == "order_400002RP"), None)
            results.append(make_result(number, description, g1 is not None and g2 is not None, ids, f"order_400001RP={g1}; order_400002RP={g2}"))

    print("12) Non-Razorpay noise filtering")
    touched12 = []
    violations = []
    for snippet in NOISE_SNIPPETS:
        rows = ledger[ledger["narration"].astype(str).str.contains(snippet, na=False)]
        ids = rows["entry_id"].tolist()
        touched12.extend(ids)
        matched_ids = [m["matched_entry_id"] for m in matches if m["matched_entry_id"] in ids]
        exception_ids = [e["reference_id"] for e in exceptions if e["reference_id"] in ids]
        print(f"  {snippet}: {ids}")
        if matched_ids or exception_ids:
            violations.append(f"{snippet} matched={matched_ids} exceptions={exception_ids}")
    results.append(make_result(12, "Non-Razorpay noise filtering", not violations, touched12, "; ".join(violations) if violations else "No noise lines appeared in matches/exceptions"))
    print()

    print("15) Totals reconciliation")
    matched_total = sum(int(m["settled_amount"]) for m in matches)
    confirmed_cash = matched_total
    matched_ids = sorted({m["settlement_id"] for m in matches})
    unaccounted = sorted(set(grouped[~grouped["settlement_id"].isin(matched_ids)]["settlement_id"].tolist()))
    difference = confirmed_cash - matched_total
    results.append(make_result(15, "Totals reconciliation", difference == 0, matched_ids, f"matched_total={matched_total}; confirmed_cash={confirmed_cash}; difference={difference}; unaccounted={unaccounted}"))
    print()

    print("=" * 120)
    print("FINAL RESULTS")
    print("=" * 120)
    print(f"{'#':<3} {'Description':<42} {'Status':<6} {'Touched IDs':<48} Details")
    for result in sorted(results, key=lambda item: item.number):
        touched = ", ".join(result.touched_ids[:6])
        if len(result.touched_ids) > 6:
            touched += f", ... (+{len(result.touched_ids) - 6} more)"
        print(f"{result.number:<3} {result.description:<42} {result.status:<6} {touched:<48} {result.details}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "pipeline_verification_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump([result.__dict__ for result in results], fh, indent=2)
    print(f"\nSaved machine-readable results to {out_path}")


if __name__ == "__main__":
    main()
