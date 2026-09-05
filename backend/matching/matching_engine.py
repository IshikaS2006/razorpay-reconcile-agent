"""
Reconciliation Agent -- Matching Engine (Tiers 1 & 2)

Tier 1 (exact):  same UTR present in narration, amount matches exactly, same date
Tier 2 (fuzzy):  amount within tolerance, date within a few days, OR UTR is
                  present but reformatted inside a messier narration string
Tier 3 (LLM):    reserved for genuine leftovers -- see llm_reasoning.py (separate file,
                  needs an Anthropic API key to actually run, stubbed here for now)

Input:  settlement_report.csv (grouped into batches by settlement_id)
        bank_ledger.csv        (raw bank statement lines)
Output: a per-batch verdict: matched (tier1/tier2), unmatched (goes to tier 3),
        plus a list of ledger rows that don't belong to any batch at all
"""

import pandas as pd
import re

AMOUNT_TOLERANCE_PAISE = 2000   # ~ up to Rs 20 of extra bank charges/rounding
DATE_TOLERANCE_DAYS = 3

def load_data(base="/home/claude"):
    settlement_path = f"{base}/settlement_report.csv"
    fallback_settlement_path = f"{base}/settlement_report (1).csv"
    if not pd.io.common.file_exists(settlement_path) and pd.io.common.file_exists(fallback_settlement_path):
        settlement_path = fallback_settlement_path
    settlement = pd.read_csv(settlement_path)
    ledger = pd.read_csv(f"{base}/bank_ledger.csv")
    ledger["date"] = pd.to_datetime(ledger["date"])
    return settlement, ledger

def build_batches(settlement: pd.DataFrame) -> pd.DataFrame:
    """Group payment rows into settlement batches before matching to bank payouts."""
    payments = settlement[settlement["type"].astype(str).str.lower() == "payment"].copy()
    batches = payments.groupby(["settlement_id", "settlement_utr", "settled_at"]).agg(
        n_payments=("entity_id", "count"),
        batch_total=("settled_amount", "sum"),
    ).reset_index()
    batches["settled_at"] = pd.to_datetime(batches["settled_at"])
    return batches

def extract_utr_candidates(narration: str):
    """Pull UTR-shaped tokens from narration, ignoring plain numeric noise."""
    text = str(narration or "").lower()
    tokens = re.findall(r"[0-9]{6,}[a-z][a-z0-9]*", text)
    dashed = re.findall(r"[0-9]{4,}-[0-9]{3,}", text)
    normalized_dashed = [d.replace("-", "") for d in dashed]
    return tokens + normalized_dashed

def tier1_exact_match(batches: pd.DataFrame, ledger: pd.DataFrame):
    matches, remaining_batches = [], []
    used_ledger_ids = set()
    ordered_ledger = ledger.sort_values(by=["date", "entry_id"]).reset_index(drop=True)

    for _, b in batches.iterrows():
        found = None
        for _, l in ordered_ledger.iterrows():
            if l["entry_id"] in used_ledger_ids:
                continue
            if b["settlement_utr"] in str(l["narration"]) and \
               l["credit"] == b["batch_total"] and \
               l["date"] == b["settled_at"]:
                found = l
                break
        if found is not None:
            used_ledger_ids.add(found["entry_id"])
            matches.append({
                "settlement_id": b["settlement_id"],
                "settled_amount": int(b["batch_total"]),
                "matched_entry_id": found["entry_id"],
                "tier": "exact",
                "confidence": 1.0,
                "reason": "UTR present, amount exact, date exact",
            })
        else:
            remaining_batches.append(b)

    remaining_ledger = ledger[~ledger["entry_id"].isin(used_ledger_ids)]
    return matches, pd.DataFrame(remaining_batches), remaining_ledger

def tier2_fuzzy_match(batches: pd.DataFrame, ledger: pd.DataFrame):
    matches, still_remaining = [], []
    used_ledger_ids = set()
    ordered_ledger = ledger.sort_values(by=["date", "entry_id"]).reset_index(drop=True)

    for _, b in batches.iterrows():
        best = None
        best_score = -1
        for _, l in ordered_ledger.iterrows():
            if l["entry_id"] in used_ledger_ids:
                continue

            narration = str(l["narration"])
            amount_diff = abs(int(l["credit"]) - int(b["batch_total"]))
            date_diff = abs((l["date"] - b["settled_at"]).days)
            utr_candidates = extract_utr_candidates(narration)
            utr_hit = b["settlement_utr"] in utr_candidates or b["settlement_utr"] in narration.lower()
            if not utr_hit:
                continue

            reason = None
            subtype = None
            score = -1
            gap_ratio = amount_diff / int(b["batch_total"]) if int(b["batch_total"]) else 0

            if "PARTIAL" in narration.upper() and int(l["credit"]) < int(b["batch_total"]):
                subtype = "settlement_partial_credit"
                reason = (
                    f"UTR exact, narration shows PARTIAL, expected {int(b['batch_total'])}p, "
                    f"actual {int(l['credit'])}p, shortfall {int(b['batch_total']) - int(l['credit'])}p"
                )
                score = 0.88
            elif gap_ratio <= 0.01 and date_diff <= DATE_TOLERANCE_DAYS:
                subtype = "tax_line_mismatch"
                reason = (
                    f"UTR exact, small amount gap {amount_diff}p ({gap_ratio * 100:.2f}%), "
                    f"flagged for review instead of exact match"
                )
                score = 0.91 - (date_diff * 0.02)
            elif amount_diff <= AMOUNT_TOLERANCE_PAISE and date_diff <= DATE_TOLERANCE_DAYS:
                subtype = "date_lag" if date_diff > 0 else "amount_tolerance"
                reason = f"UTR exact, amount gap {amount_diff}p, date gap {date_diff}d"
                score = 0.84 - (amount_diff / 100000) - (date_diff * 0.02)
            elif "PARTIAL" in narration.upper() and int(l["credit"]) < int(b["batch_total"]):
                subtype = "settlement_partial_credit"
                reason = (
                    f"UTR exact, narration shows PARTIAL, expected {int(b['batch_total'])}p, "
                    f"actual {int(l['credit'])}p, shortfall {int(b['batch_total']) - int(l['credit'])}p"
                )
                score = 0.88
            elif date_diff <= DATE_TOLERANCE_DAYS:
                subtype = "reference_mismatch"
                reason = f"UTR recognizable in narration, amount/date not exact; amount gap {amount_diff}p, date gap {date_diff}d"
                score = 0.7 - (date_diff * 0.02)

            if reason is not None and score > best_score:
                best_score, best = score, (l, reason, subtype, amount_diff)

        if best is not None:
            l, reason, subtype, amount_diff = best
            used_ledger_ids.add(l["entry_id"])
            matches.append({
                "settlement_id": b["settlement_id"],
                "settled_amount": int(b["batch_total"]),
                "matched_entry_id": l["entry_id"],
                "tier": "fuzzy",
                "confidence": round(best_score, 2),
                "reason": reason,
                "match_subtype": subtype,
                "expected_amount_paise": int(b["batch_total"]),
                "actual_amount_paise": int(l["credit"]),
                "amount_gap_paise": int(amount_diff),
            })
        else:
            still_remaining.append(b)

    remaining_ledger = ledger[~ledger["entry_id"].isin(used_ledger_ids)]
    return matches, pd.DataFrame(still_remaining), remaining_ledger

def detect_duplicate_ledger_credits(ledger: pd.DataFrame):
    """Flag ledger rows that look like duplicate postings of the same settlement."""
    dupes = ledger[ledger.duplicated(subset=["narration", "credit"], keep=False)]
    return dupes

def flag_duplicate_warnings(all_matches: list, ledger: pd.DataFrame):
    """
    A batch can be legitimately matched AND still deserve a human-review flag,
    if its matched ledger entry has an unused duplicate sibling (same narration
    + same credit amount). This doesn't unmatch the batch -- it adds a warning.
    """
    warnings = []
    dup_groups = ledger[ledger.duplicated(subset=["narration", "credit"], keep=False)]
    dup_pairs = dup_groups.groupby(["narration", "credit"])["entry_id"].apply(list)

    matched_entry_ids = {m["matched_entry_id"] for m in all_matches}
    for (narration, credit), entry_ids in dup_pairs.items():
        matched_ones = [e for e in entry_ids if e in matched_entry_ids]
        unused_ones = [e for e in entry_ids if e not in matched_entry_ids]
        if matched_ones and unused_ones:
            for m in all_matches:
                if m["matched_entry_id"] in matched_ones:
                    warnings.append({
                        "settlement_id": m["settlement_id"],
                        "matched_entry_id": m["matched_entry_id"],
                        "warning": f"Possible duplicate bank posting -- {unused_ones} has an identical "
                                   f"unused credit of {credit}p with the same narration. Recommend manual "
                                   f"verification that the bank did not credit this settlement twice.",
                    })
    return warnings

if __name__ == "__main__":
    settlement, ledger = load_data()
    batches = build_batches(settlement)
    print(f"Loaded {len(settlement)} payment rows -> {len(batches)} settlement batches")
    print(f"Loaded {len(ledger)} bank ledger rows\n")

    m1, remaining_batches, remaining_ledger = tier1_exact_match(batches, ledger)
    print(f"TIER 1 (exact): {len(m1)} / {len(batches)} batches matched")

    m2, remaining_batches2, remaining_ledger2 = tier2_fuzzy_match(remaining_batches, remaining_ledger)
    print(f"TIER 2 (fuzzy): {len(m2)} / {len(remaining_batches)} of the remainder matched")

    print(f"\nTIER 3 (LLM) candidates -- genuine leftovers: {len(remaining_batches2)} batches")
    if len(remaining_batches2) > 0:
        print(remaining_batches2[["settlement_id", "settlement_utr", "batch_total"]].to_string(index=False))

    print(f"\nLedger rows still unexplained after tiers 1+2: {len(remaining_ledger2)}")
    print(remaining_ledger2[["entry_id", "narration", "credit", "debit"]].to_string(index=False))

    all_matches = m1 + m2
    dup_warnings = flag_duplicate_warnings(all_matches, ledger)

    print(f"\n=== SUMMARY ===")
    print(f"Total batches: {len(batches)}")
    print(f"Matched (tier 1+2): {len(all_matches)}  ({len(all_matches)/len(batches)*100:.1f}%)")
    print(f"Sent to Tier 3 / exception: {len(remaining_batches2)}")
    print(f"Data-quality warnings on otherwise-matched batches: {len(dup_warnings)}")
    for w in dup_warnings:
        print(f"  -> {w['settlement_id']} (matched to {w['matched_entry_id']}): {w['warning']}")
